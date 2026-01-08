<script lang="ts">
  import { onMount } from 'svelte';
  import { Plus, Trash2, Edit, Play, History } from 'lucide-svelte';
  import Button from '$lib/components/ui/button.svelte';
  import type { Flow } from '$lib/flow/types';

  interface Props {
    onFlowSelect?: (flowId: string) => void;
    onFlowCreate?: () => void;
    onFlowSaved?: () => void;
    onFlowRun?: (flowId: string) => void;
    onFlowRuns?: (flowId: string) => void;
  }

  let { onFlowSelect, onFlowCreate, onFlowSaved, onFlowRun, onFlowRuns }: Props = $props();

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  let flows = $state<Flow[]>([]);
  let loading = $state(true);

  onMount(() => {
    fetchFlows();
  });

  async function fetchFlows() {
    try {
      loading = true;
      const res = await fetch(`${apiUrl}/api/v1/flows`);
      if (res.ok) {
        const data = await res.json();
        flows = data.flows || [];
      }
    } catch (error) {
      console.error('Failed to fetch flows:', error);
    } finally {
      loading = false;
    }
  }

  async function deleteFlow(flowId: string, event: Event) {
    event.stopPropagation();
    if (!confirm('Are you sure you want to delete this flow?')) {
      return;
    }

    try {
      const res = await fetch(`${apiUrl}/api/v1/flows/${flowId}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to delete flow');
      }

      flows = flows.filter(f => f.id !== flowId);
      alert('Flow deleted successfully');
    } catch (error) {
      console.error('Failed to delete flow:', error);
      alert('Failed to delete flow: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }

  function handleFlowClick(flowId: string) {
    if (onFlowSelect) {
      onFlowSelect(flowId);
    }
  }

  function handleCreateClick() {
    if (onFlowCreate) {
      onFlowCreate();
    }
  }

  function getStatusColor(status: string): string {
    switch (status) {
      case 'running': return '#3b82f6';
      case 'completed': return '#10b981';
      case 'failed': return '#ef4444';
      case 'saved': return '#10b981';
      default: return '#9ca3af';
    }
  }
</script>

<div class="flow-list-container">
  <div class="flow-list-header">
    <h2 class="text-2xl font-semibold">Flows</h2>
    <Button onclick={handleCreateClick} variant="default">
      <Plus size={20} class="mr-2" /> New Flow
    </Button>
  </div>

  {#if loading}
    <p class="text-muted-foreground">Loading flows...</p>
  {:else if flows.length === 0}
    <p class="text-muted-foreground">No flows found. Create a new flow to get started.</p>
  {:else}
    <div class="rounded-md border mt-4">
      <table class="w-full border-collapse">
        <thead>
          <tr class="border-b">
            <th class="p-3 text-left font-medium">Name</th>
            <th class="p-3 text-left font-medium">Status</th>
            <th class="p-3 text-left font-medium">Steps</th>
            <th class="p-3 text-left font-medium">Created</th>
            <th class="p-3 text-left font-medium">Updated</th>
            <th class="p-3 text-left font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each flows as flow (flow.id)}
            <tr 
              class="border-b cursor-pointer transition-colors hover:bg-muted/50"
              onclick={() => handleFlowClick(flow.id)}
            >
              <td class="p-3 font-medium">{flow.name}</td>
              <td class="p-3">
                <span
                  class="inline-block px-2 py-1 rounded text-xs font-medium text-white"
                  style="background-color: {getStatusColor(flow.status)}"
                >
                  {flow.status || 'draft'}
                </span>
              </td>
              <td class="p-3 text-sm">{flow.stepCount || 0}</td>
              <td class="p-3 text-sm">
                {flow.createdAt ? new Date(flow.createdAt).toLocaleString() : '-'}
              </td>
              <td class="p-3 text-sm">
                {flow.updatedAt ? new Date(flow.updatedAt).toLocaleString() : '-'}
              </td>
              <td class="p-3">
                <div class="flex gap-2 items-center">
                  {#if onFlowRun}
                    <Button
                      onclick={(e) => {
                        e.stopPropagation();
                        onFlowRun(flow.id);
                      }}
                      variant="default"
                      size="sm"
                      title="Run flow"
                    >
                      <Play size={14} class="mr-1" /> Run
                    </Button>
                  {/if}
                  {#if onFlowRuns}
                    <Button
                      onclick={(e) => {
                        e.stopPropagation();
                        onFlowRuns(flow.id);
                      }}
                      variant="outline"
                      size="sm"
                      title="View flow runs"
                    >
                      <History size={14} class="mr-1" /> Runs
                    </Button>
                  {/if}
                  <Button
                    onclick={(e) => {
                      e.stopPropagation();
                      handleFlowClick(flow.id);
                    }}
                    variant="outline"
                    size="sm"
                    title="Edit flow"
                  >
                    <Edit size={14} class="mr-1" /> Edit
                  </Button>
                  <Button
                    onclick={(e) => {
                      e.stopPropagation();
                      deleteFlow(flow.id, e);
                    }}
                    variant="secondary"
                    size="sm"
                    title="Delete flow"
                  >
                    <Trash2 size={14} class="mr-1" /> Delete
                  </Button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .flow-list-container {
    padding: 1.5rem;
  }

  .flow-list-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }

</style>

