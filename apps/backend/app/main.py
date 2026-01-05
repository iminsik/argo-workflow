import yaml, os, asyncio, json
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kubernetes import config
from kubernetes.client import CustomObjectsApi, CoreV1Api
from argo_workflows.model.object_meta import ObjectMeta
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow import IoArgoprojWorkflowV1alpha1Workflow
from argo_workflows.model.io_argoproj_workflow_v1alpha1_workflow_spec import IoArgoprojWorkflowV1alpha1WorkflowSpec
from argo_workflows.model.io_argoproj_workflow_v1alpha1_template import IoArgoprojWorkflowV1alpha1Template
from argo_workflows.model.container import Container
try:
    from argo_workflows.model.io_argoproj_workflow_v1alpha1_script_template import IoArgoprojWorkflowV1alpha1ScriptTemplate
except ImportError:
    # Fallback if the import path is different
    try:
        from argo_workflows.model.script_template import ScriptTemplate as IoArgoprojWorkflowV1alpha1ScriptTemplate
    except ImportError:
        IoArgoprojWorkflowV1alpha1ScriptTemplate = None
from sqlalchemy.orm import Session
from app.database import init_db, get_db, TaskLog, SessionLocal
try:
    from argo_workflows.model.volume_mount import VolumeMount
except ImportError:
    VolumeMount = None

app = FastAPI()

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}. Logs will not be persisted.")

# Configure CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
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
    dependencies: str | None = None  # Space or comma-separated package names
    requirementsFile: str | None = None  # requirements.txt content


def fetch_logs_from_kubernetes(task_id: str, namespace: str = None) -> list:
    """
    Fetch logs directly from Kubernetes pods.
    Returns a list of log entries with structure: {node, pod, phase, logs}
    """
    if namespace is None:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
    
    core_api = CoreV1Api()
    custom_api = CustomObjectsApi()
    
    try:
        # Get workflow to find pod names
        workflow = custom_api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            name=task_id
        )
        
        status = workflow.get("status", {})
        nodes = status.get("nodes", {})
        
        # Get the workflow's overall phase to use for log entries
        workflow_phase = determine_workflow_phase(status)
        
        # Collect logs from all nodes (pods) in the workflow
        all_logs = []
        
        for node_id, node_info in nodes.items():
            node_type = node_info.get("type", "")
            node_phase = node_info.get("phase", "")
            
            # Use workflow phase if workflow is completed, otherwise use node phase
            # This ensures log entries show the correct phase when workflow transitions
            if workflow_phase in ["Succeeded", "Failed", "Error"]:
                phase = workflow_phase
            else:
                phase = node_phase or "Pending"
            
            # Only get logs from Pod nodes
            if node_type == "Pod":
                # Try different ways to get the pod name
                pod_name = (
                    node_info.get("displayName") or 
                    node_info.get("id") or 
                    node_id
                )
                
                try:
                    # First, try to get the actual pod to check its status
                    actual_pod = None
                    try:
                        # Try to find the pod by label selector first
                        label_selector = f"workflows.argoproj.io/workflow={task_id}"
                        pods = core_api.list_namespaced_pod(
                            namespace=namespace,
                            label_selector=label_selector
                        )
                        
                        if pods.items:
                            actual_pod = pods.items[0]
                            pod_name = actual_pod.metadata.name
                    except:
                        pass
                    
                    # Check if pod is ready before trying to fetch logs
                    if actual_pod:
                        pod_phase = actual_pod.status.phase if actual_pod.status else None
                        # If pod is still initializing or pending, skip log fetch (not an error)
                        if pod_phase in ["Pending"]:
                            # Pod is still starting - this is normal, don't add error
                            continue
                    
                    # Try to fetch logs
                    try:
                        logs = core_api.read_namespaced_pod_log(
                            name=pod_name,
                            namespace=namespace,
                            container="main",
                            tail_lines=1000
                        )
                    except Exception as log_error:
                        # Check if it's a "PodInitializing" or "waiting to start" error
                        error_str = str(log_error)
                        if "PodInitializing" in error_str or "waiting to start" in error_str:
                            # Pod is still initializing - this is normal, skip silently
                            continue
                        # If that fails and we don't have the pod yet, try to find it
                        if not actual_pod:
                            label_selector = f"workflows.argoproj.io/workflow={task_id}"
                            pods = core_api.list_namespaced_pod(
                                namespace=namespace,
                                label_selector=label_selector
                            )
                            
                            if pods.items:
                                actual_pod = pods.items[0]
                                actual_pod_name = actual_pod.metadata.name
                                # Check pod phase again
                                pod_phase = actual_pod.status.phase if actual_pod.status else None
                                if pod_phase in ["Pending"]:
                                    continue
                                
                                logs = core_api.read_namespaced_pod_log(
                                    name=actual_pod_name,
                                    namespace=namespace,
                                    container="main",
                                    tail_lines=1000
                                )
                                pod_name = actual_pod_name
                            else:
                                raise Exception("No pods found for workflow")
                        else:
                            raise log_error
                    
                    all_logs.append({
                        "node": node_id,
                        "pod": pod_name,
                        "phase": phase,
                        "logs": logs
                    })
                except Exception as e:
                    error_str = str(e)
                    # Only add error message for actual errors, not for pods that are still starting
                    if "PodInitializing" not in error_str and "waiting to start" not in error_str:
                        all_logs.append({
                            "node": node_id,
                            "pod": pod_name,
                            "phase": phase,
                            "logs": f"Error fetching logs: {str(e)}"
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
        
        return all_logs
    except Exception as e:
        raise Exception(f"Error fetching logs from Kubernetes: {str(e)}")


def save_logs_to_database(task_id: str, logs: list, db: Session):
    """
    Save logs to database. Updates existing entries or creates new ones.
    """
    try:
        for log_entry in logs:
            # Check if log entry already exists for this task/node/pod combination
            existing = db.query(TaskLog).filter(
                TaskLog.task_id == task_id,
                TaskLog.node_id == log_entry["node"],
                TaskLog.pod_name == log_entry["pod"]
            ).first()
            
            if existing:
                # Update existing entry
                existing.logs = log_entry["logs"]
                existing.phase = log_entry["phase"]
            else:
                # Create new entry
                db_log = TaskLog(
                    task_id=task_id,
                    node_id=log_entry["node"],
                    pod_name=log_entry["pod"],
                    phase=log_entry["phase"],
                    logs=log_entry["logs"]
                )
                db.add(db_log)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error saving logs to database: {e}")
        raise


def get_logs_from_database(task_id: str, db: Session) -> list:
    """
    Fetch logs from database for a given task.
    Returns a list of log entries with structure: {node, pod, phase, logs}
    """
    try:
        db_logs = db.query(TaskLog).filter(
            TaskLog.task_id == task_id
        ).order_by(TaskLog.created_at).all()
        
        return [
            {
                "node": log.node_id,
                "pod": log.pod_name,
                "phase": log.phase,
                "logs": log.logs
            }
            for log in db_logs
        ]
    except Exception as e:
        print(f"Error fetching logs from database: {e}")
        return []


def determine_workflow_phase(status: dict) -> str:
    """
    Determine the actual workflow phase by checking workflow status and node states.
    This helps distinguish between 'Pending' (workflow created but pods not running) 
    and 'Running' (pods are actually executing).
    """
    if not status:
        return "Pending"
    
    phase = status.get("phase")
    if not phase:
        return "Pending"
    
    # If workflow is finished, return the final phase
    if phase in ["Succeeded", "Failed", "Error"]:
        return phase
    
    nodes = status.get("nodes", {})
    
    # If workflow phase is "Running", check node states to determine actual status
    if phase == "Running":
        if not nodes:
            # No nodes yet means workflow is still pending
            return "Pending"
        
        # Check pod node states
        has_running_pod = False
        has_pending_pod = False
        has_succeeded_pod = False
        has_failed_pod = False
        
        for node_id, node_info in nodes.items():
            node_type = node_info.get("type", "")
            node_phase = node_info.get("phase", "")
            
            # Only check Pod nodes (skip workflow-level nodes)
            if node_type == "Pod":
                if node_phase == "Running":
                    has_running_pod = True
                elif node_phase == "Succeeded":
                    has_succeeded_pod = True
                elif node_phase == "Failed" or node_phase == "Error":
                    has_failed_pod = True
                elif node_phase in ["Pending", ""]:
                    has_pending_pod = True
        
        # If we have running pods, it's actually running
        if has_running_pod:
            return "Running"
        # If pods have succeeded but workflow hasn't updated yet, still show as running
        # (workflow phase will update to Succeeded shortly)
        elif has_succeeded_pod and not has_running_pod and not has_pending_pod:
            # Pods completed but workflow phase hasn't updated yet - show as running
            # This is a transitional state
            return "Running"
        # If we only have pending pods or no pod nodes, it's pending
        elif has_pending_pod or not any(n.get("type") == "Pod" for n in nodes.values()):
            return "Pending"
        # Otherwise, trust the workflow phase
        else:
            return phase
    
    # For other phases (like "Pending"), check if nodes exist and are running
    # This handles cases where workflow phase might lag behind node states
    if nodes:
        has_running_pod = False
        for node_id, node_info in nodes.items():
            node_type = node_info.get("type", "")
            node_phase = node_info.get("phase", "")
            if node_type == "Pod" and node_phase == "Running":
                has_running_pod = True
                break
        
        # If we have running pods but workflow phase says pending, it's actually running
        if has_running_pod and phase == "Pending":
            return "Running"
    
    # Return the workflow phase as-is for other cases
    return phase

@app.post("/api/v1/tasks/submit")
async def start_task(request: TaskSubmitRequest = TaskSubmitRequest()):
    try:
        # Validate dependencies if provided
        if request.dependencies:
            # Basic validation: check for reasonable length and characters
            if len(request.dependencies) > 10000:
                raise HTTPException(
                    status_code=400,
                    detail="Dependencies string is too long (max 10000 characters)"
                )
            # Check for potentially dangerous patterns (basic security check)
            dangerous_patterns = [';', '&&', '||', '`', '$(']
            for pattern in dangerous_patterns:
                if pattern in request.dependencies:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid character in dependencies: {pattern}"
                    )
        
        if request.requirementsFile:
            # Basic validation for requirements file
            if len(request.requirementsFile) > 50000:
                raise HTTPException(
                    status_code=400,
                    detail="Requirements file is too long (max 50000 characters)"
                )
        
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # Check if PVC exists and is bound before creating workflow
        core_api = CoreV1Api()
        try:
            pvc = core_api.read_namespaced_persistent_volume_claim(
                name="task-results-pvc",
                namespace=namespace
            )
            pvc_status = pvc.status.phase if pvc.status else "Unknown"
            if pvc_status != "Bound":
                raise HTTPException(
                    status_code=400, 
                    detail=f"PVC 'task-results-pvc' is not bound. Current status: {pvc_status}. Please ensure the PV is available."
                )
        except Exception as pvc_error:
            # If PVC doesn't exist, that's also a problem
            if "404" in str(pvc_error) or "Not Found" in str(pvc_error):
                raise HTTPException(
                    status_code=400,
                    detail="PVC 'task-results-pvc' not found. Please create it first using: kubectl apply -f infrastructure/k8s/pv.yaml"
                )
            # Re-raise if it's our HTTPException
            if isinstance(pvc_error, HTTPException):
                raise pvc_error
            # Otherwise log and continue (might be a transient issue)
            print(f"Warning: Could not verify PVC status: {pvc_error}")
        
        # Use Kubernetes CustomObjectsApi to create Workflow CRD directly
        api_instance = CustomObjectsApi()
        
        # Choose workflow template based on whether dependencies are provided
        has_dependencies = bool(request.dependencies or request.requirementsFile)
        if has_dependencies:
            deps_template_path = "/infrastructure/argo/python-processor-with-deps.yaml"
            workflow_path = os.getenv("WORKFLOW_MANIFEST_PATH_DEPS", deps_template_path)
            # Fallback to default if deps template doesn't exist
            if not os.path.exists(workflow_path):
                workflow_path = os.getenv("WORKFLOW_MANIFEST_PATH", "/infrastructure/argo/python-processor.yaml")
        else:
            workflow_path = os.getenv("WORKFLOW_MANIFEST_PATH", "/infrastructure/argo/python-processor.yaml")
        
        # Read YAML file
        with open(workflow_path, "r") as f:
            manifest_dict = yaml.safe_load(f)
        
        # Construct workflow object with proper nested objects
        # Convert metadata dict to argo_workflows ObjectMeta
        metadata_dict = manifest_dict.get("metadata", {})
        metadata = ObjectMeta(**metadata_dict) if metadata_dict else None
        
        # Convert spec dict to argo_workflows WorkflowSpec
        # Need to handle nested templates array and container/script objects
        spec_dict = manifest_dict.get("spec", {}).copy() if manifest_dict.get("spec") else {}
        
        # Extract volumes to add back later (WorkflowSpec validation might fail with dict volumes)
        volumes = spec_dict.pop("volumes", [])
        
        # Check if we have dependencies - if so, we'll work with dicts directly to avoid validation issues
        has_dependencies = bool(request.dependencies or request.requirementsFile)
        use_dict_approach = has_dependencies and "script" in str(manifest_dict.get("spec", {}).get("templates", [{}])[0])
        
        if "templates" in spec_dict and spec_dict["templates"]:
            if use_dict_approach:
                # For script templates, work with dicts directly to avoid ScriptTemplate validation issues
                templates = []
                for template_dict in spec_dict["templates"]:
                    template_dict_copy = template_dict.copy()
                    
                    if "script" in template_dict_copy and template_dict_copy["script"]:
                        script_dict = template_dict_copy["script"].copy()
                        env_vars = script_dict.get("env", [])
                        
                        # Update PYTHON_CODE env var
                        for env_var in env_vars:
                            if env_var.get("name") == "PYTHON_CODE":
                                env_var["value"] = request.pythonCode
                                break
                        else:
                            env_vars.append({"name": "PYTHON_CODE", "value": request.pythonCode})
                        
                        # Update DEPENDENCIES env var and handle requirements file
                        dependencies_value = ""
                        if request.requirementsFile:
                            script_source = script_dict.get("source", "")
                            requirements_content = request.requirementsFile
                            requirements_setup = f'''
# Write requirements file
cat > /tmp/requirements.txt << 'REQ_EOF'
{requirements_content}
REQ_EOF
'''
                            if 'source "$VENV_DIR/bin/activate"' in script_source:
                                script_source = script_source.replace(
                                    'source "$VENV_DIR/bin/activate"',
                                    f'source "$VENV_DIR/bin/activate"\n{requirements_setup}'
                                )
                            script_dict["source"] = script_source
                            dependencies_value = "requirements.txt"
                        elif request.dependencies:
                            dependencies_value = request.dependencies
                        
                        # Update DEPENDENCIES env var
                        for env_var in env_vars:
                            if env_var.get("name") == "DEPENDENCIES":
                                env_var["value"] = dependencies_value
                                break
                        else:
                            env_vars.append({"name": "DEPENDENCIES", "value": dependencies_value})
                        
                        script_dict["env"] = env_vars
                        template_dict_copy["script"] = script_dict
                    
                    # Keep as dict for script templates, convert to Template object for container templates
                    if "script" in template_dict_copy:
                        templates.append(template_dict_copy)  # Keep as dict
                    else:
                        # For container templates, use Template object
                        if "container" in template_dict_copy and template_dict_copy["container"]:
                            container_dict = template_dict_copy["container"].copy()
                            volume_mounts = container_dict.get("volumeMounts", [])
                            env_vars = container_dict.pop("env", [])
                            if "args" in container_dict and container_dict["args"]:
                                container_dict["args"] = [request.pythonCode]
                            else:
                                container_dict["args"] = [request.pythonCode]
                            template_dict_copy["container"] = Container(**container_dict)
                            template_dict_copy["_volume_mounts"] = volume_mounts
                            template_dict_copy["_env"] = env_vars
                        templates.append(IoArgoprojWorkflowV1alpha1Template(**template_dict_copy))
            else:
                # Original approach for container templates
                templates = []
                for template_dict in spec_dict["templates"]:
                    template_dict_copy = template_dict.copy()
                    
                    if "container" in template_dict_copy and template_dict_copy["container"]:
                        container_dict = template_dict_copy["container"].copy()
                        volume_mounts = container_dict.get("volumeMounts", [])
                        env_vars = container_dict.pop("env", [])
                        if "args" in container_dict and container_dict["args"]:
                            container_dict["args"] = [request.pythonCode]
                        else:
                            container_dict["args"] = [request.pythonCode]
                        template_dict_copy["container"] = Container(**container_dict)
                        template_dict_copy["_volume_mounts"] = volume_mounts
                        template_dict_copy["_env"] = env_vars
                    
                    templates.append(IoArgoprojWorkflowV1alpha1Template(**template_dict_copy))
            
            spec_dict["templates"] = templates
        
        # If using dict approach for script templates, build workflow dict directly
        if use_dict_approach:
            from argo_workflows.api_client import ApiClient
            api_client = ApiClient()
            workflow_dict = {
                "apiVersion": manifest_dict.get("apiVersion"),
                "kind": manifest_dict.get("kind"),
                "metadata": api_client.sanitize_for_serialization(metadata) if metadata else manifest_dict.get("metadata", {}),
                "spec": spec_dict
            }
            # Add volumes back
            if volumes:
                workflow_dict["spec"]["volumes"] = volumes
        else:
            spec = IoArgoprojWorkflowV1alpha1WorkflowSpec(**spec_dict) if spec_dict else None
            
            # Construct workflow object with proper types
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
            
            # Add volumes back to the workflow dict
            if volumes:
                if "spec" not in workflow_dict:
                    workflow_dict["spec"] = {}
                workflow_dict["spec"]["volumes"] = volumes
        
        # Ensure volumeMounts and env are preserved in the container/script
        # The Container/Script object might not serialize volumeMounts/env, so we add them back
        if "spec" in workflow_dict and "templates" in workflow_dict["spec"]:
            for i, template in enumerate(workflow_dict["spec"]["templates"]):
                original_template = manifest_dict.get("spec", {}).get("templates", [])
                if original_template and i < len(original_template):
                    original_template_item = original_template[i]
                    
                    # Handle container template
                    if "container" in template and "container" in original_template_item:
                        original_container = original_template_item.get("container", {})
                        original_volume_mounts = original_container.get("volumeMounts", [])
                        original_env = original_container.get("env", [])
                        if original_volume_mounts:
                            # Always add volumeMounts back (they might be missing after serialization)
                            template["container"]["volumeMounts"] = original_volume_mounts
                        if original_env:
                            # Always add env back (they might be missing after serialization)
                            template["container"]["env"] = original_env
                    
                    # Handle script template
                    elif "script" in template and "script" in original_template_item:
                        original_script = original_template_item.get("script", {})
                        original_volume_mounts = original_script.get("volumeMounts", [])
                        original_env = original_script.get("env", [])
                        
                        # After serialization, script is already a dict, ensure volumeMounts are present
                        if original_volume_mounts and "volumeMounts" not in template.get("script", {}):
                            template["script"]["volumeMounts"] = original_volume_mounts
                        
                        # For script templates, we've already updated env vars, but ensure they're preserved
                        if original_env:
                            # Convert to dict if needed
                            if not isinstance(template["script"], dict):
                                from argo_workflows.api_client import ApiClient
                                api_client = ApiClient()
                                template["script"] = api_client.sanitize_for_serialization(template["script"])
                            
                            # Merge with our updated env vars
                            existing_env_names = {env.get("name") for env in template.get("script", {}).get("env", [])}
                            for env_var in original_env:
                                if env_var.get("name") not in existing_env_names:
                                    if "env" not in template["script"]:
                                        template["script"]["env"] = []
                                    template["script"]["env"].append(env_var)
        
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
            
            # Determine phase using improved logic that checks node states
            phase = determine_workflow_phase(status)
            
            # Get timestamps from status
            started_at = status.get("startedAt") or status.get("startTime") or ""
            finished_at = status.get("finishedAt") or status.get("finishTime") or ""
            
            # Extract Python code and dependencies from workflow spec
            python_code = ""
            dependencies = ""
            templates = spec.get("templates", [])
            if templates:
                # Get the first template (entrypoint)
                template = templates[0]
                
                # Check for container template (simple tasks without dependencies)
                container = template.get("container", {})
                if container:
                    args = container.get("args", [])
                    if args:
                        # The Python code is typically in the first arg
                        python_code = args[0] if isinstance(args[0], str) else ""
                    elif container.get("command"):
                        # If no args, check if command contains the code
                        command = container.get("command", [])
                        if command and len(command) > 1:
                            python_code = " ".join(command)
                
                # Check for script template (tasks with dependencies)
                script = template.get("script", {})
                if script:
                    env = script.get("env", [])
                    # Extract Python code if not already found
                    if not python_code:
                        for env_var in env:
                            if env_var.get("name") == "PYTHON_CODE":
                                python_code = env_var.get("value", "")
                                break
                    # Extract dependencies
                    for env_var in env:
                        if env_var.get("name") == "DEPENDENCIES":
                            dependencies = env_var.get("value", "")
                            break
            
            # Get workflow message/conditions for debugging
            message = status.get("message", "")
            conditions = status.get("conditions", [])
            
            workflows.append({
                "id": metadata.get("name", "unknown"),
                "generateName": metadata.get("generateName", ""),
                "phase": phase,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "createdAt": metadata.get("creationTimestamp", ""),
                "pythonCode": python_code,
                "dependencies": dependencies,
                "message": message,  # Add message for debugging
            })
        
        return {"tasks": workflows}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, db: Session = Depends(get_db)):
    """
    Get logs for a task. First tries to fetch from database, 
    then falls back to Kubernetes if not found, and saves to database.
    Also updates phase in database if workflow has completed.
    """
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        custom_api = CustomObjectsApi()
        
        # Get current workflow phase to ensure log phases are up-to-date
        try:
            workflow = custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=task_id
            )
            status = workflow.get("status", {})
            current_workflow_phase = determine_workflow_phase(status)
        except Exception as e:
            print(f"Could not fetch workflow status: {e}")
            current_workflow_phase = None
        
        # First, try to get logs from database
        db_logs = get_logs_from_database(task_id, db)
        
        # If we have logs in database, check if phase needs updating
        if db_logs and current_workflow_phase:
            # Update phase if workflow has completed and log phase is stale
            needs_update = False
            for log_entry in db_logs:
                if current_workflow_phase in ["Succeeded", "Failed", "Error"]:
                    if log_entry["phase"] != current_workflow_phase:
                        log_entry["phase"] = current_workflow_phase
                        needs_update = True
            
            # If phase was updated, save back to database
            if needs_update:
                save_logs_to_database(task_id, db_logs, db)
        
        if db_logs:
            # Logs found in database, return them (with updated phase if needed)
            return {"logs": db_logs, "source": "database"}
        
        # If not in database, fetch from Kubernetes and save to database
        try:
            k8s_logs = fetch_logs_from_kubernetes(task_id)
            if k8s_logs:
                # Save to database for future requests
                save_logs_to_database(task_id, k8s_logs, db)
                return {"logs": k8s_logs, "source": "kubernetes"}
            else:
                return {"logs": [], "source": "kubernetes"}
        except Exception as k8s_error:
            # If Kubernetes fetch fails, return empty logs
            print(f"Could not fetch logs from Kubernetes: {k8s_error}")
            return {"logs": [], "source": "error", "error": str(k8s_error)}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/tasks/{task_id}/logs")
async def websocket_logs(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for streaming logs. Fetches from database first,
    then from Kubernetes, and saves new logs to database.
    """
    await websocket.accept()
    namespace = os.getenv("ARGO_NAMESPACE", "argo")
    core_api = CoreV1Api()
    custom_api = CustomObjectsApi()
    
    # Get database session
    db = SessionLocal()
    
    last_logs_hash = ""
    last_sent_logs = []
    last_sent_phase = None
    
    # Helper function to fetch and send logs
    async def fetch_and_send_logs():
        nonlocal last_logs_hash, last_sent_logs, last_sent_phase
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
            phase = determine_workflow_phase(status)
            
            # Try to get logs from database first
            db_logs = get_logs_from_database(task_id, db)
            
            # Also fetch latest from Kubernetes to get any new logs
            try:
                k8s_logs = fetch_logs_from_kubernetes(task_id, namespace)
                
                # Save/update logs in database
                if k8s_logs:
                    save_logs_to_database(task_id, k8s_logs, db)
                    # Use Kubernetes logs (they're more up-to-date)
                    all_logs = k8s_logs
                elif db_logs:
                    # Use database logs if Kubernetes fetch failed
                    all_logs = db_logs
                else:
                    all_logs = []
            except Exception as k8s_error:
                # If Kubernetes fetch fails, use database logs
                if db_logs:
                    all_logs = db_logs
                else:
                    all_logs = []
            
            # Create hash to check if logs changed
            logs_hash = json.dumps(all_logs, sort_keys=True)
            
            # Send updates if logs changed OR phase changed (for immediate phase updates)
            logs_changed = logs_hash != last_logs_hash
            phase_changed = phase != last_sent_phase
            
            if logs_changed or phase_changed:
                if logs_changed:
                    last_logs_hash = logs_hash
                    last_sent_logs = all_logs
                
                if phase_changed:
                    last_sent_phase = phase
                
                try:
                    await websocket.send_json({
                        "type": "logs",
                        "data": all_logs,
                        "workflow_phase": phase
                    })
                except (WebSocketDisconnect, RuntimeError) as ws_error:
                    # Connection closed, stop trying to send
                    raise ws_error
            
            return phase, all_logs
        except (WebSocketDisconnect, RuntimeError) as ws_error:
            # Connection closed, re-raise to break the loop
            raise ws_error
        except Exception as e:
            print(f"Error in fetch_and_send_logs: {e}")
            import traceback
            traceback.print_exc()
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
            except (WebSocketDisconnect, RuntimeError):
                # Connection closed, can't send error message
                raise
            return "Unknown", []
    
    try:
        # Send initial logs immediately upon connection
        phase, _ = await fetch_and_send_logs()
        
        # Then continue polling
        while True:
            phase, all_logs = await fetch_and_send_logs()
            
            # Check if workflow is finished
            if phase in ["Succeeded", "Failed", "Error"]:
                # Final save to ensure all logs are persisted
                try:
                    final_logs = fetch_logs_from_kubernetes(task_id, namespace)
                    if final_logs:
                        save_logs_to_database(task_id, final_logs, db)
                        # Send final logs update
                        try:
                            await websocket.send_json({
                                "type": "logs",
                                "data": final_logs,
                                "workflow_phase": phase
                            })
                        except (WebSocketDisconnect, RuntimeError):
                            # Connection closed, break out
                            break
                except:
                    pass
                
                try:
                    await websocket.send_json({
                        "type": "complete",
                        "workflow_phase": phase
                    })
                    # Keep connection open for a bit, then close
                    await asyncio.sleep(2)
                except (WebSocketDisconnect, RuntimeError):
                    # Connection already closed
                    pass
                break
            
            # Wait before next check - reduced to 1 second for faster phase detection
            await asyncio.sleep(1)
                
    except (WebSocketDisconnect, RuntimeError):
        # Connection closed by client, this is normal
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Connection error: {str(e)}"
            })
        except (WebSocketDisconnect, RuntimeError):
            # Connection already closed, can't send error
            pass
        except:
            pass
    finally:
        db.close()

@app.delete("/api/v1/tasks/{task_id}")
async def cancel_task(task_id: str):
    """
    Cancel a running or pending task by deleting the workflow from Kubernetes.
    Does not delete logs from database.
    """
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


@app.delete("/api/v1/tasks/{task_id}/delete")
async def delete_task(task_id: str, db: Session = Depends(get_db)):
    """
    Permanently delete a task: removes workflow from Kubernetes AND logs from database.
    Works for any task regardless of status.
    """
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        api_instance = CustomObjectsApi()
        
        # Delete logs from database first
        try:
            deleted_logs = db.query(TaskLog).filter(TaskLog.task_id == task_id).delete()
            db.commit()
            print(f"Deleted {deleted_logs} log entries from database for task {task_id}")
        except Exception as db_error:
            db.rollback()
            print(f"Error deleting logs from database: {db_error}")
            # Continue with workflow deletion even if database deletion fails
        
        # Delete the workflow from Kubernetes
        try:
            api_instance.delete_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=task_id
            )
        except Exception as k8s_error:
            # If workflow doesn't exist in Kubernetes, that's okay - we still deleted the logs
            if "404" not in str(k8s_error) and "Not Found" not in str(k8s_error):
                raise k8s_error
        
        return {
            "status": "deleted", 
            "id": task_id,
            "logs_deleted": deleted_logs
        }
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
