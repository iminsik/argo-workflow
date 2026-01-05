# Persistent Volume Directory Viewer and Dependency Management

## Overview

This PR adds two major features to the Argo Workflow Manager:
1. **Persistent Volume Directory Viewer** - Browse and view files in the PV directly from the frontend
2. **Dependency Management with UV** - Allow tasks to install their own Python packages in isolated virtual environments using `uv`

## Key Features

### 1. Persistent Volume Directory Viewer

**Backend API Endpoints:**
- `GET /api/v1/pv/directories?path=/mnt/results` - List files and directories in the PV
- `GET /api/v1/pv/file?path=/mnt/results/file.json` - Get file content from the PV

**Implementation Details:**
- Creates temporary pods that mount the PVC to access PV contents
- Handles both JSON and Python dict syntax in pod logs (for compatibility)
- Supports binary files (base64 encoded) and text files
- Proper error handling and pod cleanup

**Frontend Features:**
- New `PVDirectoriesViewer` component for browsing directories
- Accessible from main page via "PV Directories" button
- Accessible from task detail dialog via "PV Directories" tab
- JSON file viewing with syntax highlighting using Monaco Editor
- File navigation (root, parent directory)
- File metadata display (size, modification date)
- Refresh functionality

**UI/UX:**
- Clean table view for directory listings
- Syntax-highlighted JSON viewer
- Responsive design with proper error handling
- Loading states and error messages

### 2. Dependency Management with UV

**Backend Changes:**
- Updated `TaskSubmitRequest` model to accept:
  - `dependencies`: Space or comma-separated package names (e.g., "numpy pandas")
  - `requirementsFile`: Requirements.txt format content
- Automatic template selection:
  - Uses script template (`python-processor-with-deps.yaml`) when dependencies are provided
  - Falls back to container template for simple tasks without dependencies
- Script template handling:
  - Creates isolated virtual environment per task
  - Installs `uv` if not present
  - Installs dependencies before executing Python code
  - Supports both package list and requirements.txt format

**Workflow Template:**
- New `python-processor-with-deps.yaml` template:
  - Uses `bash` instead of `sh` for better compatibility
  - Creates venv at `/tmp/venv-{workflow-name}`
  - Installs dependencies using `uv pip install`
  - Executes Python code with dependencies available

**Frontend Changes:**
- Added collapsible "Dependencies (Optional)" section in task submission dialog
- Two input methods:
  - Package dependencies: Text input for space/comma-separated packages
  - Requirements file: Textarea for requirements.txt format
- Dependencies display in task details:
  - Badge in task detail header
  - Highlighted section in Code tab above the code editor
- Updated task interface to include `dependencies` field

**Security & Validation:**
- Basic input validation (length limits, dangerous pattern detection)
- Isolated environments per task (no dependency conflicts)
- Proper error handling for installation failures

## Technical Details

### Backend Improvements

**PV Directory Access:**
- Uses temporary pods with PVC mounts to access PV contents
- Handles Python dict syntax in pod logs (fallback parsing)
- Improved error messages and debugging information
- Proper pod lifecycle management (create, wait, read logs, cleanup)

**Dependency Management:**
- Script template approach for maximum flexibility
- Environment variable injection for Python code and dependencies
- Requirements file support via heredoc in shell script
- Backward compatible (tasks without dependencies use original template)

**Code Extraction:**
- Enhanced Python code extraction to support both container and script templates
- Extracts code from `container.args[0]` (container templates)
- Extracts code from `script.env.PYTHON_CODE` (script templates)
- Extracts dependencies from `script.env.DEPENDENCIES`

### Frontend Improvements

**PV Viewer Component:**
- File system navigation
- JSON syntax highlighting
- File content viewing
- Error handling and retry logic

**Dependency UI:**
- Clean, intuitive interface
- Helpful placeholder text and examples
- Visual indicators for tasks with dependencies
- Proper form state management

## Files Changed

### Added Files
- `apps/frontend/src/PVDirectoriesViewer.svelte` - PV directory browser component
- `infrastructure/argo/python-processor-with-deps.yaml` - Workflow template with dependency support
- `infrastructure/argo/DEPENDENCY_MANAGEMENT.md` - Documentation for dependency management
- `infrastructure/argo/Dockerfile.python-uv` - Optional Docker image with uv pre-installed

### Modified Files
- `apps/backend/app/main.py`:
  - Added PV directory and file reading endpoints
  - Added dependency support to task submission
  - Enhanced Python code extraction for script templates
  - Added dependency extraction from workflows
  - Improved error handling and validation
  
- `apps/frontend/src/App.svelte`:
  - Added PV Directories button and modal
  - Added dependency input fields to task submission dialog
  - Updated task interface to include dependencies
  
- `apps/frontend/src/TaskDialog.svelte`:
  - Added dependencies display (badge and highlighted section)
  - Updated task interface

- `infrastructure/argo/python-processor-with-deps.yaml`:
  - Script template with uv installation and dependency management
  - Uses bash for better shell compatibility

## Usage Examples

### PV Directory Viewer
1. Click "PV Directories" button in main page
2. Browse directories and files
3. Click JSON files to view with syntax highlighting
4. Navigate using "Root" and "Parent" buttons

### Dependency Management

**Simple Package List:**
```json
{
  "pythonCode": "import numpy as np; print(np.array([1,2,3]))",
  "dependencies": "numpy"
}
```

**Multiple Packages:**
```json
{
  "pythonCode": "import pandas as pd; import requests; ...",
  "dependencies": "pandas requests numpy"
}
```

**With Versions:**
```json
{
  "pythonCode": "...",
  "dependencies": "numpy==1.24.0 pandas>=2.0.0"
}
```

**Requirements File:**
```json
{
  "pythonCode": "...",
  "requirementsFile": "numpy==1.24.0\npandas>=2.0.0\nrequests==2.31.0"
}
```

## Bug Fixes

1. **JSON Parsing Error**: Fixed pod log parsing to handle Python dict syntax as fallback
2. **Script Template Validation**: Fixed ScriptTemplate object creation issues by using dict approach for script templates
3. **Bash vs Sh**: Changed script template to use `bash` instead of `sh` for `source` command compatibility
4. **Python Code Extraction**: Fixed code extraction to support script templates (extracts from PYTHON_CODE env var)
5. **Dependency Display**: Fixed missing dependencies in task details

## Testing Recommendations

1. **PV Directory Viewer:**
   - Test browsing empty directories
   - Test viewing JSON files with syntax highlighting
   - Test navigation (root, parent, subdirectories)
   - Test error handling (missing PVC, pod failures)

2. **Dependency Management:**
   - Test task submission with simple package list
   - Test task submission with requirements file
   - Test tasks with conflicting dependency versions (isolation)
   - Test tasks without dependencies (backward compatibility)
   - Verify dependencies are displayed in task details
   - Test dependency installation failures

3. **Integration:**
   - Test PV viewer from both main page and task dialog
   - Test dependency management with various package formats
   - Verify Python code execution with installed dependencies

## Migration Notes

- **No breaking changes** - All changes are backward compatible
- Tasks without dependencies continue to work as before
- PV viewer is optional and doesn't affect existing functionality
- Dependency management is opt-in (only when dependencies are specified)

## Future Enhancements

Potential improvements for future PRs:
- Dependency caching in persistent volume
- Package whitelisting/blacklisting for security
- Dependency version conflict detection
- PV file upload/download functionality
- Directory creation and file editing in PV
- Dependency installation progress tracking

## Performance Considerations

- PV directory access creates temporary pods (adds ~2-5 seconds overhead)
- Dependency installation adds time to task execution (depends on package size)
- Each task gets isolated venv (no caching between tasks currently)
- Consider implementing venv caching for common dependencies in future

## Security Considerations

- Basic input validation for dependencies (length, dangerous patterns)
- Isolated environments prevent dependency conflicts
- Temporary pods are cleaned up after use
- No arbitrary code execution in dependency installation (uses uv pip install)

