# Persistent Volume File Manager with SVAR Integration

## Overview

This PR introduces a comprehensive file management interface for the Persistent Volume (PV) using the SVAR Svelte File Manager component. Users can now browse, view, copy, and manage files in the PV through an intuitive file manager interface integrated directly into the application.

## Key Features

### 1. SVAR Svelte File Manager Integration

**Frontend Component:**
- Integrated `@svar-ui/svelte-filemanager` for professional file browsing experience
- Full-featured file manager with grid/list views, search, and context menus
- Hierarchical file tree navigation
- File preview capabilities (especially for JSON files)

**UI/UX:**
- Modern, intuitive file manager interface
- Accessible from main page via "PV File Manager" button
- Opens in a modal dialog with proper sizing and overflow handling
- Responsive design with proper error handling and loading states

### 2. Backend API Endpoints

**New Endpoints:**
- `GET /api/v1/pv/files?path=/mnt/results` - List files and directories in the PV
- `GET /api/v1/pv/file?path=/mnt/results/file.json` - Read file content from the PV
- `POST /api/v1/pv/copy?source_path=...&destination_path=...` - Copy files within the PV

**Implementation Details:**
- Creates temporary Kubernetes pods that mount the PVC to access PV contents
- Handles both JSON and Python dict syntax in pod logs (for compatibility)
- Supports binary files (base64 encoded) and text files
- Proper error handling and pod cleanup
- Automatic duplicate filename handling (adds numbered suffix: `file_1.json`, `file_2.json`, etc.)

### 3. File Operations

**Copy/Paste Functionality:**
- Right-click context menu for file operations
- Copy files using context menu
- Paste files with automatic duplicate handling
- Real-time file list updates after operations
- Progress indicators during file operations

**File Viewing:**
- Click files to view their content
- JSON file preview with formatted display
- File metadata display (size, modification date)
- Close button to dismiss file content view

### 4. Progress Indicators

**Operation Feedback:**
- Visual progress bar (0-100%) for file operations
- Operation status messages (e.g., "Copying file.json... (1/2)")
- Percentage display for long-running operations
- Automatic cleanup when operations complete

**Supported Operations:**
- File copy operations with per-file progress
- Delete operations (placeholder for future implementation)
- Create operations (placeholder for future implementation)

### 5. Dialog Enhancements

**Dialog Component Improvements:**
- Added `closeOnEscape` prop to control Escape key behavior
- PV File Manager dialog configured to prevent accidental closure via Escape key
- Maintains backward compatibility (defaults to `true` for existing dialogs)

## Technical Details

### Backend Implementation

**PV File Access:**
- Uses temporary pods with PVC mounts to access PV contents
- Handles Python dict syntax in pod logs (fallback parsing)
- Improved error messages and debugging information
- Proper pod lifecycle management (create, wait, read logs, cleanup)

**File Copy Logic:**
- Validates source and destination paths
- Checks for existing files and generates unique names
- Uses `cp` command in temporary pod to perform actual file copy
- Returns success/error status with detailed error messages

**Error Handling:**
- Comprehensive error handling for pod creation failures
- Timeout handling for long-running operations
- Proper cleanup of temporary pods even on errors
- User-friendly error messages

### Frontend Implementation

**SVAR File Manager Integration:**
- Data transformation from backend format to SVAR format
- Hierarchical folder structure (explicit parent folders: `/`, `/mnt`, `/mnt/results`)
- Dynamic folder loading via `request-data` event
- File operation interception (`copy-files`) for custom handling

**State Management:**
- File data state management
- Loading and error states
- Selected file content state
- Operation progress state (in-progress, message, percentage)

**Event Handling:**
- `onOpen` handler for file/folder navigation
- `intercept('copy-files')` for custom copy logic
- `on('request-data')` for dynamic folder loading
- `api.exec('provide-data')` for real-time UI updates

**Context Menu Handling:**
- Context menu appears on right-click
- Paste menu appears after copying files
- Menu closes when clicking outside (via monkey-patch approach)
- Menu closes on Escape key press

## Files Changed

### Added Files
- `apps/frontend/src/PVFileManager.svelte` - Main file manager component with SVAR integration

### Modified Files
- `apps/backend/app/main.py`:
  - Added `list_pv_files()` endpoint for directory listing
  - Added `read_pv_file()` endpoint for file content reading
  - Added `copy_pv_file()` endpoint for file copying
  - Enhanced pod creation and log parsing logic
  - Improved error handling and validation
  
- `apps/frontend/src/App.svelte`:
  - Added "PV File Manager" button
  - Added dialog for PVFileManager component
  - Updated imports and component structure
  
- `apps/frontend/src/lib/components/ui/dialog.svelte`:
  - Added `closeOnEscape` prop to control Escape key behavior
  - Updated Escape key handler to respect the prop
  
- `apps/frontend/package.json`:
  - Added `@svar-ui/svelte-filemanager` dependency

## Usage Examples

### Browsing Files
1. Click "PV File Manager" button in main page
2. Browse files and folders using the file manager interface
3. Navigate using the file tree or breadcrumbs
4. Click files to view their content

### Copying Files
1. Right-click on a file
2. Select "Copy" from context menu
3. Navigate to destination folder
4. Right-click in destination folder
5. Select "Paste" from context menu
6. File is copied with automatic duplicate handling if needed

### Viewing File Content
1. Click on any file in the file manager
2. File content appears below the file manager
3. JSON files are displayed with formatted content
4. Click "Close" button to dismiss file content view

## Bug Fixes

1. **File List Not Showing**: Fixed by explicitly including parent folders in data structure for SVAR's hierarchical display
2. **Copy Operation Not Working**: Implemented backend copy API and frontend interception to handle actual file copying
3. **Filename Mismatch After Paste**: Fixed by immediately refreshing file list and updating SVAR's internal state with correct backend-generated filenames
4. **Context Menu Not Closing**: Implemented monkey-patch approach to detect and close context menus on outside click and Escape key
5. **Dialog Closing on Escape**: Added `closeOnEscape` prop to prevent accidental closure of PV File Manager dialog

## Testing Recommendations

1. **File Browsing:**
   - Test browsing empty directories
   - Test navigating through folder hierarchy
   - Test file list display with various file types
   - Test error handling (missing PVC, pod failures)

2. **File Operations:**
   - Test copying single files
   - Test copying multiple files
   - Test duplicate filename handling
   - Test copy to different directories
   - Verify file list updates after operations

3. **File Viewing:**
   - Test viewing JSON files
   - Test viewing text files
   - Test viewing binary files (base64 display)
   - Test file content close functionality

4. **UI/UX:**
   - Test context menu operations
   - Test context menu closing (click outside, Escape key)
   - Test progress indicators during operations
   - Test dialog behavior (Escape key, close button)
   - Test responsive design

5. **Error Handling:**
   - Test with missing PVC
   - Test with invalid file paths
   - Test with pod creation failures
   - Test with network errors

## Migration Notes

- **No breaking changes** - All changes are additive
- New dependency: `@svar-ui/svelte-filemanager` (requires `npm install --legacy-peer-deps`)
- PV File Manager is optional and doesn't affect existing functionality
- Backend endpoints are new and don't conflict with existing APIs

## Performance Considerations

- PV file access creates temporary pods (adds ~2-5 seconds overhead per operation)
- File list is fetched on each navigation (consider caching in future)
- Large files may take time to read (consider pagination or streaming in future)
- Multiple file operations are processed sequentially (consider parallelization in future)

## Security Considerations

- Path validation to prevent directory traversal attacks
- Temporary pods are cleaned up after use
- File operations are scoped to the PV mount point
- No arbitrary code execution (uses standard file operations)

## Future Enhancements

Potential improvements for future PRs:
- File upload/download functionality
- File deletion functionality
- File/folder creation functionality
- File editing capabilities
- File search and filtering
- Bulk file operations
- File preview for more file types (images, PDFs, etc.)
- Drag-and-drop file operations
- Keyboard shortcuts for common operations
- File operation history/undo
- File permissions management

