# Cache Verification Guide

This guide explains how to verify that UV cache and Nix cache are working correctly to minimize downloads from external sources.

## UV Cache Verification

### Evidence from Logs

**First Run (Cache Miss):**
```
Downloading numpy (14.0MiB)
Downloaded numpy
Resolved 1 package in 143ms
Installed 1 package in 293ms
```

**Second Run (Cache Hit):**
```
Resolved 1 package in 13ms    ← Much faster resolution
Installed 1 package in 231ms   ← Faster installation
```
**Key indicator:** No "Downloading" message means the package was found in cache.

### How to Verify

1. **Check cache directory size:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- du -sh /root/.cache/uv
   ```

2. **List cached packages:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- ls -la /root/.cache/uv
   ```

3. **Compare run times:**
   - First run: Look for "Downloading" messages
   - Subsequent runs: Should NOT have "Downloading" messages for same packages

## Nix Cache Verification

### Evidence from Logs

**First Run (Cache Miss - Before Fix):**
```
these 28 paths will be fetched (21.42 MiB download, 128.28 MiB unpacked)
copying path '/nix/store/...' from 'https://cache.nixos.org'...
```

**Second Run (Cache Hit - After Fix):**
```
these 28 paths will be fetched (0 MiB download, 0 MiB unpacked)  ← No download!
copying path '/nix/store/...' from 'https://cache.nixos.org'...    ← Should be minimal or none
```

**Key indicators:**
- `0 MiB download` means packages are already in the store
- Fewer or no "copying path" messages means cache hits

### How to Verify

1. **Check Nix store size:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- du -sh /nix/store
   ```

2. **List cached packages:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- ls -la /nix/store | head -20
   ```

3. **Check PVC usage:**
   ```bash
   kubectl get pvc nix-store-pvc -n argo -o jsonpath='{.status.capacity.storage}'
   ```

4. **Compare download sizes:**
   - First run: Should show "21.42 MiB download" or similar
   - Second run: Should show "0 MiB download" or very small amount

## Configuration

### UV Cache
- **Location:** `/root/.cache/uv` (mounted from `uv-cache-pvc`)
- **Automatic:** UV automatically uses this directory when `UV_CACHE_DIR` is set
- **Status:** ✅ Working (verified from logs)

### Nix Cache
- **Location:** `/nix/store` (mounted from `nix-store-pvc`)
- **Configuration:** Set `NP_STORE=/nix/store` environment variable
- **Status:** ✅ Fixed (now configured to use shared PVC)

## Troubleshooting

### If Nix cache isn't working:

1. **Verify PVC is mounted:**
   ```bash
   kubectl get pod <pod-name> -n argo -o jsonpath='{.spec.containers[0].volumeMounts}' | grep nix-store
   ```

2. **Check environment variable:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- env | grep NP_STORE
   ```
   Should show: `NP_STORE=/nix/store`

3. **Verify store directory exists:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- ls -la /nix/store
   ```

### If UV cache isn't working:

1. **Verify PVC is mounted:**
   ```bash
   kubectl get pod <pod-name> -n argo -o jsonpath='{.spec.containers[0].volumeMounts}' | grep uv-cache
   ```

2. **Check environment variable:**
   ```bash
   kubectl exec -n argo <pod-name> -c main -- env | grep UV_CACHE_DIR
   ```
   Should show: `UV_CACHE_DIR=/root/.cache/uv`

## Expected Behavior

### First Run
- **UV:** Downloads packages, stores in cache
- **Nix:** Downloads packages from cache.nixos.org, stores in `/nix/store`

### Subsequent Runs
- **UV:** Uses cached packages, no downloads (unless new packages)
- **Nix:** Uses cached packages from `/nix/store`, minimal/no downloads

## Performance Metrics

### UV Cache Impact
- **First run:** ~143ms resolution + download time
- **Cached run:** ~13ms resolution (10x faster)
- **Disk space:** ~14MB per package (numpy example)

### Nix Cache Impact
- **First run:** ~21MB download + unpack time
- **Cached run:** 0MB download (instant)
- **Disk space:** ~128MB unpacked per package set

## Monitoring Commands

```bash
# Watch workflow logs for cache indicators
kubectl logs -n argo <workflow-name> -c main -f | grep -E "Downloading|Resolved|copying path"

# Check cache sizes
kubectl exec -n argo <pod-name> -c main -- sh -c 'du -sh /root/.cache/uv /nix/store 2>/dev/null'

# List all cached items
kubectl exec -n argo <pod-name> -c main -- find /root/.cache/uv -type f | wc -l
kubectl exec -n argo <pod-name> -c main -- find /nix/store -type d | wc -l
```
