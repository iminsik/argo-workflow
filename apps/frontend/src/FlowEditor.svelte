<script lang="ts">
  import { onMount } from 'svelte';
  import { SvelteFlow, Background, Controls, MiniMap } from '@xyflow/svelte';
  import type { Node, Edge, Connection } from '@xyflow/svelte';
  import MonacoEditor from './MonacoEditor.svelte';
  import Button from '$lib/components/ui/button.svelte';
  import type { FlowStep, FlowEdge } from '$lib/flow/types';

  interface Props {
    flowId?: string;
    flowName?: string;
    onSave?: (flow: { name: string; steps: FlowStep[]; edges: FlowEdge[] }) => void;
    onClose?: () => void;
  }

  let { flowId, flowName = 'New Flow', onSave, onClose }: Props = $props();

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  // Flow state
  let nodes = $state<Node[]>([]);
  let edges = $state<Edge[]>([]);
  let selectedNodeId = $state<string | null>(null);
  let showStepEditor = $state(false);
  let currentStepCode = $state('');
  let currentStepName = $state('');
  let currentStepId = $state('');
  let currentStepDependencies = $state('');
  let saving = $state(false);
  let flowNameInput = $state(flowName);

  // Load flow if flowId provided
  onMount(async () => {
    if (flowId) {
      await loadFlow(flowId);
    } else {
      // Create initial node
      addNode();
    }
  });

  async function loadFlow(id: string) {
    try {
      const res = await fetch(`${apiUrl}/api/v1/flows/${id}`);
      if (res.ok) {
        const flow = await res.json();
        flowNameInput = flow.name;
        
        // Convert flow steps to nodes
        nodes = flow.steps.map((step: FlowStep) => ({
          id: step.id,
          type: 'default',
          position: step.position,
          data: {
            label: step.name,
            pythonCode: step.pythonCode,
            dependencies: step.dependencies || '',
          }
        }));
        
        // Convert flow edges to edges
        edges = flow.edges.map((edge: FlowEdge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourceHandle,
          targetHandle: edge.targetHandle,
        }));
      }
    } catch (error) {
      console.error('Failed to load flow:', error);
      alert('Failed to load flow');
    }
  }

  function addNode() {
    const newNodeId = `step-${Date.now()}`;
    const newNode: Node = {
      id: newNodeId,
      type: 'default',
      position: { x: Math.random() * 400, y: Math.random() * 400 },
      data: {
        label: `Step ${nodes.length + 1}`,
        pythonCode: "print('Hello from step')",
        dependencies: '',
      }
    };
    nodes = [...nodes, newNode];
  }

  function onNodeClick(event: any) {
    const node = event.node;
    if (node) {
      selectedNodeId = node.id;
      currentStepId = node.id;
      currentStepName = node.data.label;
      currentStepCode = node.data.pythonCode || "print('Hello from step')";
      currentStepDependencies = node.data.dependencies || '';
      showStepEditor = true;
    }
  }

  function onNodesDelete(deleted: Node[]) {
    nodes = nodes.filter(n => !deleted.some(d => d.id === n.id));
    edges = edges.filter(e => !deleted.some(d => d.id === e.source || d.id === e.target));
    if (selectedNodeId && deleted.some(d => d.id === selectedNodeId)) {
      selectedNodeId = null;
      showStepEditor = false;
    }
  }

  function onConnect(connection: Connection) {
    if (connection.source && connection.target) {
      const newEdge: Edge = {
        id: `edge-${connection.source}-${connection.target}`,
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle,
        targetHandle: connection.targetHandle,
      };
      edges = [...edges, newEdge];
    }
  }

  function saveStep() {
    if (!selectedNodeId) return;

    nodes = nodes.map(node => {
      if (node.id === selectedNodeId) {
        return {
          ...node,
          data: {
            ...node.data,
            label: currentStepName,
            pythonCode: currentStepCode,
            dependencies: currentStepDependencies,
          }
        };
      }
      return node;
    });

    showStepEditor = false;
    selectedNodeId = null;
  }

  async function saveFlow() {
    if (!flowNameInput.trim()) {
      alert('Please enter a flow name');
      return;
    }

    saving = true;
    try {
      const flowSteps: FlowStep[] = nodes.map(node => ({
        id: node.id,
        name: node.data.label,
        pythonCode: node.data.pythonCode || '',
        dependencies: node.data.dependencies || undefined,
        position: node.position,
      }));

      const flowEdges: FlowEdge[] = edges.map(edge => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle,
        targetHandle: edge.targetHandle,
      }));

      if (onSave) {
        onSave({
          name: flowNameInput,
          steps: flowSteps,
          edges: flowEdges,
        });
      } else {
        // Save via API
        const method = flowId ? 'PUT' : 'POST';
        const url = flowId 
          ? `${apiUrl}/api/v1/flows/${flowId}`
          : `${apiUrl}/api/v1/flows`;

        const body = {
          name: flowNameInput,
          steps: flowSteps,
          edges: flowEdges,
        };

        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!res.ok) {
          const error = await res.json();
          throw new Error(error.detail || 'Failed to save flow');
        }

        const saved = await res.json();
        alert(`Flow saved successfully: ${saved.id}`);
        if (onSave) {
          await onSave({
            name: flowNameInput,
            steps: flowSteps,
            edges: flowEdges,
          });
        }
        if (onClose) onClose();
      }
    } catch (error) {
      console.error('Failed to save flow:', error);
      alert('Failed to save flow: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      saving = false;
    }
  }

  function closeStepEditor() {
    showStepEditor = false;
    selectedNodeId = null;
  }
</script>

<div class="flow-editor-container">
  <div class="flow-editor-header">
    <input
      type="text"
      bind:value={flowNameInput}
      placeholder="Flow Name"
      class="flow-name-input"
    />
    <div class="flow-editor-actions">
      <Button onclick={addNode} variant="outline" size="sm">
        + Add Step
      </Button>
      <Button onclick={saveFlow} disabled={saving} variant="default">
        {saving ? 'Saving...' : 'Save Flow'}
      </Button>
      {#if onClose}
        <Button onclick={onClose} variant="outline">
          Close
        </Button>
      {/if}
    </div>
  </div>

  <div class="flow-editor-content">
    <div class="flow-canvas">
      <SvelteFlow
        {nodes}
        {edges}
        on:nodeclick={onNodeClick}
        on:nodesdelete={onNodesDelete}
        on:connect={onConnect}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </SvelteFlow>
    </div>

    {#if showStepEditor}
      <div class="step-editor-panel">
        <div class="step-editor-header">
          <h3>Edit Step: {currentStepName}</h3>
          <Button onclick={closeStepEditor} variant="outline" size="sm">×</Button>
        </div>
        <div class="step-editor-content">
          <div class="mb-4">
            <label class="block text-sm font-medium mb-2">Step Name</label>
            <input
              type="text"
              bind:value={currentStepName}
              class="w-full px-3 py-2 border rounded"
              placeholder="Step name"
            />
          </div>
          <div class="mb-4">
            <label class="block text-sm font-medium mb-2">Dependencies (optional)</label>
            <input
              type="text"
              bind:value={currentStepDependencies}
              class="w-full px-3 py-2 border rounded"
              placeholder="e.g., numpy pandas"
            />
          </div>
          <div class="mb-4">
            <label class="block text-sm font-medium mb-2">Python Code</label>
            <div class="code-editor-container">
              <MonacoEditor bind:value={currentStepCode} language="python" theme="vs-dark" height="400px" />
            </div>
          </div>
          <div class="step-editor-actions">
            <Button onclick={saveStep} variant="default">Save Step</Button>
            <Button onclick={closeStepEditor} variant="outline">Cancel</Button>
          </div>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .flow-editor-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
  }

  .flow-editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid #e5e7eb;
    background: white;
  }

  .flow-name-input {
    font-size: 1.25rem;
    font-weight: 600;
    border: none;
    outline: none;
    padding: 0.5rem;
    flex: 1;
    max-width: 300px;
  }

  .flow-editor-actions {
    display: flex;
    gap: 0.5rem;
  }

  .flow-editor-content {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .flow-canvas {
    flex: 1;
    position: relative;
    background: #f9fafb;
  }

  .step-editor-panel {
    width: 500px;
    border-left: 1px solid #e5e7eb;
    background: white;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .step-editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .step-editor-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }

  .code-editor-container {
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
  }

  .step-editor-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }

  :global(.flow-editor-container .svelte-flow) {
    width: 100%;
    height: 100%;
  }
</style>

