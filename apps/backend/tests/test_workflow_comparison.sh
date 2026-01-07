#!/bin/bash
# Test script to compare workflows created by current implementation vs Hera SDK

set -e

API_URL="${API_URL:-http://localhost:8000}"
NAMESPACE="${ARGO_NAMESPACE:-argo}"

echo "=========================================="
echo "Workflow Comparison Test"
echo "=========================================="
echo "API URL: $API_URL"
echo "Namespace: $NAMESPACE"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to submit a task
submit_task() {
    local python_code="$1"
    local dependencies="$2"
    local requirements_file="$3"
    
    local payload="{\"pythonCode\": \"$python_code\""
    if [ -n "$dependencies" ]; then
        payload="${payload}, \"dependencies\": \"$dependencies\""
    fi
    if [ -n "$requirements_file" ]; then
        payload="${payload}, \"requirementsFile\": \"$requirements_file\""
    fi
    payload="${payload}}"
    
    curl -s -X POST "$API_URL/api/v1/tasks/submit" \
        -H "Content-Type: application/json" \
        -d "$payload" | jq -r '.workflowId // .id'
}

# Function to get workflow YAML
get_workflow_yaml() {
    local workflow_id="$1"
    kubectl get workflow "$workflow_id" -n "$NAMESPACE" -o yaml 2>/dev/null || echo ""
}

# Function to compare workflows
compare_workflows() {
    local workflow1_id="$1"
    local workflow2_id="$2"
    local test_name="$3"
    
    echo ""
    echo "=========================================="
    echo "Comparing: $test_name"
    echo "=========================================="
    echo "Current Implementation: $workflow1_id"
    echo "Hera SDK: $workflow2_id"
    echo ""
    
    # Get workflows
    local workflow1=$(get_workflow_yaml "$workflow1_id")
    local workflow2=$(get_workflow_yaml "$workflow2_id")
    
    if [ -z "$workflow1" ] || [ -z "$workflow2" ]; then
        echo -e "${RED}❌ Could not retrieve one or both workflows${NC}"
        return 1
    fi
    
    # Save to files for comparison
    echo "$workflow1" > "/tmp/workflow_current_${test_name}.yaml"
    echo "$workflow2" > "/tmp/workflow_hera_${test_name}.yaml"
    
    # Compare key fields
    echo "Comparing key fields..."
    
    # Entrypoint
    local entrypoint1=$(echo "$workflow1" | yq '.spec.entrypoint')
    local entrypoint2=$(echo "$workflow2" | yq '.spec.entrypoint')
    if [ "$entrypoint1" = "$entrypoint2" ]; then
        echo -e "${GREEN}✅ Entrypoint: $entrypoint1${NC}"
    else
        echo -e "${RED}❌ Entrypoint differs: $entrypoint1 vs $entrypoint2${NC}"
    fi
    
    # Image
    local image1=$(echo "$workflow1" | yq '.spec.templates[0].container.image // .spec.templates[0].script.image')
    local image2=$(echo "$workflow2" | yq '.spec.templates[0].container.image // .spec.templates[0].script.image')
    if [ "$image1" = "$image2" ]; then
        echo -e "${GREEN}✅ Image: $image1${NC}"
    else
        echo -e "${RED}❌ Image differs: $image1 vs $image2${NC}"
    fi
    
    # Template type
    local type1=$(echo "$workflow1" | yq 'if .spec.templates[0].container then "container" elif .spec.templates[0].script then "script" else "unknown" end')
    local type2=$(echo "$workflow2" | yq 'if .spec.templates[0].container then "container" elif .spec.templates[0].script then "script" else "unknown" end')
    if [ "$type1" = "$type2" ]; then
        echo -e "${GREEN}✅ Template type: $type1${NC}"
    else
        echo -e "${RED}❌ Template type differs: $type1 vs $type2${NC}"
    fi
    
    echo ""
    echo "Full YAML comparison saved to:"
    echo "  /tmp/workflow_current_${test_name}.yaml"
    echo "  /tmp/workflow_hera_${test_name}.yaml"
    echo ""
    echo "To view diff:"
    echo "  diff /tmp/workflow_current_${test_name}.yaml /tmp/workflow_hera_${test_name}.yaml"
}

# Test 1: Simple workflow
echo "=========================================="
echo "Test 1: Simple Workflow (No Dependencies)"
echo "=========================================="
echo ""
echo -e "${YELLOW}Step 1: Create workflow with current implementation${NC}"
echo "Make sure USE_HERA_SDK=false"
read -p "Press Enter when ready..."
CURRENT_WF1=$(submit_task "print('Hello from test!')" "" "")
echo "Workflow ID: $CURRENT_WF1"

echo ""
echo -e "${YELLOW}Step 2: Create workflow with Hera SDK${NC}"
echo "Make sure USE_HERA_SDK=true"
read -p "Press Enter when ready..."
HERA_WF1=$(submit_task "print('Hello from test!')" "" "")
echo "Workflow ID: $HERA_WF1"

compare_workflows "$CURRENT_WF1" "$HERA_WF1" "simple"

# Test 2: With dependencies
echo ""
echo "=========================================="
echo "Test 2: Workflow with Dependencies"
echo "=========================================="
echo ""
echo -e "${YELLOW}Step 1: Create workflow with current implementation${NC}"
echo "Make sure USE_HERA_SDK=false"
read -p "Press Enter when ready..."
CURRENT_WF2=$(submit_task "import numpy as np; print(np.array([1,2,3]))" "numpy" "")
echo "Workflow ID: $CURRENT_WF2"

echo ""
echo -e "${YELLOW}Step 2: Create workflow with Hera SDK${NC}"
echo "Make sure USE_HERA_SDK=true"
read -p "Press Enter when ready..."
HERA_WF2=$(submit_task "import numpy as np; print(np.array([1,2,3]))" "numpy" "")
echo "Workflow ID: $HERA_WF2"

compare_workflows "$CURRENT_WF2" "$HERA_WF2" "with_dependencies"

echo ""
echo -e "${GREEN}Comparison complete!${NC}"
echo "Check the workflow YAML files in /tmp/ for detailed comparison"

