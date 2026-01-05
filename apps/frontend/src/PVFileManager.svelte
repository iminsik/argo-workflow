<script lang="ts">
  import { onMount } from 'svelte';
  import { Filemanager, Willow } from '@svar-ui/svelte-filemanager';
  import Button from '$lib/components/ui/button.svelte';
  import { RefreshCw } from 'lucide-svelte';

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  let fileData = $state<any[]>([]);
  let loading = $state(false);
  let error = $state<string | null>(null);
  let currentPath = $state('/mnt/results');
  let selectedFileContent = $state<string | null>(null);
  let selectedFileName = $state<string | null>(null);
  let fileManagerApi: any = null;

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
      
      // Transform data to SVAR File Manager format
      // SVAR File Manager needs parent folders to be explicitly included
      const items = data.data || [];
      
      // Create parent folder structure
      const parentFolders = [
        {
          id: '/mnt',
          size: 0,
          date: new Date(),
          type: 'folder'
        },
        {
          id: '/mnt/results',
          size: 0,
          date: new Date(),
          type: 'folder'
        }
      ];
      
      // Map file items
      const fileItems = items.map((item: any) => ({
        id: item.id, // Full path like "/mnt/results/file.json"
        size: item.size || 0,
        date: new Date(item.date),
        type: item.type // 'file' or 'folder'
      }));
      
      // Combine parent folders and files
      // SVAR will organize them hierarchically
      fileData = [...parentFolders, ...fileItems];
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error occurred';
      fileData = [];
    } finally {
      loading = false;
    }
  }

  async function handleFileOpen(ev: any) {
    const item = ev?.item || ev;
    if (!item) return;

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
        // Extract filename from path
        selectedFileName = item.id.split('/').pop() || item.id;
        
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
  <div class="flex justify-end items-center mb-4">
    <Button onclick={() => fetchFiles(currentPath)} disabled={loading} variant="outline">
      <RefreshCw size={16} class="mr-2" /> Refresh
    </Button>
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
    <!-- Debug info (remove after fixing) -->
    <div class="mb-2 text-xs text-muted-foreground">
      Debug: {fileData.length} items loaded
    </div>
    <div class="h-[70vh] border rounded overflow-hidden">
      <Willow>
        <Filemanager 
          data={fileData}
          onOpen={handleFileOpen}
          init={(api) => {
            // Store the API reference
            fileManagerApi = api;
            
            // Handle request-data event for dynamic folder loading
            api.on('request-data', async (ev: any) => {
              const folderId = ev.id || '/mnt/results';
              console.log('SVAR requesting data for folder:', folderId);
              
              try {
                const response = await fetch(`${apiUrl}/api/v1/pv/files?path=${encodeURIComponent(folderId)}`);
                if (response.ok) {
                  const data = await response.json();
                  const items = (data.data || []).map((item: any) => ({
                    id: item.id,
                    size: item.size || 0,
                    date: new Date(item.date),
                    type: item.type
                  }));
                  
                  // Provide data to SVAR
                  api.exec('provide-data', { data: items, id: folderId });
                }
              } catch (err) {
                console.error('Error loading folder data:', err);
              }
            });
          }}
        />
      </Willow>
    </div>
    
    {#if selectedFileContent !== null}
      <div class="mt-4 border rounded p-4">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-semibold truncate">File Content: {selectedFileName}</h3>
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
        <div class="bg-muted p-4 rounded max-h-[400px] overflow-auto border">
          <pre class="text-sm whitespace-pre-wrap font-mono text-foreground">{selectedFileContent}</pre>
        </div>
      </div>
    {/if}
  {/if}
</div>

