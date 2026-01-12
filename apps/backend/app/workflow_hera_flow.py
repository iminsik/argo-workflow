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
    system_dependencies: Optional[str] = None,
    use_cache: bool = True,
    flow_definition: Optional[Dict] = None
) -> str:
    """
    Build the bash script source for executing a step in a flow with helper functions
    for reading/writing step outputs via PV files.
    
    Args:
        step_id: Unique identifier for this step
        python_code: Python code to execute
        dependencies: Optional Python dependencies string
        requirements_file: Optional requirements file content
        system_dependencies: Optional system dependencies (Nix packages)
        use_cache: Whether to use cache volumes
        flow_definition: Full flow definition for context (optional)
    """
    script_parts = [
        "set -e",
        "",
    ]
    
    # Install system dependencies using nix-portable (if provided)
    if system_dependencies:
        script_parts.extend([
            "# Install system dependencies using nix-portable",
            "if ! command -v nix-portable &> /dev/null; then",
            "  echo 'Error: nix-portable not found in image. Using nix-portable base image required.'",
            "  exit 1",
            "fi",
            "",
        ])
        
        # Configure nix-portable to use shared PVC store if cache is enabled
        if use_cache:
            script_parts.extend([
                "# Configure nix-portable to use shared PVC store",
                "# NP_STORE tells nix-portable where to store packages",
                "export NP_STORE=/nix/store",
                "mkdir -p /nix/store",
                "# Ensure store has proper permissions",
                "chmod 755 /nix/store 2>/dev/null || true",
                'echo "Using Nix store cache at: $NP_STORE"',
                "# Verify store is accessible",
                "if [ -w \"$NP_STORE\" ]; then",
                "  echo \"Nix store is writable\"",
                "else",
                "  echo \"Warning: Nix store may not be writable\"",
                "fi",
                "# Copy packages from shared store to nix-portable's location BEFORE nix-shell runs",
                "# This ensures nix-portable can use cached packages",
                "# Create nix-portable directory structure if it doesn't exist",
                "mkdir -p ~/.nix-portable/nix/store",
                "if [ -d \"$NP_STORE\" ] && [ \"$(ls -A $NP_STORE 2>/dev/null)\" ]; then",
                "  echo \"Syncing packages from shared store to nix-portable location...\"",
                "  # Use rsync with --link-dest to create hardlinks when possible (faster and saves space)",
                "  # This preserves all file attributes and ensures packages are recognized by nix-portable",
                "  rsync -a --link-dest=\"$NP_STORE\" --ignore-existing \"$NP_STORE/\" ~/.nix-portable/nix/store/ 2>/dev/null || {",
                "    # Fallback: copy with preserve attributes",
                "    rsync -a --ignore-existing \"$NP_STORE/\" ~/.nix-portable/nix/store/ 2>/dev/null || {",
                "      find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d -exec cp -a {} ~/.nix-portable/nix/store/ \\; 2>/dev/null || true",
                "    }",
                "  }",
                "  SYNCED_COUNT=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Synced $SYNCED_COUNT packages to nix-portable location\"",
                "  # Verify some packages are actually there",
                "  if [ $SYNCED_COUNT -gt 0 ]; then",
                "    SAMPLE_PKG=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d | head -1)",
                "    if [ -n \"$SAMPLE_PKG\" ] && [ -d \"$SAMPLE_PKG\" ]; then",
                "      echo \"Sample package verified: $(basename $SAMPLE_PKG)\"",
                "    fi",
                "  fi",
                "else",
                "  echo \"No packages found in shared store to sync\"",
                "fi",
                "",
            ])
        
        script_parts.extend([
            'echo "Installing system dependencies: $SYSTEM_DEPS"',
            "# Convert comma-separated to space-separated",
            'SYSTEM_DEPS=$(echo "$SYSTEM_DEPS" | tr "," " ")',
            "",
            "# Check Nix store cache status",
            "if [ -n \"$NP_STORE\" ] && [ -d \"$NP_STORE\" ]; then",
            "  STORE_COUNT=$(find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
            "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Store contains $STORE_COUNT packages\"",
            "else",
            "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m No shared store configured, using local cache\"",
            "fi",
            "",
            "# Build nix-shell command with all system dependencies",
            "# We'll use nix-shell directly when executing Python code - no separate preparation needed",
            "# nix-shell will handle downloading packages if needed (fast if cached)",
            "NIX_PACKAGES=\"\"",
            "for dep in $SYSTEM_DEPS; do",
            "  NIX_PACKAGES=\"$NIX_PACKAGES -p $dep\"",
            "  echo \"System dependency: $dep (will be available via nix-shell)\"",
            "done",
            "export NIX_SHELL_PACKAGES=\"$NIX_PACKAGES\"",
            "echo \"System dependencies configured. Packages will be available when executing Python code.\"",
            "",
            "# Final cache status",
            "if [ -n \"$NP_STORE\" ] && [ -d \"$NP_STORE\" ]; then",
            "  FINAL_COUNT=$(find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
            "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Final store count: $FINAL_COUNT packages\"",
            "fi",
            "",
            "echo 'System dependencies installed successfully'",
            "",
        ])
    
    # Install uv if not present
    script_parts.extend([
        "# Install uv if not present",
        "if ! command -v uv &> /dev/null; then",
        "  pip install --no-cache-dir uv",
        "fi",
        "",
    ])
    
    # Set UV cache directory if cache is enabled
    if use_cache:
        script_parts.extend([
            "# Use shared UV cache",
            "export UV_CACHE_DIR=/root/.cache/uv",
            "mkdir -p $UV_CACHE_DIR",
            "echo 'Using UV cache at: $UV_CACHE_DIR'",
            "# Check cache status",
            "if [ -d \"$UV_CACHE_DIR\" ]; then",
            "  CACHE_SIZE=$(du -sh \"$UV_CACHE_DIR\" 2>/dev/null | cut -f1)",
            "  CACHE_FILES=$(find \"$UV_CACHE_DIR\" -type f 2>/dev/null | wc -l)",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m Cache directory size: $CACHE_SIZE ($CACHE_FILES files)\"",
            "else",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m Cache directory does not exist, will be created\"",
            "fi",
            "",
        ])
    
    # Create isolated virtual environment
    script_parts.extend([
        "# Create isolated virtual environment",
        f'VENV_DIR="/tmp/venv-{step_id}-{{{{workflow.name}}}}"',
        'uv venv "$VENV_DIR"',
        "",
        "# Activate virtual environment",
        'source "$VENV_DIR/bin/activate"',
    ])
    
    # Handle requirements file
    if requirements_file:
        script_parts.extend([
            "",
            "# Write requirements file",
            "cat > /tmp/requirements.txt << 'REQ_EOF'",
            requirements_file,
            "REQ_EOF",
            "",
            "# Install dependencies from requirements.txt with cache logging",
            "echo 'Installing from requirements.txt...'",
            "# Check cache status before installation",
            "if [ -n \"$UV_CACHE_DIR\" ] && [ -d \"$UV_CACHE_DIR\" ]; then",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m Checking cache for packages in requirements.txt...\"",
            "  while IFS= read -r line || [ -n \"$line\" ]; do",
            "    # Skip comments and empty lines",
            "    [ -z \"$line\" ] || [ \"${line#\"#\"}\" != \"$line\" ] && continue",
            "    PKG_NAME=$(echo \"$line\" | cut -d'=' -f1 | cut -d'[' -f1 | xargs)",
            "    if [ -n \"$PKG_NAME\" ] && find \"$UV_CACHE_DIR\" -name \"*${PKG_NAME}*\" -type f 2>/dev/null | grep -q .; then",
            "      echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m $PKG_NAME found in \\033[1;32mLOCAL CACHE\\033[0m\"",
            "    elif [ -n \"$PKG_NAME\" ]; then",
            "      echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m $PKG_NAME will be downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI)\"",
            "    fi",
            "  done < /tmp/requirements.txt",
            "fi",
            "# Install packages and capture output to detect cache usage",
            "INSTALL_OUTPUT=$(uv pip install -r /tmp/requirements.txt 2>&1)",
            "INSTALL_STATUS=$?",
            "# Check if packages were downloaded or from cache",
            "if echo \"$INSTALL_OUTPUT\" | grep -q \"Downloading\"; then",
            "  DOWNLOADED_PKGS=$(echo \"$INSTALL_OUTPUT\" | grep \"Downloading\" | sed \"s/.*Downloading \\([^ ]*\\).*/\\1/\" | tr \"\\n\" \" \")",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m Downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI): $DOWNLOADED_PKGS\"",
            "fi",
            "if echo \"$INSTALL_OUTPUT\" | grep -q \"Resolved.*in.*ms\"; then",
            "  RESOLVE_TIME=$(echo \"$INSTALL_OUTPUT\" | grep -oP 'Resolved.*in \\K[0-9]+ms' | head -1)",
            "  if [ -z \"$DOWNLOADED_PKGS\" ]; then",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m All packages from \\033[1;32mLOCAL CACHE\\033[0m (resolved in $RESOLVE_TIME)\"",
            "  fi",
            "fi",
            "if [ $INSTALL_STATUS -eq 0 ]; then",
            "  echo 'Dependencies installed successfully'",
            "else",
            "  echo 'Error installing dependencies'",
            "  echo \"$INSTALL_OUTPUT\"",
            "  exit 1",
            "fi",
        ])
    elif dependencies:
        script_parts.extend([
            "",
            "# Install dependencies with cache logging",
            "echo 'Installing packages: $DEPENDENCIES'",
            "# Check which packages are already cached",
            "for pkg in $(echo \"$DEPENDENCIES\" | tr ',' ' '); do",
            "  PKG_NAME=$(echo \"$pkg\" | cut -d'=' -f1 | cut -d'[' -f1)",
            "  if [ -n \"$UV_CACHE_DIR\" ] && find \"$UV_CACHE_DIR\" -name \"*${PKG_NAME}*\" -type f 2>/dev/null | grep -q .; then",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m $PKG_NAME found in \\033[1;32mLOCAL CACHE\\033[0m\"",
            "  else",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m $PKG_NAME will be downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI)\"",
            "  fi",
            "done",
            "# Install packages and capture output to detect cache usage",
            "INSTALL_OUTPUT=$(echo \"$DEPENDENCIES\" | tr ',' ' ' | xargs uv pip install 2>&1)",
            "INSTALL_STATUS=$?",
            "# Check if packages were downloaded or from cache",
            "if echo \"$INSTALL_OUTPUT\" | grep -q \"Downloading\"; then",
            "  DOWNLOADED_PKGS=$(echo \"$INSTALL_OUTPUT\" | grep \"Downloading\" | sed \"s/.*Downloading \\([^ ]*\\).*/\\1/\" | tr \"\\n\" \" \")",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m Downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI): $DOWNLOADED_PKGS\"",
            "fi",
            "if echo \"$INSTALL_OUTPUT\" | grep -q \"Resolved.*in.*ms\"; then",
            "  RESOLVE_TIME=$(echo \"$INSTALL_OUTPUT\" | grep -oP 'Resolved.*in \\K[0-9]+ms' | head -1)",
            "  if [ -z \"$DOWNLOADED_PKGS\" ]; then",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m All packages from \\033[1;32mLOCAL CACHE\\033[0m (resolved in $RESOLVE_TIME)\"",
            "  fi",
            "fi",
            "if [ $INSTALL_STATUS -eq 0 ]; then",
            "  echo 'Dependencies installed successfully'",
            "else",
            "  echo 'Error installing dependencies'",
            "  echo \"$INSTALL_OUTPUT\"",
            "  exit 1",
            "fi",
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
        "# If system dependencies are needed, wrap execution in nix-shell",
        "if [ -n \"$SYSTEM_DEPS\" ] && [ -n \"$NIX_SHELL_PACKAGES\" ]; then",
        "  echo \"Executing Python code with system dependencies available via nix-shell...\"",
        "  nix-portable nix-shell $NIX_SHELL_PACKAGES --run 'python /tmp/execute_step.py'",
        "  # After execution, copy any new packages to shared store",
        "  if [ -n \"$NP_STORE\" ] && [ -d \"$NP_STORE\" ] && [ -d ~/.nix-portable/nix/store ]; then",
        "    echo \"Syncing packages to shared store...\"",
        "    rsync -a --ignore-existing ~/.nix-portable/nix/store/ \"$NP_STORE/\" 2>/dev/null || {",
        "      find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d -exec cp -r {} \"$NP_STORE/\" \\; 2>/dev/null || true",
        "    }",
        "    SYNCED_COUNT=$(find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
        "    echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Synced packages to shared store. Total: $SYNCED_COUNT packages\"",
        "  fi",
        "else",
        "  python /tmp/execute_step.py",
        "fi",
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
    
    # Create workflow with Hera (volumes will be set later)
    workflow = Workflow(
        generate_name="flow-",
        entrypoint="dag",
        namespace=namespace,
        volumes=[]  # Will be set below
    )
    
    # Check if cache volumes should be used (default: True)
    use_cache = True  # Can be made configurable later
    
    # Build volumes list
    volumes = [
        Volume(
            name="task-results",
            persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="task-results-pvc")
        )
    ]
    
    # Add cache volumes if enabled
    if use_cache:
        volumes.extend([
            Volume(
                name="uv-cache",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="uv-cache-pvc")
            ),
            Volume(
                name="nix-store",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="nix-store-pvc")
            )
        ])
    
    # Build volume mounts
    volume_mounts = [
        VolumeMount(name="task-results", mount_path="/mnt/results")
    ]
    
    if use_cache:
        volume_mounts.extend([
            VolumeMount(name="uv-cache", mount_path="/root/.cache/uv"),
            VolumeMount(name="nix-store", mount_path="/nix/store")
        ])
    
    # Update workflow volumes
    workflow.volumes = volumes
    
    # Create task templates for each step
    step_templates = {}
    for step in steps:
        step_id = step["id"]
        step_name = step.get("name", step_id)
        python_code = step.get("pythonCode", "")
        dependencies = step.get("dependencies")
        requirements_file = step.get("requirementsFile")
        system_dependencies = step.get("systemDependencies")
        
        # Determine base image
        base_image = "python:3.11-slim"
        if system_dependencies:
            base_image = os.getenv("NIX_PORTABLE_BASE_IMAGE", "nix-portable-base:latest")
        
        # Build environment variables
        env_vars = [
            EnvVar(name="ARGO_WORKFLOW_NAME", value="{{workflow.name}}"),
            EnvVar(name="STEP_ID", value=step_id),
            EnvVar(name="STEP_NAME", value=step_name),
        ]
        
        if system_dependencies:
            env_vars.append(EnvVar(name="SYSTEM_DEPS", value=system_dependencies))
        
        has_dependencies = bool(dependencies or requirements_file or system_dependencies)
        
        if has_dependencies:
            dependencies_value = "requirements.txt" if requirements_file else (dependencies or "")
            env_vars.append(EnvVar(name="DEPENDENCIES", value=dependencies_value))
            
            script_source = build_step_script_source(
                step_id=step_id,
                python_code=python_code,
                dependencies=dependencies,
                requirements_file=requirements_file,
                system_dependencies=system_dependencies,
                use_cache=use_cache,
                flow_definition=flow_definition
            )
            
            script_template = Script(
                name=step_id,
                image=base_image,
                image_pull_policy="IfNotPresent",  # Use local image in kind clusters
                command=["bash"],
                source=script_source,
                env=env_vars,
                volume_mounts=volume_mounts
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
                system_dependencies=system_dependencies,
                use_cache=use_cache,
                flow_definition=flow_definition
            )
            
            script_template = Script(
                name=step_id,
                image=base_image,
                image_pull_policy="IfNotPresent",  # Use local image in kind clusters
                command=["bash"],
                source=script_source,
                env=env_vars,
                volume_mounts=volume_mounts
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


def generate_flow_workflow_template(
    flow_definition: Dict,
    namespace: str = "argo"
) -> Dict:
    """
    Generate an Argo Workflow template from a flow definition without submitting it.
    This uses the exact same logic as create_flow_workflow_with_hera but doesn't submit to Kubernetes.
    
    Args:
        flow_definition: Flow definition containing:
            - steps: List of step definitions with id, name, pythonCode, dependencies, etc.
            - edges: List of edge definitions with source, target (dependencies)
        namespace: Kubernetes namespace for the workflow
        
    Returns:
        workflow_dict: The workflow dictionary (ready to be converted to YAML)
        
    Raises:
        HTTPException: If workflow generation fails
    """
    # Extract steps and edges from definition
    steps = flow_definition.get("steps", [])
    edges = flow_definition.get("edges", [])
    
    if not steps:
        raise HTTPException(
            status_code=400,
            detail="Flow definition must contain at least one step"
        )
    
    # Validate DAG structure (check for cycles) - same as create_flow_workflow_with_hera
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
    
    # Create workflow with Hera - same as create_flow_workflow_with_hera
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
    
    # Create task templates for each step - same logic as create_flow_workflow_with_hera
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
                image_pull_policy="IfNotPresent",  # Use local image in kind clusters
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
                image_pull_policy="IfNotPresent",  # Use local image in kind clusters
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
    
    # Build workflow object using Hera SDK - same as create_flow_workflow_with_hera
    workflow_obj = workflow.build()
    
    # Convert Workflow object to dict
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
    
    # Debug: Verify templates are included
    # Templates should be in spec.templates for Argo Workflows
    if 'spec' in workflow_dict and 'templates' in workflow_dict['spec']:
        template_count = len(workflow_dict['spec']['templates'])
        print(f"Generated workflow has {template_count} templates (expected {len(steps) + 1} = {len(steps)} steps + 1 DAG)")
    else:
        print(f"Warning: Templates not found in expected location. Workflow dict keys: {workflow_dict.keys()}")
        if 'spec' in workflow_dict:
            print(f"Spec keys: {workflow_dict['spec'].keys()}")
    
    return workflow_dict

