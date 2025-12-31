# Log Fetching and Storage Explanation

## Overview

Task logs are now stored in a PostgreSQL database for persistence and faster retrieval. The system uses a hybrid approach: it fetches logs from the database when available, and falls back to Kubernetes pods when needed.

## Architecture

### Database Storage

- **Database**: PostgreSQL (running in Docker Compose)
- **Table**: `task_logs`
- **Schema**:
  - `id`: Primary key (auto-increment)
  - `task_id`: Workflow/task identifier (indexed)
  - `node_id`: Argo workflow node identifier
  - `pod_name`: Kubernetes pod name
  - `phase`: Workflow phase (Running, Succeeded, Failed, etc.)
  - `logs`: Log content (Text field)
  - `created_at`: Timestamp when log entry was created
  - `updated_at`: Timestamp when log entry was last updated

### Log Fetching Flow

#### 1. REST Endpoint (`GET /api/v1/tasks/{task_id}/logs`)

```
1. Check database for existing logs
   ↓
2. If found in database → Return logs from database
   ↓
3. If not found → Fetch from Kubernetes pods
   ↓
4. Save fetched logs to database
   ↓
5. Return logs from Kubernetes
```

**Benefits:**
- Fast retrieval for previously fetched logs
- Persistent storage even after pods are deleted
- Automatic fallback to Kubernetes for new logs

#### 2. WebSocket Endpoint (`WS /ws/tasks/{task_id}/logs`)

```
1. Get logs from database (if available)
   ↓
2. Fetch latest logs from Kubernetes pods
   ↓
3. Save/update logs in database
   ↓
4. Send logs to client via WebSocket
   ↓
5. Repeat every 2 seconds until workflow completes
   ↓
6. Final save when workflow finishes
```

**Benefits:**
- Real-time log streaming
- Automatic persistence of all logs
- Database acts as cache for faster subsequent requests

### Key Functions

#### `fetch_logs_from_kubernetes(task_id, namespace)`
- Fetches logs directly from Kubernetes pods
- Handles pod name resolution (displayName, node ID, label selector)
- Returns list of log entries: `[{node, pod, phase, logs}, ...]`

#### `save_logs_to_database(task_id, logs, db)`
- Saves or updates logs in the database
- Updates existing entries if they already exist (by task_id + node_id + pod_name)
- Creates new entries for new log sources

#### `get_logs_from_database(task_id, db)`
- Retrieves all logs for a task from the database
- Returns logs ordered by creation time
- Returns empty list if no logs found

## Database Connection

- **Connection String**: `postgresql://postgres:password@postgres:5432/postgres`
- **Environment Variable**: `DATABASE_URL` (can be overridden)
- **Initialization**: Database tables are created automatically on backend startup
- **Health Check**: Docker Compose ensures PostgreSQL is ready before starting backend

## Benefits of Database Storage

1. **Persistence**: Logs survive pod deletion
2. **Performance**: Faster retrieval from database than Kubernetes API
3. **Reliability**: Can retrieve logs even if Kubernetes cluster is temporarily unavailable
4. **History**: Maintains log history for completed tasks
5. **Scalability**: Database can handle many concurrent log requests

## Migration Notes

- Existing functionality remains the same from the frontend perspective
- Logs are automatically saved to database on first fetch
- No manual migration needed - database is initialized automatically
- If database is unavailable, system falls back to Kubernetes-only mode (with warnings)

