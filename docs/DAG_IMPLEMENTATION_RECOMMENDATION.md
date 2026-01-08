# DAG Implementation Recommendation

## Overview

This document provides a comprehensive recommendation for implementing a DAG (Directed Acyclic Graph) flow editor similar to Windmill, allowing users to:
- Define multi-step workflows with dependencies
- Edit Python code for each step with syntax highlighting
- Run entire flows or individual steps
- Share data between steps via PV files or JSON outputs
- Access PV files from any step

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Svelte)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         DAG Flow Editor (React Flow / Cytoscape)      │  │
│  │  • Visual node editor                                │  │
│  │  • Drag & drop connections                            │  │
│  │  • Step properties panel                             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Step Editor (Monaco Editor)                  │  │
│  │  • Python code editor per step                       │  │
│  │  • Dependencies management                           │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Flow Management API                          │  │
│  │  • CRUD operations for flows                         │  │
│  │  • Step management                                   │  │
│  │  • Flow execution                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Workflow Generation (Hera SDK)               │  │
│  │  • Convert DAG to Argo Workflow                      │  │
│  │  • Dependency management                             │  │
│  │  • Data passing between steps                        │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Argo Workflows (Kubernetes)                     │
│  • DAG execution                                             │
│  • Step orchestration                                        │
│  • PV file access                                            │
└──────────────────────────────────────────────────────────────┘
```

## Frontend Implementation

### 1. DAG Editor Library Selection

**Recommendation: Use `@xyflow/svelte` (formerly React Flow for Svelte)**

**Why:**
- Native Svelte support (matches your stack)
- Excellent performance for large graphs
- Built-in node/edge editing
- Customizable node types
- Good documentation

**Alternative: Cytoscape.js**
- More feature-rich but heavier
- Better for complex graph analysis
- More complex API

**Installation:**
```bash
npm install @xyflow/svelte
```

### 2. Component Structure

```
src/
├── FlowEditor.svelte          # Main DAG editor component
├── FlowNode.svelte            # Custom node component (with Python editor)
├── FlowStepEditor.svelte      # Step properties panel
├── FlowList.svelte            # List of saved flows
└── lib/
    └── flow/
        ├── types.ts           # TypeScript types for flows
        ├── utils.ts           # DAG utilities (validation, etc.)
        └── store.ts           # Flow state management
```

### 3. Data Model

```typescript
// types.ts
interface FlowStep {
  id: string;                    // Unique step ID (e.g., "step-1")
  name: string;                  // Human-readable name
  pythonCode: string;            // Python code to execute
  dependencies?: string;         // Optional dependencies
  requirementsFile?: string;     // Optional requirements.txt
  position: { x: number; y: number }; // Node position in graph
  inputs?: StepInput[];          // Input parameters
  outputs?: StepOutput[];        // Output definitions
}

interface StepInput {
  name: string;
  source: 'flow_input' | 'step_output' | 'static';
  sourceStepId?: string;         // If from step_output
  sourceOutputName?: string;      // Output name from source step
  defaultValue?: any;            // If static
}

interface StepOutput {
  name: string;
  type: 'json' | 'file' | 'pv_file';
  path?: string;                  // For file outputs
}

interface Flow {
  id: string;
  name: string;
  description?: string;
  steps: FlowStep[];
  edges: FlowEdge[];             // Dependencies between steps
  createdAt: string;
  updatedAt: string;
  status: 'draft' | 'saved' | 'running' | 'completed' | 'failed';
}

interface FlowEdge {
  id: string;
  source: string;                // Source step ID
  target: string;                // Target step ID
  sourceHandle?: string;         // Output handle name
  targetHandle?: string;         // Input handle name
}
```

### 4. Flow Editor Features

**Core Features:**
1. **Node Creation**: Click to add new step nodes
2. **Node Editing**: Double-click or panel to edit Python code
3. **Connection**: Drag from output to input to create dependencies
4. **Validation**: Check for cycles, validate DAG structure
5. **Step Execution**: Right-click node to "Run this step only"
6. **Flow Execution**: Run entire flow from start

**UI Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  [Flow Name] [Save] [Run Flow] [Run Selected Step]     │
├──────────────┬──────────────────────────────────────────┤
│              │                                          │
│  Step List   │         DAG Canvas                      │
│  (Sidebar)   │         (Main Area)                     │
│              │                                          │
│  - Step 1    │         [Step 1] ──→ [Step 2]            │
│  - Step 2    │              │                          │
│  - Step 3    │              └──→ [Step 3]              │
│              │                                          │
├──────────────┴──────────────────────────────────────────┤
│  Step Properties Panel (Bottom/Collapsible)              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Step: Step 1                                     │  │
│  │  Python Code: [Monaco Editor]                   │  │
│  │  Dependencies: [Input field]                    │  │
│  │  Inputs: [List of inputs]                      │  │
│  │  Outputs: [List of outputs]                    │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Backend Implementation

### 1. Database Schema Extensions

```python
# database.py additions

class Flow(Base):
    """Model for storing flow definitions (DAGs)."""
    __tablename__ = "flows"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    definition: Mapped[str] = mapped_column(JSON, nullable=False)  # FlowStep[] + edges
    status: Mapped[str] = mapped_column(String, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    runs: Mapped[list["FlowRun"]] = relationship("FlowRun", back_populates="flow", cascade="all, delete-orphan")

class FlowRun(Base):
    """Model for storing flow execution runs."""
    __tablename__ = "flow_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_id: Mapped[str] = mapped_column(String, ForeignKey("flows.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[str] = mapped_column(String, index=True)  # Argo workflow name
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String, default="Pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    flow: Mapped["Flow"] = relationship("Flow", back_populates="runs")
    step_runs: Mapped[list["FlowStepRun"]] = relationship("FlowStepRun", back_populates="flow_run", cascade="all, delete-orphan")

class FlowStepRun(Base):
    """Model for storing individual step execution within a flow run."""
    __tablename__ = "flow_step_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("flow_runs.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(String, nullable=False)  # Step ID from flow definition
    workflow_node_id: Mapped[str] = mapped_column(String, nullable=False)  # Argo workflow node name
    phase: Mapped[str] = mapped_column(String, default="Pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    flow_run: Mapped["FlowRun"] = relationship("FlowRun", back_populates="step_runs")
    logs: Mapped[list["FlowStepLog"]] = relationship("FlowStepLog", back_populates="step_run", cascade="all, delete-orphan")
```

### 2. API Endpoints

```python
# main.py additions

# Flow Management
@app.post("/api/v1/flows")
async def create_flow(flow: FlowCreateRequest):
    """Create a new flow definition."""
    pass

@app.get("/api/v1/flows")
async def list_flows():
    """List all flows."""
    pass

@app.get("/api/v1/flows/{flow_id}")
async def get_flow(flow_id: str):
    """Get flow definition."""
    pass

@app.put("/api/v1/flows/{flow_id}")
async def update_flow(flow_id: str, flow: FlowUpdateRequest):
    """Update flow definition."""
    pass

@app.delete("/api/v1/flows/{flow_id}")
async def delete_flow(flow_id: str):
    """Delete flow."""
    pass

# Flow Execution
@app.post("/api/v1/flows/{flow_id}/run")
async def run_flow(flow_id: str, options: FlowRunOptions):
    """Run entire flow."""
    pass

@app.post("/api/v1/flows/{flow_id}/steps/{step_id}/run")
async def run_flow_step(flow_id: str, step_id: str, options: StepRunOptions):
    """Run a single step from a flow (for testing)."""
    pass

# Flow Status
@app.get("/api/v1/flows/{flow_id}/runs")
async def list_flow_runs(flow_id: str):
    """List all runs for a flow."""
    pass

@app.get("/api/v1/flows/{flow_id}/runs/{run_number}")
async def get_flow_run(flow_id: str, run_number: int):
    """Get flow run details."""
    pass

@app.get("/api/v1/flows/{flow_id}/runs/{run_number}/logs")
async def get_flow_run_logs(flow_id: str, run_number: int):
    """Get logs for a flow run."""
    pass
```

### 3. Workflow Generation with Hera SDK

```python
# workflow_hera_flow.py

from hera.workflows import Workflow, DAG, Task, Parameter
from typing import List, Dict

def create_flow_workflow_with_hera(
    flow_definition: Dict,  # Contains steps and edges
    namespace: str = "argo"
) -> str:
    """
    Create an Argo Workflow from a flow definition (DAG).
    
    Args:
        flow_definition: Flow definition with steps and edges
        namespace: Kubernetes namespace
        
    Returns:
        workflow_id: The generated workflow name/ID
    """
    workflow = Workflow(
        generate_name="flow-",
        entrypoint="dag",
        namespace=namespace,
        volumes=[
            Volume(
                name="task-results",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="task-results-pvc")
            )
        ]
    )
    
    # Create DAG template
    dag_template = DAG(name="dag")
    
    # Create task templates for each step
    step_templates = {}
    for step in flow_definition["steps"]:
        # Build task template for this step
        task_template = create_step_task_template(step, flow_definition)
        step_templates[step["id"]] = task_template
        workflow.templates.append(task_template)
    
    # Add tasks to DAG with dependencies
    for step in flow_definition["steps"]:
        step_id = step["id"]
        task = Task(
            name=step_id,
            template=step_id,
            dependencies=[edge["source"] for edge in flow_definition["edges"] if edge["target"] == step_id]
        )
        dag_template.tasks.append(task)
    
    workflow.templates.append(dag_template)
    
    # Submit workflow
    workflow_obj = workflow.build()
    # ... (same submission logic as single-task workflow)
    
    return workflow_id

def create_step_task_template(step: Dict, flow_definition: Dict):
    """Create a task template for a single step."""
    # Similar to create_workflow_with_hera but for individual steps
    # Handle inputs from previous steps
    # Handle outputs to next steps
    pass
```

### 4. Data Exchange Between Steps

**Option 1: JSON via Argo Parameters (Recommended for small data)**
- Use Argo's parameter passing mechanism
- Steps output JSON, passed as parameters to dependent steps
- Limited by Kubernetes resource limits (~1MB)

**Option 2: PV Files (Recommended for large data)**
- Steps write outputs to `/mnt/results/{step_id}/output.json`
- Dependent steps read from `/mnt/results/{source_step_id}/output.json`
- No size limits, supports binary data

**Option 3: Hybrid Approach**
- Small outputs (<100KB): Use Argo parameters
- Large outputs: Use PV files
- Automatic selection based on output size

**Implementation:**
```python
# In step execution code, inject helper functions:
python_code_with_helpers = f"""
import json
import os
from pathlib import Path

# Helper function to read previous step output
def read_step_output(step_id: str, output_name: str = "output"):
    \"\"\"Read output from a previous step.\"\"\"
    output_path = Path(f"/mnt/results/{{step_id}}/{{output_name}}.json")
    if output_path.exists():
        with open(output_path, 'r') as f:
            return json.load(f)
    return None

# Helper function to write step output
def write_step_output(data: dict, output_name: str = "output"):
    \"\"\"Write output for this step.\"\"\"
    step_id = os.getenv("ARGO_WORKFLOW_NAME", "unknown")
    output_dir = Path(f"/mnt/results/{{step_id}}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{{output_name}}.json"
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    return str(output_path)

# User's Python code
{step["pythonCode"]}
"""
```

## Implementation Plan

### Phase 1: Foundation (Week 1)
1. ✅ Install `@xyflow/svelte`
2. ✅ Create basic FlowEditor component
3. ✅ Add Flow model to database
4. ✅ Create flow CRUD API endpoints
5. ✅ Test basic flow save/load

### Phase 2: DAG Editor (Week 2)
1. ✅ Implement node creation/editing
2. ✅ Implement edge creation (dependencies)
3. ✅ Add step properties panel with Monaco editor
4. ✅ Implement DAG validation (cycle detection)
5. ✅ Add flow list view

### Phase 3: Workflow Generation (Week 3)
1. ✅ Extend Hera SDK to support multi-step workflows
2. ✅ Implement dependency resolution
3. ✅ Add data passing between steps (PV files)
4. ✅ Test simple 2-step flow execution

### Phase 4: Step Execution (Week 4)
1. ✅ Implement individual step execution
2. ✅ Add step run history
3. ✅ Implement step logs viewing
4. ✅ Add step status indicators in DAG

### Phase 5: Polish & Testing (Week 5)
1. ✅ Add flow run history
2. ✅ Improve error handling
3. ✅ Add flow templates/examples
4. ✅ Documentation
5. ✅ End-to-end testing

## Key Design Decisions

### 1. Data Exchange Strategy
**Decision: Use PV files for all step outputs**
- **Rationale**: 
  - No size limits
  - Supports binary data
  - Consistent with existing PV file manager
  - Simple to implement
  - Easy to debug (files visible in PV File Manager)

### 2. Step Isolation
**Decision: Each step runs in its own pod**
- **Rationale**:
  - Matches Argo Workflows architecture
  - Better resource isolation
  - Easier to scale
  - Independent dependency management per step

### 3. Flow vs Task
**Decision: Keep separate Flow and Task models**
- **Rationale**:
  - Tasks remain for single-step execution
  - Flows are multi-step workflows
  - Backward compatibility
  - Clear separation of concerns

### 4. Step Execution Mode
**Decision: Support both full flow and individual step execution**
- **Rationale**:
  - Full flow: Production use
  - Individual step: Development/testing
  - Matches Windmill's approach

## Example Flow Definition

```json
{
  "id": "flow-123",
  "name": "Data Processing Pipeline",
  "steps": [
    {
      "id": "step-1",
      "name": "Load Data",
      "pythonCode": "import json\nimport os\n\n# Load data from PV\nwith open('/mnt/results/input/data.json', 'r') as f:\n    data = json.load(f)\n\n# Process and save\noutput = {'processed': len(data)}\nwrite_step_output(output)",
      "dependencies": null,
      "position": { "x": 100, "y": 100 }
    },
    {
      "id": "step-2",
      "name": "Transform Data",
      "pythonCode": "import json\n\n# Read from step-1\nprev_output = read_step_output('step-1')\n\n# Transform\nresult = {'transformed': prev_output['processed'] * 2}\nwrite_step_output(result)",
      "dependencies": ["step-1"],
      "position": { "x": 300, "y": 100 }
    },
    {
      "id": "step-3",
      "name": "Save Results",
      "pythonCode": "import json\n\n# Read from step-2\nprev_output = read_step_output('step-2')\n\n# Save final results\nwith open('/mnt/results/final_output.json', 'w') as f:\n    json.dump(prev_output, f)\nprint('Results saved!')",
      "dependencies": ["step-2"],
      "position": { "x": 500, "y": 100 }
    }
  ],
  "edges": [
    { "id": "e1", "source": "step-1", "target": "step-2" },
    { "id": "e2", "source": "step-2", "target": "step-3" }
  ]
}
```

## Testing Strategy

1. **Unit Tests**:
   - DAG validation (cycle detection)
   - Step code generation
   - Data passing logic

2. **Integration Tests**:
   - Flow save/load
   - Flow execution
   - Step execution
   - Log retrieval

3. **E2E Tests**:
   - Create flow in UI
   - Run flow
   - Verify step execution order
   - Verify data passing

## Future Enhancements

1. **Conditional Execution**: Branch steps based on conditions
2. **Parallel Execution**: Run independent steps in parallel
3. **Retry Logic**: Per-step retry configuration
4. **Timeouts**: Per-step timeout configuration
5. **Flow Templates**: Pre-built flow templates
6. **Flow Versioning**: Version control for flows
7. **Flow Scheduling**: Schedule flows to run automatically
8. **Flow Monitoring**: Real-time flow execution dashboard

## References

- [Windmill Flows Documentation](https://www.windmill.dev/docs/getting_started/flows_quickstart)
- [@xyflow/svelte Documentation](https://svelteflow.dev/)
- [Hera SDK Documentation](https://hera-workflows.readthedocs.io/)
- [Argo Workflows DAG Documentation](https://argoproj.github.io/argo-workflows/walk-through/dag/)

