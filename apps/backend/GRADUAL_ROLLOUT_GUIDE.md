# Gradual Rollout Guide for Hera SDK

This guide provides step-by-step instructions for gradually enabling the Hera SDK in production.

## Overview

The Hera SDK integration uses a feature flag (`USE_HERA_SDK`) that allows you to:
- Test the new implementation without affecting production
- Gradually roll out to different environments
- Easily roll back if issues are detected
- Compare workflows side-by-side

## Prerequisites

- ✅ Hera SDK installed (`hera-workflows>=5.0.0`)
- ✅ Feature flag integration complete
- ✅ Test scripts available
- ✅ Monitoring/logging in place

## Rollout Phases

### Phase 1: Development Environment Testing

**Goal:** Verify Hera SDK works correctly in a controlled environment

**Steps:**
1. Set up development environment with Hera SDK installed
2. Enable feature flag for development only:
   ```bash
   # In docker-compose.dev.yaml or development config
   environment:
     - USE_HERA_SDK=true
   ```
3. Run test suite:
   ```bash
   # Test with Hera SDK enabled
   python tests/test_hera_integration.py --hera-enabled --api-url http://localhost:8000
   ```
4. Verify:
   - Workflows are created successfully
   - Workflows execute correctly
   - No errors in logs
   - Results match expected output

**Success Criteria:**
- ✅ All tests pass
- ✅ No errors in application logs
- ✅ Workflows execute successfully
- ✅ Feature parity with current implementation

**Duration:** 1-2 days

---

### Phase 2: Staging Environment Testing

**Goal:** Test in a production-like environment

**Steps:**
1. Deploy to staging with feature flag enabled:
   ```yaml
   # In staging deployment
   env:
     - name: USE_HERA_SDK
       value: "true"
   ```
2. Run comprehensive tests:
   ```bash
   # Test all scenarios
   python tests/test_hera_integration.py --compare --api-url <staging-api-url>
   ```
3. Monitor:
   - Application logs for errors
   - Workflow execution times
   - Resource usage
   - Error rates
4. Compare workflows:
   ```bash
   ./tests/test_workflow_comparison.sh
   ```

**Success Criteria:**
- ✅ All tests pass in staging
- ✅ No increase in error rates
- ✅ Performance is equivalent or better
- ✅ Workflows are functionally equivalent

**Duration:** 3-5 days

---

### Phase 3: Canary Deployment (Optional)

**Goal:** Test with a small percentage of production traffic

**Steps:**
1. Implement canary logic (if not using feature flag):
   ```python
   # Example: Enable for 10% of requests
   import random
   use_hera = random.random() < 0.10 or os.getenv("USE_HERA_SDK", "false").lower() == "true"
   ```
2. Monitor:
   - Error rates for Hera vs current implementation
   - Performance metrics
   - User-reported issues
3. Gradually increase percentage:
   - Day 1: 10%
   - Day 2: 25%
   - Day 3: 50%
   - Day 4: 75%
   - Day 5: 100%

**Success Criteria:**
- ✅ Error rates remain stable
- ✅ No performance degradation
- ✅ No user-reported issues

**Duration:** 5-7 days

---

### Phase 4: Full Production Rollout

**Goal:** Enable Hera SDK for all production traffic

**Steps:**
1. Update production deployment:
   ```yaml
   # In production deployment
   env:
     - name: USE_HERA_SDK
       value: "true"
   ```
2. Deploy during low-traffic period
3. Monitor closely for first 24-48 hours:
   - Application logs
   - Workflow execution metrics
   - Error rates
   - User feedback
4. Have rollback plan ready:
   ```bash
   # Quick rollback: set USE_HERA_SDK=false
   kubectl set env deployment/backend USE_HERA_SDK=false
   ```

**Success Criteria:**
- ✅ Stable for 48+ hours
- ✅ No increase in errors
- ✅ Performance maintained
- ✅ All workflows executing correctly

**Duration:** Ongoing monitoring

---

### Phase 5: Cleanup (After Stable Period)

**Goal:** Remove old implementation and feature flag

**Steps:**
1. Wait for stable period (2-4 weeks)
2. Remove feature flag logic:
   - Remove `USE_HERA_SDK` environment variable
   - Remove conditional code
   - Remove old YAML template files (optional)
3. Update documentation
4. Remove unused imports and code

**Duration:** 1-2 days

---

## Monitoring Checklist

During rollout, monitor:

### Application Metrics
- [ ] Error rates (should remain stable)
- [ ] Response times (should not increase)
- [ ] Workflow creation success rate
- [ ] API endpoint performance

### Workflow Metrics
- [ ] Workflow execution success rate
- [ ] Average workflow execution time
- [ ] Failed workflow count
- [ ] Workflow phase distribution

### Infrastructure Metrics
- [ ] CPU usage
- [ ] Memory usage
- [ ] Network traffic
- [ ] Kubernetes resource usage

### Logs to Watch
- [ ] Application startup logs
- [ ] Workflow creation logs
- [ ] Error logs
- [ ] Warning messages

---

## Rollback Procedure

If issues are detected:

### Quick Rollback (Feature Flag)
```bash
# Disable Hera SDK immediately
kubectl set env deployment/backend USE_HERA_SDK=false

# Or update deployment YAML
# env:
#   - name: USE_HERA_SDK
#     value: "false"
```

### Full Rollback (Code Revert)
If feature flag rollback doesn't work:
1. Revert to previous deployment
2. Investigate issues
3. Fix and retest before re-enabling

---

## Testing Checklist

Before each phase, verify:

### Functional Tests
- [ ] Simple workflow (no dependencies)
- [ ] Workflow with dependencies
- [ ] Workflow with requirements file
- [ ] Workflow rerun
- [ ] Workflow cancellation
- [ ] Workflow deletion

### Integration Tests
- [ ] API endpoint responses
- [ ] Database operations
- [ ] Kubernetes workflow creation
- [ ] Log retrieval
- [ ] WebSocket connections

### Comparison Tests
- [ ] Workflow YAML structure
- [ ] Workflow execution results
- [ ] Performance metrics
- [ ] Resource usage

---

## Communication Plan

### Before Rollout
- [ ] Notify team of rollout plan
- [ ] Schedule rollout during low-traffic period
- [ ] Prepare rollback plan
- [ ] Set up monitoring dashboards

### During Rollout
- [ ] Monitor metrics closely
- [ ] Communicate status to team
- [ ] Document any issues
- [ ] Be ready to rollback

### After Rollout
- [ ] Document results
- [ ] Share learnings with team
- [ ] Update documentation
- [ ] Plan cleanup phase

---

## Success Metrics

Track these metrics to measure success:

1. **Error Rate:** Should remain < 1%
2. **Workflow Success Rate:** Should remain > 99%
3. **Performance:** Response times should not increase > 10%
4. **Code Quality:** Reduced code complexity (70% reduction achieved)
5. **Developer Experience:** Faster development cycles

---

## Troubleshooting

### Issue: Workflows not creating
**Check:**
- Hera SDK is installed
- Feature flag is set correctly
- Kubernetes connectivity
- PVC is available

### Issue: Workflows failing
**Check:**
- Workflow YAML structure
- Container images
- Environment variables
- Volume mounts

### Issue: Performance degradation
**Check:**
- Resource limits
- Network latency
- Kubernetes cluster health
- Application logs

---

## Timeline Example

```
Week 1: Development Testing
  - Day 1-2: Setup and initial testing
  - Day 3-4: Comprehensive testing
  - Day 5: Review and prepare for staging

Week 2: Staging Testing
  - Day 1-2: Deploy to staging
  - Day 3-4: Comprehensive testing
  - Day 5: Review and prepare for production

Week 3: Production Rollout
  - Day 1: Canary deployment (10%)
  - Day 2-3: Gradual increase (25%, 50%)
  - Day 4-5: Full rollout (100%)

Week 4+: Monitoring
  - Monitor for 2-4 weeks
  - Collect metrics
  - Plan cleanup
```

---

## Support

For issues or questions:
- Check logs: `kubectl logs -f deployment/backend`
- Review workflow: `kubectl get workflow <workflow-id> -n argo -o yaml`
- Test scripts: `python tests/test_hera_integration.py --help`
- Documentation: See `README_HERA_POC.md`

