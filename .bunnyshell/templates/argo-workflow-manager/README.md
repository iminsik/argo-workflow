# Argo Workflow Manager Template

This template deploys a full-stack application for managing and monitoring Argo Workflows.

## Components

- **PostgreSQL**: Database for storing application data
- **Backend**: FastAPI service for workflow management
- **Frontend**: Svelte web application

## Prerequisites

Before deploying this template, ensure:

1. Argo Workflows is installed in your Kubernetes cluster in the `argo` namespace
2. You have `kubectl` access to configure RBAC and PVCs
3. Your cluster has sufficient resources

## Post-Deployment Steps

After deploying this template, you need to:

1. **Create PersistentVolume and PersistentVolumeClaim**:
   ```bash
   kubectl apply -f infrastructure/k8s/pv.yaml
   ```

2. **Configure RBAC**:
   ```bash
   kubectl apply -f infrastructure/k8s/rbac.yaml
   ```

3. **Update Backend ServiceAccount** (if backend is in a different namespace):
   - Find the Bunnyshell namespace: `kubectl get namespaces | grep argo-workflow-manager`
   - Create ServiceAccount in that namespace and update RoleBinding

For detailed instructions, see [BUNNYSHELL_DEPLOYMENT.md](../../../BUNNYSHELL_DEPLOYMENT.md) in the repository root.

## Configuration

### Environment Variables

- `CORS_ORIGINS`: Update to your frontend URL in production (default: `"*"`)
- `DATABASE_URL`: PostgreSQL connection string
- `ARGO_NAMESPACE`: Kubernetes namespace for Argo Workflows (default: `argo`)
- `VITE_API_URL`: Backend API URL for frontend

### Resources

Default resource allocations:
- PostgreSQL: 256Mi-512Mi memory, 250m-500m CPU
- Backend: 512Mi-1Gi memory, 500m-1000m CPU
- Frontend: 128Mi-256Mi memory, 100m-200m CPU

## Documentation

For more information, see:
- [BUNNYSHELL_DEPLOYMENT.md](../../../BUNNYSHELL_DEPLOYMENT.md) - Full deployment guide
- [README.md](../../../README.md) - Project overview
- [DEVOPS.md](../../../DEVOPS.md) - DevOps documentation

