# DevOps Guide

This guide is for DevOps engineers deploying and managing the Argo Workflow Manager infrastructure.

## Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured with cluster admin access
- Docker for building images
- Argo Workflows v3.5.0+ installed in cluster

## Infrastructure Overview

### Components

1. **Kubernetes Cluster**: Hosts Argo Workflows and application services
2. **Argo Workflows**: Workflow orchestration engine
3. **Backend Service**: FastAPI service for workflow management
4. **Frontend Service**: React web application
5. **PostgreSQL**: Database (optional, for future use)

### Architecture

```
┌─────────────────────────────────────────┐
│         Kubernetes Cluster              │
│                                         │
│  ┌──────────────┐  ┌──────────────┐   │
│  │   Frontend   │  │   Backend    │   │
│  │   (React)    │──│  (FastAPI)   │   │
│  └──────────────┘  └──────┬───────┘   │
│                            │            │
│  ┌─────────────────────────▼──────┐   │
│  │      Argo Workflows             │   │
│  │  ┌──────────┐  ┌──────────────┐ │   │
│  │  │Controller│  │   Server     │ │   │
│  │  └──────────┘  └──────────────┘ │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## Deployment Steps

### 1. Set Up Kubernetes Cluster

#### Using Kind (Local Development)

```bash
make cluster-up
```

This creates:
- Kind cluster named `argo-dev`
- Argo Workflows installed in `argo` namespace
- RBAC permissions configured

#### Using Existing Cluster

Ensure Argo Workflows is installed:

```bash
kubectl create namespace argo
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
```

### 2. Configure RBAC

Apply RBAC configuration:

```bash
kubectl apply -f infrastructure/k8s/rbac.yaml
```

This creates:
- ServiceAccount: `backend-sa` in `argo` namespace
- Role: `argo-manager` with workflow permissions
- RoleBinding: Links service account to role

### 3. Build and Push Docker Images

#### Backend Image

```bash
cd apps/backend
docker build -f Dockerfile.dev -t argo-workflow-manager-backend:latest .
# Tag and push to your registry
docker tag argo-workflow-manager-backend:latest <registry>/argo-workflow-manager-backend:latest
docker push <registry>/argo-workflow-manager-backend:latest
```

#### Frontend Image

```bash
cd apps/frontend
docker build -f Dockerfile.dev -t argo-workflow-manager-frontend:latest .
# Tag and push to your registry
docker tag argo-workflow-manager-frontend:latest <registry>/argo-workflow-manager-frontend:latest
docker push <registry>/argo-workflow-manager-frontend:latest
```

### 4. Deploy Application

#### Option A: Using Docker Compose (Development)

```bash
make dev-up
```

#### Option B: Kubernetes Manifests (Production)

Create Kubernetes deployment manifests:

```yaml
# backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: argo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      serviceAccountName: backend-sa
      containers:
      - name: backend
        image: <registry>/argo-workflow-manager-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: ARGO_NAMESPACE
          value: "argo"
        - name: WORKFLOW_MANIFEST_PATH
          value: "/infrastructure/argo/python-processor.yaml"
        volumeMounts:
        - name: infrastructure
          mountPath: /infrastructure
          readOnly: true
      volumes:
      - name: infrastructure
        configMap:
          name: workflow-manifests
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: argo
spec:
  selector:
    app: backend
  ports:
  - port: 80
    targetPort: 8000
```

## Configuration

### Environment Variables

#### Backend

- `ARGO_NAMESPACE`: Namespace for workflows (default: `argo`)
- `WORKFLOW_MANIFEST_PATH`: Path to workflow YAML file
- `KUBECONFIG`: Path to kubeconfig (if not using in-cluster config)

#### Frontend

- `VITE_API_URL`: Backend API URL

### Argo Workflows Configuration

The workflow controller runs in `--namespaced` mode, meaning it only watches the `argo` namespace. All workflows must be created in this namespace.

To change this behavior, modify the workflow controller deployment:

```bash
kubectl edit deployment workflow-controller -n argo
# Remove the --namespaced flag
```

## Monitoring

### Health Checks

#### Backend Health

```bash
curl http://localhost:8000/health  # If health endpoint exists
```

#### Frontend Health

```bash
curl http://localhost:5173
```

### Logs

#### Application Logs

```bash
# Backend logs
kubectl logs -n argo -l app=backend -f

# Frontend logs
kubectl logs -n argo -l app=frontend -f
```

#### Argo Workflows Logs

```bash
# Workflow controller
kubectl logs -n argo -l app=workflow-controller -f

# Argo server
kubectl logs -n argo -l app=argo-server -f
```

### Metrics

Argo Workflows exposes metrics on port 9090:

```bash
kubectl port-forward -n argo svc/workflow-controller-metrics 9090:9090
curl http://localhost:9090/metrics
```

## Troubleshooting

### Workflows Not Processing

**Symptoms**: Workflows stay in "Pending" status

**Diagnosis**:
```bash
# Check workflow controller
kubectl get pods -n argo | grep workflow-controller

# Check controller logs
kubectl logs -n argo -l app=workflow-controller --tail=50

# Verify namespace
kubectl get workflows -n argo
```

**Solutions**:
1. Ensure workflows are in `argo` namespace (if controller is namespaced)
2. Check RBAC permissions
3. Verify workflow controller is running
4. Check for resource constraints

### Backend Can't Connect to Kubernetes

**Symptoms**: Backend errors when creating workflows

**Diagnosis**:
```bash
# Check backend logs
kubectl logs -n argo -l app=backend

# Test Kubernetes connection from backend pod
kubectl exec -n argo <backend-pod> -- kubectl get workflows
```

**Solutions**:
1. Verify ServiceAccount has correct permissions
2. Check RBAC RoleBinding
3. Ensure backend uses in-cluster config (not kubeconfig)
4. Verify network policies allow API server access

### CORS Issues

**Symptoms**: Frontend can't call backend API

**Solutions**:
1. Verify CORS middleware is configured in backend
2. Check `allow_origins` includes frontend URL
3. Verify backend is accessible from frontend

### Resource Constraints

**Symptoms**: Workflows fail to start or are evicted

**Diagnosis**:
```bash
# Check node resources
kubectl top nodes

# Check pod resources
kubectl top pods -n argo

# Check events
kubectl get events -n argo --sort-by='.lastTimestamp'
```

**Solutions**:
1. Increase cluster resources
2. Adjust workflow resource requests/limits
3. Configure resource quotas

## Security Considerations

### RBAC

- ServiceAccount should have minimal required permissions
- Use Role (not ClusterRole) for namespace-scoped access
- Regularly audit permissions

### Network Policies

Consider implementing network policies to restrict traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
  namespace: argo
spec:
  podSelector:
    matchLabels:
      app: backend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: frontend
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: TCP
      port: 443
```

### Secrets Management

- Store sensitive data in Kubernetes Secrets
- Use external secret management (e.g., Vault) for production
- Never commit secrets to repository

## Backup and Recovery

### Workflow Data

Argo Workflows stores workflow state in etcd. Backup etcd regularly:

```bash
# Backup etcd (example for etcd operator)
kubectl exec -n kube-system etcd-<pod> -- etcdctl backup ...
```

### Configuration

Backup Kubernetes manifests:

```bash
kubectl get all -n argo -o yaml > argo-backup.yaml
kubectl get workflows -n argo -o yaml > workflows-backup.yaml
```

## Scaling

### Horizontal Scaling

#### Backend

```bash
kubectl scale deployment backend -n argo --replicas=3
```

#### Frontend

```bash
kubectl scale deployment frontend -n argo --replicas=2
```

### Workflow Controller

The workflow controller can handle multiple workflows concurrently. Monitor:

- Workflow queue length
- Controller CPU/memory usage
- Workflow processing time

## Maintenance

### Upgrading Argo Workflows

1. Check release notes for breaking changes
2. Backup current workflows
3. Update Argo Workflows manifests
4. Test in staging environment
5. Apply to production

### Cleanup

Remove old workflows:

```bash
# Delete completed workflows older than 1 day
kubectl delete workflows -n argo --field-selector status.phase=Succeeded --older-than=24h
```

## Production Checklist

- [ ] RBAC properly configured
- [ ] Network policies implemented
- [ ] Secrets properly managed
- [ ] Monitoring and alerting configured
- [ ] Backup strategy in place
- [ ] Resource limits configured
- [ ] Health checks implemented
- [ ] Logging configured
- [ ] SSL/TLS enabled
- [ ] Documentation updated

## Resources

- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/security/)
- [Argo Workflows GitHub](https://github.com/argoproj/argo-workflows)

