# Bunnyshell Deployment Guide

This guide walks you through deploying the Argo Workflow Manager to Bunnyshell.

## Prerequisites

Before deploying, ensure you have:

1. **Bunnyshell Account**: Sign up at [bunnyshell.com](https://bunnyshell.com)
2. **Kubernetes Cluster**: A Kubernetes cluster (v1.24+) that is:
   - Accessible from Bunnyshell
   - Has Argo Workflows installed (v3.5.0+)
   - Has sufficient resources (see resource requirements below)
3. **Git Repository**: Your repository connected to Bunnyshell
4. **Argo Workflows**: Installed in your Kubernetes cluster in the `argo` namespace
5. **kubectl Access**: Configured to access your Kubernetes cluster for post-deployment setup

### Pre-Deployment Checklist

Before starting the deployment, ensure:

- [ ] Argo Workflows is installed and running in the `argo` namespace
- [ ] You have `kubectl` access to the cluster
- [ ] You have permissions to create ServiceAccounts, Roles, and RoleBindings
- [ ] You have permissions to create PersistentVolumes and PersistentVolumeClaims
- [ ] Your cluster has sufficient resources (see Resource Requirements below)

### Resource Requirements

- **PostgreSQL**: 256Mi-512Mi memory, 250m-500m CPU
- **Backend**: 512Mi-1Gi memory, 500m-1000m CPU
- **Frontend**: 128Mi-256Mi memory, 100m-200m CPU

## Step-by-Step Deployment

### Step 1: Connect Your Kubernetes Cluster

1. Log in to your Bunnyshell dashboard
2. Navigate to **Clusters** in the sidebar
3. Click **Add Cluster** or **Connect Cluster**
4. Follow the instructions to connect your Kubernetes cluster
5. Verify the cluster connection is active

### Step 2: Connect Your Git Repository

1. In Bunnyshell dashboard, navigate to **Repositories**
2. Click **Add Repository** or **Connect Repository**
3. Select your Git provider (GitHub, GitLab, Bitbucket, etc.)
4. Authorize Bunnyshell to access your repositories
5. Select the repository containing this project
6. Verify the repository is connected

### Step 3: Create a New Environment

1. Navigate to **Environments** in the sidebar
2. Click **Create Environment** or **New Environment**
3. Select **From Configuration File** or **From YAML**
4. Choose your connected repository
5. Select the branch containing `bunnyshell.yaml` (e.g., `feature/svelte` or `main`)
6. Bunnyshell will automatically detect the `bunnyshell.yaml` file

### Step 4: Review and Configure Environment

The `bunnyshell.yaml` file defines three components:

1. **PostgreSQL Database**: Stores application data
2. **Backend Service**: FastAPI application
3. **Frontend Application**: Svelte web application

#### Important Configuration Notes

**CORS Configuration:**
- The backend's `CORS_ORIGINS` is currently set to `"*"` (allow all origins)
- **For production**, update this to your specific frontend URL:
  ```yaml
  - name: CORS_ORIGINS
    value: "https://your-frontend-domain.com"
  ```

**API URL Configuration:**
- The frontend's `VITE_API_URL` is set to `http://backend:8000` (internal service name)
- This is used as a build-time argument during Docker build
- For internal access within Bunnyshell, this works automatically
- If you need external access, configure ingress/routing in Bunnyshell and update the build arg

**Database Connection:**
- The backend connects to PostgreSQL using the service name `postgres`
- Connection string: `postgresql://postgres:password@postgres:5432/postgres`
- **For production**, consider using a managed database service or updating credentials

### Step 5: Configure Environment Variables (Optional)

Before deploying, you may want to customize environment variables:

1. In the environment creation/editing interface, you can override:
   - `CORS_ORIGINS` - Frontend URLs allowed to access the backend
   - `DATABASE_URL` - PostgreSQL connection string
   - `ARGO_NAMESPACE` - Kubernetes namespace for Argo Workflows (default: `argo`)
   - `WORKFLOW_MANIFEST_PATH` - Path to workflow YAML (default: `/infrastructure/argo/python-processor.yaml`)
   - `VITE_API_URL` - Backend API URL for frontend (default: `http://backend:8000`)

2. For sensitive values, use Bunnyshell's secrets management instead of plain environment variables

### Step 6: Deploy the Environment

1. Review all component configurations
2. Click **Deploy** or **Create Environment**
3. Bunnyshell will:
   - Build Docker images for backend and frontend
   - Create PostgreSQL database
   - Deploy all components to your Kubernetes cluster
   - Set up networking between components

### Step 7: Create Required Kubernetes Resources

Before the backend can function properly, you need to create:

1. **PersistentVolume and PersistentVolumeClaim** (required for task results storage):
   ```bash
   kubectl apply -f infrastructure/k8s/pv.yaml
   ```
   This creates:
   - PersistentVolume: `task-results-pv`
   - PersistentVolumeClaim: `task-results-pvc` in `argo` namespace

2. **RBAC Configuration** (required for backend to access Argo Workflows):
   ```bash
   kubectl apply -f infrastructure/k8s/rbac.yaml
   ```
   This creates:
   - ServiceAccount: `backend-sa` in `argo` namespace
   - Role: `argo-manager` with workflow permissions
   - RoleBinding: Links service account to role

**Important**: The backend component needs to use the `backend-sa` ServiceAccount. Since Bunnyshell deploys to its own namespace but the ServiceAccount is in the `argo` namespace, you have two options:

**Option A (Recommended)**: Create the ServiceAccount in the Bunnyshell namespace and bind it to the Role in `argo` namespace:
```bash
# Get the namespace where Bunnyshell deployed your components
# Replace 'argo-workflow-manager' with your actual environment name if different
BUNNYSHELL_NS=$(kubectl get namespaces | grep argo-workflow-manager | awk '{print $1}')

# If namespace not found, check Bunnyshell dashboard for the actual namespace name
# Or list all namespaces: kubectl get namespaces

# Create ServiceAccount in Bunnyshell namespace
kubectl create serviceaccount backend-sa -n $BUNNYSHELL_NS

# The Role and RoleBinding in argo namespace should already exist from Step 7
# Update the RoleBinding to reference the ServiceAccount in Bunnyshell namespace
kubectl patch rolebinding backend-sa-binding -n argo --type='json' -p='[{"op": "replace", "path": "/subjects/0/namespace", "value": "'$BUNNYSHELL_NS'"}]'
```

**Option B**: Use the existing ServiceAccount in `argo` namespace (requires the backend pod to be in the same namespace or use a ClusterRoleBinding - not recommended for security reasons).

### Step 8: Configure Backend ServiceAccount

After deployment, configure the backend to use the ServiceAccount:

1. **Find the Bunnyshell namespace**:
   ```bash
   kubectl get namespaces | grep argo-workflow-manager
   ```

2. **Update the backend deployment** to use the ServiceAccount:
   ```bash
   # Replace <namespace> with your Bunnyshell namespace (e.g., argo-workflow-manager-xxx)
   # Find the namespace first:
   kubectl get namespaces | grep argo-workflow-manager
   
   # Then patch the deployment:
   kubectl patch deployment backend -n <namespace> -p '{"spec":{"template":{"spec":{"serviceAccountName":"backend-sa"}}}}'
   ```

3. **Restart the backend pod** to apply the ServiceAccount:
   ```bash
   kubectl rollout restart deployment/backend -n <namespace>
   ```

4. **Verify the ServiceAccount is set**:
   ```bash
   kubectl get deployment backend -n <namespace> -o jsonpath='{.spec.template.spec.serviceAccountName}'
   ```
   Should output: `backend-sa`

5. **Verify the pod is using the ServiceAccount**:
   ```bash
   kubectl get pod -n <namespace> -l app=backend -o jsonpath='{.items[0].spec.serviceAccountName}'
   ```

### Step 9: Verify Deployment

1. **Check Component Status**:
   - In Bunnyshell dashboard, navigate to your environment
   - Verify all components show as "Running" or "Healthy"

2. **Check Pods**:
   ```bash
   kubectl get pods -n <bunnyshell-namespace>
   ```
   All pods should be in `Running` state

3. **Check Services**:
   ```bash
   kubectl get svc -n <bunnyshell-namespace>
   ```
   Verify services are created and have endpoints

4. **Test Backend Health**:
   - Access the backend service URL from Bunnyshell
   - Or use port-forward:
     ```bash
     kubectl port-forward -n <namespace> svc/backend 8000:8000
     curl http://localhost:8000/health
     ```

5. **Test Frontend**:
   - Access the frontend service URL from Bunnyshell
   - Verify the UI loads correctly
   - Test creating a workflow task

### Step 10: Configure Ingress/Routing (Optional)

If you need external access to your services:

1. In Bunnyshell, configure routing/ingress for:
   - Frontend (port 80)
   - Backend API (port 8000)

2. Update `CORS_ORIGINS` in backend to include your frontend's public URL

3. Update `VITE_API_URL` in frontend to point to your backend's public URL

## Post-Deployment Configuration

### Verify PVC Status

The backend requires the `task-results-pvc` to be bound before it can create workflows:

```bash
# Check PVC status
kubectl get pvc -n argo task-results-pvc

# If not bound, check PV
kubectl get pv task-results-pv

# If PVC doesn't exist, create it
kubectl apply -f infrastructure/k8s/pv.yaml
```

### Verify Argo Workflows Access

The backend uses Kubernetes in-cluster configuration (`load_incluster_config()`), which means it automatically uses the ServiceAccount token from the pod it's running in. This is why configuring the ServiceAccount is critical.

Test that the backend can create workflows:

```bash
# Check backend logs for any connection errors
kubectl logs -n <namespace> deployment/backend

# Verify the backend can see workflows
kubectl exec -n <namespace> deployment/backend -- python -c "
from kubernetes import config
from kubernetes.client import CustomObjectsApi
config.load_incluster_config()
api = CustomObjectsApi()
workflows = api.list_namespaced_custom_object('argoproj.io', 'v1alpha1', 'argo', 'workflows')
print(f'Found {len(workflows.get(\"items\", []))} workflows')
"

# Test workflow creation via API (if you have external access configured)
curl -X POST http://<backend-url>/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"pythonCode": "print(\"hello\")"}'
```

## Troubleshooting

### Components Not Starting

**Check logs:**
```bash
kubectl logs -n <namespace> <component-pod-name>
```

**Common issues:**
- Image build failures: Check Dockerfile syntax and build context
- Resource constraints: Verify cluster has sufficient resources
- Database connection: Verify PostgreSQL is running and accessible

### Backend Can't Access Argo Workflows

**Symptoms**: Backend errors when creating workflows

**Solutions**:
1. Verify PVC exists: `kubectl get pvc -n argo task-results-pvc`
2. Verify RBAC is configured: `kubectl get rolebinding -n argo`
3. Check ServiceAccount is set: `kubectl get deployment backend -n <namespace> -o yaml | grep serviceAccount`
4. Verify backend can access Kubernetes API:
   ```bash
   kubectl exec -n <namespace> <backend-pod> -- kubectl get workflows -n argo
   ```
5. Check backend logs for specific error messages:
   ```bash
   kubectl logs -n <namespace> deployment/backend
   ```

### PVC Not Found Error

**Symptoms**: Backend returns error "PVC 'task-results-pvc' not found"

**Solutions**:
1. Create the PVC: `kubectl apply -f infrastructure/k8s/pv.yaml`
2. Verify PVC is bound: `kubectl get pvc -n argo task-results-pvc`
3. If PVC is in Pending state, check if PV exists: `kubectl get pv task-results-pv`
4. Ensure the storage class matches: `kubectl get pvc -n argo task-results-pvc -o jsonpath='{.spec.storageClassName}'`

### CORS Errors

**Symptoms**: Frontend can't call backend API

**Solutions**:
1. Update `CORS_ORIGINS` in backend to include frontend URL
2. Verify backend is accessible from frontend
3. Check browser console for specific CORS error messages

### Frontend Can't Connect to Backend

**Symptoms**: Frontend shows connection errors

**Solutions**:
1. Verify `VITE_API_URL` is correct (should be `http://backend:8000` for internal access)
2. Check backend service is running: `kubectl get svc backend`
3. Verify network policies allow frontend to reach backend

## Updating the Deployment

### Update Code

1. Push changes to your Git repository
2. In Bunnyshell, trigger a rebuild/redeploy:
   - Navigate to your environment
   - Click **Redeploy** or **Rebuild**
   - Select the component(s) to update

### Update Configuration

1. Edit `bunnyshell.yaml` in your repository
2. Push changes
3. Bunnyshell will detect changes and prompt for redeployment

### Manual Updates

You can also update components manually in Bunnyshell:
1. Navigate to the component
2. Edit configuration
3. Save and redeploy

## Monitoring

### View Logs in Bunnyshell

1. Navigate to your environment
2. Click on a component
3. View logs in the component details

### View Logs via kubectl

```bash
# Backend logs
kubectl logs -n <namespace> deployment/backend -f

# Frontend logs
kubectl logs -n <namespace> deployment/frontend -f

# PostgreSQL logs
kubectl logs -n <namespace> deployment/postgres -f
```

### Monitor Resources

```bash
# Check resource usage
kubectl top pods -n <namespace>

# Check component status
kubectl get all -n <namespace>
```

## Security Best Practices

1. **Secrets Management**:
   - Use Bunnyshell's secrets management for sensitive values
   - Don't hardcode passwords in `bunnyshell.yaml`

2. **CORS Configuration**:
   - Restrict `CORS_ORIGINS` to specific domains in production
   - Don't use `"*"` in production

3. **Database Credentials**:
   - Use strong passwords for PostgreSQL
   - Consider using managed database services for production

4. **RBAC**:
   - Ensure minimal required permissions
   - Regularly audit ServiceAccount permissions

5. **Network Policies**:
   - Consider implementing network policies to restrict traffic
   - Limit external access to necessary services only

## Cleanup

To remove the deployment:

1. In Bunnyshell dashboard, navigate to your environment
2. Click **Delete Environment** or **Destroy**
3. Confirm deletion
4. Optionally, remove Kubernetes resources:
   ```bash
   # Remove RBAC
   kubectl delete -f infrastructure/k8s/rbac.yaml
   
   # Remove PVC (optional - data will be lost)
   kubectl delete pvc -n argo task-results-pvc
   
   # Remove PV (optional)
   kubectl delete pv task-results-pv
   ```

## Additional Resources

- [Bunnyshell Documentation](https://documentation.bunnyshell.com/)
- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)

## Support

For issues specific to:
- **Bunnyshell**: Contact Bunnyshell support or check their documentation
- **Application**: Check application logs and refer to [DEVOPS.md](./DEVOPS.md)
- **Argo Workflows**: Refer to [Argo Workflows troubleshooting guide](https://argoproj.github.io/argo-workflows/troubleshooting/)

