#!/bin/bash
# Quick test script for Hera SDK integration

set -e

API_URL="${API_URL:-http://localhost:8000}"
NAMESPACE="${ARGO_NAMESPACE:-argo}"

echo "=========================================="
echo "Quick Test: Hera SDK Integration"
echo "=========================================="
echo "API URL: $API_URL"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if backend is running
echo -e "${BLUE}Checking if backend is running...${NC}"
if ! curl -s "$API_URL/health" > /dev/null 2>&1 && ! curl -s "$API_URL/api/v1/tasks" > /dev/null 2>&1; then
    echo -e "${RED}❌ Backend is not running at $API_URL${NC}"
    echo "Please start the backend first:"
    echo "  cd apps/backend"
    echo "  python -m uvicorn app.main:app --reload"
    exit 1
fi
echo -e "${GREEN}✅ Backend is running${NC}"

# Check feature flag status
echo ""
echo -e "${BLUE}Current feature flag status:${NC}"
echo "  USE_HERA_SDK=${USE_HERA_SDK:-false}"

# Test 1: Simple workflow
echo ""
echo -e "${YELLOW}Test 1: Simple Workflow${NC}"
echo "----------------------------------------"
RESPONSE=$(curl -s -X POST "$API_URL/api/v1/tasks/submit" \
    -H "Content-Type: application/json" \
    -d '{"pythonCode": "print(\"Hello from test!\")"}')

WORKFLOW_ID=$(echo "$RESPONSE" | jq -r '.workflowId // .id // empty')

if [ -z "$WORKFLOW_ID" ] || [ "$WORKFLOW_ID" = "null" ]; then
    echo -e "${RED}❌ Failed to create workflow${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Workflow created: $WORKFLOW_ID${NC}"

# Wait a bit for workflow to be created in Kubernetes
sleep 2

# Check if workflow exists in Kubernetes
if kubectl get workflow "$WORKFLOW_ID" -n "$NAMESPACE" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Workflow found in Kubernetes${NC}"
    
    # Get workflow phase
    PHASE=$(kubectl get workflow "$WORKFLOW_ID" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    echo "  Phase: $PHASE"
else
    echo -e "${YELLOW}⚠️  Workflow not found in Kubernetes (may still be creating)${NC}"
fi

# Test 2: Workflow with dependencies
echo ""
echo -e "${YELLOW}Test 2: Workflow with Dependencies${NC}"
echo "----------------------------------------"
RESPONSE2=$(curl -s -X POST "$API_URL/api/v1/tasks/submit" \
    -H "Content-Type: application/json" \
    -d '{"pythonCode": "import sys; print(sys.version)", "dependencies": "numpy"}')

WORKFLOW_ID2=$(echo "$RESPONSE2" | jq -r '.workflowId // .id // empty')

if [ -z "$WORKFLOW_ID2" ] || [ "$WORKFLOW_ID2" = "null" ]; then
    echo -e "${RED}❌ Failed to create workflow with dependencies${NC}"
    echo "Response: $RESPONSE2"
    exit 1
fi

echo -e "${GREEN}✅ Workflow with dependencies created: $WORKFLOW_ID2${NC}"

# Summary
echo ""
echo "=========================================="
echo -e "${GREEN}✅ All quick tests passed!${NC}"
echo "=========================================="
echo ""
echo "Created workflows:"
echo "  1. Simple: $WORKFLOW_ID"
echo "  2. With dependencies: $WORKFLOW_ID2"
echo ""
echo "To view workflows:"
echo "  kubectl get workflows -n $NAMESPACE"
echo "  kubectl get workflow $WORKFLOW_ID -n $NAMESPACE -o yaml"
echo ""
echo "To test with different feature flag:"
echo "  USE_HERA_SDK=false ./tests/quick_test.sh"
echo "  USE_HERA_SDK=true ./tests/quick_test.sh"

