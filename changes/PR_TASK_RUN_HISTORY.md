# PR: Task Run History with Per-Run Code and Logs

## Summary
This PR implements task run history functionality, allowing users to view and manage multiple executions (runs) of the same logical task. Each run now maintains its own code snapshot, dependencies, and logs, enabling users to track changes and results across different executions.

## Key Features

### 1. Task Run History
- **Task Model**: Represents a logical task (code, dependencies) that can have multiple runs
- **TaskRun Model**: Represents individual executions of a task, each linked to an Argo Workflow
- Each run stores:
  - Unique workflow ID (Argo workflow name)
  - Run number (sequential)
  - Phase/status
  - Code snapshot (python_code, dependencies, requirements_file)
  - Timestamps (started_at, finished_at)

### 2. Per-Run Code Snapshots
- Each run stores its own code and dependencies at the time of execution
- Users can view the exact code that was used for each run
- Code changes between runs are preserved and viewable
- Frontend displays code from the selected run in the task detail dialog

### 3. Per-Run Log Isolation
- Logs are now isolated per run using `run_id` (new schema) or `workflow_id` filtering (old schema)
- Each run shows only its own logs, not logs from other runs
- Log fetching uses workflow_id to ensure proper isolation in both schemas

### 4. Rerun Functionality
- Users can rerun existing tasks with modified code
- Reruns create new TaskRun records while maintaining the same Task ID
- Each rerun preserves the code snapshot from when it was executed
- Frontend supports "Edit & Rerun" functionality

### 5. Backward Compatibility
- **Automatic Schema Detection**: Code detects whether database has new columns or old schema
- **Dynamic Column Addition**: Automatically adds `python_code`, `dependencies`, and `requirements_file` columns to `task_runs` if they don't exist
- **Dual Query Support**: Uses ORM for new schema, raw SQL for old schema
- **Graceful Fallback**: Works with both migrated and unmigrated databases

## Database Schema Changes

### New Tables
- `tasks`: Stores logical tasks (id, python_code, dependencies, requirements_file, timestamps)
- `task_runs`: Stores individual runs (id, task_id, workflow_id, run_number, phase, python_code, dependencies, requirements_file, timestamps)

### Modified Tables
- `task_logs`: Now uses `run_id` (ForeignKey to `task_runs`) instead of `task_id` for new schema
  - Old schema: Still uses `task_id` (backward compatible)
  - New schema: Uses `run_id` for proper run isolation

## API Changes

### New Endpoints
- `GET /api/v1/tasks/{task_id}/runs/{run_number}/logs` - Get logs for a specific run

### Modified Endpoints
- `POST /api/v1/tasks/submit` - Now accepts optional `taskId` for reruns
- `GET /api/v1/tasks/{task_id}` - Returns task with full run history
- `GET /api/v1/tasks/{task_id}/logs` - Accepts optional `run_number` parameter
- `GET /api/v1/tasks` - Returns tasks with latest run information

## Frontend Changes

### TaskDialog Component
- Added run selector dropdown to switch between different runs
- Displays run-specific code and dependencies
- Shows run-specific logs
- Displays run metadata (phase, timestamps)
- "Edit & Rerun" button pre-fills with selected run's code

### Task List
- Shows latest run information (phase, timestamps)
- Displays run count per task

## Technical Implementation

### Schema Detection
The code automatically detects the database schema by checking for column existence:
```python
inspector = sql_inspect(engine)
task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
has_python_code = 'python_code' in task_runs_columns
```

### Dynamic Column Addition
If columns don't exist, they're added automatically:
```python
db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS python_code TEXT"))
```

### Log Isolation Strategy
- **New Schema**: Filter by `run_id` directly
- **Old Schema**: Join `task_logs` with `task_runs` and filter by `workflow_id`, with pod_name pattern matching

## Migration Notes

### Automatic Migration
- No manual migration required
- Columns are added automatically on first use
- Existing data remains accessible

### Manual Migration (Optional)
If you prefer to migrate manually:
```sql
ALTER TABLE task_runs ADD COLUMN python_code TEXT;
ALTER TABLE task_runs ADD COLUMN dependencies TEXT;
ALTER TABLE task_runs ADD COLUMN requirements_file TEXT;
ALTER TABLE task_logs ADD COLUMN run_id INTEGER REFERENCES task_runs(id);
```

## Testing
- ✅ Task creation with code snapshots
- ✅ Task rerun with modified code
- ✅ Run history display
- ✅ Per-run log isolation
- ✅ Per-run code display
- ✅ Backward compatibility with old schema
- ✅ Dynamic column addition

## Breaking Changes
None - fully backward compatible

## Future Enhancements
- Run comparison view (diff between runs)
- Run rollback functionality
- Run tagging/labeling
- Run search and filtering

