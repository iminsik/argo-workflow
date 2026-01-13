# What is kubelet?

## Quick Answer

**kubelet** is the **node agent** that runs on every Kubernetes node. It's responsible for:
- Receiving Pod specifications from the Kubernetes API server
- Actually running containers on that node
- Reporting pod status back to the API server
- Managing container lifecycle (start, stop, restart)

Think of it as the "worker" that does the actual work on each node.

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  Kubernetes Control Plane                       │
│  - API Server                                   │
│  - Scheduler                                    │
│  - Controller Manager                           │
└──────────────────────┬──────────────────────────┘
                       │
                       │ Sends Pod specs
                       ▼
┌─────────────────────────────────────────────────┐
│  Kubernetes Node (kind node)                    │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │  kubelet (Node Agent)                    │  │
│  │  - Receives Pod specs                    │  │
│  │  - Manages container lifecycle           │  │
│  │  - Reports status                        │  │
│  └──────────────────────────────────────────┘  │
│           │                                       │
│           │ Calls via CRI                        │
│           ▼                                       │
│  ┌──────────────────────────────────────────┐  │
│  │  containerd (Container Runtime)          │  │
│  │  - Actually runs containers               │  │
│  └──────────────────────────────────────────┘  │
│           │                                       │
│           ▼                                       │
│  ┌──────────────────────────────────────────┐  │
│  │  Your Pods (containers)                   │  │
│  │  - python-job-xxx                         │  │
│  │  - nix-portable-base containers           │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Detailed Explanation

### What kubelet Does

1. **Receives Pod Specs**
   - Kubernetes API server sends Pod specifications to kubelet
   - kubelet receives instructions like: "Run this container with these settings"

2. **Manages Container Lifecycle**
   - Creates containers when Pods are scheduled
   - Starts containers
   - Monitors container health
   - Restarts containers if they crash
   - Stops containers when Pods are deleted

3. **Reports Status**
   - Tells API server: "Pod is running", "Pod failed", etc.
   - Provides resource usage (CPU, memory)
   - Reports container events

4. **Handles Volume Mounts**
   - Mounts PersistentVolumes
   - Sets up volume mounts for containers

5. **Manages Container Images**
   - Pulls container images if needed
   - Caches images locally

### The Flow: From Workflow to Container

```
1. You submit workflow via API
   ↓
2. Argo Workflows Controller creates Workflow resource
   ↓
3. Argo Controller creates Pod resource
   ↓
4. Kubernetes Scheduler assigns Pod to a node
   ↓
5. kubelet (on that node) receives Pod spec
   ↓
6. kubelet calls containerd (via CRI)
   ↓
7. containerd creates and runs the container
   ↓
8. Your nix-portable-base container starts
   ↓
9. kubelet monitors the container
   ↓
10. kubelet reports status back to API server
```

## kubelet vs containerd

### kubelet (Orchestration Layer)
- **High-level**: Manages Pod lifecycle
- **Responsibilities**: Scheduling, health checks, status reporting
- **Interface**: Uses CRI (Container Runtime Interface) to talk to container runtimes
- **Location**: Runs on every Kubernetes node

### containerd (Runtime Layer)
- **Low-level**: Actually runs containers
- **Responsibilities**: Container creation, execution, isolation
- **Interface**: Implements CRI
- **Location**: Runs on every Kubernetes node (used by kubelet)

**Analogy:**
- **kubelet** = Manager (tells what to do)
- **containerd** = Worker (does the actual work)

## How to See kubelet in Action

### Check kubelet on kind node:
```bash
# kubelet runs inside the kind node container
docker exec argo-dev-control-plane ps aux | grep kubelet
```

### Check kubelet logs:
```bash
# kubelet logs are in the kind node
docker exec argo-dev-control-plane journalctl -u kubelet | tail -20
```

### See what kubelet is managing:
```bash
# List pods that kubelet is managing
kubectl get pods -A

# Describe a pod to see kubelet's view
kubectl describe pod <pod-name>
```

## Why This Matters for Your Workflows

When you submit a workflow:

1. **Argo Controller** creates Pod resources
2. **Kubernetes Scheduler** assigns Pods to nodes
3. **kubelet** receives the Pod spec
4. **kubelet** calls **containerd** to run your container
5. **containerd** creates the container with the security context
6. **Your container** runs (with nix-portable inside)

If containerd is too restrictive (like 1.7.18), it will block nix-portable's operations even though kubelet is trying to run it.

## Summary

- **kubelet** = Node agent that manages Pods on each Kubernetes node
- **containerd** = Container runtime that actually runs containers
- **kubelet** uses **containerd** via CRI to run containers
- **Your workflows** → Argo → Kubernetes → **kubelet** → **containerd** → containers

kubelet is the "middle manager" between Kubernetes and the actual container runtime.
