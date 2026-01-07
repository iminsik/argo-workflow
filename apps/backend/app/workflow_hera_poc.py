"""
Proof of Concept: Workflow Creation with Hera SDK

This module demonstrates how workflow creation can be simplified using Hera SDK
compared to the current YAML template manipulation approach.

To use this POC:
1. Install hera-workflows: pip install hera-workflows
2. Replace the workflow creation logic in start_task() with create_workflow_with_hera()
"""

import os
from typing import Optional
from hera.workflows import Workflow, Script, Container, Parameter
from hera.workflows.models import VolumeMount, Volume, EnvVar, PersistentVolumeClaimVolumeSource
from kubernetes.client import CoreV1Api, CustomObjectsApi  # type: ignore
from fastapi import HTTPException


def build_script_source(
    python_code: str,
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None
) -> str:
    """
    Build the bash script source for executing Python code with optional dependencies.
    
    This replaces the complex YAML template manipulation and requirements file injection.
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
        'VENV_DIR="/tmp/venv-{{workflow.name}}"',
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
    
    # Execute Python code
    script_parts.extend([
        "",
        "# Execute Python code",
        'python -c "$PYTHON_CODE"',
    ])
    
    return "\n".join(script_parts)


def create_workflow_with_hera(
    python_code: str,
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None,
    namespace: str = "argo"
) -> str:
    """
    Create an Argo Workflow using Hera SDK.
    
    This replaces ~270 lines of complex YAML template manipulation with clean,
    type-safe Python code.
    
    Args:
        python_code: Python code to execute
        dependencies: Space or comma-separated package names (optional)
        requirements_file: requirements.txt content (optional)
        namespace: Kubernetes namespace for the workflow
        
    Returns:
        workflow_id: The generated workflow name/ID
        
    Raises:
        HTTPException: If workflow creation fails
    """
    # Validate PVC exists (same validation as current code)
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
    
    # Determine if we need dependencies handling
    has_dependencies = bool(dependencies or requirements_file)
    
    # Create workflow with Hera
    workflow = Workflow(
        generate_name="python-job-",
        entrypoint="main",
        namespace=namespace,
        volumes=[
            Volume(
                name="task-results",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="task-results-pvc")
            )
        ]
    )
    
    # Build environment variables
    env_vars = [
        EnvVar(name="ARGO_WORKFLOW_NAME", value="{{workflow.name}}"),
        EnvVar(name="PYTHON_CODE", value=python_code),
    ]
    
    if has_dependencies:
        # Use script template for dependency management
        dependencies_value = "requirements.txt" if requirements_file else (dependencies or "")
        env_vars.append(EnvVar(name="DEPENDENCIES", value=dependencies_value))
        
        script_source = build_script_source(
            python_code=python_code,
            dependencies=dependencies,
            requirements_file=requirements_file
        )
        
        script_template = Script(
            name="main",
            image="python:3.11-slim",
            command=["bash"],
            source=script_source,
            env=env_vars,
            volume_mounts=[
                VolumeMount(name="task-results", mount_path="/mnt/results")
            ]
        )
        
        workflow.templates.append(script_template)
    else:
        # Use container template for simple execution (no dependencies)
        container_template = Container(
            name="main",
            image="python:3.11-slim",
            command=["python", "-c"],
            args=[python_code],
            env=env_vars,
            volume_mounts=[
                VolumeMount(name="task-results", mount_path="/mnt/results")
            ]
        )
        
        workflow.templates.append(container_template)
    
    # Create the workflow using Kubernetes API directly
    # Hera SDK's create() requires Argo server host, so we build the workflow dict
    # and submit it via Kubernetes API (same as current implementation)
    try:
        # Build workflow object using Hera SDK (handles all serialization)
        workflow_obj = workflow.build()
        
        # Convert Workflow object to dict for Kubernetes API
        # Hera SDK 5.26+ uses Pydantic v2, so we use model_dump()
        if isinstance(workflow_obj, dict):
            # Already a dict
            workflow_dict = workflow_obj
        elif hasattr(workflow_obj, 'model_dump'):
            # Pydantic v2 - convert to dict with proper serialization
            workflow_dict = workflow_obj.model_dump(exclude_none=True, by_alias=True, mode='json')
        elif hasattr(workflow_obj, 'model_dump_json'):
            # Pydantic v2 - convert via JSON string
            import json
            workflow_dict = json.loads(workflow_obj.model_dump_json(exclude_none=True, by_alias=True))
        elif hasattr(workflow_obj, 'dict'):
            # Pydantic v1 - convert to dict
            workflow_dict = workflow_obj.dict(exclude_none=True, by_alias=True)
        else:
            # Fallback: try to convert using json
            import json
            try:
                workflow_dict = json.loads(json.dumps(workflow_obj, default=str))
            except Exception:
                # Last resort: convert to dict manually
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
            detail=f"Failed to create workflow: {str(e)}"
        )


# Example usage in FastAPI endpoint:
"""
@app.post("/api/v1/tasks/submit")
async def start_task(request: TaskSubmitRequest = TaskSubmitRequest()):
    try:
        # Validation (same as current code)
        if request.dependencies:
            if len(request.dependencies) > 10000:
                raise HTTPException(status_code=400, detail="Dependencies too long")
            dangerous_patterns = [';', '&&', '||', '`', '$(']
            for pattern in dangerous_patterns:
                if pattern in request.dependencies:
                    raise HTTPException(status_code=400, detail=f"Invalid character: {pattern}")
        
        if request.requirementsFile:
            if len(request.requirementsFile) > 50000:
                raise HTTPException(status_code=400, detail="Requirements file too long")
        
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # Create workflow with Hera - THIS REPLACES ~270 LINES OF CODE!
        workflow_id = create_workflow_with_hera(
            python_code=request.pythonCode,
            dependencies=request.dependencies,
            requirements_file=request.requirementsFile,
            namespace=namespace
        )
        
        # Database operations (same as current code)
        db = next(get_db())
        try:
            # ... existing database logic ...
            return {
                "id": task_id,
                "workflowId": workflow_id,
                "runNumber": next_run_number
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
"""

