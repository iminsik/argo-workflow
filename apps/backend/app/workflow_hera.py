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
                "  # Note: --link-dest requires absolute path",
                "  rsync -a --link-dest=\"$NP_STORE\" --ignore-existing \"$NP_STORE/\" ~/.nix-portable/nix/store/ 2>/dev/null || {",
                "    # Fallback: copy with preserve attributes (including timestamps, permissions, etc.)",
                "    rsync -a --ignore-existing \"$NP_STORE/\" ~/.nix-portable/nix/store/ 2>/dev/null || {",
                "      find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d -exec cp -a {} ~/.nix-portable/nix/store/ \\; 2>/dev/null || true",
                "    }",
                "  }",
                "  SYNCED_COUNT=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Synced $SYNCED_COUNT packages to nix-portable location\"",
                "  # Verify some packages are actually there and have content",
                "  if [ $SYNCED_COUNT -gt 0 ]; then",
                "    SAMPLE_PKG=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d | head -1)",
                "    if [ -n \"$SAMPLE_PKG\" ] && [ -d \"$SAMPLE_PKG\" ]; then",
                "      PKG_FILES=$(find \"$SAMPLE_PKG\" -type f 2>/dev/null | wc -l)",
                "      echo \"Sample package verified: $(basename $SAMPLE_PKG) ($PKG_FILES files)\"",
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
            'echo "Using UV cache at: $UV_CACHE_DIR"',
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
            "# Install Python dependencies with cache logging",
            "echo 'Installing Python packages: $PYTHON_DEPS'",
            "# Check which packages are already cached",
            "for pkg in $(echo \"$PYTHON_DEPS\" | tr ',' ' '); do",
            "  PKG_NAME=$(echo \"$pkg\" | cut -d'=' -f1 | cut -d'[' -f1)",
            "  if [ -n \"$UV_CACHE_DIR\" ] && find \"$UV_CACHE_DIR\" -name \"*${PKG_NAME}*\" -type f 2>/dev/null | grep -q .; then",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m $PKG_NAME found in \\033[1;32mLOCAL CACHE\\033[0m\"",
            "  else",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m $PKG_NAME will be downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI)\"",
            "  fi",
            "done",
            "# Install packages and capture output to detect cache usage",
            'INSTALL_OUTPUT=$(echo "$PYTHON_DEPS" | tr \',\' \' \' | xargs uv pip install 2>&1)',
            'INSTALL_STATUS=$?',
            '# Check if packages were downloaded or from cache',
            'if echo "$INSTALL_OUTPUT" | grep -q "Downloading"; then',
            '  DOWNLOADED_PKGS=$(echo "$INSTALL_OUTPUT" | grep "Downloading" | sed "s/.*Downloading \\([^ ]*\\).*/\\1/" | tr "\\n" " ")',
            '  echo -e "\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m Downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI): $DOWNLOADED_PKGS"',
            'fi',
            'if echo "$INSTALL_OUTPUT" | grep -q "Resolved.*in.*ms"; then',
            '  RESOLVE_TIME=$(echo "$INSTALL_OUTPUT" | grep -oP "Resolved.*in \\K[0-9]+ms" | head -1)',
            '  if [ -z "$DOWNLOADED_PKGS" ]; then',
            '    echo -e "\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m All packages from \\033[1;32mLOCAL CACHE\\033[0m (resolved in $RESOLVE_TIME)"',
            '  fi',
            'fi',
            'if [ $INSTALL_STATUS -eq 0 ]; then',
            '  echo "Python dependencies installed successfully"',
            'else',
            '  echo "Error installing dependencies"',
            '  echo "$INSTALL_OUTPUT"',
            '  exit 1',
            'fi',
        ])
    
    # Execute Python code
    # Note: $PYTHON_CODE is set as an environment variable in create_workflow_with_hera()
    script_parts.extend([
        "",
        "# Execute Python code",
        "# If system dependencies are needed, wrap execution in nix-shell",
        "if [ -n \"$SYSTEM_DEPS\" ] && [ -n \"$NIX_SHELL_PACKAGES\" ]; then",
        "  echo \"Executing Python code with system dependencies available via nix-shell...\"",
        "  # Check if packages exist in nix-portable store before running",
        "  if [ -d ~/.nix-portable/nix/store ]; then",
        "    STORE_PACKAGES=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
        "    echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Packages in nix-portable store before execution: $STORE_PACKAGES\"",
        "  fi",
        "  # Run nix-shell - it will use cached packages if they exist",
        "  nix-portable nix-shell $NIX_SHELL_PACKAGES --run 'python -c \"$PYTHON_CODE\"'",
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
        "  python -c \"$PYTHON_CODE\"",
        "fi",
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
        base_image = os.getenv("NIX_PORTABLE_BASE_IMAGE", "nix-portable-base:latest")
        # Note: For kind clusters, use "nix-portable-base:latest" (loaded via kind load docker-image)
        # For production, use your registry: "your-registry/nix-portable-base:latest"
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
            image_pull_policy="IfNotPresent",  # Use local image in kind clusters
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
            image_pull_policy="IfNotPresent",  # Use local image in kind clusters
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
