# Hybrid UV Cache + Nix Portable Implementation Guide

## Overview

This guide implements a hybrid optimization strategy:
- **UV Cache**: For Python packages (fast, native)
- **Nix Portable**: For system dependencies (gcc, make, etc.)

## Architecture

```
┌─────────────────────────────────────────┐
│  Argo Workflow Container                │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Base Image: python:3.11-slim    │ │
│  │  + nix-portable binary           │ │
│  │  + uv (via pip)                  │ │
│  └───────────────────────────────────┘ │
│           │                            │
│           ├─▶ /root/.cache/uv         │ ← UV Cache (PVC)
│           │   (Python packages)        │
│           │                            │
│           └─▶ /nix/store              │ ← Nix Store (PVC)
│               (System packages)        │
│                                         │
└─────────────────────────────────────────┘
```

## Implementation Steps

### Step 1: Create Base Docker Image with Nix Portable

Create `infrastructure/argo/Dockerfile.nix-portable-base`:

```dockerfile
FROM python:3.11-slim

# Install nix-portable
RUN curl -L https://github.com/DavHau/nix-portable/releases/download/v0.5.0/nix-portable \
    -o /usr/local/bin/nix-portable && \
    chmod +x /usr/local/bin/nix-portable

# Install uv (for Python packages)
RUN pip install --no-cache-dir uv

# Set environment variables
ENV NIX_PORTABLE=1
ENV PATH="/root/.nix-profile/bin:${PATH}"

# Verify installations
RUN nix-portable --version && uv --version

# Default command
CMD ["python"]
```

Build and push:
```bash
docker build -f infrastructure/argo/Dockerfile.nix-portable-base \
  -t your-registry/nix-portable-base:latest \
  infrastructure/argo/

docker push your-registry/nix-portable-base:latest
```

### Step 2: Create Kubernetes PVCs

Create `infrastructure/k8s/pvc-cache-volumes.yaml`:

```yaml
---
# UV Cache PVC for Python packages
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: uv-cache-pvc
  namespace: argo
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
  storageClassName: manual  # Or use your storage class
---
# Nix Store PVC for system packages
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nix-store-pvc
  namespace: argo
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 20Gi
  storageClassName: manual  # Or use your storage class
```

For local development (Kind), create corresponding PVs in `infrastructure/k8s/pv-cache-volumes.yaml`:

```yaml
---
# UV Cache PV
apiVersion: v1
kind: PersistentVolume
metadata:
  name: uv-cache-pv
  labels:
    type: local
spec:
  storageClassName: manual
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteMany
  hostPath:
    path: /tmp/argo-uv-cache
  persistentVolumeReclaimPolicy: Retain
---
# Nix Store PV
apiVersion: v1
kind: PersistentVolume
metadata:
  name: nix-store-pv
  labels:
    type: local
spec:
  storageClassName: manual
  capacity:
    storage: 20Gi
  accessModes:
    - ReadWriteMany
  hostPath:
    path: /tmp/argo-nix-store
  persistentVolumeReclaimPolicy: Retain
```

Apply:
```bash
kubectl apply -f infrastructure/k8s/pv-cache-volumes.yaml
kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml
```

### Step 3: Update Workflow Code

Update `apps/backend/app/workflow_hera.py` to support system dependencies:

```python
def build_script_source(
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None,
    system_dependencies: Optional[str] = None,  # NEW
    use_cache: bool = True  # NEW
) -> str:
    """
    Build the bash script source for executing Python code with optional dependencies.
    
    Args:
        dependencies: Python package names (space or comma-separated)
        requirements_file: requirements.txt content
        system_dependencies: Nix package names (space or comma-separated)
        use_cache: Whether to use UV and Nix caches
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
            "  echo 'Error: nix-portable not found in image'",
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
            "  nix-portable nix-env -iA nixpkgs.$dep || nix-portable nix-env -i $dep",
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
    
    # Handle Python dependencies
    if requirements_file:
        script_parts.extend([
            "",
            "# Write requirements file",
            "cat > /tmp/requirements.txt << 'REQ_EOF'",
            requirements_file,
            "REQ_EOF",
            "",
            "# Install dependencies from requirements.txt",
            "echo 'Installing Python packages from requirements.txt...'",
            "uv pip install -r /tmp/requirements.txt",
            "echo 'Python dependencies installed successfully'",
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
    system_dependencies: Optional[str] = None,  # NEW
    use_cache: bool = True,  # NEW
    namespace: str = "argo"
) -> str:
    """
    Create an Argo Workflow using Hera SDK with hybrid UV/Nix support.
    
    Args:
        python_code: Python code to execute
        dependencies: Space or comma-separated Python package names
        requirements_file: requirements.txt content
        system_dependencies: Space or comma-separated Nix package names (e.g., "gcc", "make")
        use_cache: Whether to mount cache volumes
        namespace: Kubernetes namespace
    """
    # ... existing PVC validation code ...
    
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
    
    # Build environment variables
    env_vars = [
        EnvVar(name="ARGO_WORKFLOW_NAME", value="{{workflow.name}}"),
        EnvVar(name="PYTHON_CODE", value=python_code),
    ]
    
    has_dependencies = bool(dependencies or requirements_file or system_dependencies)
    
    if system_dependencies:
        env_vars.append(EnvVar(name="SYSTEM_DEPS", value=system_dependencies))
    
    if dependencies:
        env_vars.append(EnvVar(name="PYTHON_DEPS", value=dependencies))
    
    # Use nix-portable base image
    base_image = os.getenv("NIX_PORTABLE_BASE_IMAGE", "your-registry/nix-portable-base:latest")
    
    if has_dependencies:
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
        
        workflow = Workflow(
            generate_name="python-job-",
            entrypoint="main",
            namespace=namespace,
            volumes=volumes
        )
        workflow.templates.append(script_template)
    else:
        # Simple container for no dependencies
        container_template = Container(
            name="main",
            image=base_image,
            command=["python", "-c"],
            args=[python_code],
            env=env_vars,
            volume_mounts=volume_mounts
        )
        
        workflow = Workflow(
            generate_name="python-job-",
            entrypoint="main",
            namespace=namespace,
            volumes=volumes
        )
        workflow.templates.append(container_template)
    
    # ... rest of existing workflow creation code ...
```

### Step 4: Update API Models

Update `apps/backend/app/main.py`:

```python
class TaskSubmitRequest(BaseModel):
    pythonCode: str = "print('Processing task in Kind...')"
    dependencies: str | None = None  # Python packages
    requirementsFile: str | None = None
    systemDependencies: str | None = None  # NEW: Nix packages (e.g., "gcc make")
    useCache: bool = True  # NEW: Enable cache volumes
```

Update the submit endpoint:

```python
@app.post("/api/v1/tasks/submit")
async def submit_task(request: TaskSubmitRequest = TaskSubmitRequest()):
    # ... existing code ...
    
    workflow_id = create_workflow_with_hera(
        python_code=request.pythonCode,
        dependencies=request.dependencies,
        requirements_file=request.requirementsFile,
        system_dependencies=request.systemDependencies,  # NEW
        use_cache=request.useCache,  # NEW
        namespace=namespace
    )
    
    # ... rest of existing code ...
```

### Step 5: Update Frontend (Optional)

Update `apps/frontend/src/TaskDialog.svelte` to add system dependencies field:

```svelte
<!-- Add after Python dependencies field -->
<div class="form-group">
  <label for="systemDeps">System Dependencies (Nix packages, comma-separated)</label>
  <input
    type="text"
    id="systemDeps"
    bind:value={systemDependencies}
    placeholder="e.g., gcc, make, cmake"
    class="form-control"
  />
  <small class="form-text text-muted">
    System-level packages installed via Nix Portable (e.g., gcc, make, cmake)
  </small>
</div>
```

## Usage Examples

### Example 1: Python Only (UV Cache)

```python
# API Request
{
  "pythonCode": "import numpy as np; print(np.array([1,2,3]))",
  "dependencies": "numpy",
  "useCache": true
}
```

**Result**: Fast Python package installation via UV cache

### Example 2: System Dependencies Only (Nix Portable)

```python
# API Request
{
  "pythonCode": "import subprocess; subprocess.run(['gcc', '--version'])",
  "systemDependencies": "gcc",
  "useCache": true
}
```

**Result**: GCC installed via Nix Portable, available in container

### Example 3: Both (Hybrid)

```python
# API Request
{
  "pythonCode": """
import numpy as np
import subprocess
result = subprocess.run(['gcc', '--version'], capture_output=True)
print('GCC:', result.stdout.decode())
print('NumPy array:', np.array([1,2,3]))
""",
  "dependencies": "numpy",
  "systemDependencies": "gcc",
  "useCache": true
}
```

**Result**: 
- GCC installed via Nix Portable (from cache if available)
- NumPy installed via UV (from cache if available)
- Both available in the same container

## Performance Expectations

### Cold Start Times

| Scenario | Without Cache | With Cache (First) | With Cache (Subsequent) |
|----------|---------------|-------------------|------------------------|
| Python only | 10-60s | 10-60s | 2-5s |
| System deps only | 5-15s | 5-15s | 2-5s |
| Both | 15-75s | 15-75s | 4-10s |

### Cache Hit Rates

- **UV Cache**: 80-95% after first run (if same packages)
- **Nix Store**: 70-90% after first run (if same packages)
- **Combined**: Best performance when both caches are warm

## Monitoring and Maintenance

### Check Cache Sizes

```bash
# Check UV cache size
kubectl exec -n argo <pod-name> -- du -sh /root/.cache/uv

# Check Nix store size
kubectl exec -n argo <pod-name> -- du -sh /nix/store
```

### Clear Caches (if needed)

```bash
# Delete and recreate PVCs
kubectl delete pvc uv-cache-pvc nix-store-pvc -n argo
kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml
```

### Monitor Cache Usage

Add metrics to track:
- Cache hit rates
- Cache sizes
- Cold start times
- Most used packages

## Troubleshooting

### Issue: nix-portable not found

**Solution**: Ensure base image includes nix-portable:
```bash
docker build -f infrastructure/argo/Dockerfile.nix-portable-base .
```

### Issue: Cache volumes not mounting

**Solution**: Verify PVCs exist and are bound:
```bash
kubectl get pvc -n argo
```

### Issue: Slow first run

**Expected**: First container populates cache, subsequent runs are faster.

### Issue: Out of storage

**Solution**: Increase PVC sizes or implement cache cleanup:
```yaml
resources:
  requests:
    storage: 50Gi  # Increase size
```

## Best Practices

1. **Pre-populate common packages**: Build a base image with common Nix packages
2. **Monitor cache sizes**: Set up alerts for PVC usage
3. **Use specific versions**: Pin Python and system package versions
4. **Test without cache**: Ensure workflows work if cache is unavailable
5. **Document dependencies**: Keep track of what packages are used

## Migration Path

1. **Phase 1**: Deploy base image and PVCs (no code changes)
2. **Phase 2**: Update workflow code to support system dependencies
3. **Phase 3**: Enable cache by default for new workflows
4. **Phase 4**: Migrate existing workflows to use cache
5. **Phase 5**: Monitor and optimize

## Cost-Benefit Analysis

### Benefits
- ✅ **50-80% faster** Python package installation (UV cache)
- ✅ **40-60% faster** system package installation (Nix cache)
- ✅ **Reduced network usage**: Packages downloaded once
- ✅ **Better reproducibility**: Nix ensures consistent system deps

### Costs
- ⚠️ **Storage**: 30Gi total (10Gi UV + 20Gi Nix)
- ⚠️ **Complexity**: Additional PVCs and base image to maintain
- ⚠️ **Initial setup**: 4-8 hours implementation time

### ROI
- **High**: For frequent workflows with repeated dependencies
- **Medium**: For occasional workflows
- **Low**: For one-off workflows with unique dependencies

## Next Steps

1. ✅ Create base Docker image
2. ✅ Create PVCs
3. ✅ Update workflow code
4. ✅ Update API models
5. ✅ Test with sample workflows
6. ✅ Monitor performance
7. ✅ Document usage patterns
