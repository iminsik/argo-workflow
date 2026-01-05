# Dependency Management with UV - Recommendations

This document outlines recommendations for allowing each task to install its own dependency packages using `uv` in isolated environments.

## Overview

The goal is to enable tasks to:
1. Specify dependencies (packages to install)
2. Install them in an isolated virtual environment using `uv`
3. Execute Python code with access to those dependencies
4. Maintain isolation between different tasks

## Recommended Approaches

### Option 1: Script Template with UV (Recommended)

**Pros:**
- Full control over the execution environment
- Easy to customize per task
- Supports complex dependency scenarios
- Isolated virtual environment per task

**Cons:**
- Slightly more complex workflow template
- Requires script execution instead of simple container command

**Implementation:**
- Use Argo's `script` template instead of `container` template
- Install `uv` at runtime (or use pre-built image)
- Create isolated venv per task
- Install dependencies before executing code

**Example Workflow Template:**
See `python-processor-with-deps.yaml` for a complete example.

### Option 2: Multi-Stage Container with Pre-installed UV

**Pros:**
- Faster execution (uv pre-installed)
- Simpler workflow template
- Can cache common dependencies

**Cons:**
- Requires building and maintaining custom images
- Less flexible for per-task customization

**Implementation:**
- Build custom Docker image with `uv` pre-installed
- Use in workflow template
- Still create isolated venv per task

### Option 3: Init Container Pattern

**Pros:**
- Separation of concerns (install vs execute)
- Can reuse init container across tasks

**Cons:**
- More complex workflow structure
- Requires multiple containers per task

## Recommended Implementation Details

### 1. API Changes

Update `TaskSubmitRequest` to include optional dependencies:

```python
class TaskSubmitRequest(BaseModel):
    pythonCode: str = "print('Processing task in Kind...')"
    dependencies: Optional[str] = None  # Space or comma-separated package names
    requirementsFile: Optional[str] = None  # requirements.txt content
```

### 2. Dependency Format Options

Support multiple formats:
- **Space-separated**: `"numpy pandas requests"`
- **Comma-separated**: `"numpy,pandas,requests"`
- **Requirements file**: Multi-line string with requirements.txt format
- **Version pinning**: `"numpy==1.24.0 pandas>=2.0.0"`

### 3. Virtual Environment Strategy

**Per-task isolation:**
- Create venv in `/tmp/venv-{workflow-name}` (ephemeral)
- Or use `/mnt/results/.venv-{workflow-name}` (persistent, optional)

**Benefits:**
- Complete isolation between tasks
- No dependency conflicts
- Can cache venvs if using persistent storage

### 4. Security Considerations

1. **Package Validation:**
   - Whitelist allowed packages (optional)
   - Block known malicious packages
   - Rate limit package installations

2. **Resource Limits:**
   - Set memory limits for pip/uv operations
   - Timeout for dependency installation
   - Disk space limits for venv

3. **Network Access:**
   - Consider using private PyPI mirrors
   - Block access to arbitrary URLs
   - Use package indexes you trust

### 5. Performance Optimizations

1. **Caching:**
   - Cache venvs in persistent volume (optional)
   - Use `uv`'s built-in caching
   - Share common dependencies across tasks

2. **Parallel Installation:**
   - `uv` is already fast, but can optimize further
   - Install dependencies in parallel when possible

3. **Base Image:**
   - Use slim Python images
   - Pre-install common packages if needed

## Implementation Steps

### Step 1: Update API Model

```python
class TaskSubmitRequest(BaseModel):
    pythonCode: str
    dependencies: Optional[str] = None
    requirementsFile: Optional[str] = None
```

### Step 2: Update Workflow Template

Use the script template approach (see `python-processor-with-deps.yaml`):
- Install `uv` if not present
- Create isolated venv
- Install dependencies from env vars or file
- Execute Python code

### Step 3: Update Backend Logic

Modify `start_task` endpoint to:
1. Accept dependencies in request
2. Pass dependencies to workflow as env vars
3. Optionally create requirements.txt file if provided

### Step 4: Frontend Updates

Add UI for specifying dependencies:
- Text input for package names
- Optional requirements.txt editor
- Show installed packages in task details

## Example Usage

### Simple Package List
```json
{
  "pythonCode": "import numpy as np; print(np.array([1,2,3]))",
  "dependencies": "numpy"
}
```

### Multiple Packages
```json
{
  "pythonCode": "import pandas as pd; import requests; ...",
  "dependencies": "pandas requests numpy"
}
```

### With Versions
```json
{
  "pythonCode": "...",
  "dependencies": "numpy==1.24.0 pandas>=2.0.0"
}
```

### Requirements File
```json
{
  "pythonCode": "...",
  "requirementsFile": "numpy==1.24.0\npandas>=2.0.0\nrequests==2.31.0"
}
```

## Testing Recommendations

1. **Test isolation:** Run two tasks with conflicting dependency versions
2. **Test performance:** Measure time for dependency installation
3. **Test error handling:** Invalid package names, network failures
4. **Test caching:** Verify venv caching works if implemented

## Migration Path

1. **Phase 1:** Add optional dependencies support (backward compatible)
2. **Phase 2:** Update UI to show dependency input
3. **Phase 3:** Add dependency caching if needed
4. **Phase 4:** Add security features (whitelisting, etc.)

## Alternative: Use Existing Solutions

Consider using:
- **Poetry** for dependency management
- **Pipenv** for virtual environments
- **Conda** for more complex environments

However, `uv` is recommended because:
- Fast installation
- Modern Python package manager
- Good compatibility with pip
- Active development

