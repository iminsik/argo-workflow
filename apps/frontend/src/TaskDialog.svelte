<script lang="ts">
  import { XCircle, Trash2, Play } from 'lucide-svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Badge from '$lib/components/ui/badge.svelte';
  import Dialog from '$lib/components/ui/dialog.svelte';
  import MonacoEditor from './MonacoEditor.svelte';
  import { ansiToHtml } from '$lib/ansi-to-html';

  interface Run {
    id: number;
    runNumber: number;
    workflowId: string;
    phase: string;
    pythonCode: string;
    dependencies?: string;
    requirementsFile?: string;
    systemDependencies?: string;
    startedAt: string;
    finishedAt: string;
    createdAt: string;
  }

  interface Props {
    task: {
      id: string;
      phase: string;
      pythonCode: string;
      dependencies?: string;
      systemDependencies?: string;
      message?: string;
    };
    activeTab: 'code' | 'logs';
    setActiveTab: (tab: 'code' | 'logs') => void;
    taskLogs: Array<{
      node: string;
      pod: string;
      phase: string;
      logs: string;
    }>;
    loadingLogs: boolean;
    onClose: () => void;
    onCancel: (taskId: string) => void;
    onDelete: (taskId: string) => void;
    onRerun: (task: { pythonCode: string; dependencies?: string; systemDependencies?: string; requirementsFile?: string }, taskId: string) => void;
    onRun?: (taskId: string) => void;
    onLoadRunLogs?: (taskId: string, runNumber: number) => Promise<void>;
  }

  let { task, activeTab, setActiveTab, taskLogs, loadingLogs, onClose, onCancel, onDelete, onRerun, onRun, onLoadRunLogs }: Props = $props();

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  let runs = $state<Run[]>([]);
  let selectedRunNumber = $state<number | null>(null);
  let loadingRuns = $state(false);

  const canCancel = $derived(task.phase === 'Running' || task.phase === 'Pending');
  const canRun = $derived(task.phase !== 'Running' && task.phase !== 'Pending');
  let dialogOpen = $state(true);
  
  // Get the selected run's code and dependencies
  const selectedRun = $derived(runs.find(r => r.runNumber === selectedRunNumber));
  const displayCode = $derived(selectedRun?.pythonCode || task.pythonCode);
  const displayDependencies = $derived(selectedRun?.dependencies || task.dependencies);
  const displaySystemDependencies = $derived(selectedRun?.systemDependencies || task.systemDependencies);
  const displayRequirementsFile = $derived(selectedRun?.requirementsFile || task.requirementsFile);

  function getPhaseColor(phase: string): string {
    switch (phase) {
      case 'Succeeded': return '#10b981';
      case 'Failed': return '#ef4444';
      case 'Running': return '#3b82f6';
      case 'Pending': return '#f59e0b';
      case 'Not Started': return '#9ca3af';
      default: return '#6b7280';
    }
  }

  function getBadgeVariant(phase: string): 'default' | 'secondary' | 'destructive' | 'outline' {
    switch (phase) {
      case 'Succeeded': return 'default';
      case 'Failed': return 'destructive';
      case 'Running': return 'default';
      case 'Pending': return 'secondary';
      case 'Not Started': return 'outline';
      default: return 'outline';
    }
  }

  async function fetchTaskDetails() {
    try {
      loadingRuns = true;
      const res = await fetch(`${apiUrl}/api/v1/tasks/${task.id}`);
      if (res.ok) {
        const data = await res.json();
        runs = data.runs || [];
        // Select latest run by default
        if (runs.length > 0 && !selectedRunNumber) {
          selectedRunNumber = runs[0].runNumber;
          if (onLoadRunLogs && activeTab === 'logs') {
            await onLoadRunLogs(task.id, selectedRunNumber);
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch task details:', error);
    } finally {
      loadingRuns = false;
    }
  }

  $effect(() => {
    if (dialogOpen) {
      fetchTaskDetails();
    } else {
      onClose();
    }
  });

  async function handleRunSelect(runNumber: number) {
    selectedRunNumber = runNumber;
    if (onLoadRunLogs && activeTab === 'logs') {
      await onLoadRunLogs(task.id, runNumber);
    }
    // Code tab will automatically update via reactive $derived variables
  }
</script>

<Dialog bind:open={dialogOpen} class="max-w-4xl w-[90%] h-[85vh] max-h-[85vh] flex flex-col">
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-2xl font-semibold">Task Details - {task.id}</h2>
  </div>
  <div class="mb-4 flex gap-2 items-center justify-between flex-wrap">
    <div class="flex gap-2 items-center flex-wrap">
      <Badge variant={getBadgeVariant(task.phase)} style="background-color: {getPhaseColor(task.phase)}; color: white">
        {task.phase || 'Unknown'}
      </Badge>
      {#if task.message}
        <Badge variant="secondary" class="max-w-md italic">
          {task.message}
        </Badge>
      {/if}
      {#if displayDependencies}
        <Badge variant="outline" class="max-w-md">
          📦 Python: {displayDependencies}
        </Badge>
      {/if}
      {#if displaySystemDependencies}
        <Badge variant="outline" class="max-w-md">
          🔧 System: {displaySystemDependencies}
        </Badge>
      {/if}
    </div>
    <div class="flex gap-2">
      {#if canRun && onRun}
        <Button
          onclick={() => onRun(task.id)}
          variant="default"
        >
          <Play size={16} class="mr-2" /> Run
        </Button>
      {/if}
      <Button
        onclick={() => onRerun({ 
          pythonCode: displayCode, 
          dependencies: displayDependencies,
          systemDependencies: displaySystemDependencies || "",  // Use selected run's systemDependencies, or task's if no run selected
          requirementsFile: displayRequirementsFile || ""  // Use selected run's requirementsFile, or task's if no run selected
        }, task.id)}
        variant="default"
      >
        <Play size={16} class="mr-2" /> Edit & Rerun
      </Button>
      {#if canCancel}
        <Button
          onclick={() => onCancel(task.id)}
          variant="destructive"
        >
          <XCircle size={16} class="mr-2" /> Cancel Task
        </Button>
      {/if}
      <Button
        onclick={() => onDelete(task.id)}
        variant="secondary"
      >
        <Trash2 size={16} class="mr-2" /> Delete Task
      </Button>
    </div>
  </div>
  
  <!-- Run Selector -->
  {#if runs.length > 0}
    <div class="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded border">
      <div class="text-sm font-semibold mb-2">Run History ({runs.length} total)</div>
      <div class="flex gap-2 flex-wrap">
        {#each runs as run (run.id)}
          <button
            onclick={() => handleRunSelect(run.runNumber)}
            class="px-3 py-1 text-sm border rounded transition-colors {selectedRunNumber === run.runNumber ? 'bg-primary text-primary-foreground border-primary' : 'bg-background hover:bg-muted'}"
          >
            Run #{run.runNumber} - {run.phase}
          </button>
        {/each}
      </div>
      {#if selectedRunNumber}
        <div class="mt-2 text-xs text-muted-foreground">
          Viewing Run #{selectedRunNumber} {#if runs.find(r => r.runNumber === selectedRunNumber)}
            {#if runs.find(r => r.runNumber === selectedRunNumber)?.startedAt}
              | Started: {new Date(runs.find(r => r.runNumber === selectedRunNumber)!.startedAt).toLocaleString()}
            {/if}
            {#if runs.find(r => r.runNumber === selectedRunNumber)?.finishedAt}
              | Finished: {new Date(runs.find(r => r.runNumber === selectedRunNumber)!.finishedAt).toLocaleString()}
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Tabs -->
  <div class="flex border-b mb-4">
    <button
      onclick={() => setActiveTab('code')}
      class="px-5 py-2 border-none bg-transparent cursor-pointer border-b-2 transition-colors {activeTab === 'code' ? 'border-primary text-primary font-bold' : 'border-transparent text-muted-foreground'}"
    >
      Code
    </button>
    <button
      onclick={() => {
        setActiveTab('logs');
        if (selectedRunNumber && onLoadRunLogs) {
          onLoadRunLogs(task.id, selectedRunNumber);
        }
      }}
      class="px-5 py-2 border-none bg-transparent cursor-pointer border-b-2 transition-colors {activeTab === 'logs' ? 'border-primary text-primary font-bold' : 'border-transparent text-muted-foreground'}"
    >
      Logs{#if loadingLogs} ...{/if}
    </button>
  </div>

  <!-- Tab Content -->
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    {#if activeTab === 'code'}
      <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
        {#if displayDependencies}
          <div class="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded">
            <div class="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-1 flex items-center gap-2">
              <span>📦</span>
              <span>Python Dependencies</span>
            </div>
            <div class="text-sm text-blue-800 dark:text-blue-200 font-mono break-words">{displayDependencies}</div>
          </div>
        {/if}
        {#if displaySystemDependencies}
          <div class="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded">
            <div class="text-sm font-semibold text-green-900 dark:text-green-100 mb-1 flex items-center gap-2">
              <span>🔧</span>
              <span>System Dependencies</span>
            </div>
            <div class="text-sm text-green-800 dark:text-green-200 font-mono break-words">
              {displaySystemDependencies}
            </div>
          </div>
        {/if}
        <div class="flex-1 min-h-0 overflow-hidden">
          {#if displayCode}
            <div class="h-full w-full">
              <MonacoEditor 
                value={displayCode} 
                language="python" 
                theme="vs-dark" 
                height="100%"
                readonly={true}
              />
            </div>
          {:else}
            <div class="bg-[#1e1e1e] text-[#d4d4d4] p-4 rounded border border-[#3e3e3e] flex-1 min-h-0 overflow-auto font-mono text-sm">
              No Python code available
            </div>
          {/if}
        </div>
      </div>
    {:else}
      <div class="bg-[#1e1e1e] text-[#d4d4d4] p-4 rounded border border-[#3e3e3e] flex-1 min-h-0 overflow-auto font-mono text-sm whitespace-pre-wrap">
        {#if loadingLogs}
          <div class="text-[#9ca3af]">Loading logs...</div>
        {:else if taskLogs.length === 0}
          <div class="text-[#9ca3af]">No logs available yet. The task may still be starting.</div>
        {:else}
          {#each taskLogs as logEntry, index (index)}
            <div class="mb-6">
              <div class="text-[#60a5fa] mb-2 pb-2 border-b border-[#374151]">
                <strong>Pod:</strong> {logEntry.pod} | <strong>Node:</strong> {logEntry.node} | <strong>Phase:</strong> {logEntry.phase}
              </div>
              <div class="text-[#d4d4d4] whitespace-pre-wrap break-words">
                {#each ansiToHtml(logEntry.logs) as token}
                  {#if token.classes.length > 0}
                    <span class={token.classes.join(' ')}>{token.text}</span>
                  {:else}
                    {token.text}
                  {/if}
                {/each}
              </div>
            </div>
          {/each}
        {/if}
      </div>
    {/if}
  </div>
</Dialog>
