import yaml, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import config
from argo_workflows.api import workflow_service_api
from argo_workflows.model.object_meta import ObjectMeta
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow_create_request import IoArgoprojWorkflowV1alpha1WorkflowCreateRequest
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow import IoArgoprojWorkflowV1alpha1Workflow
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow_spec import IoArgoprojWorkflowV1alpha1WorkflowSpec

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Frontend origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    config.load_incluster_config()
except:
    config.load_kube_config()

@app.post("/api/v1/tasks/submit")
async def start_task():
    try:
        api_instance = workflow_service_api.WorkflowServiceApi()
        workflow_path = os.getenv("WORKFLOW_MANIFEST_PATH", "/infrastructure/argo/python-processor.yaml")
        
        # Read YAML file
        with open(workflow_path, "r") as f:
            manifest_dict = yaml.safe_load(f)
        
        # Construct workflow object with proper nested objects
        # Convert metadata dict to argo_workflows ObjectMeta
        metadata_dict = manifest_dict.get("metadata", {})
        metadata = ObjectMeta(**metadata_dict) if metadata_dict else None
        
        # Convert spec dict to argo_workflows WorkflowSpec
        spec_dict = manifest_dict.get("spec", {})
        spec = IoArgoprojWorkflowV1alpha1WorkflowSpec(**spec_dict) if spec_dict else None
        
        # Construct workflow with proper types
        workflow = IoArgoprojWorkflowV1alpha1Workflow(
            api_version=manifest_dict.get("apiVersion"),
            kind=manifest_dict.get("kind"),
            metadata=metadata,
            spec=spec
        )
        
        result = api_instance.create_workflow(
            namespace="default", 
            body=IoArgoprojWorkflowV1alpha1WorkflowCreateRequest(workflow=workflow)
        )
        return {"id": result.metadata.name}
    except Exception as e:
        # Print full error for debugging
        import traceback
        traceback.print_exc()
        # Ensure CORS headers are sent even on error
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/tasks/callback")
async def handle_callback(data: dict):
    print(f"Callback: {data}")
    return {"status": "ok"}
