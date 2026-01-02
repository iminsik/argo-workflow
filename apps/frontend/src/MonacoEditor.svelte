<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import * as monaco from 'monaco-editor';
  import type { editor } from 'monaco-editor';

  interface Props {
    value?: string;
    language?: string;
    theme?: string;
    height?: string;
    readonly?: boolean;
  }

  let { value = $bindable(''), language = 'python', theme = 'vs-dark', height = '400px', readonly = false }: Props = $props();

  let container: HTMLDivElement;
  let editorInstance: editor.IStandaloneCodeEditor | null = null;
  let isUpdatingFromExternal = false;

  // Update editor when value prop changes - use $effect to track value
  $effect(() => {
    // Access value to create dependency
    const currentValue = value;
    
    if (editorInstance) {
      const editorValue = editorInstance.getValue();
      if (editorValue !== currentValue) {
        isUpdatingFromExternal = true;
        editorInstance.setValue(currentValue);
        // Move cursor to end and scroll to bottom
        const lineCount = editorInstance.getModel()?.getLineCount() || 1;
        editorInstance.setPosition({ lineNumber: lineCount, column: 1 });
        editorInstance.revealLine(lineCount);
        // Small delay to ensure update completes
        setTimeout(() => {
          isUpdatingFromExternal = false;
        }, 0);
      }
    }
  });

  onMount(() => {
    if (!container) return;

    editorInstance = monaco.editor.create(container, {
      value,
      language,
      theme,
      minimap: { enabled: false },
      fontSize: 14,
      lineNumbers: 'on',
      scrollBeyondLastLine: false,
      automaticLayout: true,
      readOnly: readonly,
    });

    editorInstance.onDidChangeModelContent(() => {
      // Only update the prop if the change came from user input, not from external update
      // Skip updates if editor is readonly
      if (!isUpdatingFromExternal && !readonly && editorInstance) {
        const newValue = editorInstance.getValue();
        if (newValue !== value) {
          value = newValue;
        }
      }
    });
    
    // Update readonly state when prop changes
    $effect(() => {
      if (editorInstance) {
        editorInstance.updateOptions({ readOnly: readonly });
      }
    });

    // Handle window resize
    const handleResize = () => {
      editorInstance?.layout();
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
    };
  });

  onDestroy(() => {
    if (editorInstance) {
      editorInstance.dispose();
      editorInstance = null;
    }
  });
</script>

<div bind:this={container} class="monaco-container" style="width: 100%; height: {height};"></div>

<style>
  .monaco-container {
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
  }
  
  :global(.monaco-container) {
    min-height: 200px;
  }
</style>
