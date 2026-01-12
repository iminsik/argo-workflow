"""
Workflow Creation with Hera SDK

This module provides workflow creation functionality using Hera SDK,
simplifying the process compared to YAML template manipulation.

Usage:
1. Install hera-workflows: pip install hera-workflows
2. Use create_workflow_with_hera() in your workflow creation logic
"""

import os
from typing import Optional
from hera.workflows import Workflow, Script, Container, Parameter
from hera.workflows.models import VolumeMount, Volume, EnvVar, PersistentVolumeClaimVolumeSource
from kubernetes.client import CoreV1Api, CustomObjectsApi  # type: ignore
from fastapi import HTTPException


def build_script_source(
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None,
    system_dependencies: Optional[str] = None,
    use_cache: bool = True
) -> str:
    """
    Build the bash script source for executing Python code with optional dependencies.
    
    This replaces the complex YAML template manipulation and requirements file injection.
    
    Args:
        dependencies: Python package names (space or comma-separated)
        requirements_file: requirements.txt content
        system_dependencies: Nix package names (space or comma-separated, e.g., "gcc make")
        use_cache: Whether to use UV and Nix caches (default: True)
    
    Note: The Python code is passed via the PYTHON_CODE environment variable,
    which is set separately when creating the workflow template.
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
            "echo 'Installing system dependencies: $SYSTEM_DEPS'",
            "# Convert comma-separated to space-separated",
            'SYSTEM_DEPS=$(echo "$SYSTEM_DEPS" | tr "," " ")',
            "",
            "# Install each system dependency",
            "for dep in $SYSTEM_DEPS; do",
            "  echo \"Installing system package: $dep\"",
            "  # Try nixpkgs attribute first, fallback to package name",
            "  if nix-portable nix-env -iA nixpkgs.$dep 2>&1; then",
            "    echo \"Successfully installed $dep via nixpkgs attribute\"",
            "  elif nix-portable nix-env -i $dep 2>&1; then",
            "    echo \"Successfully installed $dep via package name\"",
            "  else",
            "    echo \"Warning: Failed to install $dep, continuing...\"",
            "  fi",
            "  # Verify installation by checking if command exists",
            "  if command -v $dep &> /dev/null; then",
            "    echo \"Verifying $dep installation:\"",
            "    $dep --version 2>&1 || echo \"$dep is installed but --version failed\"",
            "  fi",
            "done",
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
            "",
        ])
    
    # Create isolated virtual environment
    script_parts.extend([
        "# Create isolated virtual environment",
        'VENV_DIR="/tmp/venv-{{workflow.name}}"',
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
            "# Install dependencies from requirements.txt",
            "echo 'Installing from requirements.txt...'",
            "uv pip install -r /tmp/requirements.txt",
            "echo 'Dependencies installed successfully'",
        ])
    elif dependencies:
        script_parts.extend([
            "",
            "# Install Python dependencies",
            "echo 'Installing Python packages: $PYTHON_DEPS'",
            'echo "$PYTHON_DEPS" | tr \',\' \' \' | xargs uv pip install',
            "echo 'Python dependencies installed successfully'",
        ])
    
    # Execute Python code
    # Note: $PYTHON_CODE is set as an environment variable in create_workflow_with_hera()
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
    system_dependencies: Optional[str] = None,
    use_cache: bool = True,
    namespace: str = "argo"
) -> str:
    """
    Create an Argo Workflow using Hera SDK with hybrid UV/Nix support.
    
    This replaces ~270 lines of complex YAML template manipulation with clean,
    type-safe Python code.
    
    Args:
        python_code: Python code to execute
        dependencies: Space or comma-separated Python package names (optional)
        requirements_file: requirements.txt content (optional)
        system_dependencies: Space or comma-separated Nix package names (optional, e.g., "gcc make")
        use_cache: Whether to mount cache volumes (default: True)
        namespace: Kubernetes namespace for the workflow
        
    Returns:
        workflow_id: The generated workflow name/ID
        
    Raises:
        HTTPException: If workflow creation fails
    """
    # Validate PVCs exist
    core_api = CoreV1Api()
    required_pvcs = ["task-results-pvc"]
    if use_cache:
        required_pvcs.extend(["uv-cache-pvc", "nix-store-pvc"])
    
    for pvc_name in required_pvcs:
        try:
            pvc = core_api.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace
            )
            pvc_status = pvc.status.phase if pvc.status else "Unknown"
            if pvc_status != "Bound":
                raise HTTPException(
                    status_code=400,
                    detail=f"PVC '{pvc_name}' is not bound. Current status: {pvc_status}."
                )
        except Exception as pvc_error:
            if "404" in str(pvc_error) or "Not Found" in str(pvc_error):
                raise HTTPException(
                    status_code=400,
                    detail=f"PVC '{pvc_name}' not found. Please create it first using: kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml"
                )
            if isinstance(pvc_error, HTTPException):
                raise pvc_error
            print(f"Warning: Could not verify PVC '{pvc_name}' status: {pvc_error}")
    
    # Determine if we need dependencies handling
    has_dependencies = bool(dependencies or requirements_file or system_dependencies)
    
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
    
    # Create workflow with Hera
    workflow = Workflow(
        generate_name="python-job-",
        entrypoint="main",
        namespace=namespace,
        volumes=volumes
    )
    
    # Build environment variables
    env_vars = [
        EnvVar(name="ARGO_WORKFLOW_NAME", value="{{workflow.name}}"),
        EnvVar(name="PYTHON_CODE", value=python_code),
    ]
    
    # Determine base image
    # Use nix-portable base if system dependencies are needed, otherwise use standard Python image
    if system_dependencies:
        base_image = os.getenv("NIX_PORTABLE_BASE_IMAGE", "python:3.11-slim")
        # Note: In production, use your built image: "your-registry/nix-portable-base:latest"
        env_vars.append(EnvVar(name="SYSTEM_DEPS", value=system_dependencies))
    else:
        base_image = "python:3.11-slim"
    
    if has_dependencies:
        # Use script template for dependency management
        if dependencies:
            env_vars.append(EnvVar(name="PYTHON_DEPS", value=dependencies))
        elif requirements_file:
            env_vars.append(EnvVar(name="DEPENDENCIES", value="requirements.txt"))
        
        script_source = build_script_source(
            dependencies=dependencies,
            requirements_file=requirements_file,
            system_dependencies=system_dependencies,
            use_cache=use_cache
        )
        
        script_template = Script(
            name="main",
            image=base_image,
            command=["bash"],
            source=script_source,
            env=env_vars,
            volume_mounts=volume_mounts
        )
        
        workflow.templates.append(script_template)
    else:
        # Use container template for simple execution (no dependencies)
        container_template = Container(
            name="main",
            image=base_image,
            command=["python", "-c"],
            args=[python_code],
            env=env_vars,
            volume_mounts=volume_mounts
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
