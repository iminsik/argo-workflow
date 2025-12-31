<script lang="ts">
  import { XCircle, Trash2 } from 'lucide-svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Badge from '$lib/components/ui/badge.svelte';
  import Dialog from '$lib/components/ui/dialog.svelte';

  interface Props {
    task: {
      id: string;
      phase: string;
      pythonCode: string;
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
  }

  let { task, activeTab, setActiveTab, taskLogs, loadingLogs, onClose, onCancel, onDelete }: Props = $props();

  const canCancel = task.phase === 'Running' || task.phase === 'Pending';
  let dialogOpen = $state(true);

  function getPhaseColor(phase: string): string {
    switch (phase) {
      case 'Succeeded': return '#10b981';
      case 'Failed': return '#ef4444';
      case 'Running': return '#3b82f6';
      case 'Pending': return '#f59e0b';
      default: return '#6b7280';
    }
  }

  function getBadgeVariant(phase: string): 'default' | 'secondary' | 'destructive' | 'outline' {
    switch (phase) {
      case 'Succeeded': return 'default';
      case 'Failed': return 'destructive';
      case 'Running': return 'default';
      case 'Pending': return 'secondary';
      default: return 'outline';
    }
  }

  $effect(() => {
    if (!dialogOpen) {
      onClose();
    }
  });
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
    </div>
    <div class="flex gap-2">
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
  
  <!-- Tabs -->
  <div class="flex border-b mb-4">
    <button
      onclick={() => setActiveTab('code')}
      class="px-5 py-2 border-none bg-transparent cursor-pointer border-b-2 transition-colors {activeTab === 'code' ? 'border-primary text-primary font-bold' : 'border-transparent text-muted-foreground'}"
    >
      Code
    </button>
    <button
      onclick={() => setActiveTab('logs')}
      class="px-5 py-2 border-none bg-transparent cursor-pointer border-b-2 transition-colors {activeTab === 'logs' ? 'border-primary text-primary font-bold' : 'border-transparent text-muted-foreground'}"
    >
      Logs {loadingLogs && '...'}
    </button>
  </div>

  <!-- Tab Content -->
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    {#if activeTab === 'code'}
      <div class="bg-[#1e1e1e] text-[#d4d4d4] p-4 rounded border border-[#3e3e3e] flex-1 min-h-0 overflow-auto font-mono text-sm whitespace-pre-wrap">
        {task.pythonCode || 'No Python code available'}
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
                {logEntry.logs}
              </div>
            </div>
          {/each}
        {/if}
      </div>
    {/if}
  </div>
</Dialog>
