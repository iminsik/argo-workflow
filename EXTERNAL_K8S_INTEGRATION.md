# Integrating External Kubernetes Cluster with Local Docker Compose

This guide explains how to connect your local docker-compose development environment to an external Kubernetes cluster (instead of a local kind cluster).

## Overview

Your setup already supports external Kubernetes clusters! The backend service:
- Mounts your `~/.kube` directory to access kubeconfig
- Automatically tries in-cluster config first, then falls back to kubeconfig
- Works with any Kubernetes cluster your kubeconfig can access

## Quick Start

### Step 1: Configure kubectl for External Cluster

```bash
# List available contexts
kubectl config get-contexts

# Switch to your external cluster context
kubectl config use-context <your-external-cluster-context>

# Verify connection
kubectl cluster-info
kubectl get nodes
```

### Step 1.5: Install Argo Workflows (if not already installed)

If your external cluster doesn't have Argo Workflows installed yet:

**Option A: Use the automated script (Recommended)**
```bash
# This will install Argo Workflows, create namespace, RBAC, and storage
make argo-setup-external
# or
./scripts/setup-k8s-resources.sh
```

**Option B: Manual installation**

1. **Create namespace**:
   ```bash
   kubectl create namespace argo
   ```

2. **Install Argo Workflows**:
   ```bash
   # Minimal installation (recommended for most cases)
   kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
   
   # Or full installation with UI (optional):
   # kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/install.yaml
   ```

3. **Wait for Argo to be ready**:
   ```bash
   kubectl wait --for=condition=ready pod -l app=workflow-controller -n argo --timeout=300s
   ```

4. **Create storage** (choose one based on your cluster type):

   **For local/kind clusters or clusters with hostPath support:**
   ```bash
   kubectl apply -f infrastructure/k8s/pv.yaml
   ```

   **For cloud clusters (GKE, EKS, AKS) with dynamic storage:**
   ```bash
   kubectl apply -f infrastructure/k8s/pv-cloud.yaml
   ```
   
   **Note**: Cloud clusters may need ReadWriteMany storage. Check your cluster's available StorageClasses:
   ```bash
   kubectl get storageclass
   ```
   If your cluster doesn't support ReadWriteMany, you may need to:
   - Use a managed NFS solution (e.g., AWS EFS, Azure Files, GCP Filestore)
   - Or modify the PVC to use ReadWriteOnce (workflows may have limitations)

5. **Create RBAC configuration**:
   ```bash
   kubectl apply -f infrastructure/k8s/rbac.yaml
   ```

6. **Verify installation**:
   ```bash
   # Check Argo Workflows pods
   kubectl get pods -n argo
   
   # Check PVC status
   kubectl get pvc -n argo task-results-pvc
   
   # Check RBAC resources
   kubectl get serviceaccount -n argo backend-sa
   kubectl get role -n argo argo-manager
   ```

**Verify Argo Workflows is installed**:
```bash
kubectl get pods -n argo
# Should show workflow-controller-* pod(s) running
```

### Step 2: Ensure Network Access

The Docker container needs to reach your external cluster's API server:

#### Option A: Public API Server
If your cluster's API server is publicly accessible:
- ✅ No additional configuration needed
- Just ensure firewall rules allow your IP

#### Option B: Private API Server
If your cluster is private, you have several options:

**Option B1: VPN/Bastion Host**
- Connect to your organization's VPN
- Or use a bastion host to tunnel traffic

**Option B2: kubectl port-forward (for testing)**
```bash
# In a separate terminal, keep this running:
kubectl port-forward -n argo service/argo-server 2746:2746
```

**Option B3: SSH Tunnel**
```bash
# Create SSH tunnel to cluster API server
ssh -L 6443:api-server-ip:6443 user@bastion-host
```

### Step 3: Start Docker Compose

```bash
# Your existing command works as-is!
make dev-up
# or
docker-compose up --build
```

The backend will automatically use the kubeconfig from `~/.kube` that points to your external cluster.

## Configuration Details

### How It Works

1. **Backend Kubernetes Client Initialization** (`apps/backend/app/main.py`):
   ```python
   try:
       config.load_incluster_config()  # Tries in-cluster first
   except:
       config.load_kube_config()       # Falls back to kubeconfig
   ```

2. **Docker Volume Mount** (`docker-compose.yaml`):
   ```yaml
   volumes: [ "~/.kube:/root/.kube:ro" ]
   ```
   This makes your local kubeconfig available inside the container.

3. **Kubeconfig Location**:
   - The container looks for kubeconfig at `/root/.kube/config`
   - This is mapped from your host's `~/.kube/config`

### Environment Variables

You can customize behavior with environment variables in `docker-compose.yaml`:

```yaml
backend:
  environment:
    - ARGO_NAMESPACE=argo  # Namespace where Argo Workflows runs
    - KUBECONFIG=/root/.kube/config  # Path to kubeconfig (default)
```

### Using Multiple Clusters

If you work with multiple clusters, you can:

1. **Switch contexts before starting docker-compose**:
   ```bash
   kubectl config use-context production-cluster
   docker-compose up
   ```

2. **Use a specific kubeconfig file**:
   ```yaml
   # In docker-compose.yaml
   volumes:
     - "~/.kube/production-config:/root/.kube/config:ro"
   ```

3. **Set KUBECONFIG environment variable**:
   ```yaml
   backend:
     environment:
       - KUBECONFIG=/root/.kube/production-config
     volumes:
       - "~/.kube:/root/.kube:ro"
   ```

## Troubleshooting

### Issue: "Unable to connect to the server"

**Symptoms:**
```
Error: Unable to connect to the server: dial tcp: lookup api.example.com: no such host
```

**Solutions:**
1. Verify cluster API server is accessible:
   ```bash
   kubectl cluster-info
   ```

2. Check if API server URL uses localhost (won't work from Docker):
   ```bash
   kubectl config view --minify | grep server
   ```
   If it shows `127.0.0.1` or `localhost`, you need to:
   - Use the actual cluster IP/hostname
   - Or set up port-forwarding/tunneling

3. Test from inside the container:
   ```bash
   docker-compose exec backend curl -k https://<api-server-url>
   ```

### Issue: "Certificate verification failed"

**Symptoms:**
```
SSL: CERTIFICATE_VERIFY_FAILED
```

**Solutions:**
1. The backend already disables SSL verification for development (see `main.py` line 48)
2. For production, ensure your kubeconfig has valid certificates
3. If needed, update certificates in your kubeconfig:
   ```bash
   kubectl config view --raw > ~/.kube/config
   ```

### Issue: "Permission denied" or "Forbidden"

**Symptoms:**
```
Error from server (Forbidden): workflows.argoproj.io is forbidden
```

**Solutions:**
1. Verify you have permissions:
   ```bash
   kubectl auth can-i create workflows -n argo
   kubectl auth can-i get workflows -n argo
   ```

2. Ensure RBAC is set up (if using ServiceAccount):
   ```bash
   kubectl apply -f infrastructure/k8s/rbac.yaml
   ```

3. Check your kubeconfig user has cluster-admin or appropriate permissions

### Issue: "Context not found"

**Symptoms:**
```
Error: context "my-cluster" does not exist
```

**Solutions:**
1. List available contexts:
   ```bash
   kubectl config get-contexts
   ```

2. Use the correct context name:
   ```bash
   kubectl config use-context <correct-context-name>
   ```

## Advanced: Network Configuration

### Using host.docker.internal

If your external cluster's API server is accessible from your host machine but uses `localhost` in kubeconfig, you can:

1. **Update kubeconfig to use host.docker.internal**:
   ```bash
   # Create a copy for Docker
   cp ~/.kube/config ~/.kube/config.docker
   # Edit and replace localhost/127.0.0.1 with host.docker.internal
   sed -i '' 's/127.0.0.1/host.docker.internal/g' ~/.kube/config.docker
   ```

2. **Mount the modified config**:
   ```yaml
   volumes:
     - "~/.kube/config.docker:/root/.kube/config:ro"
   ```

### Custom Network Configuration

For complex network setups, you can add custom network configuration:

```yaml
backend:
  network_mode: "host"  # Use host network (Linux only)
  # OR
  extra_hosts:
    - "api.example.com:192.168.1.100"  # Custom DNS mapping
```

## Comparison: Local vs External Cluster

| Aspect | Local Kind Cluster | External Cluster |
|--------|-------------------|------------------|
| Setup | `make cluster-up` | Use existing cluster |
| API Server | `127.0.0.1` (patched to `host.docker.internal`) | Actual cluster URL |
| Network | Direct access | May need VPN/tunnel |
| Resources | Limited by local machine | Uses cluster resources |
| Use Case | Development/testing | Production-like testing |

## Best Practices

1. **Use separate contexts** for different environments:
   ```bash
   kubectl config set-context dev --cluster=dev-cluster --user=dev-user
   kubectl config set-context prod --cluster=prod-cluster --user=prod-user
   ```

2. **Verify before starting docker-compose**:
   ```bash
   kubectl config current-context
   kubectl cluster-info
   ```

3. **Keep kubeconfig secure**:
   - The `:ro` (read-only) mount is already configured
   - Don't commit kubeconfig files to git
   - Use separate configs for different environments

4. **Monitor resource usage**:
   - External clusters may have resource quotas
   - Be mindful of workflow resource requests

## Example: Switching Between Clusters

```bash
# Work with local kind cluster
kubectl config use-context kind-argo-dev
make cluster-up
make dev-up

# Switch to external cluster
kubectl config use-context production-cluster
make dev-up  # Now uses external cluster!

# Switch back
kubectl config use-context kind-argo-dev
```

## Installing Argo Workflows in External Cluster

If your external Kubernetes cluster doesn't have Argo Workflows installed, follow these steps:

### Prerequisites

- kubectl configured and connected to your external cluster
- Cluster admin permissions (or permissions to create namespaces, CRDs, deployments, etc.)
- Kubernetes cluster version 1.24 or higher
- Sufficient cluster resources (at least 1 CPU core and 1GB memory available)

### Installation Methods

#### Method 1: Automated Script (Easiest)

```bash
# Ensure kubectl points to your external cluster
kubectl config use-context <your-external-cluster>

# Run the setup script
make argo-setup-external
# or
./scripts/setup-k8s-resources.sh
```

This script will:
- ✅ Create the `argo` namespace
- ✅ Install Argo Workflows v3.5.0 (minimal installation)
- ✅ Create PersistentVolume and PersistentVolumeClaim
- ✅ Set up RBAC (ServiceAccount, Role, RoleBinding)
- ✅ Verify all resources are created correctly

#### Method 2: Manual Step-by-Step

**1. Create Namespace**
```bash
kubectl create namespace argo
```

**2. Install Argo Workflows**

Choose based on your needs:

**Minimal Installation** (recommended, smaller footprint):
```bash
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
```

**Full Installation** (includes Argo Server UI):
```bash
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/install.yaml
```

**3. Wait for Installation**
```bash
# Wait for workflow controller
kubectl wait --for=condition=ready pod -l app=workflow-controller -n argo --timeout=300s

# If using full installation, also wait for argo-server
kubectl wait --for=condition=ready pod -l app=argo-server -n argo --timeout=300s
```

**4. Verify Installation**
```bash
# Check pods
kubectl get pods -n argo

# Check CRDs
kubectl get crd | grep argo
# Should show: workflows.argoproj.io, workflowtemplates.argoproj.io, etc.
```

**5. Create Storage**

**For local/kind clusters:**
```bash
kubectl apply -f infrastructure/k8s/pv.yaml
```

**For cloud clusters (GKE, EKS, AKS):**
```bash
# First, check available StorageClasses
kubectl get storageclass

# Apply cloud-optimized PVC
kubectl apply -f infrastructure/k8s/pv-cloud.yaml

# If your cluster doesn't support ReadWriteMany, you may need to:
# 1. Use a managed NFS solution (AWS EFS, Azure Files, GCP Filestore)
# 2. Or modify the PVC to use ReadWriteOnce (with limitations)
```

**6. Create RBAC**
```bash
kubectl apply -f infrastructure/k8s/rbac.yaml

# Verify
kubectl get serviceaccount -n argo backend-sa
kubectl get role -n argo argo-manager
kubectl get rolebinding -n argo backend-sa-binding
```

### Storage Configuration for Cloud Clusters

Cloud-managed Kubernetes clusters (GKE, EKS, AKS) typically don't support `hostPath` volumes. You have several options:

#### Option 1: Use Default StorageClass (ReadWriteOnce)

If ReadWriteMany isn't critical, modify `pv-cloud.yaml`:
```yaml
accessModes:
  - ReadWriteOnce  # Change from ReadWriteMany
```

#### Option 2: Use Managed NFS/File Storage

**AWS EKS with EFS:**
```bash
# Install EFS CSI driver (if not already installed)
# Then create StorageClass and use it in pv-cloud.yaml
```

**GKE with Filestore:**
```bash
# Create Filestore instance, then create StorageClass pointing to it
```

**AKS with Azure Files:**
```bash
# Azure Files supports ReadWriteMany, create StorageClass for it
```

#### Option 3: Skip Persistent Storage (for testing)

For development/testing, you can skip the PVC if workflows don't need persistent storage between tasks.

### Troubleshooting Installation

#### Issue: "Argo Workflows pods not starting"

**Check pod status:**
```bash
kubectl get pods -n argo
kubectl describe pod <pod-name> -n argo
kubectl logs <pod-name> -n argo
```

**Common causes:**
- Insufficient cluster resources
- Image pull errors (check registry access)
- RBAC issues

#### Issue: "PVC stuck in Pending"

**Check PVC status:**
```bash
kubectl get pvc -n argo task-results-pvc
kubectl describe pvc task-results-pvc -n argo
```

**Common causes:**
- No available PersistentVolume (for manual PV)
- StorageClass not found or misconfigured
- Insufficient storage quota

#### Issue: "CRDs not found"

**Verify CRDs are installed:**
```bash
kubectl get crd | grep argo
```

**If missing, install manually:**
```bash
kubectl apply -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/install.yaml
```

### Verification Checklist

After installation, verify everything is working:

```bash
# ✅ Namespace exists
kubectl get namespace argo

# ✅ Argo Workflows pods are running
kubectl get pods -n argo
# Should show: workflow-controller-* (and argo-server-* if full install)

# ✅ CRDs are installed
kubectl get crd | grep workflows.argoproj.io

# ✅ PVC is bound
kubectl get pvc -n argo task-results-pvc
# Status should be: Bound

# ✅ RBAC resources exist
kubectl get serviceaccount -n argo backend-sa
kubectl get role -n argo argo-manager
kubectl get rolebinding -n argo backend-sa-binding

# ✅ Test workflow creation (optional)
kubectl create -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: test-
  namespace: argo
spec:
  entrypoint: hello
  templates:
  - name: hello
    container:
      image: alpine:latest
      command: [echo, "Hello from Argo!"]
EOF
```

## Summary

✅ **Yes, you can integrate external Kubernetes with local docker-compose!**

Your setup already supports this:
- ✅ Kubeconfig is mounted into the container
- ✅ Backend automatically uses kubeconfig when not in-cluster
- ✅ Works with any cluster your kubeconfig can access

**To set up Argo Workflows in an external cluster:**
1. ✅ Use `make argo-setup-external` or `./scripts/setup-k8s-resources.sh`
2. ✅ Or follow the manual installation steps above
3. ✅ Choose the right storage configuration for your cluster type

**Then ensure:**
1. kubectl is configured for your external cluster
2. Network connectivity to the cluster API server
3. Proper RBAC permissions for Argo Workflows

