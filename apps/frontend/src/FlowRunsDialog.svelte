<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { X, Play, RefreshCw } from 'lucide-svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Dialog from '$lib/components/ui/dialog.svelte';
  import Badge from '$lib/components/ui/badge.svelte';

  interface Props {
    flowId: string;
    open: boolean;
    onClose: () => void;
    onRun?: (flowId: string) => void;
  }

  let { flowId, open, onClose, onRun }: Props = $props();

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  let runs = $state<any[]>([]);
  let loading = $state(false);
  let selectedRunNumber = $state<number | null>(null);
  let runDetails = $state<any | null>(null);
  let loadingDetails = $state(false);
  let refreshInterval: ReturnType<typeof setInterval> | null = null;
  const REFRESH_INTERVAL_MS = 2000; // 2 seconds, same as tasks

  function getPhaseColor(phase: string): string {
    switch (phase) {
      case 'Succeeded': return '#10b981';
      case 'Failed': return '#ef4444';
      case 'Running': return '#3b82f6';
      case 'Pending': return '#f59e0b';
      default: return '#9ca3af';
    }
  }

  async function fetchRuns() {
    try {
      loading = true;
      const res = await fetch(`${apiUrl}/api/v1/flows/${flowId}/runs`);
      if (res.ok) {
        const data = await res.json();
        runs = data.runs || [];
      }
    } catch (error) {
      console.error('Failed to fetch flow runs:', error);
    } finally {
      loading = false;
    }
  }

  async function fetchRunDetails(runNumber: number) {
    try {
      loadingDetails = true;
      const res = await fetch(`${apiUrl}/api/v1/flows/${flowId}/runs/${runNumber}`);
      if (res.ok) {
        const data = await res.json();
        runDetails = data;
      }
    } catch (error) {
      console.error('Failed to fetch run details:', error);
    } finally {
      loadingDetails = false;
    }
  }

  $effect(() => {
    if (open && flowId) {
      fetchRuns();
      
      // Set up polling for runs that are pending or running
      if (refreshInterval) {
        clearInterval(refreshInterval);
      }
      
      refreshInterval = setInterval(() => {
        // Only poll if there are pending or running runs
        const hasActiveRuns = runs.some(run => run.phase === 'Pending' || run.phase === 'Running');
        if (hasActiveRuns) {
          fetchRuns();
          // Also refresh details if a run is selected
          if (selectedRunNumber) {
            fetchRunDetails(selectedRunNumber);
          }
        }
      }, REFRESH_INTERVAL_MS);
    } else {
      // Clear interval when dialog closes
      if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
      }
    }
  });

  $effect(() => {
    if (selectedRunNumber) {
      fetchRunDetails(selectedRunNumber);
    }
  });

  onDestroy(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  });

  async function handleRun() {
    if (onRun) {
      onRun(flowId);
      await fetchRuns();
    }
  }

  // Initialize state with default value to avoid capturing initial prop value
  let dialogOpen = $state(false);
  
  // Sync prop to state using $effect
  $effect(() => {
    const currentOpen = open;
    if (currentOpen !== dialogOpen) {
      dialogOpen = currentOpen;
    }
  });
  
  $effect(() => {
    if (!dialogOpen) {
      onClose();
    }
  });
  
  function handleOpenChange(newOpen: boolean) {
    dialogOpen = newOpen;
    if (!newOpen) {
      onClose();
    }
  }
</script>

<Dialog bind:open={dialogOpen} onOpenChange={handleOpenChange} class="max-w-6xl w-[90%] h-[85vh] max-h-[85vh] flex flex-col">
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-2xl font-semibold">Flow Runs - {flowId}</h2>
    <div class="flex gap-2">
      {#if onRun}
        <Button onclick={handleRun} variant="default">
          <Play size={16} class="mr-2" /> Run Flow
        </Button>
      {/if}
      <Button onclick={fetchRuns} variant="outline">
        <RefreshCw size={16} class="mr-2" /> Refresh
      </Button>
    </div>
  </div>

  <div class="flex-1 flex gap-4 overflow-hidden">
    <!-- Runs List -->
    <div class="w-1/3 border-r pr-4 overflow-y-auto">
      <h3 class="font-semibold mb-2">Runs ({runs.length})</h3>
      {#if loading}
        <p class="text-muted-foreground">Loading runs...</p>
      {:else if runs.length === 0}
        <p class="text-muted-foreground">No runs yet</p>
      {:else}
        <div class="space-y-2">
          {#each runs as run (run.id)}
            <button
              onclick={() => selectedRunNumber = run.runNumber}
              class="w-full text-left p-3 border rounded hover:bg-muted transition-colors {selectedRunNumber === run.runNumber ? 'bg-primary text-primary-foreground' : ''}"
            >
              <div class="flex justify-between items-center mb-1">
                <span class="font-semibold">Run #{run.runNumber}</span>
                <Badge
                  style="background-color: {getPhaseColor(run.phase)}; color: white"
                >
                  {run.phase}
                </Badge>
              </div>
              <div class="text-xs text-muted-foreground">
                {run.startedAt ? new Date(run.startedAt).toLocaleString() : 'Not started'}
              </div>
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Run Details -->
    <div class="flex-1 overflow-y-auto">
      {#if selectedRunNumber === null}
        <p class="text-muted-foreground">Select a run to view details</p>
      {:else if loadingDetails}
        <p class="text-muted-foreground">Loading details...</p>
      {:else if runDetails}
        <div>
          <h3 class="font-semibold mb-4">Run #{runDetails.runNumber} Details</h3>
          
          <div class="mb-4 p-4 bg-muted rounded">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <div class="text-sm text-muted-foreground">Workflow ID</div>
                <div class="font-mono">{runDetails.workflowId}</div>
              </div>
              <div>
                <div class="text-sm text-muted-foreground">Phase</div>
                <Badge style="background-color: {getPhaseColor(runDetails.phase)}; color: white">
                  {runDetails.phase}
                </Badge>
              </div>
              <div>
                <div class="text-sm text-muted-foreground">Started</div>
                <div>{runDetails.startedAt ? new Date(runDetails.startedAt).toLocaleString() : 'N/A'}</div>
              </div>
              <div>
                <div class="text-sm text-muted-foreground">Finished</div>
                <div>{runDetails.finishedAt ? new Date(runDetails.finishedAt).toLocaleString() : 'N/A'}</div>
              </div>
            </div>
          </div>

          <div>
            <h4 class="font-semibold mb-2">Step Runs</h4>
            {#if runDetails.stepRuns && runDetails.stepRuns.length > 0}
              <div class="space-y-2">
                {#each runDetails.stepRuns as stepRun (stepRun.id)}
                  <div class="p-3 border rounded">
                    <div class="flex justify-between items-center mb-2">
                      <span class="font-medium">{stepRun.stepId}</span>
                      <Badge style="background-color: {getPhaseColor(stepRun.phase)}; color: white">
                        {stepRun.phase}
                      </Badge>
                    </div>
                    <div class="text-xs text-muted-foreground">
                      Node: {stepRun.workflowNodeId}
                    </div>
                  </div>
                {/each}
              </div>
            {:else}
              <p class="text-muted-foreground">No step runs yet</p>
            {/if}
          </div>
        </div>
      {/if}
    </div>
  </div>
</Dialog>

