"""
Multi-Step Flow Workflow Creation with Hera SDK

This module provides workflow creation functionality for flows (DAGs) with multiple steps
using Hera SDK, extending the single-step workflow functionality.
"""

import os
import json
from typing import Optional, Dict, List, Set
from hera.workflows import Workflow, Script, Container, DAG, Task
from hera.workflows.models import VolumeMount, Volume, EnvVar, PersistentVolumeClaimVolumeSource
from kubernetes.client import CoreV1Api, CustomObjectsApi  # type: ignore
from fastapi import HTTPException


def build_step_script_source(
    step_id: str,
    python_code: str,
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None,
    flow_definition: Optional[Dict] = None
) -> str:
    """
    Build the bash script source for executing a step in a flow with helper functions
    for reading/writing step outputs via PV files.
    
    Args:
        step_id: Unique identifier for this step
        python_code: Python code to execute
        dependencies: Optional dependencies string
        requirements_file: Optional requirements file content
        flow_definition: Full flow definition for context (optional)
    """
    script_parts = [
        "set -e",
        "",
        "# Install uv if not present",
        "if ! command -v uv &> /dev/null; then",
        "  pip install --no-cache-dir uv",
        "fi",
        "",
        "# Create isolated virtual environment",
        f'VENV_DIR="/tmp/venv-{step_id}-{{{{workflow.name}}}}"',
        'uv venv "$VENV_DIR"',
        "",
        "# Activate virtual environment",
        'source "$VENV_DIR/bin/activate"',
    ]
    
    # Handle requirements file
    if requirements_file:
        script_parts.extend([
            "",
            "# Write requirements file",
            "cat > /tmp/requirements.txt << 'REQ_EOF'",
            requirements_file,
            "REQ_EOF",
            "",
            "# Install dependencies from requirements.txt",
            "echo 'Installing from requirements.txt...'",
            "uv pip install -r /tmp/requirements.txt",
            "echo 'Dependencies installed successfully'",
        ])
    elif dependencies:
        script_parts.extend([
            "",
            "# Install dependencies",
            "echo 'Installing packages: $DEPENDENCIES'",
            'echo "$DEPENDENCIES" | tr \',\' \' \' | xargs uv pip install',
            "echo 'Dependencies installed successfully'",
        ])
    
    # Add helper functions for step data exchange
    script_parts.extend([
        "",
        "# Helper functions for step data exchange",
        "cat > /tmp/step_helpers.py << 'HELPERS_EOF'",
        "import json",
        "import os",
        "from pathlib import Path",
        "",
        "def read_step_output(step_id: str, output_name: str = 'output'):",
        "    \"\"\"Read output from a previous step.\"\"\"",
        "    output_path = Path(f'/mnt/results/{step_id}/{output_name}.json')",
        "    if output_path.exists():",
        "        with open(output_path, 'r') as f:",
        "            return json.load(f)",
        "    return None",
        "",
        "def write_step_output(data: dict, output_name: str = 'output'):",
        "    \"\"\"Write output for this step.\"\"\"",
        "    step_id = os.getenv('STEP_ID', 'unknown')",
        "    output_dir = Path(f'/mnt/results/{step_id}')",
        "    output_dir.mkdir(parents=True, exist_ok=True)",
        "    output_path = output_dir / f'{output_name}.json'",
        "    with open(output_path, 'w') as f:",
        "        json.dump(data, f, indent=2)",
        "    return str(output_path)",
        "HELPERS_EOF",
        "",
        "# Execute Python code with helpers available",
        "export PYTHONPATH=/tmp:$PYTHONPATH",
        "",
        "# Create Python script with helpers and user code",
        "cat > /tmp/execute_step.py << 'CODE_EOF'",
        "import sys",
        "sys.path.insert(0, '/tmp')",
        "from step_helpers import read_step_output, write_step_output",
        "",
        "# User's Python code",
        python_code,
        "CODE_EOF",
        "",
        "# Execute the Python script",
        "python /tmp/execute_step.py",
    ])
    
    return "\n".join(script_parts)


def create_flow_workflow_with_hera(
    flow_definition: Dict,
    namespace: str = "argo"
) -> str:
    """
    Create an Argo Workflow from a flow definition (DAG) using Hera SDK.
    
    Args:
        flow_definition: Flow definition containing:
            - steps: List of step definitions with id, name, pythonCode, dependencies, etc.
            - edges: List of edge definitions with source, target (dependencies)
        namespace: Kubernetes namespace for the workflow
        
    Returns:
        workflow_id: The generated workflow name/ID
        
    Raises:
        HTTPException: If workflow creation fails
    """
    # Validate PVC exists
    core_api = CoreV1Api()
    try:
        pvc = core_api.read_namespaced_persistent_volume_claim(
            name="task-results-pvc",
            namespace=namespace
        )
        pvc_status = pvc.status.phase if pvc.status else "Unknown"
        if pvc_status != "Bound":
            raise HTTPException(
                status_code=400,
                detail=f"PVC 'task-results-pvc' is not bound. Current status: {pvc_status}."
            )
    except Exception as pvc_error:
        if "404" in str(pvc_error) or "Not Found" in str(pvc_error):
            raise HTTPException(
                status_code=400,
                detail="PVC 'task-results-pvc' not found. Please create it first."
            )
        if isinstance(pvc_error, HTTPException):
            raise pvc_error
        print(f"Warning: Could not verify PVC status: {pvc_error}")
    
    # Extract steps and edges from definition
    steps = flow_definition.get("steps", [])
    edges = flow_definition.get("edges", [])
    
    if not steps:
        raise HTTPException(
            status_code=400,
            detail="Flow definition must contain at least one step"
        )
    
    # Validate DAG structure (check for cycles)
    # Build dependency map
    step_ids = {step["id"] for step in steps}
    dependencies_map: Dict[str, List[str]] = {step_id: [] for step_id in step_ids}
    
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            if source not in step_ids or target not in step_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Edge references invalid step: source={source}, target={target}"
                )
            dependencies_map[target].append(source)
    
    # Simple cycle detection using DFS
    def has_cycle(step_id: str, visited: set[str], rec_stack: set[str]) -> bool:
        visited.add(step_id)
        rec_stack.add(step_id)
        
        for dep in dependencies_map.get(step_id, []):
            if dep not in visited:
                if has_cycle(dep, visited, rec_stack):
                    return True
            elif dep in rec_stack:
                return True
        
        rec_stack.remove(step_id)
        return False
    
    visited: Set[str] = set()
    for step_id in step_ids:
        if step_id not in visited:
            if has_cycle(step_id, visited, set()):
                raise HTTPException(
                    status_code=400,
                    detail="Flow contains cycles. DAG must be acyclic."
                )
    
    # Create workflow with Hera
    workflow = Workflow(
        generate_name="flow-",
        entrypoint="dag",
        namespace=namespace,
        volumes=[
            Volume(
                name="task-results",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="task-results-pvc")
            )
        ]
    )
    
    # Create task templates for each step
    step_templates = {}
    for step in steps:
        step_id = step["id"]
        step_name = step.get("name", step_id)
        python_code = step.get("pythonCode", "")
        dependencies = step.get("dependencies")
        requirements_file = step.get("requirementsFile")
        
        # Build environment variables
        env_vars = [
            EnvVar(name="ARGO_WORKFLOW_NAME", value="{{workflow.name}}"),
            EnvVar(name="STEP_ID", value=step_id),
            EnvVar(name="STEP_NAME", value=step_name),
        ]
        
        has_dependencies = bool(dependencies or requirements_file)
        
        if has_dependencies:
            dependencies_value = "requirements.txt" if requirements_file else (dependencies or "")
            env_vars.append(EnvVar(name="DEPENDENCIES", value=dependencies_value))
            
            script_source = build_step_script_source(
                step_id=step_id,
                python_code=python_code,
                dependencies=dependencies,
                requirements_file=requirements_file,
                flow_definition=flow_definition
            )
            
            script_template = Script(
                name=step_id,
                image="python:3.11-slim",
                command=["bash"],
                source=script_source,
                env=env_vars,
                volume_mounts=[
                    VolumeMount(name="task-results", mount_path="/mnt/results")
                ]
            )
            
            workflow.templates.append(script_template)
            step_templates[step_id] = script_template
        else:
            # For steps without dependencies, we still need to inject helper functions
            # So we use a script template even for simple cases
            script_source = build_step_script_source(
                step_id=step_id,
                python_code=python_code,
                dependencies=None,
                requirements_file=None,
                flow_definition=flow_definition
            )
            
            script_template = Script(
                name=step_id,
                image="python:3.11-slim",
                command=["bash"],
                source=script_source,
                env=env_vars,
                volume_mounts=[
                    VolumeMount(name="task-results", mount_path="/mnt/results")
                ]
            )
            
            workflow.templates.append(script_template)
            step_templates[step_id] = script_template
    
    # Create DAG template with tasks and dependencies
    dag_template = DAG(name="dag")
    
    for step in steps:
        step_id = step["id"]
        # Get dependencies for this step from edges
        step_dependencies = [
            edge["source"] for edge in edges 
            if edge.get("target") == step_id
        ]
        
        task = Task(
            name=step_id,
            template=step_id,
            dependencies=step_dependencies if step_dependencies else None
        )
        dag_template.tasks.append(task)
    
    workflow.templates.append(dag_template)
    
    # Create the workflow using Kubernetes API
    try:
        # Build workflow object using Hera SDK
        workflow_obj = workflow.build()
        
        # Convert Workflow object to dict for Kubernetes API
        if isinstance(workflow_obj, dict):
            workflow_dict = workflow_obj
        elif hasattr(workflow_obj, 'model_dump'):
            # Pydantic v2
            workflow_dict = workflow_obj.model_dump(exclude_none=True, by_alias=True, mode='json')
        elif hasattr(workflow_obj, 'model_dump_json'):
            # Pydantic v2 via JSON
            workflow_dict = json.loads(workflow_obj.model_dump_json(exclude_none=True, by_alias=True))
        elif hasattr(workflow_obj, 'dict'):
            # Pydantic v1
            workflow_dict = workflow_obj.dict(exclude_none=True, by_alias=True)
        else:
            # Fallback
            import json
            try:
                workflow_dict = json.loads(json.dumps(workflow_obj, default=str))
            except Exception:
                workflow_dict = dict(workflow_obj) if hasattr(workflow_obj, '__dict__') else {}
        
        # Submit workflow via Kubernetes CustomObjectsApi
        api_instance = CustomObjectsApi()
        result = api_instance.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            body=workflow_dict
        )
        
        # Extract workflow ID from result
        workflow_id = result.get("metadata", {}).get("name", "unknown")
        
        if not workflow_id or workflow_id == "unknown":
            raise HTTPException(
                status_code=500,
                detail="Failed to extract workflow ID from created workflow"
            )
        return str(workflow_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create flow workflow: {str(e)}"
        )

