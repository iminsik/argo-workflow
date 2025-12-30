# Argo Workflow Examples

This directory contains Argo Workflow definitions and example Python code.

## Persistent Volume Setup

The workflows are configured to use a PersistentVolume (PV) and PersistentVolumeClaim (PVC) for sharing data between tasks.

### Setup

Apply the PV and PVC:

```bash
kubectl apply -f ../k8s/pv.yaml
```

Or use the Makefile:

```bash
make cluster-up  # This includes PV/PVC setup
```

### Volume Mount

All workflows mount the persistent volume at `/mnt/results`. Tasks can read from and write to this directory.

## Example Tasks

### Write to PV

The `examples/write-to-pv.py` script demonstrates how to:
- Create a results directory
- Generate task data
- Save results to a JSON file in `/mnt/results`

**Usage:**
1. Click "Run Python Task" in the frontend
2. Click "📝 Load: Write to PV" to load the example code
3. Submit the task

The task will save a JSON file with task results to the persistent volume.

### Read from PV

The `examples/read-from-pv.py` script demonstrates how to:
- Read all result files from `/mnt/results`
- Display the contents of each result file

**Usage:**
1. Click "Run Python Task" in the frontend
2. Click "📖 Load: Read from PV" to load the example code
3. Submit the task

The task will read and display all result files from previous tasks.

## Workflow Configuration

The `python-processor.yaml` file defines the base workflow template with:
- Volume mount at `/mnt/results`
- Python 3.11-slim container
- Configurable Python code via API

