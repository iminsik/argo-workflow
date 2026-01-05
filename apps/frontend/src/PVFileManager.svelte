<script lang="ts">
  import { onMount } from 'svelte';
  import { Filemanager, Willow } from '@svar-ui/svelte-filemanager';
  import Button from '$lib/components/ui/button.svelte';

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


  onMount(() => {
    fetchFiles();
  });
</script>

<div class="container mx-auto p-4">

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
            
            // Intercept copy-files to calculate and use actual destination paths
            api.intercept('copy-files', async (ev: any) => {
              const ids = ev.ids || [];
              const target = ev.target || '/mnt/results';
              console.log('SVAR copy-files intercepted:', ids, 'to', target);
              
              try {
                const actualDestinations: string[] = [];
                
                // Calculate actual destination paths and perform copy for each file
                for (const fileId of ids) {
                  const sourcePath = fileId;
                  const fileName = sourcePath.split('/').pop() || 'file';
                  
                  // Determine destination path
                  let destinationPath: string;
                  if (target === '/' || target === '') {
                    destinationPath = `/mnt/results/${fileName}`;
                  } else if (target.startsWith('/mnt/results')) {
                    destinationPath = `${target}/${fileName}`;
                  } else {
                    destinationPath = `/mnt/results/${target}/${fileName}`;
                  }
                  
                  // If file already exists, add a number suffix
                  let finalDestination = destinationPath;
                  let counter = 1;
                  while (true) {
                    // Check if destination exists
                    const targetDir = destinationPath.substring(0, destinationPath.lastIndexOf('/'));
                    const checkResponse = await fetch(`${apiUrl}/api/v1/pv/files?path=${encodeURIComponent(targetDir)}`);
                    if (checkResponse.ok) {
                      const checkData = await checkResponse.json();
                      const existingFiles = (checkData.data || []).map((f: any) => f.id);
                      if (existingFiles.includes(finalDestination)) {
                        const nameWithoutExt = fileName.substring(0, fileName.lastIndexOf('.')) || fileName;
                        const ext = fileName.includes('.') ? fileName.substring(fileName.lastIndexOf('.')) : '';
                        finalDestination = `${targetDir}/${nameWithoutExt}_${counter}${ext}`;
                        counter++;
                      } else {
                        break;
                      }
                    } else {
                      break;
                    }
                  }
                  
                  // Copy the file
                  const copyResponse = await fetch(`${apiUrl}/api/v1/pv/copy?source_path=${encodeURIComponent(sourcePath)}&destination_path=${encodeURIComponent(finalDestination)}`, {
                    method: 'POST'
                  });
                  
                  if (!copyResponse.ok) {
                    const errorData = await copyResponse.json();
                    console.error('Error copying file:', errorData);
                    alert(`Failed to copy ${fileName}: ${errorData.detail || 'Unknown error'}`);
                    return false; // Prevent the operation in SVAR
                  }
                  
                  actualDestinations.push(finalDestination);
                }
                
                // Get the target directory to update
                const targetDir = target === '/' || target === '' 
                  ? '/mnt/results' 
                  : (target.startsWith('/mnt/results') ? target : `/mnt/results/${target}`);
                
                // Immediately fetch and provide updated data to replace temp files
                // Use a small delay to ensure the file system has updated
                setTimeout(async () => {
                  const refreshResponse = await fetch(`${apiUrl}/api/v1/pv/files?path=${encodeURIComponent(targetDir)}`);
                  if (refreshResponse.ok) {
                    const refreshData = await refreshResponse.json();
                    const updatedItems = (refreshData.data || []).map((item: any) => ({
                      id: item.id,
                      size: item.size || 0,
                      date: new Date(item.date),
                      type: item.type
                    }));
                    
                    // Provide updated data to SVAR to replace temp entries with actual files
                    api.exec('provide-data', { data: updatedItems, id: targetDir });
                  }
                }, 100);
                
                // Continue with the intercepted event
                return ev;
              } catch (err) {
                console.error('Error handling copy-files:', err);
                alert(`Error copying files: ${err instanceof Error ? err.message : 'Unknown error'}`);
                return false; // Prevent the operation in SVAR
              }
            });
            
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

