import yaml, os, asyncio, json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kubernetes import config
from kubernetes.client import CustomObjectsApi, CoreV1Api
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

class TaskSubmitRequest(BaseModel):
    pythonCode: str = "print('Processing task in Kind...')"

@app.post("/api/v1/tasks/submit")
async def start_task(request: TaskSubmitRequest = TaskSubmitRequest()):
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
        
        # Extract volumes to add back later (WorkflowSpec validation might fail with dict volumes)
        volumes = spec_dict.pop("volumes", [])
        
        if "templates" in spec_dict and spec_dict["templates"]:
            # Convert template dicts to Template objects
            templates = []
            for template_dict in spec_dict["templates"]:
                template_dict_copy = template_dict.copy()
                # Convert container dict to Container object if present
                if "container" in template_dict_copy and template_dict_copy["container"]:
                    container_dict = template_dict_copy["container"].copy()
                    # Replace the Python code with the provided code
                    if "args" in container_dict and container_dict["args"]:
                        container_dict["args"] = [request.pythonCode]
                    else:
                        container_dict["args"] = [request.pythonCode]
                    template_dict_copy["container"] = Container(**container_dict)
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
        
        # Add volumes back to the workflow dict (they were removed to avoid type validation issues)
        if volumes:
            if "spec" not in workflow_dict:
                workflow_dict["spec"] = {}
            workflow_dict["spec"]["volumes"] = volumes
        
        # Create workflow using Kubernetes CustomObjectsApi
        # Use 'argo' namespace where workflow controller is watching (--namespaced mode)
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        result = api_instance.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
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

@app.get("/api/v1/tasks")
async def list_tasks():
    try:
        # Use Kubernetes CustomObjectsApi to list Workflow CRDs
        api_instance = CustomObjectsApi()
        
        # List workflows in argo namespace where workflow controller is watching (--namespaced mode)
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        result = api_instance.list_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows"
        )
        
        # Extract workflow information
        workflows = []
        for item in result.get("items", []):
            metadata = item.get("metadata", {})
            status = item.get("status", {})
            spec = item.get("spec", {})
            
            # Determine phase - check multiple possible locations
            phase = status.get("phase") or "Pending"
            if not status:  # No status means workflow hasn't been processed yet
                phase = "Pending"
            
            # Get timestamps from status
            started_at = status.get("startedAt") or status.get("startTime") or ""
            finished_at = status.get("finishedAt") or status.get("finishTime") or ""
            
            # Extract Python code from workflow spec
            python_code = ""
            templates = spec.get("templates", [])
            if templates:
                # Get the first template (entrypoint)
                template = templates[0]
                container = template.get("container", {})
                args = container.get("args", [])
                if args:
                    # The Python code is typically in the first arg
                    python_code = args[0] if isinstance(args[0], str) else ""
                elif container.get("command"):
                    # If no args, check if command contains the code
                    command = container.get("command", [])
                    if command and len(command) > 1:
                        python_code = " ".join(command)
            
            workflows.append({
                "id": metadata.get("name", "unknown"),
                "generateName": metadata.get("generateName", ""),
                "phase": phase,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "createdAt": metadata.get("creationTimestamp", ""),
                "pythonCode": python_code,
            })
        
        return {"tasks": workflows}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str):
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        core_api = CoreV1Api()
        
        # Get workflow to find pod names
        custom_api = CustomObjectsApi()
        workflow = custom_api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            name=task_id
        )
        
        status = workflow.get("status", {})
        nodes = status.get("nodes", {})
        
        # Collect logs from all nodes (pods) in the workflow
        all_logs = []
        
        for node_id, node_info in nodes.items():
            node_type = node_info.get("type", "")
            phase = node_info.get("phase", "")
            
            # Only get logs from Pod nodes
            if node_type == "Pod":
                # Try different ways to get the pod name
                pod_name = (
                    node_info.get("displayName") or 
                    node_info.get("id") or 
                    node_id
                )
                
                # Argo workflows often prefix pod names with workflow name
                # The actual pod name might be in the node ID or we need to list pods
                try:
                    # First try with the displayName/id directly
                    try:
                        logs = core_api.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=namespace,
                            tail_lines=1000
                        )
                    except:
                        # If that fails, try to find the pod by label selector
                        # Argo workflows label pods with workflow name
                        label_selector = f"workflows.argoproj.io/workflow={task_id}"
                        pods = core_api.list_namespaced_pod(
                            namespace=namespace,
                            label_selector=label_selector
                        )
                        
                        if pods.items:
                            # Get logs from the first matching pod
                            actual_pod_name = pods.items[0].metadata.name
                            logs = core_api.read_namespaced_pod_log(
                                name=actual_pod_name,
                                namespace=namespace,
                                tail_lines=1000
                            )
                            pod_name = actual_pod_name
                        else:
                            raise Exception("No pods found for workflow")
                    
                    all_logs.append({
                        "node": node_id,
                        "pod": pod_name,
                        "phase": phase,
                        "logs": logs
                    })
                except Exception as e:
                    # Pod might not exist yet or logs not available
                    all_logs.append({
                        "node": node_id,
                        "pod": pod_name,
                        "phase": phase,
                        "logs": f"Error fetching logs: {str(e)}\n\nNode info: {node_info}"
                    })
        
        # If no pod logs found, try to get workflow-level messages
        if not all_logs:
            message = status.get("message", "")
            if message:
                all_logs.append({
                    "node": "workflow",
                    "pod": "N/A",
                    "phase": status.get("phase", "Unknown"),
                    "logs": f"Workflow message: {message}"
                })
        
        return {"logs": all_logs}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/tasks/{task_id}/logs")
async def websocket_logs(websocket: WebSocket, task_id: str):
    await websocket.accept()
    namespace = os.getenv("ARGO_NAMESPACE", "argo")
    core_api = CoreV1Api()
    custom_api = CustomObjectsApi()
    
    last_logs_hash = ""
    last_sent_logs = []
    
    try:
        while True:
            try:
                # Get workflow status
                workflow = custom_api.get_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace=namespace,
                    plural="workflows",
                    name=task_id
                )
                
                status = workflow.get("status", {})
                nodes = status.get("nodes", {})
                phase = status.get("phase", "Unknown")
                
                # Collect logs from all nodes
                all_logs = []
                
                for node_id, node_info in nodes.items():
                    node_type = node_info.get("type", "")
                    node_phase = node_info.get("phase", "")
                    
                    if node_type == "Pod":
                        pod_name = (
                            node_info.get("displayName") or 
                            node_info.get("id") or 
                            node_id
                        )
                        
                        try:
                            try:
                                logs = core_api.read_namespaced_pod_log(
                                    name=pod_name,
                                    namespace=namespace,
                                    tail_lines=1000
                                )
                            except:
                                label_selector = f"workflows.argoproj.io/workflow={task_id}"
                                pods = core_api.list_namespaced_pod(
                                    namespace=namespace,
                                    label_selector=label_selector
                                )
                                
                                if pods.items:
                                    actual_pod_name = pods.items[0].metadata.name
                                    logs = core_api.read_namespaced_pod_log(
                                        name=actual_pod_name,
                                        namespace=namespace,
                                        tail_lines=1000
                                    )
                                    pod_name = actual_pod_name
                                else:
                                    raise Exception("No pods found for workflow")
                            
                            all_logs.append({
                                "node": node_id,
                                "pod": pod_name,
                                "phase": node_phase,
                                "logs": logs
                            })
                        except Exception as e:
                            all_logs.append({
                                "node": node_id,
                                "pod": pod_name,
                                "phase": node_phase,
                                "logs": f"Error fetching logs: {str(e)}"
                            })
                
                # Create hash to check if logs changed
                logs_hash = json.dumps(all_logs, sort_keys=True)
                
                # Only send if logs changed
                if logs_hash != last_logs_hash:
                    last_logs_hash = logs_hash
                    last_sent_logs = all_logs
                    
                    await websocket.send_json({
                        "type": "logs",
                        "data": all_logs,
                        "workflow_phase": phase
                    })
                
                # Check if workflow is finished
                if phase in ["Succeeded", "Failed", "Error"]:
                    await websocket.send_json({
                        "type": "complete",
                        "workflow_phase": phase
                    })
                    # Keep connection open for a bit, then close
                    await asyncio.sleep(2)
                    break
                
                # Wait before next check
                await asyncio.sleep(2)
                
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                await asyncio.sleep(2)
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Connection error: {str(e)}"
            })
        except:
            pass

@app.delete("/api/v1/tasks/{task_id}")
async def cancel_task(task_id: str):
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        api_instance = CustomObjectsApi()
        
        # Delete the workflow
        api_instance.delete_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            name=task_id
        )
        
        return {"status": "cancelled", "id": task_id}
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Check if it's a 404 (workflow not found)
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail=f"Workflow {task_id} not found")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/tasks/callback")
async def handle_callback(data: dict):
    print(f"Callback: {data}")
    return {"status": "ok"}
