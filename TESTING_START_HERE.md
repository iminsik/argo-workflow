# 🚀 Hera SDK Integration - Start Testing Here

## Quick Start

### 1. Test Current Implementation (Baseline)

```bash
# Terminal 1: Start backend with current implementation
cd apps/backend
export USE_HERA_SDK=false
python -m uvicorn app.main:app --reload

# Terminal 2: Run quick test
cd apps/backend
./tests/quick_test.sh
```

**Expected:** ✅ All tests pass, workflows created successfully

---

### 2. Test Hera SDK Implementation

```bash
# Terminal 1: Start backend with Hera SDK
cd apps/backend
export USE_HERA_SDK=true
python -m uvicorn app.main:app --reload

# Terminal 2: Run quick test
cd apps/backend
USE_HERA_SDK=true ./tests/quick_test.sh
```

**Expected:** ✅ All tests pass, workflows created successfully

---

### 3. Compare Both Implementations

```bash
# Make sure backend is running
cd apps/backend
python tests/test_hera_integration.py --compare
```

**Expected:** ✅ Workflows are functionally equivalent

---

## Test Scripts Available

| Script | Purpose | Usage |
|--------|---------|-------|
| `tests/quick_test.sh` | Quick smoke test | `./tests/quick_test.sh` |
| `tests/test_hera_integration.py` | Comprehensive test suite | `python tests/test_hera_integration.py --hera-enabled` |
| `tests/test_workflow_comparison.sh` | Interactive comparison | `./tests/test_workflow_comparison.sh` |

## Documentation

- **Testing Guide:** `apps/backend/tests/README.md`
- **Rollout Strategy:** `apps/backend/GRADUAL_ROLLOUT_GUIDE.md`
- **Integration Details:** `changes/PR_HERA_SDK_INTEGRATION.md`
- **Analysis:** `changes/PR_HERA_SDK_ANALYSIS.md`

## What to Verify

### ✅ Functional Tests
- [ ] Simple workflow (no dependencies) works
- [ ] Workflow with dependencies works
- [ ] Workflow with requirements file works
- [ ] Workflows appear in Kubernetes
- [ ] Workflows execute successfully

### ✅ Comparison Tests
- [ ] Workflows have same structure
- [ ] Workflows have same entrypoint
- [ ] Workflows use same images
- [ ] Workflows have same volumes
- [ ] Results are equivalent

### ✅ Performance Tests
- [ ] Response times are similar
- [ ] No increase in errors
- [ ] Resource usage is stable

## Troubleshooting

### Backend not running?
```bash
cd apps/backend
python -m uvicorn app.main:app --reload
```

### Tests failing?
- Check backend logs
- Verify Kubernetes connectivity
- Ensure PVC is available
- Check feature flag: `echo $USE_HERA_SDK`

### Need help?
- See `apps/backend/tests/README.md` for detailed guide
- Check `apps/backend/GRADUAL_ROLLOUT_GUIDE.md` for rollout steps

## Next Steps After Testing

1. ✅ Verify all tests pass
2. ✅ Compare workflows
3. ✅ Review logs
4. 📋 Proceed to staging (see `GRADUAL_ROLLOUT_GUIDE.md`)
5. 🚀 Production rollout when ready

---

**Ready to test? Start with step 1 above!** 🎯

