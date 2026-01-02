# Deployment Checklist

Use this checklist to ensure all steps are completed for deploying the full stack to Bunnyshell.

## Pre-Deployment

- [ ] Kubernetes cluster (v1.24+) is available and accessible
- [ ] `kubectl` is configured and can access the cluster
- [ ] Cluster has sufficient resources (2+ CPU cores, 4GB+ memory)
- [ ] Bunnyshell account is created
- [ ] Git repository is accessible

## Phase 1: Infrastructure Setup

- [ ] Kubernetes cluster connected to Bunnyshell
- [ ] Git repository connected to Bunnyshell
- [ ] Cluster connection verified in Bunnyshell dashboard

## Phase 2: Argo Workflows Installation

- [ ] `argo` namespace created
- [ ] Argo Workflows installed (v3.5.0+)
- [ ] Argo Workflows pods are running
- [ ] Argo Workflows CRDs verified

## Phase 3: Kubernetes Resources

- [ ] PersistentVolume created (`task-results-pv`)
- [ ] PersistentVolumeClaim created and bound (`task-results-pvc` in `argo` namespace)
- [ ] ServiceAccount created (`backend-sa` in `argo` namespace)
- [ ] Role created (`argo-manager` in `argo` namespace)
- [ ] RoleBinding created (`backend-sa-binding` in `argo` namespace)
- [ ] RBAC permissions tested (optional)

## Phase 4: Application Deployment

- [ ] `bunnyshell.yaml` reviewed and updated
- [ ] Environment created in Bunnyshell
- [ ] Environment variables configured:
  - [ ] Backend: `DATABASE_URL`
  - [ ] Backend: `ARGO_NAMESPACE`
  - [ ] Backend: `WORKFLOW_MANIFEST_PATH`
  - [ ] Backend: `CORS_ORIGINS` (updated for production)
  - [ ] Frontend: `VITE_API_URL`
  - [ ] PostgreSQL: `POSTGRES_PASSWORD` (using secrets)
- [ ] Resource limits configured for all components
- [ ] Environment deployed successfully
- [ ] All components show "Running" status

## Phase 5: Integration

- [ ] Bunnyshell namespace identified
- [ ] ServiceAccount created in Bunnyshell namespace (or ClusterRoleBinding created)
- [ ] RoleBinding updated to reference correct namespace
- [ ] Backend deployment patched to use ServiceAccount
- [ ] Backend pod restarted
- [ ] ServiceAccount verified on backend pod
- [ ] Ingress/routing configured (if external access needed)
- [ ] CORS_ORIGINS updated to match frontend URL (if ingress configured)

## Phase 6: Verification

- [ ] All pods are running
- [ ] All services are created
- [ ] Backend health endpoint responds
- [ ] Backend can access Argo Workflows API
- [ ] Backend can list workflows in `argo` namespace
- [ ] PVC is accessible from backend
- [ ] Frontend loads correctly
- [ ] Frontend can communicate with backend
- [ ] Test workflow creation via frontend
- [ ] Workflow appears in Argo Workflows
- [ ] Resource usage is within limits

## Post-Deployment

- [ ] Monitoring configured
- [ ] Logging configured
- [ ] Backup strategy implemented
- [ ] Security settings reviewed
- [ ] Documentation updated
- [ ] Team notified of deployment

## Quick Verification Commands

```bash
# Set your namespace
export NS="<bunnyshell-namespace>"

# Check all components
kubectl get all -n $NS

# Check Argo Workflows
kubectl get workflows -n argo

# Check PVC
kubectl get pvc -n argo task-results-pvc

# Test backend
kubectl port-forward -n $NS svc/backend 8000:8000
curl http://localhost:8000/health

# Test frontend
kubectl port-forward -n $NS svc/frontend 8080:80
# Open http://localhost:8080 in browser
```

## Troubleshooting Checklist

If something isn't working:

- [ ] Check pod logs: `kubectl logs -n $NS deployment/<component>`
- [ ] Check pod status: `kubectl describe pod -n $NS <pod-name>`
- [ ] Verify environment variables: `kubectl get deployment -n $NS <component> -o yaml`
- [ ] Check ServiceAccount: `kubectl get deployment -n $NS backend -o yaml | grep serviceAccount`
- [ ] Verify RBAC: `kubectl get rolebinding -n argo backend-sa-binding -o yaml`
- [ ] Check PVC: `kubectl get pvc -n argo task-results-pvc`
- [ ] Verify Argo Workflows: `kubectl get pods -n argo`

