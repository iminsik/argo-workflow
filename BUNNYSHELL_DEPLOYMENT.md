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
- This works within the Bunnyshell environment
- If you need external access, configure ingress/routing in Bunnyshell

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

### Step 7: Configure Kubernetes RBAC

After deployment, you need to configure RBAC for the backend to access Argo Workflows:

1. Access your Kubernetes cluster (via `kubectl` or Bunnyshell's cluster access)
2. Apply the RBAC configuration:
   ```bash
   kubectl apply -f infrastructure/k8s/rbac.yaml
   ```

This creates:
- ServiceAccount: `backend-sa` in `argo` namespace
- Role: `argo-manager` with workflow permissions
- RoleBinding: Links service account to role

**Note**: The backend component needs to use this ServiceAccount. You may need to update the Bunnyshell component configuration or manually patch the deployment.

### Step 8: Verify Deployment

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

### Step 9: Configure Ingress/Routing (Optional)

If you need external access to your services:

1. In Bunnyshell, configure routing/ingress for:
   - Frontend (port 80)
   - Backend API (port 8000)

2. Update `CORS_ORIGINS` in backend to include your frontend's public URL

3. Update `VITE_API_URL` in frontend to point to your backend's public URL

## Post-Deployment Configuration

### Update Backend ServiceAccount

The backend needs to use the `backend-sa` ServiceAccount to access Argo Workflows. You may need to:

1. Edit the backend deployment in Bunnyshell
2. Add ServiceAccount configuration:
   ```yaml
   serviceAccountName: backend-sa
   ```
3. Or patch the deployment:
   ```bash
   kubectl patch deployment backend -n <namespace> -p '{"spec":{"template":{"spec":{"serviceAccountName":"backend-sa"}}}}'
   ```

### Verify Argo Workflows Access

Test that the backend can create workflows:

```bash
# Check backend logs
kubectl logs -n <namespace> deployment/backend

# Test workflow creation via API
curl -X POST http://<backend-url>/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "code": "print(\"hello\")"}'
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
1. Verify RBAC is configured: `kubectl get rolebinding -n argo`
2. Check ServiceAccount is set: `kubectl get deployment backend -o yaml | grep serviceAccount`
3. Verify backend can access Kubernetes API:
   ```bash
   kubectl exec -n <namespace> <backend-pod> -- kubectl get workflows -n argo
   ```

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
4. Optionally, remove RBAC resources:
   ```bash
   kubectl delete -f infrastructure/k8s/rbac.yaml
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

