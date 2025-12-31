# Frontend Migration to Svelte and Infrastructure Improvements

## Overview

This PR introduces a major frontend refactoring from React to Svelte, along with significant infrastructure improvements including Docker containerization, Bunnyshell deployment configuration, and enhanced backend functionality for task processing and log management.

## Key Changes

### Frontend Migration: React → Svelte

**Major Refactoring:**
- Migrated entire frontend from React/TypeScript to Svelte 5
- Replaced React components with Svelte components:
  - `App.tsx` → `App.svelte`
  - `main.tsx` → `main.ts`
  - Added new Svelte components: `MonacoEditor.svelte`, `TaskDialog.svelte`, `TaskRow.svelte`

**UI Framework & Styling:**
- Integrated Tailwind CSS with PostCSS configuration
- Added shadcn-svelte component library
- Implemented UI components: `badge.svelte`, `button.svelte`, `dialog.svelte`, `table.svelte`
- Replaced `@monaco-editor/react` with direct `monaco-editor` integration
- Updated dependencies: `lucide-react` → `lucide-svelte`

**Configuration:**
- Added `svelte.config.js` for Svelte build configuration
- Added `tailwind.config.js` for Tailwind CSS setup
- Added `postcss.config.js` for PostCSS processing
- Updated `tsconfig.json` and added `tsconfig.node.json` for TypeScript configuration
- Updated `vite.config.ts` to use Svelte plugin instead of React plugin
- Added `components.json` for shadcn-svelte component configuration

### Infrastructure & Deployment

**Docker Containerization:**
- Added `Dockerfile` and `.dockerignore` for both backend and frontend applications
- Updated `Dockerfile.dev` for frontend development environment
- Configured Docker builds for production deployment

**Bunnyshell Integration:**
- Added `bunnyshell.yaml` configuration file for cloud deployment
- Configured environment setup for Bunnyshell platform

### Backend Enhancements

**Task Processing Improvements:**
- Enhanced task serialization to preserve environment variables in addition to volume mounts
- Updated backend logic to ensure `ARGO_WORKFLOW_NAME` is included in container configuration
- Modified Python processor YAML to define `ARGO_WORKFLOW_NAME` environment variable

**Log Management:**
- Improved error handling for Kubernetes pod log retrieval
- Added checks to only fetch logs for ready pods (skip Pending/Initializing pods)
- Enhanced log fetching logic to handle pod initialization states gracefully
- Improved error messages and handling for log retrieval failures

**WebSocket Enhancements:**
- Implemented error handling for WebSocket connections
- Added graceful disconnection and reconnection logic
- Optimized log updates based on content changes
- Added checks to skip WebSocket connections for completed tasks
- Implemented periodic task status updates

**CORS Configuration:**
- Made CORS origins configurable via `CORS_ORIGINS` environment variable
- Defaults to `http://localhost:5173,http://localhost:3000` for local development

### Frontend Task Management

**Task Log Handling:**
- Updated frontend to track fetched logs for completed tasks
- Prevented redundant log fetch attempts
- Ensured logs are displayed when accessing completed tasks
- Improved UI to reflect loading states more clearly

**WebSocket Management:**
- Implemented manual WebSocket connection management
- Prevented unnecessary reconnections
- Optimized log updates based on content changes

### Documentation

- Updated `README.md` with Bunnyshell deployment information
- Added deployment prerequisites and configuration notes

## Files Changed

### Added Files
- `apps/backend/Dockerfile`
- `apps/backend/.dockerignore`
- `apps/frontend/Dockerfile`
- `apps/frontend/.dockerignore`
- `apps/frontend/components.json`
- `apps/frontend/postcss.config.js`
- `apps/frontend/svelte.config.js`
- `apps/frontend/tailwind.config.js`
- `apps/frontend/tsconfig.json`
- `apps/frontend/tsconfig.node.json`
- `apps/frontend/src/App.svelte`
- `apps/frontend/src/MonacoEditor.svelte`
- `apps/frontend/src/TaskDialog.svelte`
- `apps/frontend/src/TaskRow.svelte`
- `apps/frontend/src/app.css`
- `apps/frontend/src/app.d.ts`
- `apps/frontend/src/lib/components/ui/badge.svelte`
- `apps/frontend/src/lib/components/ui/button.svelte`
- `apps/frontend/src/lib/components/ui/dialog.svelte`
- `apps/frontend/src/lib/components/ui/table.svelte`
- `apps/frontend/src/lib/utils.ts`
- `apps/frontend/src/main.ts`
- `apps/frontend/src/vite-env.d.ts`
- `bunnyshell.yaml`

### Modified Files
- `README.md`
- `apps/backend/app/main.py`
- `apps/frontend/Dockerfile.dev`
- `apps/frontend/index.html`
- `apps/frontend/package.json`
- `apps/frontend/package-lock.json`
- `apps/frontend/vite.config.ts`
- `infrastructure/argo/python-processor.yaml`

### Deleted Files
- `apps/frontend/src/App.tsx`
- `apps/frontend/src/main.tsx`

## Statistics

- **34 files changed**
- **3,777 insertions(+), 2,059 deletions(-)**
- Net change: +1,718 lines

## Testing Recommendations

1. **Frontend Testing:**
   - Verify all UI components render correctly
   - Test task creation, editing, and deletion
   - Verify Monaco editor integration
   - Test WebSocket log streaming
   - Verify responsive design with Tailwind CSS

2. **Backend Testing:**
   - Test task submission with environment variables
   - Verify log fetching for various pod states
   - Test WebSocket connection handling
   - Verify CORS configuration with different origins

3. **Infrastructure Testing:**
   - Test Docker builds for both frontend and backend
   - Verify Bunnyshell deployment configuration
   - Test Kubernetes pod log retrieval

## Migration Notes

- Frontend now uses Svelte 5 instead of React 18
- Monaco Editor is now directly integrated instead of using React wrapper
- UI components use shadcn-svelte instead of React components
- Styling migrated from inline styles to Tailwind CSS
- Build process updated to use Svelte compiler instead of React

## Breaking Changes

- Frontend framework changed from React to Svelte - any React-specific code or dependencies need to be migrated
- Package dependencies significantly changed - `npm install` required
- Build process changed - use `npm install --legacy-peer-deps` if needed

