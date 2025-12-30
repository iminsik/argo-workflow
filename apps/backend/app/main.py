import yaml, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import config
from kubernetes.client import CustomObjectsApi
from argo_workflows.model.object_meta import ObjectMeta
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow import IoArgoprojWorkflowV1alpha1Workflow
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow_spec import IoArgoprojWorkflowV1alpha1WorkflowSpec
from argo_workflows.model.io_argoproj_workflow_v1alpha1_template import IoArgoprojWorkflowV1alpha1Template
from argo_workflows.model.container import Container

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
    # Patch configuration for Docker: replace 127.0.0.1 with host.docker.internal
    # and disable SSL verification for development (kind uses self-signed certs)
    from kubernetes.client import Configuration
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    configuration = Configuration.get_default_copy()
    if configuration.host and '127.0.0.1' in configuration.host:
        configuration.host = configuration.host.replace('127.0.0.1', 'host.docker.internal')
        # Disable SSL verification for development (kind uses self-signed certs)
        configuration.verify_ssl = False
        Configuration.set_default(configuration)

@app.post("/api/v1/tasks/submit")
async def start_task():
    try:
        # Use Kubernetes CustomObjectsApi to create Workflow CRD directly
        api_instance = CustomObjectsApi()
        workflow_path = os.getenv("WORKFLOW_MANIFEST_PATH", "/infrastructure/argo/python-processor.yaml")
        
        # Read YAML file
        with open(workflow_path, "r") as f:
            manifest_dict = yaml.safe_load(f)
        
        # Construct workflow object with proper nested objects
        # Convert metadata dict to argo_workflows ObjectMeta
        metadata_dict = manifest_dict.get("metadata", {})
        metadata = ObjectMeta(**metadata_dict) if metadata_dict else None
        
        # Convert spec dict to argo_workflows WorkflowSpec
        # Need to handle nested templates array and container objects
        spec_dict = manifest_dict.get("spec", {}).copy() if manifest_dict.get("spec") else {}
        if "templates" in spec_dict and spec_dict["templates"]:
            # Convert template dicts to Template objects
            templates = []
            for template_dict in spec_dict["templates"]:
                template_dict_copy = template_dict.copy()
                # Convert container dict to Container object if present
                if "container" in template_dict_copy and template_dict_copy["container"]:
                    template_dict_copy["container"] = Container(**template_dict_copy["container"])
                templates.append(IoArgoprojWorkflowV1alpha1Template(**template_dict_copy))
            spec_dict["templates"] = templates
        
        spec = IoArgoprojWorkflowV1alpha1WorkflowSpec(**spec_dict) if spec_dict else None
        
        # Construct workflow with proper types
        workflow = IoArgoprojWorkflowV1alpha1Workflow(
            api_version=manifest_dict.get("apiVersion"),
            kind=manifest_dict.get("kind"),
            metadata=metadata,
            spec=spec
        )
        
        # Convert workflow object to dict for Kubernetes API
        # Use the ApiClient to serialize the workflow object
        from argo_workflows.api_client import ApiClient
        api_client = ApiClient()
        workflow_dict = api_client.sanitize_for_serialization(workflow)
        
        # Create workflow using Kubernetes CustomObjectsApi
        result = api_instance.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="default",
            plural="workflows",
            body=workflow_dict
        )
        
        return {"id": result.get("metadata", {}).get("name", "unknown")}
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
