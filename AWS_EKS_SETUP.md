# AWS EKS Setup Guide

This guide explains how to deploy the Argo Workflow Manager to an AWS EKS (Elastic Kubernetes Service) cluster.

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured (`aws configure`)
3. **kubectl** installed
4. **eksctl** (recommended) or AWS Console access for cluster creation
5. **Docker** and **docker-compose** for local development

## Step 1: Create EKS Cluster

### Option A: Using eksctl (Recommended)

```bash
# Install eksctl if not already installed
# macOS: brew install eksctl
# Linux: https://github.com/weaveworks/eksctl#installation

# Create EKS cluster
eksctl create cluster \
  --name argo-workflow-cluster \
  --region us-west-2 \
  --node-type t3.medium \
  --nodes 2 \
  --nodes-min 1 \
  --nodes-max 3 \
  --managed

# This will take 15-20 minutes
```

### Option B: Using AWS Console

1. Go to AWS Console → EKS → Clusters
2. Click "Create cluster"
3. Configure:
   - Name: `argo-workflow-cluster`
   - Kubernetes version: Latest stable
   - Node group: Choose instance type (t3.medium recommended)
   - Node count: 2-3 nodes
4. Click "Create"

## Step 2: Configure kubectl

After cluster creation, configure kubectl to access your cluster:

```bash
# Update kubeconfig (eksctl does this automatically)
aws eks update-kubeconfig --name argo-workflow-cluster --region us-west-2

# Verify connection
kubectl get nodes
```

## Step 3: Install Argo Workflows

```bash
# Create argo namespace
kubectl create namespace argo

# Install Argo Workflows
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/install.yaml

# Wait for Argo Workflows to be ready
kubectl wait --for=condition=ready pod -l app=workflow-controller -n argo --timeout=300s
kubectl wait --for=condition=ready pod -l app=argo-server -n argo --timeout=300s
```

## Step 4: Set Up EFS (Elastic File System)

EFS is required for persistent storage that supports ReadWriteMany access mode.

### 4.1 Create EFS File System

```bash
# Get your VPC ID and subnet IDs
VPC_ID=$(aws eks describe-cluster --name argo-workflow-cluster --region us-west-2 --query "cluster.resourcesVpcConfig.vpcId" --output text)
SUBNET_IDS=$(aws eks describe-cluster --name argo-workflow-cluster --region us-west-2 --query "cluster.resourcesVpcConfig.subnetIds" --output text)

# Create security group for EFS
SG_ID=$(aws ec2 create-security-group \
  --group-name argo-efs-sg \
  --description "Security group for EFS" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

# Allow NFS traffic from EKS nodes
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 2049 \
  --source-group $(aws eks describe-cluster --name argo-workflow-cluster --region us-west-2 --query "cluster.resourcesVpcConfig.clusterSecurityGroupId" --output text)

# Create EFS file system
EFS_ID=$(aws efs create-file-system \
  --creation-token argo-workflow-pv \
  --performance-mode generalPurpose \
  --throughput-mode provisioned \
  --provisioned-throughput-in-mibps 100 \
  --tags Key=Name,Value=argo-workflow-pv \
  --query 'FileSystemId' \
  --output text)

echo "EFS File System ID: $EFS_ID"
```

### 4.2 Create Mount Targets

```bash
# Get subnet IDs as array
SUBNET_1=$(echo $SUBNET_IDS | cut -d' ' -f1)
SUBNET_2=$(echo $SUBNET_IDS | cut -d' ' -f2)

# Create mount targets in each subnet
aws efs create-mount-target \
  --file-system-id $EFS_ID \
  --subnet-id $SUBNET_1 \
  --security-groups $SG_ID

aws efs create-mount-target \
  --file-system-id $EFS_ID \
  --subnet-id $SUBNET_2 \
  --security-groups $SG_ID
```

### 4.3 Install EFS CSI Driver

```bash
# Add EFS CSI driver Helm chart
helm repo add aws-efs-csi-driver https://kubernetes-sigs.github.io/aws-efs-csi-driver/
helm repo update

# Install EFS CSI driver
helm upgrade -i aws-efs-csi-driver aws-efs-csi-driver/aws-efs-csi-driver \
  --namespace kube-system \
  --set controller.serviceAccount.create=false

# Create IAM role for EFS CSI driver (if using IRSA)
# See: https://docs.aws.amazon.com/eks/latest/userguide/efs-csi.html
```

### 4.4 Configure PersistentVolume

Edit `infrastructure/k8s/pv-aws-efs-simple.yaml` and replace `<EFS_FILE_SYSTEM_ID>` with your EFS ID:

```bash
# Replace EFS_ID in the file
sed -i.bak "s/<EFS_FILE_SYSTEM_ID>/$EFS_ID/g" infrastructure/k8s/pv-aws-efs-simple.yaml

# Apply the configuration
kubectl apply -f infrastructure/k8s/pv-aws-efs-simple.yaml

# Verify PVC is bound
kubectl get pvc -n argo task-results-pvc
```

**Important**: The Persistent Volume File Manager feature requires:
- The PVC `task-results-pvc` to exist in the `argo` namespace
- The PVC must be bound to a PV with `ReadWriteMany` access mode (EFS supports this)
- The backend will automatically create a persistent pod that mounts this PVC for file operations

## Step 5: Set Up RBAC

```bash
# Apply RBAC configuration
kubectl apply -f infrastructure/k8s/rbac.yaml
```

## Step 6: Configure Backend for EKS

### Option A: Using docker-compose (Local Development)

1. **Get your kubeconfig**:
   ```bash
   # Your kubeconfig is at ~/.kube/config after running aws eks update-kubeconfig
   ```

2. **Set environment variables**:
   ```bash
   export KUBERNETES_CLUSTER_TYPE=eks
   export KUBECONFIG_PATH=~/.kube
   ```

3. **Start services**:
   ```bash
   docker-compose up
   ```

### Option B: Deploy to EKS Cluster

1. **Build and push Docker images**:
   ```bash
   # Set your ECR repository URL
   export ECR_REPO=123456789012.dkr.ecr.us-west-2.amazonaws.com/argo-workflow

   # Build and push backend
   docker build -t $ECR_REPO/backend:latest ./apps/backend
   aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin $ECR_REPO
   docker push $ECR_REPO/backend:latest

   # Build and push frontend
   docker build -t $ECR_REPO/frontend:latest ./apps/frontend
   docker push $ECR_REPO/frontend:latest
   ```

2. **Create deployment manifests** (see `DEVOPS.md` for examples)

3. **Deploy**:
   ```bash
   kubectl apply -f k8s-deployments/
   ```

## Step 7: Configure Database

### Option A: Deploy PostgreSQL in EKS

```bash
# Deploy PostgreSQL using Helm
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql \
  --set auth.postgresPassword=password \
  --set auth.database=postgres \
  --namespace argo
```

### Option B: Use AWS RDS

1. Create RDS PostgreSQL instance in AWS Console
2. Update `DATABASE_URL` environment variable in backend deployment
3. Ensure EKS nodes can access RDS (security groups, VPC configuration)

## Step 8: Verify Deployment

```bash
# Check pods
kubectl get pods -n argo

# Check services
kubectl get svc -n argo

# Check persistent volumes
kubectl get pv
kubectl get pvc -n argo

# Test backend connection
kubectl port-forward -n argo svc/backend 8000:8000
curl http://localhost:8000/health
```

## Step 9: Access Argo Workflows UI

```bash
# Port forward to Argo Server
kubectl port-forward -n argo svc/argo-server 2746:2746

# Access UI at http://localhost:2746
```

## Environment Variables Reference

### Backend Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `KUBERNETES_CLUSTER_TYPE` | Cluster type: `auto`, `kind`, `eks`, `external` | `auto` | `eks` |
| `KUBECONFIG` | Path to kubeconfig file | `~/.kube/config` | `/root/.kube/config` |
| `KIND_CLUSTER` | Set to `true` if using local KinD | `false` | `false` |
| `ARGO_NAMESPACE` | Kubernetes namespace for Argo Workflows | `argo` | `argo` |
| `DATABASE_URL` | PostgreSQL connection string | - | `postgresql://user:pass@host:5432/db` |

### Docker Compose Environment Variables

Set these in your shell or `.env` file:

```bash
# For AWS EKS
export KUBERNETES_CLUSTER_TYPE=eks
export KUBECONFIG_PATH=~/.kube

# For local KinD
export KUBERNETES_CLUSTER_TYPE=kind
export KIND_CLUSTER=true
```

## Troubleshooting

### Backend Can't Connect to Kubernetes

1. **Check kubeconfig**:
   ```bash
   kubectl config view
   kubectl get nodes
   ```

2. **Verify kubeconfig is mounted**:
   ```bash
   docker-compose exec backend ls -la /root/.kube/
   ```

3. **Check environment variables**:
   ```bash
   docker-compose exec backend env | grep KUBERNETES
   ```

### PersistentVolume Issues

1. **Check EFS CSI driver**:
   ```bash
   kubectl get pods -n kube-system | grep efs
   ```

2. **Verify EFS mount targets**:
   ```bash
   aws efs describe-mount-targets --file-system-id $EFS_ID
   ```

3. **Check PV/PVC status**:
   ```bash
   kubectl describe pv task-results-pv-efs
   kubectl describe pvc task-results-pvc -n argo
   ```

4. **Verify PVC is bound** (required for Persistent Volume File Manager):
   ```bash
   kubectl get pvc -n argo task-results-pvc
   # Should show STATUS: Bound
   ```

5. **Check persistent PV pod** (created by backend for file operations):
   ```bash
   kubectl get pods -n argo | grep pv-persistent
   kubectl logs -n argo <pv-persistent-pod-name>
   ```

### Network Issues

1. **Check security groups** allow traffic between:
   - EKS nodes and EFS
   - EKS nodes and RDS (if using RDS)
   - Your IP and EKS API server

2. **Verify VPC configuration**:
   ```bash
   aws eks describe-cluster --name argo-workflow-cluster --query "cluster.resourcesVpcConfig"
   ```

## Security Best Practices

1. **Use IAM Roles for Service Accounts (IRSA)** for EFS CSI driver
2. **Enable encryption at rest** for EFS
3. **Use RDS with encryption** for database
4. **Restrict security groups** to minimum required access
5. **Use AWS Secrets Manager** for sensitive configuration
6. **Enable VPC Flow Logs** for network monitoring

## Cost Optimization

1. **Use spot instances** for non-production workloads
2. **Enable cluster autoscaling** to scale down during idle periods
3. **Use EFS Infrequent Access** storage class for old data
4. **Monitor CloudWatch** for unused resources

## Additional Resources

- [EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/)
- [EFS CSI Driver](https://github.com/kubernetes-sigs/aws-efs-csi-driver)
- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [EKS Best Practices](https://aws.github.io/aws-eks-best-practices/)

