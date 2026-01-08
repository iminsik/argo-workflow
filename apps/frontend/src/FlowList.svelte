<script lang="ts">
  import { onMount } from 'svelte';
  import { Plus, Trash2, Edit, Play } from 'lucide-svelte';
  import Button from '$lib/components/ui/button.svelte';
  import type { Flow } from '$lib/flow/types';

  interface Props {
    onFlowSelect?: (flowId: string) => void;
    onFlowCreate?: () => void;
    onFlowSaved?: () => void;
  }

  let { onFlowSelect, onFlowCreate, onFlowSaved }: Props = $props();

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
    <div class="flow-list">
      {#each flows as flow (flow.id)}
        <div
          class="flow-item"
          onclick={() => handleFlowClick(flow.id)}
          role="button"
          tabindex="0"
        >
          <div class="flow-item-content">
            <div class="flow-item-header">
              <h3 class="flow-item-name">{flow.name}</h3>
              <span
                class="flow-status-badge"
                style="background-color: {getStatusColor(flow.status)}"
              >
                {flow.status}
              </span>
            </div>
            {#if flow.description}
              <p class="flow-item-description">{flow.description}</p>
            {/if}
            <div class="flow-item-meta">
              <span class="text-sm text-muted-foreground">
                {flow.stepCount || 0} steps
              </span>
              <span class="text-sm text-muted-foreground">
                Updated: {new Date(flow.updatedAt).toLocaleDateString()}
              </span>
            </div>
          </div>
          <div class="flow-item-actions" onclick={(e) => e.stopPropagation()}>
            <Button
              onclick={() => handleFlowClick(flow.id)}
              variant="outline"
              size="sm"
            >
              <Edit size={16} class="mr-1" /> Edit
            </Button>
            <Button
              onclick={(e) => deleteFlow(flow.id, e)}
              variant="outline"
              size="sm"
            >
              <Trash2 size={16} class="mr-1" /> Delete
            </Button>
          </div>
        </div>
      {/each}
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

  .flow-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
  }

  .flow-item {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s;
    background: white;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }

  .flow-item:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  .flow-item-content {
    flex: 1;
  }

  .flow-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .flow-item-name {
    font-size: 1.125rem;
    font-weight: 600;
    margin: 0;
  }

  .flow-status-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    color: white;
    text-transform: capitalize;
  }

  .flow-item-description {
    color: #6b7280;
    font-size: 0.875rem;
    margin: 0.5rem 0;
  }

  .flow-item-meta {
    display: flex;
    gap: 1rem;
    margin-top: 0.5rem;
  }

  .flow-item-actions {
    display: flex;
    gap: 0.5rem;
    margin-left: 1rem;
  }
</style>

