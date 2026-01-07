# Hera SDK Adoption Analysis

## Executive Summary

The backend codebase currently uses the low-level `argo_workflows` Python client library and raw Kubernetes CustomObjectsApi to create and manage Argo Workflows. This results in complex, error-prone code with manual YAML template manipulation, serialization issues, and verbose workflow management operations.

Adopting the **Hera SDK** would significantly improve code quality, maintainability, and developer experience by providing:
- Pythonic workflow definitions (no YAML templates needed)
- Type-safe workflow construction
- Simplified template creation and management
- Cleaner API for workflow operations
- Reduced serialization complexity

## Current Pain Points

### 1. Complex Workflow Creation (Lines 820-1091 in `main.py`)

**Current Issues:**
- Manual YAML template loading and parsing
- Complex dict manipulation for script vs container templates
- Serialization workarounds using `ApiClient.sanitize_for_serialization()`
- Separate code paths for dependencies vs no-dependencies workflows
- Manual handling of volumes, volumeMounts, and environment variables
- Error-prone template merging logic (lines 1036-1080)

**Code Complexity:**
```python
# Current approach requires:
1. Loading YAML template
2. Converting to dict
3. Manually updating env vars, script source, volumes
4. Handling serialization issues
5. Converting back to dict for Kubernetes API
6. Manual preservation of volumeMounts/env after serialization
```

**Hera Improvement:**
```python
# With Hera, this becomes:
from hera.workflows import Workflow, Script, Parameter
from hera.shared import VolumeMount, Volume

workflow = Workflow(
    generate_name="python-job-",
    entrypoint="main",
    volumes=[Volume(name="task-results", persistent_volume_claim="task-results-pvc")]
)

script_template = Script(
    name="main",
    image="python:3.11-slim",
    source=build_script_source(request),
    env=[
        {"name": "PYTHON_CODE", "value": request.pythonCode},
        {"name": "DEPENDENCIES", "value": request.dependencies or ""}
    ],
    volume_mounts=[VolumeMount(name="task-results", mount_path="/mnt/results")]
)

workflow.add_template(script_template)
workflow.create()
```

**Benefits:**
- Eliminates ~270 lines of complex template manipulation code
- Type-safe construction prevents runtime errors
- No serialization issues
- Clear, readable workflow definition

### 2. Workflow Querying Operations

**Current Issues:**
- Multiple places using `get_namespaced_custom_object()` with manual dict parsing
- Repeated code for extracting workflow status/phase
- Manual datetime parsing and conversion
- Error handling scattered across multiple endpoints

**Locations:**
- `list_tasks()` (line 1319)
- `get_task()` (line 1536)
- `get_run_logs()` (line 1684)
- `get_task_logs()` (line 1828)
- `fetch_logs_from_kubernetes()` (line 327)

**Hera Improvement:**
```python
from hera.workflows import WorkflowService

service = WorkflowService()
workflow = service.get_workflow(name=workflow_id, namespace=namespace)

# Type-safe access to workflow properties
phase = workflow.status.phase
started_at = workflow.status.started_at
finished_at = workflow.status.finished_at
```

**Benefits:**
- Type-safe workflow objects instead of dicts
- Consistent error handling
- Reduced code duplication
- Better IDE support and autocomplete

### 3. Workflow Deletion Operations

**Current Issues:**
- Direct use of `delete_namespaced_custom_object()` with manual error handling
- Locations: `cancel_task()` (line 2030) and `delete_task()` (line 2097)

**Hera Improvement:**
```python
from hera.workflows import WorkflowService

service = WorkflowService()
service.delete_workflow(name=workflow_id, namespace=namespace)
```

**Benefits:**
- Cleaner API
- Consistent error handling
- Less boilerplate code

### 4. Template Management Complexity

**Current Issues:**
- Separate handling for script templates vs container templates
- Complex logic to preserve volumeMounts and env vars after serialization (lines 1036-1080)
- Manual script source manipulation for requirements.txt injection (lines 934-945)
- Workarounds for ScriptTemplate validation issues (line 908)

**Hera Improvement:**
- Unified template API
- Automatic handling of volumes and env vars
- Clean script source construction
- No serialization workarounds needed

### 5. Workflow Status and Phase Determination

**Current Issues:**
- Custom `determine_workflow_phase()` function (line 740) with complex logic
- Manual parsing of workflow status dicts
- Node state inspection logic

**Hera Improvement:**
- Hera provides built-in status helpers
- Type-safe status objects
- Less custom logic needed

## Specific Code Sections to Refactor

### High Priority (High Impact, Medium Effort)

1. **`start_task()` endpoint (lines 820-1263)**
   - **Impact:** Eliminates ~270 lines of complex code
   - **Effort:** Medium - requires refactoring workflow creation logic
   - **Benefit:** Massive reduction in complexity, better maintainability

2. **Workflow querying operations (multiple locations)**
   - **Impact:** Reduces code duplication, improves type safety
   - **Effort:** Low-Medium - replace dict access with Hera objects
   - **Benefit:** Better error handling, less code

### Medium Priority (Medium Impact, Low Effort)

3. **Workflow deletion operations (lines 2019-2045, 2048-2111)**
   - **Impact:** Cleaner code, consistent error handling
   - **Effort:** Low - simple API replacement
   - **Benefit:** Less boilerplate

4. **`determine_workflow_phase()` function (line 740)**
   - **Impact:** Can potentially be simplified or removed
   - **Effort:** Low - evaluate if Hera provides equivalent functionality
   - **Benefit:** Less custom logic to maintain

### Low Priority (Nice to Have)

5. **Template YAML files (`python-processor.yaml`, `python-processor-with-deps.yaml`)**
   - **Impact:** Can be removed if workflows are fully defined in Python
   - **Effort:** Low - after refactoring workflow creation
   - **Benefit:** One less thing to maintain

## Migration Strategy

### Phase 1: Add Hera SDK
1. Add `hera-workflows` to `pyproject.toml`
2. Keep existing code working (no breaking changes)

### Phase 2: Refactor Workflow Creation
1. Create new `create_workflow_with_hera()` function
2. Test with existing endpoints
3. Gradually migrate `start_task()` endpoint

### Phase 3: Refactor Workflow Queries
1. Replace `get_namespaced_custom_object()` calls with Hera `WorkflowService`
2. Update status/phase extraction logic
3. Remove `determine_workflow_phase()` if Hera provides equivalent

### Phase 4: Refactor Workflow Deletion
1. Replace deletion calls with Hera API
2. Simplify error handling

### Phase 5: Cleanup
1. Remove YAML template files (if no longer needed)
2. Remove unused `argo_workflows` model imports
3. Remove serialization workarounds

## Estimated Benefits

### Code Reduction
- **Workflow Creation:** ~270 lines → ~50-80 lines (70% reduction)
- **Workflow Queries:** ~100 lines → ~30-40 lines (60% reduction)
- **Total:** ~370 lines of complex code → ~80-120 lines of clean code

### Maintainability
- **Type Safety:** Catch errors at development time, not runtime
- **Readability:** Pythonic code vs complex dict manipulation
- **Testing:** Easier to unit test Python code vs YAML templates
- **Documentation:** Hera SDK is well-documented

### Developer Experience
- **IDE Support:** Better autocomplete and type checking
- **Debugging:** Clearer error messages
- **Onboarding:** Easier for new developers to understand

## Potential Challenges

1. **Learning Curve:** Team needs to learn Hera SDK API
   - **Mitigation:** Hera has good documentation and examples

2. **Migration Risk:** Need to ensure feature parity
   - **Mitigation:** Gradual migration, keep old code until verified

3. **Dependency:** Adding another dependency
   - **Mitigation:** Hera is actively maintained and widely used

4. **Template Flexibility:** Need to verify Hera supports all current template features
   - **Mitigation:** Hera supports all Argo Workflows features

## Recommendation

**Strongly recommend adopting Hera SDK**, especially for:
- Workflow creation logic (highest impact)
- Workflow querying operations (high impact, low risk)
- Workflow deletion operations (low effort, good cleanup)

The benefits significantly outweigh the migration effort, and the codebase will be much more maintainable and easier to extend.

## Example: Before/After Comparison

### Before (Current Code - ~50 lines for simple workflow)
```python
# Load YAML template
with open(workflow_path, "r") as f:
    manifest_dict = yaml.safe_load(f)

# Convert metadata
metadata_dict = manifest_dict.get("metadata", {})
metadata = ObjectMeta(**metadata_dict) if metadata_dict else None

# Extract and manipulate spec
spec_dict = manifest_dict.get("spec", {}).copy()
volumes = spec_dict.pop("volumes", [])

# Complex template manipulation...
# (50+ more lines of dict manipulation, serialization, etc.)

# Create workflow
result = api_instance.create_namespaced_custom_object(
    group="argoproj.io",
    version="v1alpha1",
    namespace=namespace,
    plural="workflows",
    body=workflow_dict
)
```

### After (With Hera - ~15 lines)
```python
from hera.workflows import Workflow, Script
from hera.shared import VolumeMount, Volume

workflow = Workflow(
    generate_name="python-job-",
    entrypoint="main",
    volumes=[Volume(name="task-results", persistent_volume_claim="task-results-pvc")]
)

script = Script(
    name="main",
    image="python:3.11-slim",
    source=build_script(request),
    env=[
        {"name": "PYTHON_CODE", "value": request.pythonCode},
        {"name": "DEPENDENCIES", "value": request.dependencies or ""}
    ],
    volume_mounts=[VolumeMount(name="task-results", mount_path="/mnt/results")]
)

workflow.add_template(script)
result = workflow.create()
```

## Next Steps

1. **Evaluate Hera SDK:** Review Hera documentation and examples
2. **Proof of Concept:** Create a small POC for workflow creation
3. **Plan Migration:** Create detailed migration plan with timeline
4. **Team Discussion:** Review this analysis with the team
5. **Start Migration:** Begin with Phase 1 (add SDK) and Phase 2 (refactor creation)

