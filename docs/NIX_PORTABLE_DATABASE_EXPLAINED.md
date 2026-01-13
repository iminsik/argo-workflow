# Nix-Portable Database Explained

## Answer to Your Question

**Yes, nix-portable does maintain and manage a downloaded database catalog**, and it uses this database to determine whether packages should be downloaded from the internet or used from the cache store.

## How Nix-Store Database Works

### Database Location

nix-portable maintains a SQLite database at:
```
~/.nix-portable/nix/var/nix/db/db.sqlite
```

This database tracks:
- Which packages exist in the store
- Package metadata (hashes, dependencies, etc.)
- Package validity and integrity

### How Nix Uses the Database

When you run `nix-shell -p gcc`, Nix:

1. **Evaluates dependencies**: Determines what packages are needed
2. **Checks the database**: Queries `db.sqlite` to see if packages exist locally
3. **If found in database**: Uses packages from local store (no download)
4. **If not found**: Downloads from internet and updates the database

### The Problem We Had

**Before the fix:**
- We synced packages from `/nix/store` (shared PVC) to `~/.nix-portable/nix/store`
- But we **didn't sync the database**
- Result: Packages existed on disk, but nix-portable didn't know about them
- So nix-portable downloaded them again

**After the fix:**
- We sync packages AND the database
- The database tells nix-portable which packages exist
- Result: nix-portable recognizes synced packages and uses them

## Current Implementation

### Step 1: Sync Packages and Database (At Startup)

```bash
# Sync packages from shared PVC to nix-portable location
rsync -a "$NP_STORE/" ~/.nix-portable/nix/store/

# Sync database from shared PVC
cp "$NP_STORE/.nix-db/db.sqlite" ~/.nix-portable/nix/var/nix/db/db.sqlite
```

### Step 2: Use Packages (During Execution)

```bash
# nix-shell checks the database first
# If packages are in database → uses local cache
# If packages are missing → downloads from internet
nix-portable nix-shell -p gcc --run 'python code'
```

### Step 3: Sync Back (After Execution)

```bash
# Sync new packages to shared PVC
rsync -a ~/.nix-portable/nix/store/ "$NP_STORE/"

# Sync updated database to shared PVC
cp ~/.nix-portable/nix/var/nix/db/db.sqlite "$NP_STORE/.nix-db/db.sqlite"
```

## Database Structure

The SQLite database contains tables like:
- `ValidPaths`: Tracks which package paths are valid
- `References`: Tracks package dependencies
- `Derivations`: Tracks package metadata

## Why This Matters

**Without database sync:**
- Packages exist on disk but nix-portable doesn't know about them
- nix-portable downloads packages even though they're cached
- Wastes time and bandwidth

**With database sync:**
- nix-portable knows which packages exist
- Uses cached packages immediately
- Only downloads missing packages

## Storage Location

We store the database in the PVC at:
```
/nix/store/.nix-db/db.sqlite
```

This keeps it within the PVC mount point and accessible to all containers.

## Summary

**Who manages the database?**
- nix-portable creates and maintains it automatically
- We sync it to/from the shared PVC

**How does it know what to download?**
- Checks the database first
- If package is in database → uses cache
- If package is missing → downloads

**How do we know what packages are needed?**
- User specifies in task definition: `systemDependencies: "gcc ffmpeg"`
- Nix automatically resolves all dependencies
- Database tracks everything

This is why syncing the database is critical for cache efficiency!
