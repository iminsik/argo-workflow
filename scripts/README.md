# Deployment Helper Scripts

This directory contains helper scripts to automate common deployment tasks for the Argo Workflow Manager on Bunnyshell.

## Scripts

### `setup-k8s-resources.sh`

Sets up all required Kubernetes resources before deploying via Bunnyshell.

**What it does:**
- Creates `argo` namespace
- Installs Argo Workflows (v3.5.0 minimal installation)
- Creates PersistentVolume and PersistentVolumeClaim
- Configures RBAC (ServiceAccount, Role, RoleBinding)

**Usage:**
```bash
./scripts/setup-k8s-resources.sh
```

**Prerequisites:**
- `kubectl` configured and connected to your cluster
- Cluster admin permissions
- Internet access (to download Argo Workflows manifests)

**When to run:**
- Before deploying via Bunnyshell (Phase 2-3 in DEPLOYMENT_STRATEGY.md)
- Can be run multiple times safely (idempotent)

---

### `configure-serviceaccount.sh`

Configures the ServiceAccount for the backend component after Bunnyshell deployment.

**What it does:**
- Finds or accepts the Bunnyshell namespace
- Creates ServiceAccount `backend-sa` in Bunnyshell namespace
- Updates RoleBinding to reference ServiceAccount in Bunnyshell namespace
- Updates backend deployment to use the ServiceAccount
- Restarts backend pod
- Verifies configuration

**Usage:**
```bash
# Auto-detect namespace
./scripts/configure-serviceaccount.sh

# Or specify namespace explicitly
./scripts/configure-serviceaccount.sh <namespace>
```

**Prerequisites:**
- Bunnyshell deployment completed
- RBAC resources already created (run `setup-k8s-resources.sh` first)
- `kubectl` configured and connected to your cluster

**When to run:**
- After deploying via Bunnyshell (Phase 5 in DEPLOYMENT_STRATEGY.md)
- Required for backend to access Argo Workflows

---

## Quick Start

### Complete Setup (First Time)

```bash
# 1. Set up Kubernetes resources
./scripts/setup-k8s-resources.sh

# 2. Deploy via Bunnyshell UI
# - Connect cluster and repository
# - Create environment from bunnyshell.yaml
# - Deploy

# 3. Configure ServiceAccount
./scripts/configure-serviceaccount.sh
```

### Verification

After running the scripts, verify everything is working:

```bash
# Check Argo Workflows
kubectl get pods -n argo

# Check PVC
kubectl get pvc -n argo task-results-pvc

# Check RBAC
kubectl get serviceaccount -n argo backend-sa
kubectl get rolebinding -n argo backend-sa-binding

# Find Bunnyshell namespace
kubectl get namespaces | grep argo-workflow-manager

# Check backend deployment (replace NS with your namespace)
kubectl get deployment backend -n <namespace>
kubectl get deployment backend -n <namespace> -o jsonpath='{.spec.template.spec.serviceAccountName}'
```

---

## Troubleshooting

### Script fails with "kubectl not found"

Install kubectl or ensure it's in your PATH:
- macOS: `brew install kubectl`
- Linux: See [kubectl installation guide](https://kubernetes.io/docs/tasks/tools/)

### Script fails with "Cannot connect to cluster"

Configure kubectl:
```bash
# For GKE
gcloud container clusters get-credentials <cluster-name> --zone <zone>

# For EKS
aws eks update-kubeconfig --name <cluster-name>

# For AKS
az aks get-credentials --resource-group <resource-group> --name <cluster-name>
```

### ServiceAccount script can't find namespace

List all namespaces to find the correct one:
```bash
kubectl get namespaces
```

Then run with explicit namespace:
```bash
./scripts/configure-serviceaccount.sh <namespace>
```

### Argo Workflows installation takes too long

The script waits up to 5 minutes. If it times out, check manually:
```bash
kubectl get pods -n argo
kubectl describe pod -n argo <pod-name>
```

### PVC not binding

For cloud providers, you may need to use a StorageClass instead of manual PV. Check:
```bash
kubectl get pv task-results-pv
kubectl get pvc -n argo task-results-pvc
kubectl describe pvc -n argo task-results-pvc
```

---

## Manual Steps (Alternative)

If you prefer to run commands manually, see:
- `DEPLOYMENT_STRATEGY.md` for detailed step-by-step instructions
- `DEPLOYMENT_CHECKLIST.md` for a checklist of all steps

---

## Script Details

### Error Handling

Both scripts use `set -e` to exit on any error. They also include:
- Color-coded output for better readability
- Verification steps before proceeding
- Idempotent operations (safe to run multiple times)
- Clear error messages with suggested fixes

### Dependencies

- `bash` (version 4.0+)
- `kubectl` (configured and connected)
- Internet access (for Argo Workflows installation)

### Permissions

The scripts require:
- Cluster admin permissions (for creating namespaces, RBAC, etc.)
- Ability to create resources in `argo` namespace
- Ability to patch deployments in Bunnyshell namespace

---

## Contributing

If you improve these scripts, please:
1. Test thoroughly
2. Update this README
3. Ensure scripts remain idempotent
4. Add error handling for edge cases

