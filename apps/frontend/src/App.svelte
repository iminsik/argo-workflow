<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
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
  let taskLogs = $state<LogEntry[]>([]);
  let loadingLogs = $state(false);
  let showSubmitModal = $state(false);
  let pythonCode = $state("print('Processing task in Kind...')");
  let submitting = $state(false);

  let ws: WebSocket | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  let lastLogsHash = '';

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

  function logsChanged(oldLogs: LogEntry[], newLogs: LogEntry[]): boolean {
    if (oldLogs.length !== newLogs.length) return true;
    return oldLogs.some((oldLog, i) => {
      const newLog = newLogs[i];
      return !newLog || oldLog.logs !== newLog.logs || oldLog.phase !== newLog.phase;
    });
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
  }

  function connectWebSocket(taskId: string) {
    lastLogsHash = '';
    disconnectWebSocket();

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
          
          if (message.type === 'logs') {
            const newLogs = message.data || [];
            const newHash = logsHash(newLogs);
            
            if (newHash !== lastLogsHash && logsChanged(taskLogs, newLogs)) {
              lastLogsHash = newHash;
              taskLogs = newLogs;
            }
            loadingLogs = false;
          } else if (message.type === 'complete') {
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
    try {
      loadingLogs = true;
      const res = await fetch(`${apiUrl}/api/v1/tasks/${taskId}/logs`);
      if (res.ok) {
        const data = await res.json();
        const logs = data.logs || [];
        if (logs.length > 0) {
          taskLogs = logs;
        }
      }
    } catch (error) {
      console.error('Failed to fetch logs via REST:', error);
    } finally {
      loadingLogs = false;
    }
  }

  // Convert reactive statement to $effect
  $effect(() => {
    if (selectedTask && activeTab === 'logs') {
      lastLogsHash = '';
      fetchLogsViaRest(selectedTask.id);
      connectWebSocket(selectedTask.id);
      
      return () => {
        disconnectWebSocket();
        if (activeTab !== 'logs') {
          taskLogs = [];
        }
        lastLogsHash = '';
      };
    } else {
      disconnectWebSocket();
      if (activeTab !== 'logs') {
        taskLogs = [];
      }
      lastLogsHash = '';
    }
  });

  async function runTask() {
    try {
      submitting = true;
      const res = await fetch(`${apiUrl}/api/v1/tasks/submit`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ pythonCode }),
      });
      
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to submit task');
      }
      
      const data = await res.json();
      alert('Started Workflow: ' + data.id);
      showSubmitModal = false;
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

  onMount(() => {
    fetchTasks(true);
  });

  onDestroy(() => {
    disconnectWebSocket();
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
                onTaskClick={(t) => selectedTaskId = t.id}
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
      setActiveTab={(tab) => activeTab = tab}
      {taskLogs}
      {loadingLogs}
      onClose={() => {
        selectedTaskId = null;
        activeTab = 'code';
        taskLogs = [];
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
