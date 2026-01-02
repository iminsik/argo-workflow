# Complete Kubernetes Deployment Strategy for Bunnyshell

This document outlines the best strategy and step-by-step process for deploying the entire application stack (Argo Workflows, Database, Backend, and Frontend) in a Kubernetes environment using Bunnyshell.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Bunnyshell Environment Namespace             │  │
│  │                                                       │  │
│  │  ┌──────────────┐  ┌──────────────┐                │
│  │  │   Frontend   │  │   Backend    │  │  ┌──────────┐ │  │
│  │  │   (Svelte)   │──│  (FastAPI)   │──│  │PostgreSQL│ │  │
│  │  │   Port: 80   │  │  Port: 8000  │  │  │ Port:5432│ │  │
│  │  └──────────────┘  └──────┬───────┘  │  └──────────┘ │  │
│  │                           │           │                │  │
│  └───────────────────────────┼───────────┼────────────────┘  │
│                              │           │                    │
│  ┌───────────────────────────▼───────────▼────────────────┐  │
│  │              Argo Workflows Namespace (argo)            │  │
│  │                                                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │  │
│  │  │  Controller  │  │    Server    │  │  Workflows   │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  PersistentVolumeClaim: task-results-pvc         │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  ServiceAccount: backend-sa (with RBAC)          │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Deployment Strategy: Phased Approach

### Phase 1: Prerequisites & Infrastructure Setup
**Goal**: Ensure all prerequisites are met before application deployment

### Phase 2: Argo Workflows Installation
**Goal**: Install and configure Argo Workflows in the cluster

### Phase 3: Kubernetes Resources Setup
**Goal**: Create required RBAC, PVCs, and ServiceAccounts

### Phase 4: Application Deployment via Bunnyshell
**Goal**: Deploy application components (Database, Backend, Frontend)

### Phase 5: Integration & Configuration
**Goal**: Connect components and configure cross-namespace access

### Phase 6: Verification & Optimization
**Goal**: Verify deployment and optimize for production

---

## Detailed Step-by-Step Deployment

### Phase 1: Prerequisites & Infrastructure Setup

#### Step 1.1: Verify Kubernetes Cluster Access
```bash
# Verify cluster connection
kubectl cluster-info

# Check cluster version (should be v1.24+)
kubectl version --short

# Verify you have admin access
kubectl auth can-i '*' '*' --all-namespaces
```

#### Step 1.2: Verify Cluster Resources
```bash
# Check available resources
kubectl top nodes

# Ensure you have sufficient capacity:
# - At least 2 CPU cores available
# - At least 4GB memory available
# - Storage for PVCs
```

#### Step 1.3: Connect Cluster to Bunnyshell
1. Log in to [Bunnyshell Dashboard](https://dashboard.bunnyshell.com)
2. Navigate to **Clusters** → **Add Cluster**
3. Follow the connection wizard:
   - Choose your cluster type (GKE, EKS, AKS, or custom)
   - Provide cluster credentials (kubeconfig or service account)
   - Verify connection status
4. **Verify**: Cluster should show as "Connected" and "Active"

#### Step 1.4: Connect Git Repository to Bunnyshell
1. Navigate to **Repositories** → **Add Repository**
2. Select your Git provider (GitHub, GitLab, Bitbucket)
3. Authorize Bunnyshell access
4. Select the repository: `argo-monorepo-old1`
5. **Verify**: Repository should show as "Connected"

---

### Phase 2: Argo Workflows Installation

**Quick Option**: Use the helper script to automate Phases 2-3:
```bash
./scripts/setup-k8s-resources.sh
```

This script handles all steps in Phase 2 and Phase 3 automatically. If you prefer manual setup, follow the steps below.

#### Step 2.1: Create Argo Namespace
```bash
kubectl create namespace argo
```

#### Step 2.2: Install Argo Workflows
```bash
# Install Argo Workflows (minimal installation for production)
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml

# Or for full installation with UI:
# kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/install.yaml
```

#### Step 2.3: Verify Argo Workflows Installation
```bash
# Check Argo Workflows pods
kubectl get pods -n argo

# Expected output should show:
# - workflow-controller-* (Running)
# - argo-server-* (Running, if full installation)

# Check Argo Workflows CRDs
kubectl get crd | grep argo

# Should include:
# - workflows.argoproj.io
# - workflowtemplates.argoproj.io
```

#### Step 2.4: Wait for Argo Workflows to be Ready
```bash
# Wait for all pods to be running
kubectl wait --for=condition=ready pod -l app=workflow-controller -n argo --timeout=300s

# If argo-server is installed:
kubectl wait --for=condition=ready pod -l app=argo-server -n argo --timeout=300s
```

---

### Phase 3: Kubernetes Resources Setup

**Quick Option**: If you used `setup-k8s-resources.sh`, this phase is already complete. Otherwise, follow the steps below.

#### Step 3.1: Create PersistentVolume and PersistentVolumeClaim
```bash
# Apply PV and PVC configuration
kubectl apply -f infrastructure/k8s/pv.yaml

# Verify PV is created
kubectl get pv task-results-pv

# Verify PVC is bound
kubectl get pvc -n argo task-results-pvc

# Expected status: Bound
```

**Note**: If using a cloud provider (GKE, EKS, AKS), you may need to:
- Use a StorageClass instead of manual PV
- Update `pv.yaml` to use dynamic provisioning
- Or use a managed storage solution

#### Step 3.2: Create RBAC Configuration
```bash
# Apply RBAC configuration
kubectl apply -f infrastructure/k8s/rbac.yaml

# Verify ServiceAccount
kubectl get serviceaccount -n argo backend-sa

# Verify Role
kubectl get role -n argo argo-manager

# Verify RoleBinding
kubectl get rolebinding -n argo backend-sa-binding
```

#### Step 3.3: Test RBAC Permissions (Optional)
```bash
# Create a test pod with the ServiceAccount
kubectl run test-backend-sa \
  --image=bitnami/kubectl:latest \
  --serviceaccount=backend-sa \
  --namespace=argo \
  --rm -it --restart=Never \
  --command -- /bin/bash

# Inside the pod, test permissions:
# kubectl get workflows -n argo
# kubectl create workflow -n argo --dry-run=client -o yaml
```

---

### Phase 4: Application Deployment via Bunnyshell

#### Step 4.1: Review and Update bunnyshell.yaml

**Current Configuration Check:**
- Verify `bunnyshell.yaml` is in the repository root
- Check that all components are properly defined
- Ensure build contexts and Dockerfiles are correct

**Key Configuration Points:**
1. **Database Component**:
   - Image: `postgres:15-alpine`
   - Environment variables for credentials
   - Resource limits

2. **Backend Component**:
   - Build context and Dockerfile path
   - Environment variables (DATABASE_URL, ARGO_NAMESPACE, etc.)
   - ServiceAccount reference (will be configured in Phase 5)
   - Resource limits

3. **Frontend Component**:
   - Build context and Dockerfile path
   - Build args for VITE_API_URL
   - Resource limits

#### Step 4.2: Create Environment in Bunnyshell

1. Navigate to **Environments** → **Create Environment**
2. Select **From Configuration File** or **From YAML**
3. Choose your connected repository
4. Select the branch (e.g., `main`, `master`, or your feature branch)
5. Bunnyshell will auto-detect `bunnyshell.yaml`
6. Review the detected components:
   - PostgreSQL
   - Backend
   - Frontend

#### Step 4.3: Configure Environment Variables

**Before deploying, configure these in Bunnyshell UI:**

1. **Backend Environment Variables**:
   ```
   DATABASE_URL: postgresql://postgres:password@postgres:5432/postgres
   ARGO_NAMESPACE: argo
   WORKFLOW_MANIFEST_PATH: /infrastructure/argo/python-processor.yaml
   CORS_ORIGINS: "*"  # Update to your frontend URL in production
   ```

2. **Frontend Environment Variables**:
   ```
   VITE_API_URL: http://backend:8000  # For internal access
   # Or use Bunnyshell domain if ingress is configured:
   # VITE_API_URL: https://api-{{env.BUNNYSHELL_SPACE_DOMAIN}}
   ```

3. **PostgreSQL Environment Variables**:
   ```
   POSTGRES_PASSWORD: <strong-password>  # Use Bunnyshell secrets
   POSTGRES_DB: postgres
   ```

**Security Best Practice**: Use Bunnyshell's **Secrets Management** for sensitive values like passwords.

#### Step 4.4: Configure Resource Limits

In Bunnyshell UI, for each component, set resource limits:

**PostgreSQL**:
- Requests: Memory 256Mi, CPU 250m
- Limits: Memory 512Mi, CPU 500m

**Backend**:
- Requests: Memory 512Mi, CPU 500m
- Limits: Memory 1Gi, CPU 1000m

**Frontend**:
- Requests: Memory 128Mi, CPU 100m
- Limits: Memory 256Mi, CPU 200m

#### Step 4.5: Deploy Environment

1. Click **Deploy** or **Create Environment**
2. Monitor the deployment progress:
   - Image builds
   - Component creation
   - Pod startup
3. Wait for all components to show "Running" or "Healthy"

**Expected Timeline**:
- Image builds: 5-10 minutes (first time)
- Component deployment: 2-5 minutes
- Total: ~10-15 minutes

---

### Phase 5: Integration & Configuration

#### Step 5.1: Identify Bunnyshell Namespace

```bash
# Find the namespace where Bunnyshell deployed your components
kubectl get namespaces | grep argo-workflow-manager

# Or check all namespaces
kubectl get namespaces

# Note the namespace name (e.g., argo-workflow-manager-abc123)
export BUNNYSHELL_NS="<your-namespace>"
```

#### Step 5.2: Configure Backend ServiceAccount

**Quick Option**: Use the helper script to automate this step:
```bash
./scripts/configure-serviceaccount.sh
```

The script will auto-detect the Bunnyshell namespace and configure everything. If you prefer manual setup, follow the steps below.

**Option A: Create ServiceAccount in Bunnyshell Namespace (Recommended)**

```bash
# Set the namespace
export BUNNYSHELL_NS="<your-bunnyshell-namespace>"

# Create ServiceAccount in Bunnyshell namespace
kubectl create serviceaccount backend-sa -n $BUNNYSHELL_NS

# Update RoleBinding to reference ServiceAccount in Bunnyshell namespace
kubectl patch rolebinding backend-sa-binding -n argo --type='json' \
  -p='[{"op": "replace", "path": "/subjects/0/namespace", "value": "'$BUNNYSHELL_NS'"}]'

# Verify RoleBinding
kubectl get rolebinding backend-sa-binding -n argo -o yaml
```

**Option B: Use ClusterRoleBinding (Less Secure, but Simpler)**

```bash
# Create ClusterRoleBinding to allow backend-sa from any namespace
kubectl create clusterrolebinding backend-sa-cluster-binding \
  --clusterrole=argo-manager \
  --serviceaccount=$BUNNYSHELL_NS:backend-sa
```

#### Step 5.3: Update Backend Deployment to Use ServiceAccount

```bash
# Patch the backend deployment
kubectl patch deployment backend -n $BUNNYSHELL_NS \
  -p '{"spec":{"template":{"spec":{"serviceAccountName":"backend-sa"}}}}'

# Restart the backend pod
kubectl rollout restart deployment/backend -n $BUNNYSHELL_NS

# Wait for rollout to complete
kubectl rollout status deployment/backend -n $BUNNYSHELL_NS

# Verify ServiceAccount is set
kubectl get deployment backend -n $BUNNYSHELL_NS \
  -o jsonpath='{.spec.template.spec.serviceAccountName}'
# Should output: backend-sa
```

#### Step 5.4: Configure Ingress/Routing (Optional, for External Access)

**In Bunnyshell UI:**

1. Navigate to your environment
2. For **Backend** component:
   - Go to **Routing** or **Hosts**
   - Add host: `api-{{env.BUNNYSHELL_SPACE_DOMAIN}}`
   - Path: `/`
   - Port: `8000`

3. For **Frontend** component:
   - Go to **Routing** or **Hosts**
   - Add host: `web-{{env.BUNNYSHELL_SPACE_DOMAIN}}`
   - Path: `/`
   - Port: `80`

4. Update environment variables:
   - Backend: `CORS_ORIGINS: "https://web-{{env.BUNNYSHELL_SPACE_DOMAIN}}"`
   - Frontend: `VITE_API_URL: "https://api-{{env.BUNNYSHELL_SPACE_DOMAIN}}"`

---

### Phase 6: Verification & Optimization

#### Step 6.1: Verify Component Health

```bash
# Check all pods are running
kubectl get pods -n $BUNNYSHELL_NS

# Check services
kubectl get svc -n $BUNNYSHELL_NS

# Check component logs
kubectl logs -n $BUNNYSHELL_NS deployment/backend
kubectl logs -n $BUNNYSHELL_NS deployment/frontend
kubectl logs -n $BUNNYSHELL_NS deployment/postgres
```

#### Step 6.2: Test Backend API

```bash
# Port-forward to backend
kubectl port-forward -n $BUNNYSHELL_NS svc/backend 8000:8000

# In another terminal, test health endpoint
curl http://localhost:8000/health

# Test API endpoints
curl http://localhost:8000/api/v1/tasks
```

#### Step 6.3: Test Argo Workflows Integration

```bash
# Check backend can access Argo Workflows
kubectl exec -n $BUNNYSHELL_NS deployment/backend -- python -c "
from kubernetes import config
from kubernetes.client import CustomObjectsApi
config.load_incluster_config()
api = CustomObjectsApi()
workflows = api.list_namespaced_custom_object('argoproj.io', 'v1alpha1', 'argo', 'workflows')
print(f'Found {len(workflows.get(\"items\", []))} workflows')
"

# Test workflow creation via API
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"pythonCode": "print(\"Hello from Argo!\")"}'
```

#### Step 6.4: Test Frontend

1. Access frontend URL from Bunnyshell dashboard
2. Or port-forward:
   ```bash
   kubectl port-forward -n $BUNNYSHELL_NS svc/frontend 8080:80
   ```
3. Open browser: `http://localhost:8080`
4. Test creating a workflow task
5. Verify task appears in the list
6. Check workflow execution in Argo Workflows

#### Step 6.5: Verify PVC Access

```bash
# Check PVC is bound and accessible
kubectl get pvc -n argo task-results-pvc

# Verify backend can reference it
kubectl exec -n $BUNNYSHELL_NS deployment/backend -- \
  kubectl get pvc -n argo task-results-pvc
```

#### Step 6.6: Monitor Resource Usage

```bash
# Check resource usage
kubectl top pods -n $BUNNYSHELL_NS

# Check if any pods are being throttled
kubectl describe pod -n $BUNNYSHELL_NS <pod-name> | grep -i throttle
```

---

## Troubleshooting Guide

### Common Issues and Solutions

#### Issue 1: Backend Can't Access Argo Workflows

**Symptoms**: Backend errors when creating workflows, 403 Forbidden errors

**Solutions**:
1. Verify ServiceAccount is set:
   ```bash
   kubectl get deployment backend -n $BUNNYSHELL_NS -o yaml | grep serviceAccount
   ```

2. Verify RoleBinding references correct namespace:
   ```bash
   kubectl get rolebinding backend-sa-binding -n argo -o yaml
   ```

3. Test permissions:
   ```bash
   kubectl auth can-i create workflows --as=system:serviceaccount:$BUNNYSHELL_NS:backend-sa -n argo
   ```

#### Issue 2: PVC Not Found

**Symptoms**: Backend returns "PVC 'task-results-pvc' not found"

**Solutions**:
1. Verify PVC exists:
   ```bash
   kubectl get pvc -n argo task-results-pvc
   ```

2. If not bound, check PV:
   ```bash
   kubectl get pv task-results-pv
   ```

3. For cloud providers, use StorageClass instead of manual PV

#### Issue 3: Database Connection Failed

**Symptoms**: Backend can't connect to PostgreSQL

**Solutions**:
1. Verify PostgreSQL is running:
   ```bash
   kubectl get pods -n $BUNNYSHELL_NS | grep postgres
   ```

2. Check DATABASE_URL environment variable:
   ```bash
   kubectl get deployment backend -n $BUNNYSHELL_NS -o yaml | grep DATABASE_URL
   ```

3. Test connection from backend pod:
   ```bash
   kubectl exec -n $BUNNYSHELL_NS deployment/backend -- \
     python -c "import psycopg2; conn = psycopg2.connect('postgresql://postgres:password@postgres:5432/postgres'); print('Connected!')"
   ```

#### Issue 4: Frontend Can't Reach Backend

**Symptoms**: CORS errors, network errors in browser

**Solutions**:
1. Verify CORS_ORIGINS includes frontend URL
2. Check backend service is accessible:
   ```bash
   kubectl get svc backend -n $BUNNYSHELL_NS
   ```

3. Test from frontend pod:
   ```bash
   kubectl exec -n $BUNNYSHELL_NS deployment/frontend -- \
     curl http://backend:8000/health
   ```

#### Issue 5: Image Build Failures

**Symptoms**: Components fail to start, build errors in Bunnyshell

**Solutions**:
1. Check Dockerfile syntax
2. Verify build context is correct
3. Check for missing dependencies in Dockerfile
4. Review build logs in Bunnyshell UI

---

## Production Considerations

### Security Hardening

1. **Secrets Management**:
   - Use Bunnyshell secrets for all sensitive values
   - Never hardcode passwords in `bunnyshell.yaml`
   - Rotate credentials regularly

2. **CORS Configuration**:
   - Remove wildcard (`"*"`) in production
   - Specify exact frontend domain(s)

3. **Network Policies**:
   - Implement network policies to restrict traffic
   - Limit external access to necessary services only

4. **RBAC**:
   - Use least-privilege principle
   - Regularly audit ServiceAccount permissions

### Performance Optimization

1. **Resource Tuning**:
   - Monitor actual resource usage
   - Adjust requests/limits based on metrics
   - Use Horizontal Pod Autoscaler for scaling

2. **Database Optimization**:
   - Consider using managed database service
   - Implement connection pooling
   - Set up database backups

3. **Caching**:
   - Implement Redis for session/cache storage
   - Cache frequently accessed data

### Monitoring & Observability

1. **Logging**:
   - Centralize logs using Bunnyshell's logging or external service
   - Set up log aggregation

2. **Metrics**:
   - Expose Prometheus metrics from backend
   - Set up Grafana dashboards

3. **Alerting**:
   - Configure alerts for component failures
   - Monitor resource usage thresholds

### Backup & Disaster Recovery

1. **Database Backups**:
   - Set up automated PostgreSQL backups
   - Test restore procedures

2. **Configuration Backup**:
   - Version control all configuration files
   - Document all manual changes

3. **Disaster Recovery Plan**:
   - Document recovery procedures
   - Test recovery scenarios regularly

---

## Maintenance & Updates

### Updating Application Code

1. Push changes to Git repository
2. In Bunnyshell, trigger rebuild:
   - Navigate to environment
   - Select component(s) to update
   - Click **Rebuild** or **Redeploy**

### Updating Configuration

1. Edit `bunnyshell.yaml` in repository
2. Push changes
3. Bunnyshell will detect changes and prompt for redeployment

### Scaling Components

1. In Bunnyshell UI, adjust replica count
2. Or update `bunnyshell.yaml` with replica configuration
3. Redeploy environment

---

## Quick Reference Commands

```bash
# Set namespace variable
export BUNNYSHELL_NS="<your-namespace>"

# Check all components
kubectl get all -n $BUNNYSHELL_NS

# View backend logs
kubectl logs -n $BUNNYSHELL_NS deployment/backend -f

# Restart backend
kubectl rollout restart deployment/backend -n $BUNNYSHELL_NS

# Check Argo Workflows
kubectl get workflows -n argo

# Check PVC status
kubectl get pvc -n argo task-results-pvc

# Port-forward services
kubectl port-forward -n $BUNNYSHELL_NS svc/backend 8000:8000
kubectl port-forward -n $BUNNYSHELL_NS svc/frontend 8080:80
```

---

## Next Steps

After successful deployment:

1. ✅ Configure monitoring and alerting
2. ✅ Set up CI/CD pipeline for automated deployments
3. ✅ Implement backup strategy
4. ✅ Configure production-grade security settings
5. ✅ Set up staging environment for testing
6. ✅ Document runbooks for common operations

---

## Support Resources

- **Bunnyshell Documentation**: https://documentation.bunnyshell.com/
- **Argo Workflows Docs**: https://argoproj.github.io/argo-workflows/
- **Kubernetes Docs**: https://kubernetes.io/docs/
- **Project Documentation**: See `BUNNYSHELL_DEPLOYMENT.md` for detailed troubleshooting

