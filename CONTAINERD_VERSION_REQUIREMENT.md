# Containerd Version Requirement

## Overview

This project requires **containerd version >= 2.0.0** for proper nix-portable functionality. Older versions (like 1.7.18) may cause nix-portable to fail due to stricter security context enforcement.

## Why This Matters

- **containerd 2.x** has better security context handling and is more permissive for certain operations
- **nix-portable** requires certain capabilities that containerd 2.x handles more gracefully
- **containerd 1.7.18** (and older) may block nix-portable operations even with proot

## Checking Your Version

### Quick Check
```bash
# Check containerd version in your kind cluster
make check-containerd
```

Or manually:
```bash
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
# Should show: containerd://2.2.0 or newer
```

### Pre-flight Checks
Before creating a cluster, run pre-flight checks:
```bash
make preflight
```

This will verify:
- Docker is installed and running
- kind is installed (v0.31.0+ recommended)
- kubectl is installed
- Existing cluster has correct containerd version (if applicable)

## Ensuring Correct Version

### For New Clusters

1. **Upgrade kind** (if needed):
   ```bash
   brew upgrade kind
   # Verify: kind version (should be v0.31.0+)
   ```

2. **Create cluster** (will use containerd 2.x from kind node image):
   ```bash
   make cluster-up
   ```

3. **Verify version**:
   ```bash
   make check-containerd
   ```

### For Existing Clusters

If your cluster has containerd < 2.0.0:

1. **Delete old cluster**:
   ```bash
   kind delete cluster --name argo-dev
   ```

2. **Upgrade kind** (if needed):
   ```bash
   brew upgrade kind
   ```

3. **Recreate cluster**:
   ```bash
   make cluster-up
   ```

4. **Verify version**:
   ```bash
   make check-containerd
   ```

## Version Requirements

| Component | Minimum Version | Recommended Version |
|-----------|----------------|---------------------|
| containerd | 2.0.0 | 2.2.0+ |
| kind | 0.31.0 | 0.31.0+ |
| kubectl | 1.35.0 | 1.35.0+ |
| Docker Desktop | 27.5.0 | Latest |

## Troubleshooting

### "Containerd version does not meet requirement"

**Solution**: Upgrade kind and recreate the cluster:
```bash
brew upgrade kind
kind delete cluster --name argo-dev
make cluster-up
make check-containerd
```

### "Could not retrieve containerd version"

**Possible causes**:
- Cluster is not running
- kubectl is not configured correctly
- Network issues

**Solution**:
```bash
# Check cluster status
kind get clusters
kubectl get nodes

# If cluster is not running, create it
make cluster-up
```

## Integration

The version check is automatically run:
- After `make cluster-up` (with warning if check fails)
- Via `make check-containerd` (standalone check)
- Via `make preflight` (before cluster creation)
- Via `./diagnose-nix-portable.sh` (in diagnostics)

## Scripts

- **`scripts/check-containerd-version.sh`**: Standalone version check
- **`scripts/preflight-checks.sh`**: Comprehensive pre-flight checks
- **`diagnose-nix-portable.sh`**: Includes containerd version in diagnostics
