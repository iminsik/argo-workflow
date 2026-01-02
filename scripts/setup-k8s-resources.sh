#!/bin/bash
# Helper script to set up required Kubernetes resources before Bunnyshell deployment
# This script creates:
# - Argo Workflows namespace and installation
# - PersistentVolume and PersistentVolumeClaim
# - RBAC configuration (ServiceAccount, Role, RoleBinding)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Kubernetes Resources Setup ===${NC}\n"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed or not in PATH${NC}"
    exit 1
fi

# Check cluster connection
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
    echo "Please configure kubectl to access your cluster"
    exit 1
fi

echo -e "${GREEN}✓ Connected to Kubernetes cluster${NC}\n"

# Step 1: Create Argo namespace
echo -e "${YELLOW}Step 1: Creating 'argo' namespace...${NC}"
if kubectl get namespace argo &> /dev/null; then
    echo -e "${GREEN}✓ Namespace 'argo' already exists${NC}"
else
    kubectl create namespace argo
    echo -e "${GREEN}✓ Namespace 'argo' created${NC}"
fi

# Step 2: Install Argo Workflows
echo -e "\n${YELLOW}Step 2: Installing Argo Workflows...${NC}"
if kubectl get deployment workflow-controller -n argo &> /dev/null; then
    echo -e "${GREEN}✓ Argo Workflows already installed${NC}"
else
    echo -e "${BLUE}Installing Argo Workflows (minimal installation)...${NC}"
    kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
    
    echo -e "${BLUE}Waiting for Argo Workflows to be ready...${NC}"
    kubectl wait --for=condition=ready pod -l app=workflow-controller -n argo --timeout=300s || {
        echo -e "${YELLOW}⚠ Argo Workflows installation may still be in progress${NC}"
        echo "   You can check status with: kubectl get pods -n argo"
    }
    echo -e "${GREEN}✓ Argo Workflows installed${NC}"
fi

# Step 3: Create PersistentVolume and PersistentVolumeClaim
echo -e "\n${YELLOW}Step 3: Creating PersistentVolume and PersistentVolumeClaim...${NC}"

PV_YAML="infrastructure/k8s/pv.yaml"
if [ ! -f "$PV_YAML" ]; then
    echo -e "${RED}Error: $PV_YAML not found${NC}"
    exit 1
fi

# Check if PV exists
if kubectl get pv task-results-pv &> /dev/null; then
    echo -e "${GREEN}✓ PersistentVolume 'task-results-pv' already exists${NC}"
else
    kubectl apply -f "$PV_YAML"
    echo -e "${GREEN}✓ PersistentVolume and PersistentVolumeClaim created${NC}"
fi

# Check PVC status
echo -e "\n${BLUE}Checking PVC status...${NC}"
PVC_STATUS=$(kubectl get pvc -n argo task-results-pvc -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")

if [ "$PVC_STATUS" = "Bound" ]; then
    echo -e "${GREEN}✓ PersistentVolumeClaim is bound${NC}"
elif [ "$PVC_STATUS" = "Pending" ]; then
    echo -e "${YELLOW}⚠ PersistentVolumeClaim is pending${NC}"
    echo "   This may be normal. Check with: kubectl get pvc -n argo task-results-pvc"
elif [ "$PVC_STATUS" = "NotFound" ]; then
    echo -e "${YELLOW}⚠ PersistentVolumeClaim not found, applying again...${NC}"
    kubectl apply -f "$PV_YAML"
else
    echo -e "${YELLOW}⚠ PersistentVolumeClaim status: $PVC_STATUS${NC}"
fi

# Step 4: Create RBAC configuration
echo -e "\n${YELLOW}Step 4: Creating RBAC configuration...${NC}"

RBAC_YAML="infrastructure/k8s/rbac.yaml"
if [ ! -f "$RBAC_YAML" ]; then
    echo -e "${RED}Error: $RBAC_YAML not found${NC}"
    exit 1
fi

kubectl apply -f "$RBAC_YAML"
echo -e "${GREEN}✓ RBAC configuration applied${NC}"

# Verify RBAC resources
echo -e "\n${BLUE}Verifying RBAC resources...${NC}"

if kubectl get serviceaccount backend-sa -n argo &> /dev/null; then
    echo -e "${GREEN}✓ ServiceAccount 'backend-sa' exists${NC}"
else
    echo -e "${RED}✗ ServiceAccount 'backend-sa' not found${NC}"
fi

if kubectl get role argo-manager -n argo &> /dev/null; then
    echo -e "${GREEN}✓ Role 'argo-manager' exists${NC}"
else
    echo -e "${RED}✗ Role 'argo-manager' not found${NC}"
fi

if kubectl get rolebinding backend-sa-binding -n argo &> /dev/null; then
    echo -e "${GREEN}✓ RoleBinding 'backend-sa-binding' exists${NC}"
else
    echo -e "${RED}✗ RoleBinding 'backend-sa-binding' not found${NC}"
fi

# Summary
echo -e "\n${GREEN}=== Setup Complete ===${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo "  ✓ Argo namespace created"
echo "  ✓ Argo Workflows installed"
echo "  ✓ PersistentVolume and PersistentVolumeClaim created"
echo "  ✓ RBAC configuration applied"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Deploy your application via Bunnyshell using bunnyshell.yaml"
echo "2. After deployment, run: ./scripts/configure-serviceaccount.sh"
echo ""
echo -e "${BLUE}Verification commands:${NC}"
echo "  kubectl get pods -n argo"
echo "  kubectl get pvc -n argo task-results-pvc"
echo "  kubectl get serviceaccount -n argo backend-sa"
echo "  kubectl get rolebinding -n argo backend-sa-binding"

