#!/bin/bash
# Helper script to configure ServiceAccount for backend after Bunnyshell deployment
# Usage: ./scripts/configure-serviceaccount.sh [namespace]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Backend ServiceAccount Configuration ===${NC}\n"

# Get namespace
if [ -z "$1" ]; then
    echo -e "${YELLOW}Finding Bunnyshell namespace...${NC}"
    NS=$(kubectl get namespaces -o name | grep -i argo-workflow-manager | sed 's/namespace\///' | head -n 1)
    
    if [ -z "$NS" ]; then
        echo -e "${RED}Error: Could not find Bunnyshell namespace${NC}"
        echo "Please provide the namespace as an argument:"
        echo "  ./scripts/configure-serviceaccount.sh <namespace>"
        echo ""
        echo "Available namespaces:"
        kubectl get namespaces
        exit 1
    fi
    
    echo -e "${GREEN}Found namespace: ${NS}${NC}\n"
else
    NS="$1"
    echo -e "${GREEN}Using namespace: ${NS}${NC}\n"
fi

# Verify namespace exists
if ! kubectl get namespace "$NS" > /dev/null 2>&1; then
    echo -e "${RED}Error: Namespace '$NS' does not exist${NC}"
    exit 1
fi

# Verify backend deployment exists
if ! kubectl get deployment backend -n "$NS" > /dev/null 2>&1; then
    echo -e "${RED}Error: Backend deployment not found in namespace '$NS'${NC}"
    exit 1
fi

# Verify RBAC resources exist
echo -e "${YELLOW}Checking RBAC resources...${NC}"
if ! kubectl get serviceaccount backend-sa -n argo > /dev/null 2>&1; then
    echo -e "${RED}Error: ServiceAccount 'backend-sa' not found in 'argo' namespace${NC}"
    echo "Please run: kubectl apply -f infrastructure/k8s/rbac.yaml"
    exit 1
fi

if ! kubectl get rolebinding backend-sa-binding -n argo > /dev/null 2>&1; then
    echo -e "${RED}Error: RoleBinding 'backend-sa-binding' not found in 'argo' namespace${NC}"
    echo "Please run: kubectl apply -f infrastructure/k8s/rbac.yaml"
    exit 1
fi

echo -e "${GREEN}✓ RBAC resources found${NC}\n"

# Step 1: Create ServiceAccount in Bunnyshell namespace
echo -e "${YELLOW}Step 1: Creating ServiceAccount in Bunnyshell namespace...${NC}"
if kubectl get serviceaccount backend-sa -n "$NS" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ ServiceAccount 'backend-sa' already exists in '$NS'${NC}"
else
    kubectl create serviceaccount backend-sa -n "$NS"
    echo -e "${GREEN}✓ ServiceAccount 'backend-sa' created in '$NS'${NC}"
fi

# Step 2: Update RoleBinding to reference ServiceAccount in Bunnyshell namespace
echo -e "\n${YELLOW}Step 2: Updating RoleBinding to reference ServiceAccount in '$NS'...${NC}"

# Check current RoleBinding
CURRENT_NS=$(kubectl get rolebinding backend-sa-binding -n argo -o jsonpath='{.subjects[0].namespace}' 2>/dev/null || echo "")

if [ "$CURRENT_NS" = "$NS" ]; then
    echo -e "${GREEN}✓ RoleBinding already references namespace '$NS'${NC}"
else
    # Update RoleBinding
    kubectl patch rolebinding backend-sa-binding -n argo --type='json' \
        -p="[{\"op\": \"replace\", \"path\": \"/subjects/0/namespace\", \"value\": \"$NS\"}]"
    echo -e "${GREEN}✓ RoleBinding updated to reference namespace '$NS'${NC}"
fi

# Step 3: Update backend deployment to use ServiceAccount
echo -e "\n${YELLOW}Step 3: Updating backend deployment to use ServiceAccount...${NC}"

CURRENT_SA=$(kubectl get deployment backend -n "$NS" -o jsonpath='{.spec.template.spec.serviceAccountName}' 2>/dev/null || echo "")

if [ "$CURRENT_SA" = "backend-sa" ]; then
    echo -e "${GREEN}✓ Backend deployment already uses ServiceAccount 'backend-sa'${NC}"
else
    kubectl patch deployment backend -n "$NS" \
        -p '{"spec":{"template":{"spec":{"serviceAccountName":"backend-sa"}}}}'
    echo -e "${GREEN}✓ Backend deployment updated to use ServiceAccount 'backend-sa'${NC}"
fi

# Step 4: Restart backend pod
echo -e "\n${YELLOW}Step 4: Restarting backend pod...${NC}"
kubectl rollout restart deployment/backend -n "$NS"
echo -e "${GREEN}✓ Backend deployment restarted${NC}"

# Step 5: Wait for rollout
echo -e "\n${YELLOW}Step 5: Waiting for rollout to complete...${NC}"
kubectl rollout status deployment/backend -n "$NS" --timeout=120s
echo -e "${GREEN}✓ Rollout completed${NC}"

# Step 6: Verify configuration
echo -e "\n${YELLOW}Step 6: Verifying configuration...${NC}"

# Check ServiceAccount
SA_CHECK=$(kubectl get deployment backend -n "$NS" -o jsonpath='{.spec.template.spec.serviceAccountName}')
if [ "$SA_CHECK" = "backend-sa" ]; then
    echo -e "${GREEN}✓ ServiceAccount configured correctly${NC}"
else
    echo -e "${RED}✗ ServiceAccount not configured correctly${NC}"
    exit 1
fi

# Check pod ServiceAccount
POD_SA=$(kubectl get pod -n "$NS" -l app=backend -o jsonpath='{.items[0].spec.serviceAccountName}' 2>/dev/null || echo "")
if [ "$POD_SA" = "backend-sa" ]; then
    echo -e "${GREEN}✓ Pod is using correct ServiceAccount${NC}"
else
    echo -e "${YELLOW}⚠ Pod ServiceAccount check: $POD_SA${NC}"
    echo "   (This may be normal if pod hasn't restarted yet)"
fi

# Summary
echo -e "\n${GREEN}=== Configuration Complete ===${NC}"
echo -e "Namespace: ${NS}"
echo -e "ServiceAccount: backend-sa"
echo -e "RoleBinding: backend-sa-binding (in 'argo' namespace)"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Verify backend can access Argo Workflows:"
echo "   kubectl exec -n $NS deployment/backend -- python -c \"from kubernetes import config; from kubernetes.client import CustomObjectsApi; config.load_incluster_config(); api = CustomObjectsApi(); workflows = api.list_namespaced_custom_object('argoproj.io', 'v1alpha1', 'argo', 'workflows'); print(f'Found {len(workflows.get(\\\"items\\\", []))} workflows')\""
echo ""
echo "2. Check backend logs:"
echo "   kubectl logs -n $NS deployment/backend -f"
echo ""
echo "3. Test workflow creation via API (if port-forward is set up):"
echo "   kubectl port-forward -n $NS svc/backend 8000:8000"
echo "   curl -X POST http://localhost:8000/api/v1/tasks/submit -H 'Content-Type: application/json' -d '{\"pythonCode\": \"print(\\\"test\\\")\"}'"

