# Testing Guide for Hera SDK Integration

This directory contains test scripts for verifying the Hera SDK integration.

## Test Scripts

### 1. `test_hera_integration.py`

Comprehensive Python test script for testing both implementations.

**Usage:**

```bash
# Test with current implementation (Hera disabled)
python tests/test_hera_integration.py --hera-disabled

# Test with Hera SDK (Hera enabled)
python tests/test_hera_integration.py --hera-enabled

# Test both and compare workflows
python tests/test_hera_integration.py --compare

# Custom API URL
python tests/test_hera_integration.py --hera-enabled --api-url http://localhost:8000
```

**Requirements:**
- `requests` library
- `kubernetes` Python client
- Access to Kubernetes cluster
- Backend API running

**Install dependencies:**
```bash
pip install requests kubernetes pyyaml
```

### 2. `test_workflow_comparison.sh`

Bash script for interactive workflow comparison.

**Usage:**

```bash
# Make executable (first time only)
chmod +x tests/test_workflow_comparison.sh

# Run comparison
./tests/test_workflow_comparison.sh

# With custom API URL
API_URL=http://localhost:8000 ./tests/test_workflow_comparison.sh
```

**Requirements:**
- `curl`
- `jq` (JSON processor)
- `yq` (YAML processor)
- `kubectl` configured
- Backend API running

**Install dependencies:**
```bash
# macOS
brew install jq yq

# Linux
sudo apt-get install jq yq
```

## Quick Start Testing

### Step 1: Start Backend API

```bash
cd apps/backend
python -m uvicorn app.main:app --reload
```

### Step 2: Test Current Implementation

```bash
# In a new terminal
export USE_HERA_SDK=false
python tests/test_hera_integration.py --hera-disabled
```

### Step 3: Test Hera SDK

```bash
# In a new terminal
export USE_HERA_SDK=true
python tests/test_hera_integration.py --hera-enabled
```

### Step 4: Compare Both

```bash
# Run comparison mode
python tests/test_hera_integration.py --compare
```

## Test Scenarios

The test scripts cover:

1. **Simple Workflow**
   - No dependencies
   - Basic Python code execution

2. **Workflow with Dependencies**
   - Space/comma-separated packages
   - Package installation via uv

3. **Workflow with Requirements File**
   - requirements.txt format
   - Multiple packages with versions

## Expected Results

### Success Indicators

- ✅ Workflows created successfully
- ✅ Workflow IDs returned
- ✅ Workflows appear in Kubernetes
- ✅ Workflows execute successfully
- ✅ Results match between implementations

### Comparison Results

When comparing workflows, you should see:
- ✅ Same entrypoint
- ✅ Same template type (container/script)
- ✅ Same image
- ✅ Same volumes
- ✅ Functionally equivalent structure

## Troubleshooting

### Issue: "Connection refused"
**Solution:** Make sure backend API is running on the specified URL

### Issue: "Cannot retrieve workflow"
**Solution:** 
- Check kubectl is configured correctly
- Verify namespace is correct (default: argo)
- Ensure workflow exists: `kubectl get workflows -n argo`

### Issue: "Module not found"
**Solution:** Install required Python packages:
```bash
pip install requests kubernetes pyyaml
```

### Issue: "Feature flag not working"
**Solution:**
- Verify environment variable is set: `echo $USE_HERA_SDK`
- Check backend logs for feature flag status
- Restart backend after setting environment variable

## Manual Testing

### Test 1: Simple Workflow

```bash
# With current implementation
export USE_HERA_SDK=false
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"pythonCode": "print(\"Hello World\")"}'

# With Hera SDK
export USE_HERA_SDK=true
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"pythonCode": "print(\"Hello World\")"}'
```

### Test 2: Compare Workflows

```bash
# Get workflow created with current implementation
kubectl get workflow <workflow-id-1> -n argo -o yaml > current.yaml

# Get workflow created with Hera SDK
kubectl get workflow <workflow-id-2> -n argo -o yaml > hera.yaml

# Compare
diff current.yaml hera.yaml
```

## Continuous Testing

For CI/CD integration:

```bash
# In CI pipeline
export USE_HERA_SDK=true
python tests/test_hera_integration.py --hera-enabled --api-url $API_URL

# Check exit code
if [ $? -eq 0 ]; then
    echo "Tests passed"
else
    echo "Tests failed"
    exit 1
fi
```

## Next Steps

After testing:
1. Review test results
2. Compare workflows
3. Check application logs
4. Proceed with gradual rollout (see `GRADUAL_ROLLOUT_GUIDE.md`)

