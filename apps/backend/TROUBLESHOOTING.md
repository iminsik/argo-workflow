# Troubleshooting Guide

## Issue: "python-multipart" not found error

### Problem
When starting the backend, you see:
```
RuntimeError: Form data requires "python-multipart" to be installed.
```

### Solution

**Option 1: Use Poetry Run (Recommended)**
```bash
cd apps/backend
poetry run python -m uvicorn app.main:app --reload
```

**Option 2: Use the run script**
```bash
cd apps/backend
./run_dev.sh
```

**Option 3: Activate Poetry Shell**
```bash
cd apps/backend
poetry shell
python -m uvicorn app.main:app --reload
```

### Why This Happens

When you run `python` directly, it might use your system Python instead of the Poetry virtual environment where dependencies are installed. Using `poetry run` ensures the correct environment is used.

### Verify Installation

```bash
# Check if installed
poetry show python-multipart

# Test import
poetry run python -c "import multipart; print('OK')"
```

---

## Issue: Feature Flag Not Working

### Problem
Setting `USE_HERA_SDK=true` doesn't seem to have any effect.

### Solution

1. **Check environment variable is set:**
   ```bash
   echo $USE_HERA_SDK
   ```

2. **Set it before starting server:**
   ```bash
   export USE_HERA_SDK=true
   poetry run python -m uvicorn app.main:app --reload
   ```

3. **Or use the run script:**
   ```bash
   USE_HERA_SDK=true ./run_dev.sh
   ```

4. **Check backend logs for confirmation:**
   Look for messages indicating which implementation is being used.

---

## Issue: Hera SDK Import Error

### Problem
```
ImportError: cannot import name 'create_workflow_with_hera' from 'app.workflow_hera'
```

### Solution

1. **Verify hera-workflows is installed:**
   ```bash
   poetry show hera-workflows
   ```

2. **Reinstall if needed:**
   ```bash
   poetry install --no-root
   ```

3. **Check the import path:**
   Make sure `workflow_hera.py` is in `app/` directory.

---

## Issue: Kubernetes Connection Errors

### Problem
Backend can't connect to Kubernetes cluster.

### Solution

1. **Check kubeconfig:**
   ```bash
   kubectl config current-context
   kubectl get nodes
   ```

2. **For local development (Kind):**
   - Ensure Kind cluster is running: `kind get clusters`
   - Backend should auto-detect and patch configuration

3. **For remote cluster:**
   - Ensure kubeconfig is in `~/.kube/config`
   - Check network connectivity

---

## Issue: Workflows Not Creating

### Problem
API returns success but workflow doesn't appear in Kubernetes.

### Solution

1. **Check PVC exists:**
   ```bash
   kubectl get pvc -n argo
   ```

2. **Check namespace:**
   ```bash
   kubectl get workflows -n argo
   ```

3. **Check backend logs:**
   ```bash
   # Look for error messages
   poetry run python -m uvicorn app.main:app --reload 2>&1 | grep -i error
   ```

4. **Verify Argo Workflows controller:**
   ```bash
   kubectl get pods -n argo | grep workflow-controller
   ```

---

## Issue: Test Scripts Failing

### Problem
Test scripts can't connect to backend or Kubernetes.

### Solution

1. **Backend not running:**
   ```bash
   # Start backend first
   cd apps/backend
   ./run_dev.sh
   ```

2. **Wrong API URL:**
   ```bash
   # Set correct URL
   export API_URL=http://localhost:8000
   ./tests/quick_test.sh
   ```

3. **Kubernetes not configured:**
   ```bash
   # Verify kubectl works
   kubectl get nodes
   ```

---

## General Debugging Tips

### Check Dependencies
```bash
cd apps/backend
poetry show
```

### Check Python Environment
```bash
poetry run python --version
poetry run which python
```

### View Backend Logs
```bash
# When running with uvicorn
# Logs appear in terminal

# Check for specific errors
poetry run python -m uvicorn app.main:app --reload 2>&1 | grep -i error
```

### Test API Directly
```bash
# Health check
curl http://localhost:8000/health

# List tasks
curl http://localhost:8000/api/v1/tasks
```

### Verify Feature Flag in Code
```bash
# Check if feature flag is being read
poetry run python -c "import os; print('USE_HERA_SDK:', os.getenv('USE_HERA_SDK', 'not set'))"
```

---

## Still Having Issues?

1. **Check all dependencies are installed:**
   ```bash
   poetry install --no-root
   ```

2. **Verify Python version:**
   ```bash
   poetry run python --version
   # Should be 3.9, 3.10, or 3.11
   ```

3. **Clear Poetry cache (if needed):**
   ```bash
   poetry cache clear pypi --all
   poetry install --no-root
   ```

4. **Check for conflicting packages:**
   ```bash
   poetry show --tree
   ```

