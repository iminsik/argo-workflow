# Upgrade Machine 1 to Match Machine 2

## Problem
Machine 1 has older versions that prevent nix-portable from working:
- containerd: 1.7.18 (too old)
- Docker: 27.3.1 (older)
- Kubernetes: v1.31.0 (older)
- kind: v0.24.0 (older)

Machine 2 works because it has:
- containerd: 2.2.0 ✅
- Docker: 27.5.1 ✅
- Kubernetes: v1.35.0 ✅
- kind: v0.31.0 ✅

## Solution: Upgrade Steps

### 1. Upgrade Docker Desktop
```bash
# Check current version
docker --version

# Update Docker Desktop to latest version (27.5.1 or newer)
# This will automatically update containerd to 2.x
```

### 2. Upgrade kind
```bash
# Remove old kind
brew uninstall kind

# Install latest kind
brew install kind

# Verify version (should be v0.31.0 or newer)
kind version
```

### 3. Upgrade kubectl
```bash
# Install latest kubectl
brew install kubectl

# Or upgrade if already installed
brew upgrade kubectl

# Verify version (should be v1.35.0 or newer)
kubectl version --client
```

### 4. Recreate Kind Cluster
After upgrading, you'll need to recreate your kind cluster to get the new containerd version:

```bash
# Delete old cluster
kind delete cluster --name argo-dev

# Recreate cluster (will use new containerd version)
kind create cluster --name argo-dev --config infrastructure/k8s/kind-config.yaml

# Verify containerd version
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
# Should show: containerd://2.2.0 or newer
```

### 5. Rebuild and Load Images
```bash
# Rebuild nix-portable base image
make build-nix-image

# Load into kind cluster
kind load docker-image nix-portable-base:latest --name argo-dev
```

## Why This Matters

**containerd 2.x** has significant improvements:
- Better security context handling
- Improved capabilities support
- Better compatibility with tools like nix-portable that use bubblewrap/proot
- More permissive default settings for container operations

The older containerd 1.7.18 on Machine 1 is likely too restrictive for nix-portable to initialize properly, even with proot.

## Verification

After upgrading, verify the versions match Machine 2:
```bash
docker --version          # Should be 27.5.1+
kubectl version --client  # Should be v1.35.0+
kind version              # Should be v0.31.0+
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
# Should show: containerd://2.2.0+
```

Then test nix-portable again - it should work like on Machine 2.
