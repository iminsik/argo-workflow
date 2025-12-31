<script lang="ts">
  import { XCircle, Trash2 } from 'lucide-svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Badge from '$lib/components/ui/badge.svelte';

  interface Props {
    task: {
      id: string;
      phase: string;
      startedAt: string;
      finishedAt: string;
      createdAt: string;
    };
    getPhaseColor: (phase: string) => string;
    onTaskClick: (task: any) => void;
    onCancel: (taskId: string) => void;
    onDelete: (taskId: string) => void;
  }

  let { task, getPhaseColor, onTaskClick, onCancel, onDelete }: Props = $props();

  const canCancel = $derived(task.phase === 'Running' || task.phase === 'Pending');

  function handleCancelClick(e: MouseEvent) {
    e.stopPropagation();
    onCancel(task.id);
  }

  function handleDeleteClick(e: MouseEvent) {
    e.stopPropagation();
    onDelete(task.id);
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
</script>

<tr 
  class="border-b cursor-pointer transition-colors hover:bg-muted/50"
  onclick={() => onTaskClick(task)}
>
  <td class="p-3 font-mono text-sm">{task.id}</td>
  <td class="p-3">
    <Badge variant={getBadgeVariant(task.phase)} style="background-color: {getPhaseColor(task.phase)}; color: white">
      {task.phase || 'Unknown'}
    </Badge>
  </td>
  <td class="p-3 text-sm">
    {task.startedAt ? new Date(task.startedAt).toLocaleString() : '-'}
  </td>
  <td class="p-3 text-sm">
    {task.finishedAt ? new Date(task.finishedAt).toLocaleString() : '-'}
  </td>
  <td class="p-3 text-sm">
    {task.createdAt ? new Date(task.createdAt).toLocaleString() : '-'}
  </td>
  <td class="p-3">
    <div class="flex gap-2 items-center">
      {#if canCancel}
        <Button
          onclick={handleCancelClick}
          variant="destructive"
          size="sm"
          title="Cancel task"
        >
          <XCircle size={14} class="mr-1" /> Cancel
        </Button>
      {/if}
      <Button
        onclick={handleDeleteClick}
        variant="secondary"
        size="sm"
        title="Delete task (removes workflow and logs)"
      >
        <Trash2 size={14} class="mr-1" /> Delete
      </Button>
    </div>
  </td>
</tr>
