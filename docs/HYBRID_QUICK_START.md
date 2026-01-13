# Hybrid UV Cache + Nix Portable - Quick Start

## Overview

This implementation provides:
- **UV Cache**: Fast Python package installation (50-80% faster)
- **Nix Portable**: System dependency management (gcc, make, etc.)
- **Hybrid approach**: Best of both worlds

## Quick Setup (5 Steps)

### 1. Build Base Image

```bash
cd infrastructure/argo
docker build -f Dockerfile.nix-portable-base -t nix-portable-base:latest .
# Or push to your registry:
# docker tag nix-portable-base:latest your-registry/nix-portable-base:latest
# docker push your-registry/nix-portable-base:latest
```

### 2. Create PVCs

```bash
# For local development (Kind)
kubectl apply -f ../k8s/pv-cache-volumes.yaml
kubectl apply -f ../k8s/pvc-cache-volumes.yaml

# Verify PVCs are bound
kubectl get pvc -n argo
```

### 3. Update Environment Variable (Optional)

If using a custom registry for the base image:

```bash
export NIX_PORTABLE_BASE_IMAGE="your-registry/nix-portable-base:latest"
```

### 4. Restart Backend

```bash
# Restart backend to pick up code changes
docker-compose restart backend
# Or rebuild:
docker-compose up -d --build backend
```

### 5. Test It!

#### Test 1: Python Only (UV Cache)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "pythonCode": "import numpy as np; print(np.array([1,2,3]))",
    "dependencies": "numpy",
    "useCache": true
  }'
```

#### Test 2: System Dependencies (Nix Portable)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "pythonCode": "import subprocess; print(subprocess.run([\"gcc\", \"--version\"], capture_output=True).stdout.decode())",
    "systemDependencies": "gcc",
    "useCache": true
  }'
```

#### Test 3: Both (Hybrid)

```bash
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "pythonCode": "import numpy as np; import subprocess; print(\"GCC:\", subprocess.run([\"gcc\", \"--version\"], capture_output=True).stdout.decode()[:50]); print(\"NumPy:\", np.array([1,2,3]))",
    "dependencies": "numpy",
    "systemDependencies": "gcc",
    "useCache": true
  }'
```

## API Usage

### Request Format

```json
{
  "pythonCode": "print('Hello')",
  "dependencies": "numpy,pandas",           // Optional: Python packages
  "requirementsFile": "numpy>=1.0.0\n...",  // Optional: requirements.txt content
  "systemDependencies": "gcc,make",          // Optional: Nix packages
  "useCache": true                           // Optional: Enable cache (default: true)
}
```

### Response

```json
{
  "id": "task-abc123",
  "message": "Task saved successfully. Use /api/v1/tasks/{task_id}/run to execute it."
}
```

## Performance Expectations

| Scenario | First Run | Subsequent Runs |
|----------|-----------|-----------------|
| Python only | 10-60s | 2-5s (cache hit) |
| System deps only | 5-15s | 2-5s (cache hit) |
| Both | 15-75s | 4-10s (cache hit) |

## Common Nix Packages

- `gcc` - C compiler
- `make` - Build tool
- `cmake` - CMake build system
- `pkg-config` - Package configuration
- `git` - Version control
- `curl` - HTTP client
- `wget` - File downloader
- `python3` - Python (if needed separately)

## Troubleshooting

### Issue: nix-portable not found

**Solution**: Ensure you're using the nix-portable base image:
- Check `NIX_PORTABLE_BASE_IMAGE` environment variable
- Or update workflow code to use your image

### Issue: PVC not found

**Solution**: Create PVCs:
```bash
kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml
```

### Issue: Cache not working

**Solution**: 
1. Verify PVCs are bound: `kubectl get pvc -n argo`
2. Check volume mounts in workflow logs
3. Ensure `useCache: true` in request

### Issue: System dependency not found

**Solution**: 
- Check Nix package name (use `nix search nixpkgs <name>`)
- Some packages need full path: `nixpkgs.gcc` instead of `gcc`

## Next Steps

1. ✅ Test with your workflows
2. ✅ Monitor cache hit rates
3. ✅ Adjust PVC sizes if needed
4. ✅ Add more common packages to base image (optional)

## Files Created

- `infrastructure/argo/Dockerfile.nix-portable-base` - Base image
- `infrastructure/k8s/pv-cache-volumes.yaml` - PersistentVolumes (local)
- `infrastructure/k8s/pvc-cache-volumes.yaml` - PersistentVolumeClaims
- `apps/backend/app/workflow_hera.py` - Updated workflow code
- `apps/backend/app/main.py` - Updated API models

## Documentation

- Full implementation guide: `docs/HYBRID_UV_NIX_IMPLEMENTATION.md`
- Optimization strategies: `docs/DEPENDENCY_OPTIMIZATION_STRATEGIES.md`
- Nix Portable analysis: `docs/NIX_PORTABLE_ANALYSIS.md`
