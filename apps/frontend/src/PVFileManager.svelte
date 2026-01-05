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


  // Handle uploads - following SVAR's recommended approach
  const handleUpload = async (ev: any) => {
    console.log('🔴 handleUpload called with:', ev);
    console.log('🔴 ev.detail:', ev.detail);
    console.log('🔴 ev type:', typeof ev);
    console.log('🔴 ev keys:', Object.keys(ev || {}));
    
    // SVAR passes: { files: File[], target: string }
    // Try multiple ways to extract files and target
    const files = ev.detail?.files || ev.files || ev.data?.files || (ev.data?.file ? [ev.data.file] : []) || [];
    const target = ev.detail?.target || ev.target || ev.data?.target || ev.destination || '/mnt/results';
    
    console.log('🔴 Extracted:', { files: files.length, target, filesArray: files });
    
    if (files.length === 0) {
      console.log('No files to upload');
      return;
    }
    
    try {
      operationInProgress = true;
      operationMessage = `Uploading ${files.length} file(s)...`;
      operationProgress = 0;
      
      // Determine target directory (ensure it's within /mnt/results)
      let targetDir = target;
      if (target === '/' || target === '') {
        targetDir = '/mnt/results';
      } else if (!target.startsWith('/mnt/results')) {
        // If target is relative or doesn't start with /mnt/results, make it absolute
        targetDir = `/mnt/results/${target.replace(/^\//, '')}`;
      }
      
      console.log('Uploading to:', targetDir);
      
      // Upload each file
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        operationMessage = `Uploading ${file.name}... (${i + 1}/${files.length})`;
        operationProgress = Math.round((i / files.length) * 90);
        
        // Create FormData as recommended
        const formData = new FormData();
        formData.append('file', file);
        formData.append('path', targetDir);  // Use 'path' as recommended
        
        // Upload file
        const response = await fetch(`${apiUrl}/api/v1/pv/upload`, {
          method: 'POST',
          body: formData
        });
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(`Failed to upload ${file.name}: ${errorData.detail || 'Unknown error'}`);
        }
        
        const uploadData = await response.json();
        console.log('Uploaded:', uploadData);
      }
      
      operationProgress = 100;
      operationMessage = 'Upload complete!';
      
      // Refresh SVAR file manager - use exec('refresh') or provide-data
      if (fileManagerApi) {
        try {
          // Try different refresh methods
          if (typeof fileManagerApi.refresh === 'function') {
            fileManagerApi.refresh();
          } else if (typeof fileManagerApi.exec === 'function') {
            // Refresh by providing updated data
            const refreshResponse = await fetch(`${apiUrl}/api/v1/pv/files?path=${encodeURIComponent(targetDir)}`);
            if (refreshResponse.ok) {
              const refreshData = await refreshResponse.json();
              const updatedItems = (refreshData.data || []).map((item: any) => ({
                id: item.id,
                size: item.size || 0,
                date: new Date(item.date),
                type: item.type
              }));
              fileManagerApi.exec('provide-data', { data: updatedItems, id: targetDir });
            }
          }
        } catch (err) {
          console.warn('Could not refresh file manager:', err);
        }
      }
      
      // Also refresh our file list
      await fetchFiles(targetDir);
      
      setTimeout(() => {
        operationInProgress = false;
        operationMessage = null;
        operationProgress = 0;
      }, 500);
    } catch (err) {
      console.error('Upload error:', err);
      operationInProgress = false;
      operationMessage = null;
      operationProgress = 0;
      alert(`Error uploading files: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

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
    
    <!-- Manual upload button (fallback if SVAR upload doesn't work) -->
    <div class="mb-2">
      <Button
        onclick={async () => {
          const input = document.createElement('input');
          input.type = 'file';
          input.multiple = true;
          input.onchange = (e: any) => {
            const files = Array.from(e.target.files || []);
            if (files.length > 0) {
              console.log('📁 Files selected via manual button:', files);
              handleUpload({ detail: { files, target: currentPath } });
            }
          };
          input.click();
        }}
        variant="outline"
        size="sm"
      >
        Upload Files
      </Button>
    </div>
    <div class="h-[70vh] border rounded overflow-hidden">
      <Willow>
        <Filemanager 
          data={fileData}
          onOpen={handleFileOpen}
          on:upload={(ev) => {
            console.log('🟢 on:upload event fired:', ev);
            console.log('🟢 Event detail:', ev.detail);
            console.log('🟢 Event type:', typeof ev);
            handleUpload(ev);
          }}
          upload={true}
          uploadUrl={`${apiUrl}/api/v1/pv/upload`}
          previews={(file: any, width?: number, height?: number) => {
            // Enable previews for image files
            const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico'];
            const fileId = file.id || file.name || '';
            const isImage = imageExtensions.some(ext => fileId.toLowerCase().endsWith(ext));
            
            if (isImage) {
              // Return preview URL for images
              const params = new URLSearchParams({
                path: fileId
              });
              if (width) params.append('width', width.toString());
              if (height) params.append('height', height.toString());
              return `${apiUrl}/api/v1/pv/preview?${params.toString()}`;
            }
            
            // Return null for non-image files (no preview)
            return null;
          }}
          init={(api) => {
            // Store the API reference for refresh
            fileManagerApi = api;
            
            console.log('Filemanager API initialized:', api);
            console.log('🔍 Available API methods:', Object.keys(api));
            
            // Check if SVAR has upload-related methods or properties
            if (typeof api.upload === 'function') {
              console.log('✅ SVAR has upload() method');
            }
            if (typeof api.triggerUpload === 'function') {
              console.log('✅ SVAR has triggerUpload() method');
            }
            
            // Note: SVAR's built-in upload button doesn't seem to fire events
            // The manual "Upload Files" button works perfectly, so we'll use that
            // If SVAR's upload events start firing, they'll be caught by the listeners above
            
            // Also set up event listeners in init (fallback)
            api.on('upload', (ev: any) => {
              console.log('🟡 api.on("upload") event fired:', ev);
              handleUpload(ev);
            });
            
            // Try intercepting upload events - handle it ourselves
            api.intercept('upload', (ev: any) => {
              console.log('🟠 api.intercept("upload") event fired:', ev);
              console.log('🟠 Intercept event keys:', Object.keys(ev || {}));
              console.log('🟠 Intercept event detail:', ev.detail);
              // Handle the upload ourselves
              handleUpload(ev);
              // Return false to prevent SVAR's default upload behavior
              return false;
            });
            
            // Listen for create-files which might be triggered by "Upload file" menu option
            api.on('create-files', (ev: any) => {
              console.log('🔵 api.on("create-files") event fired:', ev);
              // Check if this is actually an upload (has files)
              if (ev.files || ev.detail?.files) {
                console.log('🔵 create-files has files, treating as upload');
                handleUpload(ev);
              }
            });
            
            // Also listen for file-upload event (alternative name)
            api.on('file-upload', (ev: any) => {
              console.log('🟣 api.on("file-upload") event fired:', ev);
              handleUpload(ev);
            });
            
            // Log all events to see what's happening
            const logAllEvents = (eventName: string) => {
              api.on(eventName, (ev: any) => {
                console.log(`📢 Event "${eventName}" fired:`, ev);
              });
            };
            
            // Monitor common upload-related events
            ['upload', 'file-upload', 'add-files', 'create-files'].forEach(logAllEvents);
            
            // Since uploadUrl is provided, SVAR might make direct HTTP requests
            // Intercept fetch requests to catch SVAR's upload requests
            const originalFetch = window.fetch;
            window.fetch = async function(...args) {
              const [url, options] = args;
              
              // Check if this is an upload request
              if (typeof url === 'string' && url.includes('/api/v1/pv/upload')) {
                console.log('🌐 Fetch intercepted upload request:', url, options);
                
                if (options?.body instanceof FormData) {
                  // Get current target directory
                  const currentTarget = currentPath || '/mnt/results';
                  
                  // Add path parameter if not present
                  if (!options.body.has('path')) {
                    options.body.append('path', currentTarget);
                    console.log('🌐 Added path parameter to FormData:', currentTarget);
                  }
                  
                  // Show progress
                  operationInProgress = true;
                  operationMessage = 'Uploading file...';
                  operationProgress = 0;
                  
                  try {
                    const response = await originalFetch(url, options);
                    console.log('🌐 Upload response:', response.status);
                    
                    if (response.ok) {
                      operationProgress = 100;
                      setTimeout(async () => {
                        operationInProgress = false;
                        operationMessage = null;
                        operationProgress = 0;
                        // Refresh file list
                        await fetchFiles(currentTarget);
                      }, 300);
                    } else {
                      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                      operationInProgress = false;
                      operationMessage = null;
                      operationProgress = 0;
                      alert(`Upload failed: ${errorData.detail || 'Unknown error'}`);
                    }
                    
                    return response;
                  } catch (err) {
                    console.error('🌐 Upload error:', err);
                    operationInProgress = false;
                    operationMessage = null;
                    operationProgress = 0;
                    throw err;
                  }
                }
              }
              
              return originalFetch.apply(this, args);
            };
            
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

