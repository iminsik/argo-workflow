# Deployment Strategy Summary

## Best Strategy for Deploying Full Stack to Bunnyshell

### Recommended Approach: Phased Deployment

The best strategy is to deploy in **6 phases** to ensure each component is properly configured before moving to the next:

1. **Prerequisites & Infrastructure** → Set up cluster and repository connections
2. **Argo Workflows Installation** → Install Argo Workflows in the cluster
3. **Kubernetes Resources** → Create RBAC, PVCs, and ServiceAccounts
4. **Application Deployment** → Deploy via Bunnyshell (Database, Backend, Frontend)
5. **Integration** → Connect components and configure cross-namespace access
6. **Verification** → Test and validate the complete stack

### Why This Approach?

- **Isolation**: Each phase can be verified independently
- **Dependency Management**: Prerequisites are met before dependent components
- **Troubleshooting**: Easier to identify issues at each phase
- **Rollback**: Can rollback individual phases if needed

---

## Key Configuration Considerations

### 1. Current `bunnyshell.yaml` Format

Your current `bunnyshell.yaml` uses the format:
```yaml
components:
  - name: postgres
    type: postgresql
    image: postgres:15-alpine
```

**Note**: Bunnyshell supports multiple formats. Your current format should work, but you may want to consider adding:
- ServiceAccount configuration for backend (currently missing)
- Host/routing configuration for external access (optional)

### 2. ServiceAccount Configuration

**Current Issue**: The `bunnyshell.yaml` doesn't specify the ServiceAccount for the backend component. This needs to be configured manually after deployment.

**Recommendation**: You can either:
- **Option A**: Add it to `bunnyshell.yaml` (if your Bunnyshell version supports `pod.serviceAccountName`)
- **Option B**: Configure it manually after deployment (as documented in Phase 5)

### 3. Namespace Strategy

**Important**: Bunnyshell creates its own namespace for your environment, but Argo Workflows runs in the `argo` namespace. This requires:
- Cross-namespace RBAC configuration
- ServiceAccount in Bunnyshell namespace with permissions in `argo` namespace

---

## Quick Start Guide

### For First-Time Deployment:

1. **Follow the checklist**: Use `DEPLOYMENT_CHECKLIST.md` to track progress
2. **Read the strategy**: Review `DEPLOYMENT_STRATEGY.md` for detailed steps
3. **Execute phases sequentially**: Don't skip phases
4. **Verify each phase**: Ensure each phase is complete before proceeding

### For Experienced Users (Using CLI + Helper Scripts):

```bash
# 1. Set up Kubernetes resources (Argo Workflows, RBAC, PVC)
./scripts/setup-k8s-resources.sh

# 2. Deploy via Bunnyshell CLI
bns environments create \
  --name argo-workflow-manager \
  --cluster-id <cluster-id> \
  --repository-id <repository-id> \
  --branch main \
  --config-file bunnyshell.yaml

bns environments deploy --id <environment-id>

# 3. Configure ServiceAccount (after deployment)
./scripts/configure-serviceaccount.sh
```

**Or use the UI:**
```bash
# 1. Set up Kubernetes resources
./scripts/setup-k8s-resources.sh

# 2. Deploy via Bunnyshell UI
# - Connect cluster and repository
# - Create environment from bunnyshell.yaml
# - Configure environment variables
# - Deploy

# 3. Configure ServiceAccount (after deployment)
./scripts/configure-serviceaccount.sh
```

### For Experienced Users (Manual Steps):

```bash
# 1. Install Argo Workflows
kubectl create namespace argo
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml

# 2. Create Kubernetes resources
kubectl apply -f infrastructure/k8s/pv.yaml
kubectl apply -f infrastructure/k8s/rbac.yaml

# 3. Deploy via Bunnyshell UI
# - Connect cluster and repository
# - Create environment from bunnyshell.yaml
# - Configure environment variables
# - Deploy

# 4. Configure ServiceAccount (after deployment)
export NS="<bunnyshell-namespace>"
kubectl create serviceaccount backend-sa -n $NS
kubectl patch rolebinding backend-sa-binding -n argo --type='json' \
  -p='[{"op": "replace", "path": "/subjects/0/namespace", "value": "'$NS'"}]'
kubectl patch deployment backend -n $NS \
  -p '{"spec":{"template":{"spec":{"serviceAccountName":"backend-sa"}}}}'
kubectl rollout restart deployment/backend -n $NS
```

---

## Configuration Recommendations

### Update `bunnyshell.yaml` (Optional Improvements)

If you want to add ServiceAccount support directly in the YAML (if your Bunnyshell version supports it):

```yaml
  # Backend API Service
  - name: backend
    type: application
    build:
      context: .
      dockerfile: ./apps/backend/Dockerfile
    # Add this if supported:
    # pod:
    #   serviceAccountName: backend-sa
    environmentVariables:
      # ... existing vars ...
```

**Note**: Test if your Bunnyshell version supports `pod.serviceAccountName` in the component definition. If not, use the manual configuration approach (Phase 5).

### Environment Variables Best Practices

1. **Use Bunnyshell Secrets** for:
   - `POSTGRES_PASSWORD`
   - Any API keys or tokens

2. **Update for Production**:
   - `CORS_ORIGINS`: Change from `"*"` to specific domain(s)
   - `VITE_API_URL`: Update if using external ingress

3. **Keep Internal URLs** for:
   - `DATABASE_URL`: Use service name `postgres:5432`
   - Internal service communication

---

## Common Pitfalls to Avoid

1. **Skipping Argo Workflows Installation**: The backend requires Argo Workflows to be installed first
2. **Missing RBAC Configuration**: Backend won't be able to create workflows without proper permissions
3. **PVC Not Created**: Workflows will fail if `task-results-pvc` doesn't exist
4. **Wrong Namespace for ServiceAccount**: ServiceAccount must be in the same namespace as the backend pod
5. **CORS Misconfiguration**: Frontend won't be able to call backend if CORS is misconfigured

---

## Expected Timeline

- **Phase 1-2**: 15-30 minutes (cluster setup, Argo installation)
- **Phase 3**: 5-10 minutes (K8s resources)
- **Phase 4**: 10-15 minutes (Bunnyshell deployment)
- **Phase 5**: 5-10 minutes (integration)
- **Phase 6**: 10-15 minutes (verification)

**Total**: ~45-80 minutes for first-time deployment

---

## Next Steps After Deployment

1. ✅ Set up monitoring and alerting
2. ✅ Configure automated backups
3. ✅ Implement CI/CD pipeline
4. ✅ Set up staging environment
5. ✅ Document runbooks
6. ✅ Train team on operations

---

## Helper Scripts

Automation scripts are available in the `scripts/` directory:

- **`scripts/setup-k8s-resources.sh`**: Automates Phases 2-3 (Argo installation, RBAC, PVC)
- **`scripts/configure-serviceaccount.sh`**: Automates Phase 5 (ServiceAccount configuration)

See `scripts/README.md` for detailed usage instructions.

## Documentation Files

- **`DEPLOYMENT_STRATEGY.md`**: Comprehensive step-by-step guide
- **`DEPLOYMENT_CHECKLIST.md`**: Quick checklist for tracking progress
- **`BUNNYSHELL_DEPLOYMENT.md`**: Original deployment guide (UI-based)
- **`BUNNYSHELL_CLI_DEPLOYMENT.md`**: CLI-based deployment guide
- **`DEPLOYMENT_SUMMARY.md`**: This file - quick overview
- **`scripts/README.md`**: Helper scripts documentation

---

## Getting Help

If you encounter issues:

1. Check the **Troubleshooting Guide** in `DEPLOYMENT_STRATEGY.md`
2. Review component logs in Bunnyshell UI
3. Verify each phase was completed correctly
4. Check the checklist to ensure nothing was missed

For Bunnyshell-specific issues, refer to: https://documentation.bunnyshell.com/

