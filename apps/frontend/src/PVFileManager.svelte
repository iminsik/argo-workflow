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
  let operationInProgress = $state(false);
  let operationMessage = $state<string | null>(null);
  let operationProgress = $state(0); // 0-100

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
    <!-- Operation Progress Indicator -->
    {#if operationInProgress}
      <div class="mb-4 p-4 bg-primary/10 border border-primary rounded">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">{operationMessage || 'Processing...'}</span>
          <span class="text-sm text-muted-foreground">{operationProgress}%</span>
        </div>
        <div class="w-full bg-muted rounded-full h-2">
          <div 
            class="bg-primary h-2 rounded-full transition-all duration-300"
            style="width: {operationProgress}%"
          ></div>
        </div>
      </div>
    {/if}
    
    <!-- Debug info (remove after fixing) -->
    <div class="mb-2 text-xs text-muted-foreground">
      Debug: {fileData.length} items loaded
    </div>
    <div class="h-[70vh] border rounded overflow-hidden">
      <Willow>
        <Filemanager 
          data={fileData}
          onOpen={handleFileOpen}
          uploadUrl={`${apiUrl}/api/v1/pv/upload`}
          init={(api) => {
            // Store the API reference
            fileManagerApi = api;
            
            // Intercept upload-files to handle file uploads
            api.intercept('upload-files', async (ev: any) => {
              const files = ev.files || [];
              const target = ev.target || '/mnt/results';
              
              if (files.length === 0) {
                return ev; // Continue with default behavior if no files
              }
              
              try {
                operationInProgress = true;
                operationMessage = `Uploading ${files.length} file(s)...`;
                operationProgress = 0;
                
                const uploadedFiles: string[] = [];
                const totalFiles = files.length;
                
                // Determine target directory
                let targetDir = target;
                if (target === '/' || target === '') {
                  targetDir = '/mnt/results';
                } else if (!target.startsWith('/mnt/results')) {
                  targetDir = `/mnt/results/${target}`;
                }
                
                // Upload each file
                for (let i = 0; i < files.length; i++) {
                  const file = files[i];
                  operationMessage = `Uploading ${file.name}... (${i + 1}/${totalFiles})`;
                  operationProgress = Math.round((i / totalFiles) * 90);
                  
                  // Create FormData for file upload
                  const formData = new FormData();
                  formData.append('file', file);
                  formData.append('destination_path', targetDir);
                  formData.append('target', targetDir);
                  
                  // Upload file
                  const uploadResponse = await fetch(`${apiUrl}/api/v1/pv/upload`, {
                    method: 'POST',
                    body: formData
                  });
                  
                  if (!uploadResponse.ok) {
                    const errorData = await uploadResponse.json();
                    throw new Error(`Failed to upload ${file.name}: ${errorData.detail || 'Unknown error'}`);
                  }
                  
                  const uploadData = await uploadResponse.json();
                  uploadedFiles.push(uploadData.path);
                }
                
                operationMessage = 'Finalizing...';
                operationProgress = 95;
                
                // Refresh file list
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
                    
                    api.exec('provide-data', { data: updatedItems, id: targetDir });
                  }
                  
                  operationProgress = 100;
                  setTimeout(() => {
                    operationInProgress = false;
                    operationMessage = null;
                    operationProgress = 0;
                  }, 300);
                }, 100);
                
                // Continue with the intercepted event
                return ev;
              } catch (err) {
                console.error('Error uploading files:', err);
                operationInProgress = false;
                operationMessage = null;
                operationProgress = 0;
                alert(`Error uploading files: ${err instanceof Error ? err.message : 'Unknown error'}`);
                return false; // Prevent the operation in SVAR
              }
            });
            
            // Intercept copy-files to calculate and use actual destination paths
            api.intercept('copy-files', async (ev: any) => {
              const ids = ev.ids || [];
              const target = ev.target || '/mnt/results';
              console.log('SVAR copy-files intercepted:', ids, 'to', target);
              
              try {
                operationInProgress = true;
                operationMessage = `Copying ${ids.length} file(s)...`;
                operationProgress = 0;
                
                const actualDestinations: string[] = [];
                const totalFiles = ids.length;
                
                // Calculate actual destination paths and perform copy for each file
                for (let i = 0; i < ids.length; i++) {
                  const fileId = ids[i];
                  const sourcePath = fileId;
                  const fileName = sourcePath.split('/').pop() || 'file';
                  
                  operationMessage = `Copying ${fileName}... (${i + 1}/${totalFiles})`;
                  operationProgress = Math.round((i / totalFiles) * 50); // First half for preparation
                  
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
                  
                  operationMessage = `Copying ${fileName}... (${i + 1}/${totalFiles})`;
                  operationProgress = Math.round(50 + (i / totalFiles) * 40); // 50-90% for copying
                  
                  // Copy the file
                  const copyResponse = await fetch(`${apiUrl}/api/v1/pv/copy?source_path=${encodeURIComponent(sourcePath)}&destination_path=${encodeURIComponent(finalDestination)}`, {
                    method: 'POST'
                  });
                  
                  if (!copyResponse.ok) {
                    const errorData = await copyResponse.json();
                    console.error('Error copying file:', errorData);
                    operationInProgress = false;
                    operationMessage = null;
                    alert(`Failed to copy ${fileName}: ${errorData.detail || 'Unknown error'}`);
                    return false; // Prevent the operation in SVAR
                  }
                  
                  actualDestinations.push(finalDestination);
                }
                
                operationMessage = 'Finalizing...';
                operationProgress = 95;
                
                // Get the target directory to update
                const targetDir = target === '/' || target === '' 
                  ? '/mnt/results' 
                  : (target.startsWith('/mnt/results') ? target : `/mnt/results/${target}`);
                
                operationProgress = 98;
                
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
                  
                  operationProgress = 100;
                  setTimeout(() => {
                    operationInProgress = false;
                    operationMessage = null;
                    operationProgress = 0;
                  }, 300);
                }, 100);
                
                // Continue with the intercepted event
                return ev;
              } catch (err) {
                console.error('Error handling copy-files:', err);
                operationInProgress = false;
                operationMessage = null;
                operationProgress = 0;
                alert(`Error copying files: ${err instanceof Error ? err.message : 'Unknown error'}`);
                return false; // Prevent the operation in SVAR
              }
            });
            
            // Handle delete operation
            api.on('delete-files', async (ev: any) => {
              const ids = ev.ids || [];
              operationInProgress = true;
              operationMessage = `Deleting ${ids.length} file(s)...`;
              operationProgress = 0;
              // Note: Delete API would need to be implemented
              // For now, just show progress
              setTimeout(() => {
                operationInProgress = false;
                operationMessage = null;
                operationProgress = 0;
              }, 1000);
            });
            
            
            // Handle create operation (for creating new files/folders)
            api.on('create-files', async (ev: any) => {
              // This is for creating new empty files or folders
              // For now, we'll handle folder creation
              const items = ev.items || [];
              const target = ev.target || '/mnt/results';
              
              try {
                operationInProgress = true;
                operationMessage = `Creating ${items.length} item(s)...`;
                operationProgress = 0;
                
                // Determine target directory
                let targetDir = target;
                if (target === '/' || target === '') {
                  targetDir = '/mnt/results';
                } else if (!target.startsWith('/mnt/results')) {
                  targetDir = `/mnt/results/${target}`;
                }
                
                // Note: Create API would need to be implemented in backend
                // For now, just show progress
                setTimeout(() => {
                  operationInProgress = false;
                  operationMessage = null;
                  operationProgress = 0;
                }, 1000);
              } catch (err) {
                console.error('Error creating files:', err);
                operationInProgress = false;
                operationMessage = null;
                operationProgress = 0;
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

