# Add DAG Flow Editor with Template Preview and Dagre Layout

## Overview
This PR implements a comprehensive DAG (Directed Acyclic Graph) flow editor for creating and managing multi-step workflows, similar to Windmill flows. It includes visual flow editing, automatic layout using Dagre, workflow template preview, and full integration with Argo Workflows.

## Features

### 1. Visual Flow Editor (`FlowEditor.svelte`)
- **DAG Canvas**: Interactive node-based editor using `@xyflow/svelte` for creating flow steps and dependencies
- **Step Management**: 
  - Add/delete steps with visual nodes
  - Connect steps to define dependencies (edges)
  - Edit step details (name, Python code, dependencies) in a side panel
  - Monaco Editor integration for syntax-highlighted Python code editing
- **Dagre Layout**: Automatic hierarchical layout of nodes using `@dagrejs/dagre` library
  - Nodes are automatically arranged in a top-to-bottom DAG structure
  - Layout is applied when steps are added, connected, or deleted
  - Manual node dragging is still supported
- **Flow Name Editing**: Editable flow name input field in the editor header
- **Template Preview**: Button to preview the Argo Workflow YAML template before running

### 2. Flow Management
- **Flow List View**: Table-based list of all flows with status, step count, and actions
- **Flow CRUD Operations**: Create, read, update, and delete flows via API
- **Flow Execution**: Run entire flows or individual steps independently
- **Flow Runs Dialog**: View run history with real-time status updates and step-level details

### 3. Workflow Template Preview
- **Flow Editor Preview**: Generate and view Argo Workflow YAML template from current flow definition
  - Endpoint: `POST /api/v1/flows/preview-template`
  - Shows complete workflow spec including all step templates, DAG structure, volumes, and environment variables
- **Run Template View**: View the actual Argo Workflow template for any completed run
  - Endpoint: `GET /api/v1/flows/{flow_id}/runs/{run_number}/template`
  - Displays the exact workflow that was submitted to Kubernetes
- **Syntax Highlighting**: Both previews use Monaco Editor with YAML syntax highlighting

### 4. Backend Enhancements

#### Database Models (`database.py`)
- `Flow`: Stores flow definitions with JSONB for steps and edges
- `FlowRun`: Tracks individual workflow executions
- `FlowStepRun`: Tracks individual step executions within a flow run
- `FlowStepLog`: Stores logs for each step execution

#### API Endpoints (`main.py`)
- `POST /api/v1/flows`: Create a new flow
- `GET /api/v1/flows`: List all flows
- `GET /api/v1/flows/{flow_id}`: Get flow details
- `PUT /api/v1/flows/{flow_id}`: Update flow
- `DELETE /api/v1/flows/{flow_id}`: Delete flow
- `POST /api/v1/flows/{flow_id}/run`: Run an entire flow
- `POST /api/v1/flows/{flow_id}/steps/{step_id}/run`: Run an individual step
- `GET /api/v1/flows/{flow_id}/runs`: List runs for a flow
- `GET /api/v1/flows/{flow_id}/runs/{run_number}`: Get run details with real-time status updates
- `GET /api/v1/flows/{flow_id}/runs/{run_number}/logs`: Get logs for a run
- `GET /api/v1/flows/{flow_id}/runs/{run_number}/template`: Get workflow template for a run
- `POST /api/v1/flows/preview-template`: Generate preview template from flow definition

#### Workflow Generation (`workflow_hera_flow.py`)
- `create_flow_workflow_with_hera()`: Creates and submits multi-step Argo Workflows using Hera SDK
- `generate_flow_workflow_template()`: Generates workflow template without submitting (for preview)
- `build_step_script_source()`: Builds bash scripts for each step with:
  - Dependency installation using `uv`
  - Helper functions for reading/writing step outputs via PV files
  - Python code execution
- Cycle detection to ensure DAG is acyclic
- Proper volume mounts and environment variable configuration

### 5. Frontend Routing (`routes.ts`, `App.svelte`)
- Client-side routing with browser History API
- Routes: `/tasks` (default), `/flows`, `/flows/{flow_id}`, `/flows/new`
- URL state management for flow editor
- Automatic redirect from `/` to `/tasks`

### 6. UI/UX Improvements
- Fixed flow name input field reactivity issues
- Improved dialog close button functionality
- Real-time status polling for active flow runs
- Better error handling and user feedback
- Consistent styling with existing task views

## Technical Details

### Dependencies Added
- `@dagrejs/dagre`: Automatic graph layout for DAG visualization
- `@xyflow/svelte`: Node-based flow editor component

### Architecture
- **Frontend**: Svelte 5 with reactive state management
- **Backend**: FastAPI with SQLAlchemy ORM
- **Workflow Engine**: Argo Workflows via Hera SDK
- **Data Exchange**: Persistent Volumes (PV) for sharing data between steps

### Data Flow
1. User creates flow definition in frontend (nodes + edges)
2. Flow is saved to PostgreSQL database
3. When run, backend generates Argo Workflow using Hera SDK
4. Workflow is submitted to Kubernetes
5. Steps execute in order based on DAG dependencies
6. Each step can read outputs from previous steps via PV files (`/mnt/results/{step_id}/output.json`)
7. Status updates are fetched from Argo Workflows API and synced to database

## Testing
- [x] Create flows with multiple steps
- [x] Connect steps to form dependencies
- [x] Edit step details (name, code, dependencies)
- [x] Save and load flows
- [x] Run entire flows
- [x] Run individual steps
- [x] View workflow templates (preview and actual runs)
- [x] View run history and step statuses
- [x] Dagre layout automatically arranges nodes

## Breaking Changes
None - this is a new feature addition.

## Migration Notes
- New database tables will be created automatically on first run
- Existing tasks/flows are unaffected

## Screenshots
- Flow Editor with DAG canvas
- Step editing panel with Monaco Editor
- Flow Runs dialog with template view
- Template preview dialog with syntax highlighting

## Related Issues
- Implements DAG workflow functionality as requested
- Adds template preview capability
- Improves flow editor UX with automatic layout

