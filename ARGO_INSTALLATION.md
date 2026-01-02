# Argo Workflows Installation Guide

Quick reference for installing Argo Workflows in a Kubernetes cluster (local or external).

## Quick Install (Automated)

```bash
# Point kubectl to your cluster
kubectl config use-context <your-cluster-context>

# Run automated setup
make argo-setup-external
# or
./scripts/setup-k8s-resources.sh
```

## Manual Installation

### 1. Create Namespace
```bash
kubectl create namespace argo
```

### 2. Install Argo Workflows

**Minimal (recommended):**
```bash
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
```

**Full (with UI):**
```bash
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/install.yaml
```

### 3. Wait for Ready
```bash
kubectl wait --for=condition=ready pod -l app=workflow-controller -n argo --timeout=300s
```

### 4. Create Storage

**Local/Kind clusters:**
```bash
kubectl apply -f infrastructure/k8s/pv.yaml
```

**Cloud clusters (GKE/EKS/AKS):**
```bash
kubectl apply -f infrastructure/k8s/pv-cloud.yaml
```

### 5. Create RBAC
```bash
kubectl apply -f infrastructure/k8s/rbac.yaml
```

### 6. Verify
```bash
kubectl get pods -n argo
kubectl get pvc -n argo
kubectl get serviceaccount -n argo backend-sa
```

## Storage Options

### For Local/Kind Clusters
- Use `infrastructure/k8s/pv.yaml` (hostPath-based)

### For Cloud Clusters
- Use `infrastructure/k8s/pv-cloud.yaml` (dynamic provisioning)
- May need to configure StorageClass for ReadWriteMany support
- Consider managed NFS solutions (EFS, Azure Files, Filestore)

## Troubleshooting

**Pods not starting:**
```bash
kubectl describe pod <pod-name> -n argo
kubectl logs <pod-name> -n argo
```

**PVC stuck in Pending:**
```bash
kubectl describe pvc task-results-pvc -n argo
kubectl get storageclass
```

**CRDs missing:**
```bash
kubectl get crd | grep argo
# If missing, re-run install.yaml
```

## What Gets Installed

- **Namespace**: `argo`
- **CRDs**: `workflows.argoproj.io`, `workflowtemplates.argoproj.io`
- **Deployments**: `workflow-controller` (and `argo-server` if full install)
- **Storage**: `task-results-pv` (PV) and `task-results-pvc` (PVC)
- **RBAC**: `backend-sa` (ServiceAccount), `argo-manager` (Role), `backend-sa-binding` (RoleBinding)

## Requirements

- Kubernetes 1.24+
- Cluster admin permissions (or equivalent)
- ~1 CPU core and 1GB memory available
- Network access to download images from container registries

