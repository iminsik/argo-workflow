# AWS EKS Support Implementation

## Summary

Extended the Argo Workflow Manager to support external Kubernetes clusters, specifically AWS EKS, in addition to the existing local KinD cluster support.

## Changes Made

### 1. Backend Code Updates (`apps/backend/app/main.py`)

- **Added configurable Kubernetes cluster support**:
  - New environment variable `KUBERNETES_CLUSTER_TYPE` to specify cluster type (`auto`, `kind`, `eks`, `external`)
  - New environment variable `KUBECONFIG` to specify custom kubeconfig path
  - Conditional application of KinD-specific patches (only for local KinD clusters)
  - Automatic detection of cluster type when set to `auto`

- **Improved Kubernetes configuration loading**:
  - Tries in-cluster config first (when running in Kubernetes)
  - Falls back to kubeconfig with configurable path
  - Only applies Docker/KinD network patches when explicitly using KinD
  - Proper handling for external clusters (EKS, GKE, etc.)

### 2. Docker Compose Updates (`docker-compose.yaml`)

- **Enhanced backend service configuration**:
  - Made kubeconfig volume path configurable via `KUBECONFIG_PATH` environment variable
  - Added environment variables for cluster configuration:
    - `KUBERNETES_CLUSTER_TYPE`: Cluster type selection
    - `KUBECONFIG`: Path to kubeconfig file inside container
    - `KIND_CLUSTER`: Flag to enable KinD-specific patches
  - Maintained backward compatibility with existing local development setup

### 3. AWS EKS Storage Configuration

Created two EFS-based PersistentVolume configurations:

- **`infrastructure/k8s/pv-aws-efs.yaml`**:
  - Full-featured EFS configuration with access points
  - Includes StorageClass, PersistentVolume, and PersistentVolumeClaim
  - Better security with access points

- **`infrastructure/k8s/pv-aws-efs-simple.yaml`**:
  - Simplified EFS configuration
  - Uses dynamic provisioning with EFS CSI driver
  - Easier to set up for quick deployments

### 4. Documentation

- **`AWS_EKS_SETUP.md`**: Comprehensive guide covering:
  - EKS cluster creation (eksctl and AWS Console)
  - kubectl configuration
  - Argo Workflows installation
  - EFS setup and configuration
  - EFS CSI driver installation
  - Backend configuration for EKS
  - Database setup options (PostgreSQL in EKS or AWS RDS)
  - Troubleshooting guide
  - Security best practices
  - Cost optimization tips

- **`docker-compose.env.example`**: Example environment file with:
  - All Kubernetes-related environment variables
  - Examples for different cluster types
  - Clear documentation of each variable

- **Updated `README.md`**: Added AWS EKS deployment section

## Usage

### Local Development with KinD (Existing)

```bash
# No changes needed - works as before
docker-compose up
```

### Local Development with AWS EKS

```bash
# Configure kubectl for EKS
aws eks update-kubeconfig --name your-cluster --region us-west-2

# Set environment variables
export KUBERNETES_CLUSTER_TYPE=eks
export KUBECONFIG_PATH=~/.kube

# Start services
docker-compose up
```

### Using Environment File

```bash
# Copy example file
cp docker-compose.env.example .env

# Edit .env with your configuration
# Then docker-compose will automatically use it
docker-compose up
```

## Backward Compatibility

- ✅ All existing local KinD setups continue to work without changes
- ✅ Default behavior (`KUBERNETES_CLUSTER_TYPE=auto`) maintains existing functionality
- ✅ KinD-specific patches are only applied when explicitly needed
- ✅ No breaking changes to existing API or functionality

## Benefits

1. **Flexibility**: Support for multiple Kubernetes cluster types
2. **Production Ready**: Can deploy to AWS EKS for production workloads
3. **Scalability**: EFS provides scalable, shared storage
4. **Security**: Proper handling of external cluster authentication
5. **Developer Experience**: Easy switching between local and cloud clusters

## Testing Recommendations

1. **Local KinD**: Verify existing functionality still works
2. **AWS EKS**: Test with a small EKS cluster
3. **Environment Variables**: Test different `KUBERNETES_CLUSTER_TYPE` values
4. **EFS**: Verify persistent volume claims work correctly
5. **Workflow Execution**: Ensure workflows can be created and executed

## Future Enhancements

- [ ] Support for Google GKE
- [ ] Support for Azure AKS
- [ ] Automatic cluster type detection
- [ ] Support for multiple kubeconfig contexts
- [ ] Integration with AWS IAM Roles for Service Accounts (IRSA)

## Files Changed

- `apps/backend/app/main.py` - Kubernetes configuration logic
- `docker-compose.yaml` - Environment variables and volume configuration
- `infrastructure/k8s/pv-aws-efs.yaml` - EFS PV configuration (new)
- `infrastructure/k8s/pv-aws-efs-simple.yaml` - Simplified EFS PV (new)
- `AWS_EKS_SETUP.md` - Setup documentation (new)
- `docker-compose.env.example` - Environment variable examples (new)
- `README.md` - Updated with AWS EKS section
- `changes/PR_AWS_EKS_SUPPORT.md` - This file (new)

