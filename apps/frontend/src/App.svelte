<script lang="ts">
  import { onMount, onDestroy, untrack } from 'svelte';
  import { Play, RefreshCw, X, XCircle, Trash2 } from 'lucide-svelte';
  import MonacoEditor from './MonacoEditor.svelte';
  import TaskRow from './TaskRow.svelte';
  import TaskDialog from './TaskDialog.svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Dialog from '$lib/components/ui/dialog.svelte';

  interface Task {
    id: string;
    generateName: string;
    phase: string;
    startedAt: string;
    finishedAt: string;
    createdAt: string;
    pythonCode: string;
    dependencies?: string;
    message?: string;
  }

  interface LogEntry {
    node: string;
    pod: string;
    phase: string;
    logs: string;
  }

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  // Convert to $state runes
  let tasks = $state<Task[]>([]);
  let initialLoading = $state(true);
  let selectedTaskId = $state<string | null>(null);
  let activeTab = $state<'code' | 'logs'>('code');
  
  // Track previous values to detect actual changes
  let prevSelectedTaskId: string | null = null;
  let prevActiveTab: 'code' | 'logs' = 'code';
  let taskLogs = $state<LogEntry[]>([]);
  let loadingLogs = $state(false);
  let showSubmitModal = $state(false);
  const defaultPythonCode = "print('Processing task in Kind...')";
  let pythonCode = $state(defaultPythonCode);
  let dependencies = $state('');
  let requirementsFile = $state('');
  let showDependencies = $state(false);
  let submitting = $state(false);

  // Reset form when dialog closes
  $effect(() => {
    if (!showSubmitModal) {
      pythonCode = defaultPythonCode;
      dependencies = '';
      requirementsFile = '';
      showDependencies = false;
    }
  });

  let ws: WebSocket | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  let lastLogsHash = '';
  let taskRefreshInterval: ReturnType<typeof setInterval> | null = null;
  const TASK_REFRESH_INTERVAL_MS = 2000; // 2 seconds - reduced to catch faster phase transitions
  let currentWebSocketTaskId: string | null = null;
  
  // Track the last connected task/tab to prevent unnecessary reconnections
  let lastConnectedTaskId: string | null = null;
  let lastConnectedTab: 'code' | 'logs' | null = null;
  
  // Track which completed tasks have already had their final logs fetched
  let completedTasksWithLogsFetched = $state<Set<string>>(new Set());
  
  // Manual subscription pattern - only update when values actually change
  // This avoids the reactive effect system causing unnecessary re-runs

  // Convert reactive statement to $derived
  let selectedTask = $derived(selectedTaskId ? tasks.find(t => t.id === selectedTaskId) || null : null);

  function getPhaseColor(phase: string): string {
    switch (phase) {
      case 'Succeeded': return '#10b981';
      case 'Failed': return '#ef4444';
      case 'Running': return '#3b82f6';
      case 'Pending': return '#f59e0b';
      default: return '#6b7280';
    }
  }

  function tasksChanged(oldTasks: Task[], newTasks: Task[]): boolean {
    if (oldTasks.length !== newTasks.length) return true;
    
    const oldMap = new Map(oldTasks.map(t => [t.id, t]));
    
    for (const newTask of newTasks) {
      const oldTask = oldMap.get(newTask.id);
      if (!oldTask) return true;
      
      if (
        oldTask.phase !== newTask.phase ||
        oldTask.startedAt !== newTask.startedAt ||
        oldTask.finishedAt !== newTask.finishedAt
      ) {
        return true;
      }
    }
    
    return false;
  }

  async function fetchTasks(isInitial = false) {
    try {
      if (isInitial) {
        initialLoading = true;
      }
      const res = await fetch(`${apiUrl}/api/v1/tasks`);
      const data = await res.json();
      const newTasks = data.tasks || [];
      
      if (tasksChanged(tasks, newTasks)) {
        tasks = newTasks;
      }
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
    } finally {
      if (isInitial) {
        initialLoading = false;
      }
    }
  }

  function logsHash(logs: LogEntry[]): string {
    return logs.map(l => `${l.node}:${l.pod}:${l.phase}:${l.logs.length}:${l.logs.slice(-100)}`).join('|');
  }

  function getTotalLogsLength(logs: LogEntry[]): number {
    return logs.reduce((total, log) => total + log.logs.length, 0);
  }

  function hasMoreLogs(oldLogs: LogEntry[], newLogs: LogEntry[]): boolean {
    // Always update if old logs are empty (initial load)
    if (oldLogs.length === 0 && newLogs.length > 0) return true;
    
    // If new logs have more entries, they have more content
    if (newLogs.length > oldLogs.length) return true;
    
    // If same number of entries, check if any log entry has more content
    if (newLogs.length === oldLogs.length) {
      for (let i = 0; i < newLogs.length; i++) {
        const oldLog = oldLogs[i];
        const newLog = newLogs[i];
        
        // If entry doesn't exist in old logs, it's new content
        if (!oldLog) return true;
        
        // If logs content is longer, it has more content
        if (newLog.logs.length > oldLog.logs.length) return true;
        
        // If logs content changed and is longer or equal but different (new content appended)
        if (newLog.logs !== oldLog.logs && newLog.logs.length >= oldLog.logs.length) {
          // Check if new logs contain old logs (content was appended)
          if (newLog.logs.startsWith(oldLog.logs)) return true;
        }
      }
    }
    
    // Check total length as fallback
    const oldTotal = getTotalLogsLength(oldLogs);
    const newTotal = getTotalLogsLength(newLogs);
    return newTotal > oldTotal;
  }

  function disconnectWebSocket() {
    if (ws) {
      ws.close();
      ws = null;
    }
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    reconnectAttempts = 0;
    currentWebSocketTaskId = null;
  }

  function connectWebSocket(taskId: string) {
    // Check if task is already completed - don't connect WebSocket for completed tasks
    const task = tasks.find(t => t.id === taskId);
    if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
      console.log('Task is completed, skipping WebSocket connection:', taskId, task.phase);
      // Ensure we've fetched final logs once
      if (!completedTasksWithLogsFetched.has(taskId)) {
        completedTasksWithLogsFetched.add(taskId);
        fetchLogsViaRest(taskId);
      }
      return;
    }
    
    // Don't reconnect if already connected to the same task
    if (ws && ws.readyState === WebSocket.OPEN && currentWebSocketTaskId === taskId) {
      console.log('WebSocket already connected to task:', taskId);
      return;
    }
    
    // Additional check: if we're already in the process of connecting to this task, don't connect again
    if (currentWebSocketTaskId === taskId && ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
      console.log('WebSocket connection already in progress or open for task:', taskId);
      return;
    }
    
    console.log('Connecting WebSocket to task:', taskId);
    lastLogsHash = '';
    disconnectWebSocket();
    currentWebSocketTaskId = taskId;

    const wsUrl = apiUrl.replace(/^http/, 'ws') + `/ws/tasks/${taskId}/logs`;
    
    loadingLogs = true;
    reconnectAttempts = 0;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected for task:', taskId);
        loadingLogs = false;
        reconnectAttempts = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          // Check if task is completed - stop processing messages for completed tasks
          const task = tasks.find(t => t.id === taskId);
          if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
            console.log('Task completed, closing WebSocket:', taskId, task.phase);
            // Mark as fetched before disconnecting
            if (!completedTasksWithLogsFetched.has(taskId)) {
              completedTasksWithLogsFetched.add(taskId);
            }
            disconnectWebSocket();
            loadingLogs = false;
            return;
          }
          
          if (message.type === 'logs') {
            const newLogs = message.data || [];
            const newHash = logsHash(newLogs);
            const logsChanged = newHash !== lastLogsHash && hasMoreLogs(taskLogs, newLogs);
            
            // Check if phases in log entries have changed (even if log content hasn't)
            const phasesChanged = newLogs.length > 0 && taskLogs.length > 0 && 
              newLogs.some((newLog, i) => {
                const oldLog = taskLogs[i];
                return oldLog && newLog.phase !== oldLog.phase;
              });
            
            // Update logs if they have more content OR if phases have changed
            // This ensures log entry phases stay in sync with workflow phase
            if (logsChanged || phasesChanged) {
              lastLogsHash = newHash;
              taskLogs = newLogs;
            }
            
            // Always update task phase if provided in the message (even if logs haven't changed)
            // This ensures phase transitions are captured immediately
            if (message.workflow_phase) {
              const taskIndex = tasks.findIndex(t => t.id === taskId);
              if (taskIndex !== -1 && tasks[taskIndex].phase !== message.workflow_phase) {
                // Create a new array to ensure reactivity
                tasks = tasks.map((t, i) => i === taskIndex ? { ...t, phase: message.workflow_phase } : t);
                
                // Trigger a task refresh to ensure list view is updated
                // This helps catch phase transitions that might be missed
                fetchTasks(false);
              }
            }
            
            loadingLogs = false;
          } else if (message.type === 'complete') {
            // Task completed - mark as fetched and disconnect WebSocket
            console.log('Task completed via WebSocket, disconnecting:', taskId);
            
            // Update task phase if provided in the message
            if (message.workflow_phase) {
              const taskIndex = tasks.findIndex(t => t.id === taskId);
              if (taskIndex !== -1 && tasks[taskIndex].phase !== message.workflow_phase) {
                // Create a new array to ensure reactivity
                tasks = tasks.map((t, i) => i === taskIndex ? { ...t, phase: message.workflow_phase } : t);
              }
            }
            
            completedTasksWithLogsFetched.add(taskId);
            disconnectWebSocket();
            loadingLogs = false;
          } else if (message.type === 'error') {
            console.error('WebSocket error:', message.message);
            if (taskLogs.length === 0) {
              taskLogs = [{
                node: 'error',
                pod: 'N/A',
                phase: 'Error',
                logs: `Error: ${message.message}`
              }];
            }
            loadingLogs = false;
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        loadingLogs = false;
      };

      ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        ws = null;
        
        if (event.code !== 1000 && selectedTaskId === taskId && reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
          
          console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${maxReconnectAttempts})...`);
          
          reconnectTimeout = setTimeout(() => {
            connectWebSocket(taskId);
          }, delay);
        } else if (reconnectAttempts >= maxReconnectAttempts) {
          if (taskLogs.length === 0) {
            taskLogs = [{
              node: 'error',
              pod: 'N/A',
              phase: 'Error',
              logs: 'Connection lost. Maximum reconnection attempts reached.'
            }];
          }
          loadingLogs = false;
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      loadingLogs = false;
      taskLogs = [{
        node: 'error',
        pod: 'N/A',
        phase: 'Error',
        logs: `Failed to connect: ${error instanceof Error ? error.message : 'Unknown error'}`
      }];
    }
  }

  async function fetchLogsViaRest(taskId: string) {
    // Check if task is already completed
    const task = tasks.find(t => t.id === taskId);
    if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
      // For completed tasks, only skip if we've already fetched AND we have logs displayed
      // This allows fetching logs when user opens a completed task for the first time
      if (completedTasksWithLogsFetched.has(taskId) && taskLogs.length > 0) {
        console.log('Task is completed and logs already fetched, skipping:', taskId, task.phase);
        return;
      }
      console.log('Fetching logs for completed task:', taskId, task.phase);
    }
    
    try {
      loadingLogs = true;
      const res = await fetch(`${apiUrl}/api/v1/tasks/${taskId}/logs`);
      if (res.ok) {
        const data = await res.json();
        const logs = data.logs || [];
        // For completed tasks, always update if we got logs (even if same content)
        // For running tasks, only update if logs have more content
        if (logs.length > 0) {
          if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
            // For completed tasks, always show the logs and mark as fetched
            taskLogs = logs;
            completedTasksWithLogsFetched.add(taskId);
          } else if (hasMoreLogs(taskLogs, logs)) {
            // For running tasks, only update if more content
            taskLogs = logs;
          }
        } else if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
          // Even if no logs, mark as fetched to prevent repeated attempts
          completedTasksWithLogsFetched.add(taskId);
        }
      }
    } catch (error) {
      console.error('Failed to fetch logs via REST:', error);
      // Mark as fetched even on error to prevent repeated failed attempts for completed tasks
      if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
        completedTasksWithLogsFetched.add(taskId);
      }
    } finally {
      loadingLogs = false;
    }
  }

  // Manual WebSocket management - separate from reactive system
  // This function only reconnects if the taskId or tab actually changed
  function manageWebSocketConnection(taskId: string | null, tab: 'code' | 'logs') {
    // Check if task is already completed
    if (taskId) {
      const task = tasks.find(t => t.id === taskId);
      if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
        // For completed tasks, fetch logs once when user opens logs tab
        if (tab === 'logs') {
          // Fetch logs if we haven't fetched yet OR if we don't have logs displayed
          // This ensures logs are shown when user opens a completed task
          if (!completedTasksWithLogsFetched.has(taskId) || taskLogs.length === 0) {
            console.log('Task completed, fetching logs:', taskId, task.phase);
            // Fetch logs (will mark as fetched inside fetchLogsViaRest)
            fetchLogsViaRest(taskId);
          }
          // Don't connect WebSocket for completed tasks
          if (lastConnectedTaskId === taskId) {
            disconnectWebSocket();
            lastConnectedTaskId = null;
            lastConnectedTab = null;
          }
          return;
        } else {
          // Not on logs tab - just disconnect if connected
          if (lastConnectedTaskId === taskId) {
            disconnectWebSocket();
            lastConnectedTaskId = null;
            lastConnectedTab = null;
          }
          return;
        }
      }
    }
    
    // Check if values actually changed compared to what we last connected to
    const taskIdChanged = taskId !== lastConnectedTaskId;
    const tabChanged = tab !== lastConnectedTab;
    
    // Early return if values haven't changed - prevents unnecessary reconnections
    if (!taskIdChanged && !tabChanged) {
      return;
    }
    
    // Disconnect any existing connection first
    if (lastConnectedTaskId !== null) {
      disconnectWebSocket();
    }
    
    const shouldConnect = taskId && tab === 'logs';
    
    if (shouldConnect) {
      // Connect to the new task
      lastLogsHash = '';
      fetchLogsViaRest(taskId);
      connectWebSocket(taskId);
      lastConnectedTaskId = taskId;
      lastConnectedTab = tab;
    } else {
      // Not on logs tab or no task selected
      lastConnectedTaskId = null;
      lastConnectedTab = null;
      if (tab !== 'logs') {
        taskLogs = [];
      }
      lastLogsHash = '';
    }
  }
  
  // Remove reactive effect - we'll manage WebSocket connections manually
  // This prevents the reactive system from causing unnecessary reconnections
  // WebSocket management is now triggered explicitly when selectedTaskId or activeTab change

  async function runTask() {
    try {
      submitting = true;
      const requestBody: any = { pythonCode };
      if (dependencies.trim()) {
        requestBody.dependencies = dependencies.trim();
      }
      if (requirementsFile.trim()) {
        requestBody.requirementsFile = requirementsFile.trim();
      }
      
      const res = await fetch(`${apiUrl}/api/v1/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to submit task');
      }
      
      const data = await res.json();
      alert('Started Workflow: ' + data.id);
      showSubmitModal = false;
      // pythonCode will be reset by the $effect when showSubmitModal becomes false
      fetchTasks();
    } catch (error) {
      console.error('Failed to submit task:', error);
      alert('Failed to submit task: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      submitting = false;
    }
  }

  async function cancelTask(taskId: string) {
    if (!confirm('Are you sure you want to cancel this task?')) {
      return;
    }

    try {
      const res = await fetch(`${apiUrl}/api/v1/tasks/${taskId}`, {
        method: 'DELETE',
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to cancel task');
      }
      
      if (selectedTaskId === taskId) {
        selectedTaskId = null;
        activeTab = 'code';
        taskLogs = [];
        disconnectWebSocket();
      }
      
      fetchTasks();
      alert('Task cancelled successfully');
    } catch (error) {
      console.error('Failed to cancel task:', error);
      alert('Failed to cancel task: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }

  async function deleteTask(taskId: string) {
    if (!confirm('Are you sure you want to delete this task? This will permanently remove the workflow and all its logs from the database.')) {
      return;
    }

    try {
      const res = await fetch(`${apiUrl}/api/v1/tasks/${taskId}/delete`, {
        method: 'DELETE',
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to delete task');
      }
      
      if (selectedTaskId === taskId) {
        selectedTaskId = null;
        activeTab = 'code';
        taskLogs = [];
        disconnectWebSocket();
      }
      
      fetchTasks();
      alert('Task deleted successfully');
    } catch (error) {
      console.error('Failed to delete task:', error);
      alert('Failed to delete task: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }

  function loadWriteToPV() {
    pythonCode = `import json
import os
from datetime import datetime

# Create results directory if it doesn't exist
results_dir = "/mnt/results"
os.makedirs(results_dir, exist_ok=True)

# Generate some data to save
task_id = os.getenv("ARGO_WORKFLOW_NAME", "unknown-task")
result_data = {
    "task_id": task_id,
    "timestamp": datetime.now().isoformat(),
    "status": "completed",
    "result": "Task executed successfully!",
    "data": {
        "processed_items": 42,
        "computation_time": 1.23,
        "output": "Sample output data"
    }
}

# Write to file
output_file = os.path.join(results_dir, f"{task_id}_result.json")
with open(output_file, "w") as f:
    json.dump(result_data, f, indent=2)

print(f"Results saved to {output_file}")
print(f"Data: {json.dumps(result_data, indent=2)}")`;
  }

  function loadReadFromPV() {
    pythonCode = `import json
import os
from datetime import datetime

# Read from results directory
results_dir = "/mnt/results"

if not os.path.exists(results_dir):
    print(f"Error: Results directory {results_dir} does not exist")
    exit(1)

# List all result files
result_files = [f for f in os.listdir(results_dir) if f.endswith("_result.json")]

if not result_files:
    print("No result files found in /mnt/results")
    print(f"Directory contents: {os.listdir(results_dir)}")
    exit(0)

print(f"Found {len(result_files)} result file(s):")
print("-" * 50)

# Read and display each result file
for result_file in sorted(result_files):
    file_path = os.path.join(results_dir, result_file)
    print(f"\\nReading: {result_file}")
    print("-" * 50)
    
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error reading {result_file}: {e}")

print("\\n" + "=" * 50)
print(f"Successfully read {len(result_files)} result file(s)")`;
  }

  // Effect to refresh tasks when selected task phase changes (to ensure UI stays in sync)
  $effect(() => {
    if (selectedTaskId && selectedTask) {
      // When task phase changes to completed, refresh tasks to get final status
      const task = tasks.find(t => t.id === selectedTaskId);
      if (task && (task.phase === 'Succeeded' || task.phase === 'Failed')) {
        // Refresh tasks to ensure we have the latest status
        fetchTasks(false);
      }
    }
  });

  onMount(() => {
    fetchTasks(true);
    
    // Set up periodic task status updates
    taskRefreshInterval = setInterval(() => {
      fetchTasks(false);
    }, TASK_REFRESH_INTERVAL_MS);
  });

  onDestroy(() => {
    disconnectWebSocket();
    if (taskRefreshInterval) {
      clearInterval(taskRefreshInterval);
      taskRefreshInterval = null;
    }
  });
</script>

<div class="container mx-auto p-8 max-w-7xl">
  <div class="flex justify-between items-center mb-8">
    <h1 class="text-3xl font-bold">Argo Workflow Manager</h1>
    <div class="flex gap-2">
      <Button 
        onclick={() => fetchTasks(true)} 
        disabled={initialLoading}
        variant="outline"
      >
        <RefreshCw size={20} class="mr-2" /> Refresh
      </Button>
      <Button 
        onclick={() => showSubmitModal = true}
        variant="default"
      >
        <Play size={20} class="mr-2" /> Run Python Task
      </Button>
    </div>
  </div>

  <div class="mt-8">
    <h2 class="text-2xl font-semibold mb-4">Submitted Tasks</h2>
    {#if initialLoading && tasks.length === 0}
      <p class="text-muted-foreground">Loading tasks...</p>
    {:else if tasks.length === 0}
      <p class="text-muted-foreground">No tasks found. Submit a task to get started.</p>
    {:else}
      <div class="rounded-md border mt-4">
        <table class="w-full border-collapse">
          <thead>
            <tr class="border-b">
              <th class="p-3 text-left font-medium">ID</th>
              <th class="p-3 text-left font-medium">Phase</th>
              <th class="p-3 text-left font-medium">Started</th>
              <th class="p-3 text-left font-medium">Finished</th>
              <th class="p-3 text-left font-medium">Created</th>
              <th class="p-3 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each tasks as task (task.id)}
              <TaskRow 
                {task}
                {getPhaseColor}
                onTaskClick={(t) => {
                  const newTaskId = t.id;
                  if (selectedTaskId !== newTaskId) {
                    selectedTaskId = newTaskId;
                    // Update previous values
                    prevSelectedTaskId = newTaskId;
                    // Clear logs when switching to a different task
                    taskLogs = [];
                    // Manually trigger WebSocket management
                    manageWebSocketConnection(newTaskId, activeTab);
                  }
                }}
                onCancel={cancelTask}
                onDelete={deleteTask}
              />
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>

  {#if selectedTask}
    <TaskDialog
      task={selectedTask}
      {activeTab}
      setActiveTab={(tab) => {
        if (activeTab !== tab) {
          activeTab = tab;
          // Update previous values
          prevActiveTab = tab;
          // Manually trigger WebSocket management
          manageWebSocketConnection(selectedTaskId, tab);
        }
      }}
      {taskLogs}
      {loadingLogs}
      onClose={() => {
        selectedTaskId = null;
        activeTab = 'code';
        taskLogs = [];
        // Manually disconnect
        disconnectWebSocket();
        lastConnectedTaskId = null;
        lastConnectedTab = null;
      }}
      onCancel={cancelTask}
      onDelete={deleteTask}
    />
  {/if}

  <Dialog bind:open={showSubmitModal} class="max-w-4xl w-[90%] max-h-[85vh] overflow-auto flex flex-col">
    <div class="flex justify-between items-center mb-6">
      <h2 class="text-2xl font-semibold">Write Python Code to Execute</h2>
    </div>
    
    <div class="mb-4 flex gap-2 flex-wrap">
      <Button
        onclick={loadWriteToPV}
        disabled={submitting}
        variant="outline"
        size="sm"
      >
        📝 Load: Write to PV
      </Button>
      <Button
        onclick={loadReadFromPV}
        disabled={submitting}
        variant="outline"
        size="sm"
      >
        📖 Load: Read from PV
      </Button>
    </div>
    
    <div class="mb-4">
      <Button
        onclick={() => showDependencies = !showDependencies}
        variant="outline"
        size="sm"
        disabled={submitting}
      >
        {showDependencies ? '▼' : '▶'} Dependencies (Optional)
      </Button>
    </div>

    {#if showDependencies}
      <div class="mb-4 p-4 border rounded bg-muted/50">
        <div class="mb-4">
          <label class="block text-sm font-medium mb-2">
            Package Dependencies (space or comma-separated)
          </label>
          <input
            type="text"
            bind:value={dependencies}
            placeholder="e.g., numpy pandas requests"
            class="w-full px-3 py-2 border rounded bg-background"
            disabled={submitting}
          />
          <p class="text-xs text-muted-foreground mt-1">
            Example: numpy pandas requests or numpy==1.24.0 pandas>=2.0.0
          </p>
        </div>
        
        <div class="mb-2">
          <label class="block text-sm font-medium mb-2">
            Requirements File (alternative to package list)
          </label>
          <textarea
            bind:value={requirementsFile}
            placeholder="numpy==1.24.0&#10;pandas>=2.0.0&#10;requests==2.31.0"
            class="w-full px-3 py-2 border rounded bg-background font-mono text-sm"
            rows="5"
            disabled={submitting}
          />
          <p class="text-xs text-muted-foreground mt-1">
            Enter requirements.txt format. If provided, this takes precedence over package dependencies.
          </p>
        </div>
      </div>
    {/if}
    
    <div class="flex-1 min-h-[400px] mb-6">
      <MonacoEditor bind:value={pythonCode} language="python" theme="vs-dark" height="400px" />
    </div>

    <div class="flex gap-2 justify-end">
      <Button
        onclick={() => showSubmitModal = false}
        disabled={submitting}
        variant="outline"
      >
        Cancel
      </Button>
      <Button
        onclick={runTask}
        disabled={submitting || !pythonCode.trim()}
        variant="default"
      >
        {submitting ? 'Submitting...' : 'Submit Task'}
        {#if !submitting}
          <Play size={18} class="ml-2" />
        {/if}
      </Button>
    </div>
  </Dialog>
</div>
