# Who Uses containerd?

## Quick Answer

**containerd** is the **container runtime** used by:
1. **Kubernetes** (via CRI - Container Runtime Interface)
2. **kind** (Kubernetes in Docker) - runs containers in cluster nodes
3. **Docker Desktop** (can use containerd as backend)
4. **Your Argo Workflow pods** - all containers run via containerd

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  Your Mac (Host)                                 │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │  Docker Desktop                           │  │
│  │  - Uses containerd as container runtime  │  │
│  └──────────────────────────────────────────┘  │
│           │                                       │
│           ▼                                       │
│  ┌──────────────────────────────────────────┐  │
│  │  kind Cluster (argo-dev)                 │  │
│  │  - Runs as Docker container              │  │
│  │  - Contains Kubernetes node             │  │
│  └──────────────────────────────────────────┘  │
│           │                                       │
│           ▼                                       │
│  ┌──────────────────────────────────────────┐  │
│  │  Kubernetes (inside kind node)          │  │
│  │  - Uses containerd via CRI              │  │
│  │  - Manages pods and containers          │  │
│  └──────────────────────────────────────────┘  │
│           │                                       │
│           ▼                                       │
│  ┌──────────────────────────────────────────┐  │
│  │  containerd (inside kind node)          │  │
│  │  - Actually runs the containers         │  │
│  │  - Manages container lifecycle          │  │
│  │  - Handles security contexts            │  │
│  └──────────────────────────────────────────┘  │
│           │                                       │
│           ▼                                       │
│  ┌──────────────────────────────────────────┐  │
│  │  Your Argo Workflow Pods                │  │
│  │  - python-job-xxx pods                  │  │
│  │  - nix-portable-base containers          │  │
│  │  - All run via containerd                │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Detailed Explanation

### 1. **Kubernetes Uses containerd**

Kubernetes doesn't run containers directly. Instead, it uses the **Container Runtime Interface (CRI)** to communicate with a container runtime like containerd.

```
Kubernetes API Server
    ↓
kubelet (node agent)
    ↓
CRI (Container Runtime Interface)
    ↓
containerd
    ↓
Your containers (pods)
```

### 2. **kind Uses containerd**

When you create a kind cluster:
- kind creates a Docker container that runs a Kubernetes node
- Inside that container, Kubernetes uses containerd to run pods
- The containerd version comes from the **kind node image** (e.g., `kindest/node:v1.35.0`)

### 3. **Your Workflow Pods Use containerd**

When Argo Workflows creates a pod:
1. Argo Workflows controller submits a Pod spec to Kubernetes
2. Kubernetes scheduler assigns it to a node
3. kubelet on that node receives the Pod spec
4. kubelet calls containerd (via CRI) to create the container
5. containerd actually runs your `nix-portable-base` container

### 4. **Why containerd Version Matters**

containerd 2.2.0 vs 1.7.18 differences:

**containerd 1.7.18 (old):**
- Stricter security context enforcement
- More restrictive capabilities handling
- May block operations that nix-portable needs (even with proot)

**containerd 2.2.0 (new):**
- Better security context handling
- More permissive for certain operations
- Better compatibility with tools like nix-portable

## How to Check What's Using containerd

### Check containerd version in kind cluster:
```bash
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
# Output: containerd://2.2.0
```

### Check what containers are running via containerd:
```bash
# Inside the kind node
docker exec argo-dev-control-plane crictl ps
```

### Check containerd directly (if accessible):
```bash
# Inside the kind node
docker exec argo-dev-control-plane ctr version
```

## Summary

- **containerd** is the low-level container runtime
- **Kubernetes** uses it via CRI to run all pods
- **Your Argo Workflow pods** are all running via containerd
- **nix-portable** runs inside containers that are managed by containerd
- The **containerd version** determines what security contexts and capabilities are allowed
- **containerd 2.2.0** is more permissive than 1.7.18, which is why nix-portable works on Machine 2

## Why This Matters for nix-portable

nix-portable needs to:
- Create namespaces (via bubblewrap/proot)
- Mount filesystems
- Set up sandboxed environments

These operations require certain capabilities and permissions that containerd controls. The newer containerd 2.2.0 handles these more gracefully than the older 1.7.18 version.
