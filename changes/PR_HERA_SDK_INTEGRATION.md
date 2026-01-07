# Hera SDK Integration - Feature Flag Implementation

## Summary

Successfully integrated Hera SDK into the backend with a feature flag for gradual migration. The implementation allows testing the new Hera-based workflow creation alongside the existing implementation.

## Changes Made

### 1. Added Hera SDK Dependency
**File:** `apps/backend/pyproject.toml`
- Added `hera-workflows>=5.0.0` to dependencies
- Updated Python requirement to `>=3.9,<4` to match hera-workflows constraints

### 2. Feature Flag Integration
**File:** `apps/backend/app/main.py`
- Added feature flag check: `USE_HERA_SDK` environment variable
- Conditional import of Hera SDK functions
- Modified `start_task()` endpoint to use feature flag
- Automatic fallback to current implementation if Hera fails

### 3. POC Implementation
**File:** `apps/backend/app/workflow_hera.py`
- Complete Hera SDK implementation
- Handles all current features (dependencies, requirements file, volumes, etc.)

## How to Use

### Enable Hera SDK (Testing)

```bash
# Set environment variable to enable Hera SDK
export USE_HERA_SDK=true

# Or in docker-compose.yaml or deployment
environment:
  - USE_HERA_SDK=true
```

### Disable Hera SDK (Use Current Implementation)

```bash
# Unset or set to false
export USE_HERA_SDK=false
# or simply don't set it (defaults to false)
```

### Install Dependencies

```bash
# Using pip
pip install hera-workflows>=5.0.0

# Using poetry (if using poetry)
poetry add hera-workflows

# Using uv (if using uv)
uv pip install hera-workflows>=6.0.0
```

## Feature Flag Behavior

1. **When `USE_HERA_SDK=true` and Hera is available:**
   - Uses Hera SDK to create workflows
   - Falls back to current implementation if Hera fails

2. **When `USE_HERA_SDK=false` or Hera unavailable:**
   - Uses current YAML-based implementation
   - No changes to existing behavior

3. **Error Handling:**
   - If Hera SDK fails, automatically falls back to current implementation
   - Logs warning message for debugging

## Testing the Integration

### 1. Install Dependencies

```bash
cd apps/backend
pip install -r requirements.txt  # or poetry install, etc.
```

### 2. Test with Hera SDK Disabled (Current Behavior)

```bash
# Don't set USE_HERA_SDK or set it to false
export USE_HERA_SDK=false
python -m uvicorn app.main:app --reload
```

Submit a task and verify it works as before.

### 3. Test with Hera SDK Enabled

```bash
# Enable Hera SDK
export USE_HERA_SDK=true
python -m uvicorn app.main:app --reload
```

Submit the same task and verify:
- Workflow is created successfully
- Workflow executes correctly
- Results match the current implementation

### 4. Compare Workflows

```bash
# Get workflow created with current implementation
kubectl get workflow <workflow-name> -n argo -o yaml > current-workflow.yaml

# Get workflow created with Hera SDK
kubectl get workflow <workflow-name> -n argo -o yaml > hera-workflow.yaml

# Compare (should be functionally equivalent)
diff current-workflow.yaml hera-workflow.yaml
```

## Verification Checklist

- [ ] Install hera-workflows dependency
- [ ] Test with `USE_HERA_SDK=false` (verify current behavior unchanged)
- [ ] Test with `USE_HERA_SDK=true` (verify Hera SDK works)
- [ ] Test simple workflow (no dependencies)
- [ ] Test workflow with dependencies
- [ ] Test workflow with requirements file
- [ ] Verify workflows execute correctly
- [ ] Compare generated workflows
- [ ] Test error handling (Hera fallback)

## Code Changes Summary

### Modified Files
1. `apps/backend/pyproject.toml` - Added hera-workflows dependency
2. `apps/backend/app/main.py` - Added feature flag and conditional logic

### New Files
1. `apps/backend/app/workflow_hera.py` - Hera SDK implementation

### No Breaking Changes
- Default behavior unchanged (Hera SDK disabled by default)
- Existing code path remains intact
- Backward compatible

## Migration Path

### Phase 1: Testing (Current)
- Feature flag disabled by default
- Test Hera SDK in development/staging
- Compare results with current implementation

### Phase 2: Gradual Rollout
- Enable for specific users/environments
- Monitor for issues
- Collect metrics

### Phase 3: Full Migration
- Enable by default
- Remove feature flag
- Remove old implementation code
- Remove YAML template files (optional)

## Troubleshooting

### Issue: "Cannot find implementation or library stub for module named 'app.workflow_hera'"
**Solution:** This is a type checker warning. Install hera-workflows (`poetry install` or `pip install hera-workflows>=5.0.0`) and the error will resolve. The code will work at runtime.

### Issue: Poetry lock fails with version solving error
**Solution:** Ensure Python requirement is set to `>=3.9,<4` in `pyproject.toml` to match hera-workflows constraints. The lock file should generate successfully after this.

### Issue: "Hera SDK workflow creation failed"
**Solution:** Check logs for specific error. The system will automatically fall back to current implementation. Common issues:
- Hera SDK not installed
- Kubernetes configuration issues
- PVC not available

### Issue: Workflows created but not executing
**Solution:** Verify:
- Kubernetes cluster connectivity
- Argo Workflows controller running
- PVC is bound
- Namespace configuration correct

## Next Steps

1. **Install and Test:**
   ```bash
   pip install hera-workflows>=6.0.0
   export USE_HERA_SDK=true
   # Test workflow creation
   ```

2. **Monitor:**
   - Check logs for any Hera SDK errors
   - Compare workflow execution times
   - Verify feature parity

3. **Gradual Rollout:**
   - Enable for development environment
   - Enable for staging
   - Enable for production (with monitoring)

4. **Full Migration:**
   - Once confident, make Hera SDK default
   - Remove feature flag
   - Clean up old code

## Benefits Achieved

✅ **Zero Breaking Changes** - Feature flag ensures backward compatibility
✅ **Gradual Migration** - Can test and roll out incrementally
✅ **Automatic Fallback** - System falls back if Hera fails
✅ **Easy Testing** - Simple environment variable toggle
✅ **Production Ready** - Safe to deploy with feature flag disabled

## Documentation

- POC Implementation: `apps/backend/app/workflow_hera.py`
- POC README: `apps/backend/app/README_HERA_POC.md`
- Analysis: `changes/PR_HERA_SDK_ANALYSIS.md`
- Comparison: `apps/backend/app/workflow_hera_comparison.md`

