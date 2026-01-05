<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '$lib/components/ui/button.svelte';
  import { RefreshCw, Folder, File, ChevronRight, ChevronLeft } from 'lucide-svelte';

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  let fileData = $state<any[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let currentPath = $state('/mnt/results');
  let selectedFileContent = $state<string | null>(null);
  let selectedFileName = $state<string | null>(null);

  interface FileItem {
    id: string;
    name: string;
    type: 'file' | 'folder';
    size: number;
    date: string;
  }

  async function fetchFiles(path: string = '/mnt/results') {
    try {
      loading = true;
      error = null;
      currentPath = path;
      selectedFileContent = null;
      selectedFileName = null;

      const response = await fetch(`${apiUrl}/api/v1/pv/files?path=${encodeURIComponent(path)}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch files');
      }

      const data = await response.json();
      // Convert date strings to Date objects for SVAR File Manager
      fileData = (data.data || []).map((item: any) => ({
        ...item,
        date: new Date(item.date)
      }));
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error occurred';
      fileData = [];
    } finally {
      loading = false;
    }
  }

  async function handleFileClick(item: FileItem) {
    if (item.type === 'folder') {
      // Navigate into folder
      await fetchFiles(item.id);
    } else if (item.type === 'file') {
      // Read and display file content
      try {
        loading = true;
        const response = await fetch(`${apiUrl}/api/v1/pv/file?path=${encodeURIComponent(item.id)}`);
        
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to read file');
        }

        const fileData = await response.json();
        selectedFileName = item.name;
        
        if (fileData.encoding === 'base64') {
          selectedFileContent = `[Binary file - ${item.size} bytes]\nBase64 encoded content available.`;
        } else {
          selectedFileContent = fileData.content;
        }
      } catch (err) {
        error = err instanceof Error ? err.message : 'Unknown error occurred';
        selectedFileContent = null;
      } finally {
        loading = false;
      }
    }
  }

  function navigateToParent() {
    if (currentPath === '/mnt/results') {
      return; // Already at root
    }
    const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/mnt/results';
    fetchFiles(parentPath);
  }

  function navigateToRoot() {
    fetchFiles('/mnt/results');
  }

  onMount(() => {
    fetchFiles();
  });
</script>

<div class="container mx-auto p-4">
  <div class="flex justify-between items-center mb-4">
    <h2 class="text-2xl font-semibold">Persistent Volume File Manager</h2>
    <div class="flex gap-2">
      <Button onclick={() => fetchFiles(currentPath)} disabled={loading} variant="outline">
        <RefreshCw size={16} class="mr-2" /> Refresh
      </Button>
    </div>
  </div>

  <div class="mb-4">
    <div class="flex items-center gap-2 text-sm text-muted-foreground">
      <button 
        onclick={navigateToRoot}
        class="hover:text-foreground underline"
        disabled={currentPath === '/mnt/results'}
      >
        /mnt/results
      </button>
      {#if currentPath !== '/mnt/results'}
        <span>/</span>
        <button 
          onclick={navigateToParent}
          class="hover:text-foreground underline"
        >
          ..
        </button>
      {/if}
    </div>
    <div class="text-sm text-muted-foreground mt-1">
      Current path: <code class="bg-muted px-1 rounded">{currentPath}</code>
    </div>
  </div>

  {#if error}
    <div class="mb-4 p-4 bg-destructive/10 border border-destructive rounded text-destructive">
      Error: {error}
    </div>
  {/if}

  {#if loading}
    <div class="text-center p-8 text-muted-foreground">
      Loading files...
    </div>
  {:else if fileData.length === 0 && !error}
    <div class="text-center p-8 text-muted-foreground">
      No files or directories found in this location.
    </div>
  {:else if !error}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div class="border rounded p-4">
        <h3 class="text-lg font-semibold mb-4">Files and Directories</h3>
        <div class="space-y-1 max-h-[600px] overflow-auto">
          {#each fileData as item (item.id)}
            <div 
              class="p-3 hover:bg-muted rounded cursor-pointer flex items-center justify-between group transition-colors"
              onclick={() => handleFileClick(item)}
            >
              <div class="flex items-center gap-3 flex-1 min-w-0">
                {#if item.type === 'folder'}
                  <Folder size={20} class="text-blue-500 flex-shrink-0" />
                {:else}
                  <File size={20} class="text-gray-500 flex-shrink-0" />
                {/if}
                <span class="font-medium truncate">{item.name}</span>
                {#if item.type === 'folder'}
                  <ChevronRight size={16} class="text-muted-foreground flex-shrink-0 ml-auto" />
                {/if}
              </div>
              <div class="text-sm text-muted-foreground flex-shrink-0 ml-2">
                {#if item.type === 'file'}
                  {item.size < 1024 
                    ? `${item.size} B` 
                    : item.size < 1024 * 1024 
                    ? `${(item.size / 1024).toFixed(2)} KB` 
                    : `${(item.size / (1024 * 1024)).toFixed(2)} MB`}
                {/if}
              </div>
            </div>
          {/each}
        </div>
      </div>
      
      <div class="border rounded p-4">
        {#if selectedFileContent !== null}
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-semibold truncate">File: {selectedFileName}</h3>
            <Button
              onclick={() => {
                selectedFileContent = null;
                selectedFileName = null;
              }}
              variant="ghost"
              size="sm"
            >
              Close
            </Button>
          </div>
          <div class="bg-muted p-4 rounded max-h-[600px] overflow-auto border">
            <pre class="text-sm whitespace-pre-wrap font-mono text-foreground">{selectedFileContent}</pre>
          </div>
        {:else}
          <div class="text-center text-muted-foreground p-8 h-full flex items-center justify-center">
            <div>
              <File size={48} class="mx-auto mb-4 opacity-50" />
              <p>Click on a file to view its contents</p>
            </div>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

