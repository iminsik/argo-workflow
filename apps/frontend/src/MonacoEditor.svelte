<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import * as monaco from 'monaco-editor';
  import type { editor } from 'monaco-editor';

  interface Props {
    value?: string;
    language?: string;
    theme?: string;
    height?: string;
  }

  let { value = $bindable(''), language = 'python', theme = 'vs-dark', height = '400px' }: Props = $props();

  let container: HTMLDivElement;
  let editorInstance: editor.IStandaloneCodeEditor | null = null;

  $effect(() => {
    if (editorInstance && editorInstance.getValue() !== value) {
      editorInstance.setValue(value);
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
    });

    editorInstance.onDidChangeModelContent(() => {
      const newValue = editorInstance?.getValue() || '';
      if (newValue !== value) {
        value = newValue;
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

<div bind:this={container} style="width: 100%; height: {height};"></div>

<style>
  div {
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
  }
</style>
