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
    onRun?: (flowId: string) => void;
  }

  let { flowId, flowName = 'New Flow', onSave, onClose, onRun }: Props = $props();

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
  let running = $state(false);
  // Initialize state with default values to avoid capturing initial prop values
  let flowNameInput = $state('');
  let savedFlowId = $state<string | null>(null);
  
  // Sync props to state using $effect - this properly tracks prop changes
  $effect(() => {
    // Access props inside effect to create reactive dependency
    const currentFlowName = flowName || 'New Flow';
    const currentFlowId = flowId;
    
    // Only update if different to avoid unnecessary updates
    if (currentFlowName !== flowNameInput) {
      flowNameInput = currentFlowName;
    }
    
    const newFlowId = currentFlowId || null;
    if (newFlowId !== savedFlowId) {
      savedFlowId = newFlowId;
    }
  });

  // Load flow if flowId provided
  onMount(async () => {
    if (flowId) {
      await loadFlow(flowId);
    } else {
      // Create initial node - this will auto-open the editor
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
    
    // Automatically open editor for the new node
    // Use setTimeout to ensure reactive updates happen
    setTimeout(() => {
      selectedNodeId = newNodeId;
      currentStepId = newNodeId;
      currentStepName = newNode.data.label;
      currentStepCode = newNode.data.pythonCode;
      currentStepDependencies = newNode.data.dependencies;
      showStepEditor = true;
    }, 50);
  }

  function onNodeClick(event: any) {
    console.log('onNodeClick called with event:', event);
    console.log('Event type:', typeof event);
    console.log('Event detail:', event.detail);
    console.log('Event keys:', Object.keys(event));
    
    // @xyflow/svelte can pass the node in different ways:
    // - As event.detail.node (CustomEvent)
    // - As event.node (direct property)
    // - As event.detail itself (if it's the node)
    const node = event.detail?.node || event.node || (event.detail && typeof event.detail === 'object' && 'id' in event.detail ? event.detail : null);
    
    if (!node || !node.id) {
      console.warn('onNodeClick: Invalid node in event', event);
      console.warn('Trying to extract node from event.detail:', event.detail);
      return;
    }
    
    // Find the node in our nodes array to get the latest data
    const nodeInState = nodes.find(n => n.id === node.id);
    const nodeData = nodeInState?.data || node.data || {};
    
    console.log('onNodeClick: Opening editor for node', node.id, 'data:', nodeData);
    
    // Update all state synchronously
    selectedNodeId = node.id;
    currentStepId = node.id;
    currentStepName = nodeData.label || nodeData.name || `Step ${node.id}`;
    currentStepCode = nodeData.pythonCode || "print('Hello from step')";
    currentStepDependencies = nodeData.dependencies || '';
    
    // Open the editor panel
    showStepEditor = true;
  }

  function onNodeDoubleClick(event: any) {
    console.log('onNodeDoubleClick called with event:', event);
    // Double-click also opens editor (alternative to single click)
    // Extract node from event - @xyflow/svelte may pass it differently
    const node = event.detail?.node || event.node || (event.detail && typeof event.detail === 'object' && 'id' in event.detail ? event.detail : null);
    
    if (!node || !node.id) {
      console.warn('onNodeDoubleClick: Invalid node in event', event);
      return;
    }
    
    // Find the node in our nodes array to get the latest data
    const nodeInState = nodes.find(n => n.id === node.id);
    const nodeData = nodeInState?.data || node.data || {};
    
    console.log('onNodeDoubleClick: Opening editor for node', node.id, 'data:', nodeData);
    
    // Update all state synchronously
    selectedNodeId = node.id;
    currentStepId = node.id;
    currentStepName = nodeData.label || nodeData.name || `Step ${node.id}`;
    currentStepCode = nodeData.pythonCode || "print('Hello from step')";
    currentStepDependencies = nodeData.dependencies || '';
    
    // Open the editor panel
    showStepEditor = true;
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
    // Don't clear selectedNodeId - allow reopening the same node
  }

  async function saveFlow() {
    if (!flowNameInput.trim()) {
      alert('Please enter a flow name');
      return;
    }

    saving = true;
    try {
      // Ensure we have nodes before saving
      if (nodes.length === 0) {
        alert('Please add at least one step to the flow before saving');
        saving = false;
        return;
      }

      const flowSteps: FlowStep[] = nodes.map(node => {
        // Ensure node data exists
        const nodeData = node.data || {};
        return {
          id: node.id,
          name: (nodeData.label as string) || node.id,
          pythonCode: (nodeData.pythonCode as string) || '',
          dependencies: (nodeData.dependencies as string) || undefined,
          position: node.position,
        };
      });

      const flowEdges: FlowEdge[] = edges.map(edge => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle,
        targetHandle: edge.targetHandle,
      }));

      // Always save via API first
      const method = savedFlowId || flowId ? 'PUT' : 'POST';
      const url = savedFlowId || flowId
        ? `${apiUrl}/api/v1/flows/${savedFlowId || flowId}`
        : `${apiUrl}/api/v1/flows`;

      const body = {
        name: flowNameInput,
        steps: flowSteps,
        edges: flowEdges,
      };

      console.log('Saving flow with body:', JSON.stringify(body, null, 2));
      console.log('Number of steps:', flowSteps.length);
      console.log('Number of edges:', flowEdges.length);

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
      savedFlowId = saved.id;
      
      // Call onSave callback if provided (to refresh the flow list)
      if (onSave) {
        await onSave({
          name: flowNameInput,
          steps: flowSteps,
          edges: flowEdges,
        });
      }
      
      // Close the dialog
      if (onClose) {
        onClose();
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
    // Don't clear selectedNodeId - allow reopening the same node
  }

  async function runFlow() {
    const flowIdToRun = savedFlowId || flowId;
    if (!flowIdToRun) {
      alert('Please save the flow before running it');
      return;
    }

    running = true;
    try {
      const res = await fetch(`${apiUrl}/api/v1/flows/${flowIdToRun}/run`, {
        method: 'POST',
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Failed to run flow');
      }

      const result = await res.json();
      alert(`Flow started successfully: ${result.message}`);
      
      if (onRun) {
        onRun(flowIdToRun);
      }
    } catch (error) {
      console.error('Failed to run flow:', error);
      alert('Failed to run flow: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      running = false;
    }
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
        <Button onclick={addNode} variant="outline" size="sm" title="Add a new step (editor will open automatically)">
          + Add Step
        </Button>
      <Button onclick={saveFlow} disabled={saving} variant="default">
        {saving ? 'Saving...' : 'Save Flow'}
      </Button>
      {#if (savedFlowId || flowId) && onRun}
        <Button onclick={runFlow} disabled={running} variant="default">
          {running ? 'Running...' : 'Run Flow'}
        </Button>
      {/if}
      {#if onClose}
        <Button onclick={onClose} variant="outline">
          Close
        </Button>
      {/if}
    </div>
  </div>

  <div class="flow-editor-content">
    <div class="flow-canvas">
      <div class="canvas-hint">
        <p class="text-sm text-muted-foreground">
          💡 Click or double-click on any step node to edit it
        </p>
      </div>
      <SvelteFlow
        {nodes}
        {edges}
        nodesSelectable={true}
        nodesDraggable={true}
        nodesConnectable={true}
        onnodeclick={onNodeClick}
        onnodedoubleclick={onNodeDoubleClick}
        onnodesdelete={onNodesDelete}
        onconnect={onConnect}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </SvelteFlow>
    </div>

    {#if showStepEditor}
      <div class="step-editor-panel" role="region" aria-label="Step Editor">
        <div class="step-editor-header">
          <div>
            <h3>Edit Step: {currentStepName}</h3>
            <p class="text-xs text-muted-foreground">Step ID: {currentStepId}</p>
          </div>
          <Button onclick={closeStepEditor} variant="outline" size="sm" title="Close editor">×</Button>
        </div>
        <div class="step-editor-content">
          <div class="mb-4">
            <label for="step-name-input" class="block text-sm font-medium mb-2">Step Name</label>
            <input
              id="step-name-input"
              type="text"
              bind:value={currentStepName}
              class="w-full px-3 py-2 border rounded"
              placeholder="Step name"
            />
          </div>
          <div class="mb-4">
            <label for="step-dependencies-input" class="block text-sm font-medium mb-2">Dependencies (optional)</label>
            <input
              id="step-dependencies-input"
              type="text"
              bind:value={currentStepDependencies}
              class="w-full px-3 py-2 border rounded"
              placeholder="e.g., numpy pandas"
            />
          </div>
          <div class="mb-4">
            <label for="step-code-editor" class="block text-sm font-medium mb-2">Python Code</label>
            <div id="step-code-editor" class="code-editor-container">
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
    min-height: 0;
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
    border: 1px solid transparent;
    border-radius: 4px;
    outline: none;
    padding: 0.5rem;
    flex: 1;
    max-width: 300px;
    background: transparent;
    transition: border-color 0.2s, background-color 0.2s;
  }
  
  .flow-name-input:hover {
    border-color: #e5e7eb;
    background: #f9fafb;
  }
  
  .flow-name-input:focus {
    border-color: #3b82f6;
    background: white;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
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
    min-width: 0;
  }


  .canvas-hint {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 10;
    background: rgba(255, 255, 255, 0.9);
    padding: 8px 12px;
    border-radius: 4px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .step-editor-panel {
    width: 500px;
    min-width: 500px;
    max-width: 500px;
    border-left: 1px solid #e5e7eb;
    background: white;
    display: flex !important;
    flex-direction: column;
    overflow: hidden;
    flex-shrink: 0;
    z-index: 100;
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
  
  /* Make nodes narrower for better centering */
  :global(.flow-canvas .svelte-flow__node) {
    width: 120px !important;
    min-width: 120px !important;
    max-width: 120px !important;
  }
  
  :global(.flow-canvas .svelte-flow__node .svelte-flow__node-label) {
    font-size: 12px !important;
    padding: 8px !important;
    text-align: center !important;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }
</style>

