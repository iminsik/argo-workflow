import yaml, os, asyncio, json, uuid
from datetime import datetime
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
from app.database import init_db, get_db, TaskLog, Task, TaskRun, SessionLocal
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
    taskId: str | None = None  # Optional: task ID for rerun (creates new run of existing task)


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


def save_logs_to_database(run_id: int, logs: list, db: Session, task_id: str = None, workflow_id: str = None):
    """
    Save logs to database for a specific run. Updates existing entries or creates new ones.
    Handles both old schema (task_id) and new schema (run_id).
    """
    try:
        from sqlalchemy import text, inspect
        from app.database import engine
        
        # Check which schema we're using
        inspector = inspect(engine)
        task_logs_columns = [col['name'] for col in inspector.get_columns('task_logs')]
        has_run_id = 'run_id' in task_logs_columns
        has_task_id = 'task_id' in task_logs_columns
        
        for log_entry in logs:
            if has_run_id:
                # New schema: use run_id
                existing = db.query(TaskLog).filter(
                    TaskLog.run_id == run_id,
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
                        run_id=run_id,
                        node_id=log_entry["node"],
                        pod_name=log_entry["pod"],
                        phase=log_entry["phase"],
                        logs=log_entry["logs"]
                    )
                    db.add(db_log)
            elif has_task_id and task_id:
                # Old schema: use task_id (fallback)
                # Use raw SQL to avoid ORM issues with missing run_id column
                existing = db.execute(
                    text("SELECT id FROM task_logs WHERE task_id = :task_id AND node_id = :node_id AND pod_name = :pod_name"),
                    {"task_id": task_id, "node_id": log_entry["node"], "pod_name": log_entry["pod"]}
                ).fetchone()
                
                if existing:
                    # Update existing entry
                    db.execute(
                        text("UPDATE task_logs SET logs = :logs, phase = :phase WHERE id = :id"),
                        {"logs": log_entry["logs"], "phase": log_entry["phase"], "id": existing[0]}
                    )
                else:
                    # Create new entry
                    now = datetime.utcnow()
                    db.execute(
                        text("INSERT INTO task_logs (task_id, node_id, pod_name, phase, logs, created_at, updated_at) VALUES (:task_id, :node_id, :pod_name, :phase, :logs, :created_at, :updated_at)"),
                        {
                            "task_id": task_id,
                            "node_id": log_entry["node"],
                            "pod_name": log_entry["pod"],
                            "phase": log_entry["phase"],
                            "logs": log_entry["logs"],
                            "created_at": now,
                            "updated_at": now
                        }
                    )
            else:
                # Schema not migrated and no task_id provided - skip saving
                print(f"Warning: Cannot save logs - schema not migrated and task_id not provided")
                continue
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error saving logs to database: {e}")
        # Don't raise - allow logs to still be returned from Kubernetes


def get_logs_from_database(run_id: int, db: Session, task_id: str = None, workflow_id: str = None) -> list:
    """
    Fetch logs from database for a given run.
    Handles both old schema (task_id) and new schema (run_id).
    Returns a list of log entries with structure: {node, pod, phase, logs}
    """
    try:
        from sqlalchemy import text, inspect
        from app.database import engine
        
        # Check which schema we're using
        inspector = inspect(engine)
        task_logs_columns = [col['name'] for col in inspector.get_columns('task_logs')]
        has_run_id = 'run_id' in task_logs_columns
        has_task_id = 'task_id' in task_logs_columns
        
        if has_run_id:
            # New schema: use run_id
            db_logs = db.query(TaskLog).filter(
                TaskLog.run_id == run_id
            ).order_by(TaskLog.created_at).all()
        elif has_task_id and task_id:
            # Old schema: use task_id (fallback)
            db_logs = db.query(TaskLog).filter(
                TaskLog.task_id == task_id
            ).order_by(TaskLog.created_at).all()
        else:
            # No matching schema or missing task_id
            return []
        
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


def extract_task_details(workflow_item: dict) -> dict:
    """
    Extract task details (code, dependencies, phase, etc.) from a workflow item.
    Returns a dict with task information.
    """
    metadata = workflow_item.get("metadata", {})
    status = workflow_item.get("status", {})
    spec = workflow_item.get("spec", {})
    
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
    
    return {
        "id": metadata.get("name", "unknown"),
        "generateName": metadata.get("generateName", ""),
        "phase": phase,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "createdAt": metadata.get("creationTimestamp", ""),
        "pythonCode": python_code,
        "dependencies": dependencies,
        "message": message,
    }


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
        
        workflow_id = result.get("metadata", {}).get("name", "unknown")
        
        # Create/update Task and TaskRun in database
        db = next(get_db())
        try:
            # Determine task_id: use provided taskId for rerun, or generate new one
            if request.taskId:
                # Rerun: update existing task and create new run
                task = db.query(Task).filter(Task.id == request.taskId).first()
                if not task:
                    raise HTTPException(status_code=404, detail=f"Task {request.taskId} not found")
                
                # Update task code and dependencies
                task.python_code = request.pythonCode
                task.dependencies = request.dependencies if request.dependencies else None
                task.requirements_file = request.requirementsFile if request.requirementsFile else None
                task.updated_at = datetime.utcnow()
                
                # Get next run number (check schema first to avoid querying non-existent columns)
                from sqlalchemy import inspect as sql_inspect, text
                from app.database import engine
                inspector = sql_inspect(engine)
                task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                has_python_code = 'python_code' in task_runs_columns
                
                if has_python_code:
                    max_run = db.query(TaskRun).filter(TaskRun.task_id == request.taskId).order_by(TaskRun.run_number.desc()).first()
                    next_run_number = (max_run.run_number + 1) if max_run else 1
                else:
                    result = db.execute(
                        text("SELECT run_number FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                        {"task_id": request.taskId}
                    ).fetchone()
                    if result:
                        next_run_number = (getattr(result, 'run_number', result[0]) + 1) if result else 1
                    else:
                        next_run_number = 1
                
                task_id = request.taskId
                # Commit task update before creating TaskRun
                db.commit()
            else:
                # New task: create Task record
                task_id = f"task-{uuid.uuid4().hex[:12]}"
                task = Task(
                    id=task_id,
                    python_code=request.pythonCode,
                    dependencies=request.dependencies if request.dependencies else None,
                    requirements_file=request.requirementsFile if request.requirementsFile else None
                )
                db.add(task)
                next_run_number = 1
                # Commit Task first to ensure foreign key constraint is satisfied
                db.commit()
            
            # Create TaskRun record with code snapshot (if schema supports it)
            # Note: has_python_code is already set for reruns, need to check again for new tasks
            if not request.taskId:
                from sqlalchemy import inspect as sql_inspect, text
                from app.database import engine
                inspector = sql_inspect(engine)
                task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                has_python_code = 'python_code' in task_runs_columns
            
            if has_python_code:
                # New schema: store code in TaskRun using ORM
                task_run = TaskRun(
                    task_id=task_id,
                    workflow_id=workflow_id,
                    run_number=next_run_number,
                    phase="Pending",
                    python_code=request.pythonCode,
                    dependencies=request.dependencies if request.dependencies else None,
                    requirements_file=request.requirementsFile if request.requirementsFile else None
                )
                db.add(task_run)
                db.commit()
            else:
                # Old schema: use raw SQL to avoid ORM trying to insert non-existent columns
                # Task must already be committed for foreign key constraint
                result = db.execute(
                    text("""
                        INSERT INTO task_runs (task_id, workflow_id, run_number, phase, created_at)
                        VALUES (:task_id, :workflow_id, :run_number, :phase, :created_at)
                        RETURNING id
                    """),
                    {
                        "task_id": task_id,
                        "workflow_id": workflow_id,
                        "run_number": next_run_number,
                        "phase": "Pending",
                        "created_at": datetime.utcnow()
                    }
                )
                db.commit()
                # Note: In old schema, code is stored in Task, not TaskRun
            
            return {
                "id": task_id,
                "workflowId": workflow_id,
                "runNumber": next_run_number
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as db_error:
            db.rollback()
            print(f"Error saving task to database: {db_error}")
            # Still return workflow_id even if DB save fails
            return {"id": workflow_id, "workflowId": workflow_id}
        finally:
            db.close()
    except Exception as e:
        # Print full error for debugging
        import traceback
        traceback.print_exc()
        # Ensure CORS headers are sent even on error
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks")
async def list_tasks():
    """
    List all tasks from database with their latest run information.
    Syncs phase from Kubernetes for the latest run.
    """
    try:
        db = next(get_db())
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        custom_api = CustomObjectsApi()
        
        # Get all tasks from database
        tasks = db.query(Task).order_by(Task.created_at.desc()).all()
        
        task_list = []
        for task in tasks:
            # Get latest run (handle schema migration)
            from sqlalchemy import inspect as sql_inspect
            from app.database import engine
            inspector = sql_inspect(engine)
            task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
            has_python_code = 'python_code' in task_runs_columns
            
            # Query only columns that exist
            if has_python_code:
                latest_run = db.query(TaskRun).filter(
                    TaskRun.task_id == task.id
                ).order_by(TaskRun.run_number.desc()).first()
            else:
                # Old schema: query without code columns
                from sqlalchemy import text
                result = db.execute(
                    text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                    {"task_id": task.id}
                ).fetchone()
                latest_run = result  # Will be a Row object, not TaskRun
            
            if latest_run:
                # Handle both TaskRun object and Row object from raw SQL
                if has_python_code:
                    # New schema: latest_run is a TaskRun object
                    workflow_id = latest_run.workflow_id
                    run_phase = latest_run.phase
                    run_started_at = latest_run.started_at
                    run_finished_at = latest_run.finished_at
                else:
                    # Old schema: latest_run is a Row object - SQLAlchemy Row supports column name access
                    workflow_id = getattr(latest_run, 'workflow_id', latest_run[2])
                    run_phase = getattr(latest_run, 'phase', latest_run[4] if len(latest_run) > 4 else "Pending")
                    run_started_at = getattr(latest_run, 'started_at', latest_run[5] if len(latest_run) > 5 else None)
                    run_finished_at = getattr(latest_run, 'finished_at', latest_run[6] if len(latest_run) > 6 else None)
                
                # Sync phase from Kubernetes
                try:
                    workflow = custom_api.get_namespaced_custom_object(
                        group="argoproj.io",
                        version="v1alpha1",
                        namespace=namespace,
                        plural="workflows",
                        name=workflow_id
                    )
                    status = workflow.get("status", {})
                    phase = determine_workflow_phase(status)
                    
                    # Update run phase if changed (only if we have a TaskRun object)
                    if has_python_code and latest_run.phase != phase:
                        latest_run.phase = phase
                        try:
                            if status.get("startedAt"):
                                started_str = status.get("startedAt")
                                if started_str.endswith("Z"):
                                    started_str = started_str.replace("Z", "+00:00")
                                latest_run.started_at = datetime.fromisoformat(started_str)
                            if status.get("finishedAt"):
                                finished_str = status.get("finishedAt")
                                if finished_str.endswith("Z"):
                                    finished_str = finished_str.replace("Z", "+00:00")
                                latest_run.finished_at = datetime.fromisoformat(finished_str)
                        except Exception as dt_error:
                            print(f"Error parsing datetime: {dt_error}")
                        db.commit()
                        run_phase = phase
                        run_started_at = latest_run.started_at
                        run_finished_at = latest_run.finished_at
                    else:
                        phase = run_phase
                    
                    started_at = run_started_at.isoformat() if run_started_at else ""
                    finished_at = run_finished_at.isoformat() if run_finished_at else ""
                except Exception as e:
                    # Workflow might not exist in Kubernetes anymore
                    phase = run_phase
                    started_at = run_started_at.isoformat() if run_started_at else ""
                    finished_at = run_finished_at.isoformat() if run_finished_at else ""
            else:
                phase = "Pending"
                started_at = ""
                finished_at = ""
            
            task_list.append({
                "id": task.id,
                "phase": phase,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "createdAt": task.created_at.isoformat(),
                "pythonCode": task.python_code,
                "dependencies": task.dependencies or "",
                "runCount": db.query(TaskRun).filter(TaskRun.task_id == task.id).count() if has_python_code else len([r for r in db.execute(text("SELECT id FROM task_runs WHERE task_id = :task_id"), {"task_id": task.id}).fetchall()]),
                "latestRunNumber": (latest_run.run_number if has_python_code else getattr(latest_run, 'run_number', latest_run[3] if len(latest_run) > 3 else 0)) if latest_run else 0
            })
        
        db.close()
        return {"tasks": task_list}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str):
    """
    Get a single task's details including Python code, dependencies, and run history.
    """
    try:
        db = next(get_db())
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task:
            db.close()
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Check if schema supports code in runs
        from sqlalchemy import inspect as sql_inspect
        from app.database import engine
        inspector = sql_inspect(engine)
        task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
        has_python_code = 'python_code' in task_runs_columns
        
        # Get all runs for this task
        if has_python_code:
            runs = db.query(TaskRun).filter(
                TaskRun.task_id == task_id
            ).order_by(TaskRun.run_number.desc()).all()
        else:
            # Old schema: use raw SQL
            from sqlalchemy import text
            run_rows = db.execute(
                text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC"),
                {"task_id": task_id}
            ).fetchall()
            runs = run_rows  # Will be list of Row objects
        
        run_list = []
        for run in runs:
            if has_python_code:
                # New schema: run is a TaskRun object
                run_data = {
                    "id": run.id,
                    "runNumber": run.run_number,
                    "workflowId": run.workflow_id,
                    "phase": run.phase,
                    "pythonCode": run.python_code,
                    "dependencies": run.dependencies or "",
                    "requirementsFile": run.requirements_file or "",
                    "startedAt": run.started_at.isoformat() if run.started_at else "",
                    "finishedAt": run.finished_at.isoformat() if run.finished_at else "",
                    "createdAt": run.created_at.isoformat()
                }
            else:
                # Old schema: run is a Row object, use task's code
                # SQLAlchemy Row objects support column name access
                run_data = {
                    "id": getattr(run, 'id', run[0]),
                    "runNumber": getattr(run, 'run_number', run[3] if len(run) > 3 else 0),
                    "workflowId": getattr(run, 'workflow_id', run[2] if len(run) > 2 else ""),
                    "phase": getattr(run, 'phase', run[4] if len(run) > 4 else "Pending"),
                    "pythonCode": task.python_code,  # Fallback to task's code
                    "dependencies": task.dependencies or "",
                    "requirementsFile": task.requirements_file or "",
                    "startedAt": (getattr(run, 'started_at', None) or (run[5] if len(run) > 5 else None)),
                    "finishedAt": (getattr(run, 'finished_at', None) or (run[6] if len(run) > 6 else None)),
                    "createdAt": (getattr(run, 'created_at', None) or (run[7] if len(run) > 7 else None))
                }
                # Convert datetime objects to ISO format strings
                if run_data["startedAt"] and hasattr(run_data["startedAt"], 'isoformat'):
                    run_data["startedAt"] = run_data["startedAt"].isoformat()
                if run_data["finishedAt"] and hasattr(run_data["finishedAt"], 'isoformat'):
                    run_data["finishedAt"] = run_data["finishedAt"].isoformat()
                if run_data["createdAt"] and hasattr(run_data["createdAt"], 'isoformat'):
                    run_data["createdAt"] = run_data["createdAt"].isoformat()
                # Ensure empty strings if None
                run_data["startedAt"] = run_data["startedAt"] or ""
                run_data["finishedAt"] = run_data["finishedAt"] or ""
                run_data["createdAt"] = run_data["createdAt"] or ""
            run_list.append(run_data)
        
        db.close()
        
        # Return task info with latest run's code (for backward compatibility)
        latest_run = runs[0] if runs else None
        if latest_run and has_python_code:
            # New schema: use latest run's code
            return {
                "id": task.id,
                "pythonCode": latest_run.python_code,
                "dependencies": latest_run.dependencies or "",
                "requirementsFile": latest_run.requirements_file or "",
                "createdAt": task.created_at.isoformat(),
                "updatedAt": task.updated_at.isoformat(),
                "runs": run_list
            }
        else:
            # Old schema or no runs: use task's code
            return {
                "id": task.id,
                "pythonCode": task.python_code,
                "dependencies": task.dependencies or "",
                "requirementsFile": task.requirements_file or "",
                "createdAt": task.created_at.isoformat(),
                "updatedAt": task.updated_at.isoformat(),
                "runs": run_list
            }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/{task_id}/runs/{run_number}/logs")
async def get_run_logs(task_id: str, run_number: int, db: Session = Depends(get_db)):
    """
    Get logs for a specific run of a task.
    """
    try:
        # Check schema and get run appropriately
        from sqlalchemy import inspect as sql_inspect, text
        from app.database import engine
        inspector = sql_inspect(engine)
        task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
        has_python_code = 'python_code' in task_runs_columns
        
        # Get the run
        if has_python_code:
            run = db.query(TaskRun).filter(
                TaskRun.task_id == task_id,
                TaskRun.run_number == run_number
            ).first()
        else:
            result = db.execute(
                text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id AND run_number = :run_number LIMIT 1"),
                {"task_id": task_id, "run_number": run_number}
            ).fetchone()
            run = result
        
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_number} not found for task {task_id}")
        
        # Get workflow_id (handle both TaskRun objects and Row objects)
        if has_python_code:
            workflow_id = run.workflow_id
        else:
            workflow_id = getattr(run, 'workflow_id', run[2] if len(run) > 2 else None)
        
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        custom_api = CustomObjectsApi()
        
        # Get current workflow phase to ensure log phases are up-to-date
        try:
            workflow = custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=workflow_id
            )
            status = workflow.get("status", {})
            current_workflow_phase = determine_workflow_phase(status)
            
            # Get current phase (handle both TaskRun objects and Row objects)
            current_phase = run.phase if has_python_code else (getattr(run, 'phase', run[4] if len(run) > 4 else "Pending"))
            
            # Update run phase if changed
            if current_phase != current_workflow_phase:
                if has_python_code:
                    # New schema: update TaskRun object
                    run.phase = current_workflow_phase
                    if status.get("startedAt"):
                        run.started_at = datetime.fromisoformat(status.get("startedAt").replace("Z", "+00:00"))
                    if status.get("finishedAt"):
                        run.finished_at = datetime.fromisoformat(status.get("finishedAt").replace("Z", "+00:00"))
                    db.commit()
                else:
                    # Old schema: update using raw SQL
                    run_id_val = getattr(run, 'id', run[0] if len(run) > 0 else None)
                    update_params = {"run_id": run_id_val, "phase": current_workflow_phase}
                    update_sql = "UPDATE task_runs SET phase = :phase"
                    
                    if status.get("startedAt"):
                        started_str = status.get("startedAt").replace("Z", "+00:00")
                        update_sql += ", started_at = :started_at"
                        update_params["started_at"] = datetime.fromisoformat(started_str)
                    if status.get("finishedAt"):
                        finished_str = status.get("finishedAt").replace("Z", "+00:00")
                        update_sql += ", finished_at = :finished_at"
                        update_params["finished_at"] = datetime.fromisoformat(finished_str)
                    
                    update_sql += " WHERE id = :run_id"
                    db.execute(text(update_sql), update_params)
                    db.commit()
        except Exception as e:
            print(f"Could not fetch workflow status: {e}")
            current_workflow_phase = run.phase if has_python_code else (getattr(run, 'phase', run[4] if len(run) > 4 else "Pending"))
        
        # First, try to get logs from database
        run_id_val = run.id if has_python_code else (getattr(run, 'id', run[0] if len(run) > 0 else None))
        db_logs = get_logs_from_database(run_id_val, db, task_id=task_id, workflow_id=workflow_id)
        
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
                save_logs_to_database(run.id, db_logs, db, task_id=task_id, workflow_id=run.workflow_id)
        
        if db_logs:
            # Logs found in database, return them (with updated phase if needed)
            return {"logs": db_logs, "source": "database", "runId": run.id, "runNumber": run.run_number}
        
        # If not in database, fetch from Kubernetes and save to database
        try:
            k8s_logs = fetch_logs_from_kubernetes(run.workflow_id)
            if k8s_logs:
                # Save to database for future requests
                save_logs_to_database(run.id, k8s_logs, db, task_id=task_id, workflow_id=run.workflow_id)
                return {"logs": k8s_logs, "source": "kubernetes", "runId": run.id, "runNumber": run.run_number}
            else:
                return {"logs": [], "source": "kubernetes", "runId": run.id, "runNumber": run.run_number}
        except Exception as k8s_error:
            # If Kubernetes fetch fails, return empty logs
            print(f"Could not fetch logs from Kubernetes: {k8s_error}")
            return {"logs": [], "source": "error", "error": str(k8s_error), "runId": run.id, "runNumber": run.run_number}
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, run_number: int = None, db: Session = Depends(get_db)):
    """
    Get logs for a task. If run_number is provided, get logs for that specific run.
    Otherwise, get logs for the latest run.
    """
    try:
        # Get the task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Check schema and get run appropriately
        from sqlalchemy import inspect as sql_inspect, text
        from app.database import engine
        inspector = sql_inspect(engine)
        task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
        has_python_code = 'python_code' in task_runs_columns
        
        # Get the run
        if run_number:
            if has_python_code:
                run = db.query(TaskRun).filter(
                    TaskRun.task_id == task_id,
                    TaskRun.run_number == run_number
                ).first()
            else:
                result = db.execute(
                    text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id AND run_number = :run_number LIMIT 1"),
                    {"task_id": task_id, "run_number": run_number}
                ).fetchone()
                run = result
        else:
            # Get latest run
            if has_python_code:
                run = db.query(TaskRun).filter(
                    TaskRun.task_id == task_id
                ).order_by(TaskRun.run_number.desc()).first()
            else:
                result = db.execute(
                    text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                    {"task_id": task_id}
                ).fetchone()
                run = result
        
        if not run:
            return {"logs": [], "source": "database", "runNumber": 0}
        
        # Get workflow_id (handle both TaskRun objects and Row objects)
        if has_python_code:
            workflow_id = run.workflow_id
        else:
            workflow_id = getattr(run, 'workflow_id', run[2] if len(run) > 2 else None)
        
        # Call get_run_logs logic directly
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        custom_api = CustomObjectsApi()
        
        # Get current workflow phase
        try:
            workflow = custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=workflow_id
            )
            status = workflow.get("status", {})
            current_workflow_phase = determine_workflow_phase(status)
            
            # Get current phase (handle both TaskRun objects and Row objects)
            current_phase = run.phase if has_python_code else (getattr(run, 'phase', run[4] if len(run) > 4 else "Pending"))
            
            # Update run phase if changed
            if current_phase != current_workflow_phase:
                if has_python_code:
                    # New schema: update TaskRun object
                    run.phase = current_workflow_phase
                    if status.get("startedAt"):
                        run.started_at = datetime.fromisoformat(status.get("startedAt").replace("Z", "+00:00"))
                    if status.get("finishedAt"):
                        run.finished_at = datetime.fromisoformat(status.get("finishedAt").replace("Z", "+00:00"))
                    db.commit()
                else:
                    # Old schema: update using raw SQL
                    run_id_val = getattr(run, 'id', run[0] if len(run) > 0 else None)
                    update_params = {"run_id": run_id_val, "phase": current_workflow_phase}
                    update_sql = "UPDATE task_runs SET phase = :phase"
                    
                    if status.get("startedAt"):
                        started_str = status.get("startedAt").replace("Z", "+00:00")
                        update_sql += ", started_at = :started_at"
                        update_params["started_at"] = datetime.fromisoformat(started_str)
                    if status.get("finishedAt"):
                        finished_str = status.get("finishedAt").replace("Z", "+00:00")
                        update_sql += ", finished_at = :finished_at"
                        update_params["finished_at"] = datetime.fromisoformat(finished_str)
                    
                    update_sql += " WHERE id = :run_id"
                    db.execute(text(update_sql), update_params)
                    db.commit()
        except Exception as e:
            print(f"Could not fetch workflow status: {e}")
            current_workflow_phase = run.phase if has_python_code else (getattr(run, 'phase', run[4] if len(run) > 4 else "Pending"))
        
        # Get run_id and run_number (handle both TaskRun objects and Row objects)
        run_id_val = run.id if has_python_code else (getattr(run, 'id', run[0] if len(run) > 0 else None))
        run_number_val = run.run_number if has_python_code else (getattr(run, 'run_number', run[3] if len(run) > 3 else 0))
        
        # Get logs from database
        db_logs = get_logs_from_database(run_id_val, db, task_id=task_id, workflow_id=workflow_id)
        
        # Update phases if needed
        if db_logs and current_workflow_phase:
            needs_update = False
            for log_entry in db_logs:
                if current_workflow_phase in ["Succeeded", "Failed", "Error"]:
                    if log_entry["phase"] != current_workflow_phase:
                        log_entry["phase"] = current_workflow_phase
                        needs_update = True
            if needs_update:
                save_logs_to_database(run_id_val, db_logs, db, task_id=task_id, workflow_id=workflow_id)
        
        if db_logs:
            return {"logs": db_logs, "source": "database", "runId": run_id_val, "runNumber": run_number_val}
        
        # Fetch from Kubernetes
        try:
            k8s_logs = fetch_logs_from_kubernetes(workflow_id)
            if k8s_logs:
                save_logs_to_database(run_id_val, k8s_logs, db, task_id=task_id, workflow_id=workflow_id)
                return {"logs": k8s_logs, "source": "kubernetes", "runId": run_id_val, "runNumber": run_number_val}
            else:
                return {"logs": [], "source": "kubernetes", "runId": run_id_val, "runNumber": run_number_val}
        except Exception as k8s_error:
            print(f"Could not fetch logs from Kubernetes: {k8s_error}")
            return {"logs": [], "source": "error", "error": str(k8s_error), "runId": run.id, "runNumber": run.run_number}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/tasks/{task_id}/logs")
async def websocket_logs(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for streaming logs. Fetches from database first,
    then from Kubernetes, and saves new logs to database.
    Uses the latest run's workflow_id to fetch logs.
    """
    await websocket.accept()
    namespace = os.getenv("ARGO_NAMESPACE", "argo")
    core_api = CoreV1Api()
    custom_api = CustomObjectsApi()
    
    # Get database session
    db = SessionLocal()
    
    # Get the latest run for this task (handle schema migration)
    from sqlalchemy import inspect as sql_inspect, text
    from app.database import engine
    inspector = sql_inspect(engine)
    task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
    has_python_code = 'python_code' in task_runs_columns
    
    if has_python_code:
        # New schema: use ORM
        latest_run = db.query(TaskRun).filter(
            TaskRun.task_id == task_id
        ).order_by(TaskRun.run_number.desc()).first()
    else:
        # Old schema: use raw SQL
        result = db.execute(
            text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
            {"task_id": task_id}
        ).fetchone()
        latest_run = result  # Will be a Row object
    
    if not latest_run:
        await websocket.send_json({
            "type": "error",
            "message": f"No runs found for task {task_id}"
        })
        db.close()
        return
    
    # Handle both TaskRun objects and Row objects
    if has_python_code:
        workflow_id = latest_run.workflow_id
        run_id = latest_run.id
    else:
        run_id = getattr(latest_run, 'id', latest_run[0] if len(latest_run) > 0 else None)
        workflow_id = getattr(latest_run, 'workflow_id', latest_run[2] if len(latest_run) > 2 else None)
    
    last_logs_hash = ""
    last_sent_logs = []
    last_sent_phase = None
    
    # Helper function to fetch and send logs
    async def fetch_and_send_logs():
        nonlocal last_logs_hash, last_sent_logs, last_sent_phase, latest_run
        try:
            # Get workflow status using workflow_id
            workflow = custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=workflow_id
            )
            
            status = workflow.get("status", {})
            phase = determine_workflow_phase(status)
            
            # Get current phase (handle both TaskRun objects and Row objects)
            current_phase = latest_run.phase if has_python_code else (getattr(latest_run, 'phase', latest_run[4] if len(latest_run) > 4 else "Pending"))
            
            # Update run phase if changed
            if current_phase != phase:
                if has_python_code:
                    # New schema: update TaskRun object
                    latest_run.phase = phase
                    try:
                        if status.get("startedAt"):
                            started_str = status.get("startedAt")
                            if started_str.endswith("Z"):
                                started_str = started_str.replace("Z", "+00:00")
                            latest_run.started_at = datetime.fromisoformat(started_str)
                        if status.get("finishedAt"):
                            finished_str = status.get("finishedAt")
                            if finished_str.endswith("Z"):
                                finished_str = finished_str.replace("Z", "+00:00")
                            latest_run.finished_at = datetime.fromisoformat(finished_str)
                    except Exception as dt_error:
                        print(f"Error parsing datetime: {dt_error}")
                    db.commit()
                else:
                    # Old schema: update using raw SQL
                    update_params = {"run_id": run_id, "phase": phase}
                    update_sql = "UPDATE task_runs SET phase = :phase"
                    
                    try:
                        if status.get("startedAt"):
                            started_str = status.get("startedAt")
                            if started_str.endswith("Z"):
                                started_str = started_str.replace("Z", "+00:00")
                            update_sql += ", started_at = :started_at"
                            update_params["started_at"] = datetime.fromisoformat(started_str)
                        if status.get("finishedAt"):
                            finished_str = status.get("finishedAt")
                            if finished_str.endswith("Z"):
                                finished_str = finished_str.replace("Z", "+00:00")
                            update_sql += ", finished_at = :finished_at"
                            update_params["finished_at"] = datetime.fromisoformat(finished_str)
                    except Exception as dt_error:
                        print(f"Error parsing datetime: {dt_error}")
                    
                    update_sql += " WHERE id = :run_id"
                    db.execute(text(update_sql), update_params)
                    db.commit()
                    
                    # Refresh latest_run by re-querying
                    latest_run = db.execute(
                        text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE id = :run_id"),
                        {"run_id": run_id}
                    ).fetchone()
            
            # Try to get logs from database first (using run_id)
            db_logs = get_logs_from_database(run_id, db, task_id=task_id, workflow_id=workflow_id)
            
            # Also fetch latest from Kubernetes to get any new logs
            try:
                k8s_logs = fetch_logs_from_kubernetes(workflow_id, namespace)
                
                # Save/update logs in database (using run_id)
                if k8s_logs:
                    save_logs_to_database(run_id, k8s_logs, db, task_id=task_id, workflow_id=workflow_id)
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
                    final_logs = fetch_logs_from_kubernetes(workflow_id, namespace)
                    if final_logs:
                        save_logs_to_database(run_id, final_logs, db, task_id=task_id, workflow_id=workflow_id)
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
    Permanently delete a task: removes all workflows from Kubernetes AND all runs/logs from database.
    Works for any task regardless of status.
    """
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        api_instance = CustomObjectsApi()
        
        # Initialize counters
        deleted_logs = 0
        deleted_runs = 0
        deleted_workflows = 0
        
        # Get the task and all its runs
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        
        # Check schema and get runs appropriately
        from sqlalchemy import text, inspect
        from app.database import engine
        inspector = inspect(engine)
        task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
        has_python_code = 'python_code' in task_runs_columns
        
        # Get all runs for this task to delete workflows
        if has_python_code:
            # New schema: use ORM
            runs = db.query(TaskRun).filter(TaskRun.task_id == task_id).all()
        else:
            # Old schema: use raw SQL
            run_rows = db.execute(
                text("SELECT id, workflow_id FROM task_runs WHERE task_id = :task_id"),
                {"task_id": task_id}
            ).fetchall()
            runs = run_rows
        
        # Delete workflows from Kubernetes
        for run in runs:
            # Handle both TaskRun objects and Row objects
            if has_python_code:
                workflow_id = run.workflow_id
            else:
                workflow_id = getattr(run, 'workflow_id', run[1] if len(run) > 1 else None)
            
            if workflow_id:
                try:
                    api_instance.delete_namespaced_custom_object(
                        group="argoproj.io",
                        version="v1alpha1",
                        namespace=namespace,
                        plural="workflows",
                        name=workflow_id
                    )
                    deleted_workflows += 1
                except Exception as k8s_error:
                    # If workflow doesn't exist in Kubernetes, that's okay
                    if "404" not in str(k8s_error) and "Not Found" not in str(k8s_error):
                        print(f"Warning: Could not delete workflow {workflow_id}: {k8s_error}")
        
        # Delete task from database
        # Manually delete runs first to avoid ORM relationship loading issues with unmigrated schema
        try:
            deleted_runs = len(runs)
            deleted_logs = 0
            
            # Check which schema we're using
            from sqlalchemy import text, inspect
            from app.database import engine
            inspector = inspect(engine)
            task_logs_columns = [col['name'] for col in inspector.get_columns('task_logs')]
            has_run_id = 'run_id' in task_logs_columns
            has_task_id = 'task_id' in task_logs_columns
            
            # Delete logs first (manually to avoid ORM relationship issues)
            if has_run_id:
                # New schema: delete logs via run_id
                for run in runs:
                    run_id = run.id if has_python_code else (getattr(run, 'id', run[0]) if len(run) > 0 else None)
                    if run_id:
                        log_count = db.execute(text("DELETE FROM task_logs WHERE run_id = :run_id"), {"run_id": run_id}).rowcount
                        deleted_logs += log_count
            elif has_task_id:
                # Old schema: delete logs via task_id
                deleted_logs = db.execute(text("DELETE FROM task_logs WHERE task_id = :task_id"), {"task_id": task_id}).rowcount
            # If neither exists, logs table might be empty or in unexpected state
            
            # Delete runs manually (to avoid ORM cascade loading relationships)
            for run in runs:
                run_id = run.id if has_python_code else (getattr(run, 'id', run[0]) if len(run) > 0 else None)
                if run_id:
                    db.execute(text("DELETE FROM task_runs WHERE id = :run_id"), {"run_id": run_id})
            
            # Finally delete the task using raw SQL to avoid ORM cascade issues
            # Using raw SQL prevents SQLAlchemy from trying to load relationships with non-existent columns
            db.execute(text("DELETE FROM tasks WHERE id = :task_id"), {"task_id": task_id})
            db.commit()
            
            print(f"Deleted task {task_id}: {deleted_runs} runs, {deleted_logs} log entries, {deleted_workflows} workflows")
        except Exception as db_error:
            db.rollback()
            print(f"Error deleting task from database: {db_error}")
            raise
        
        return {
            "status": "deleted", 
            "id": task_id,
            "runs_deleted": deleted_runs,
            "logs_deleted": deleted_logs,
            "workflows_deleted": deleted_workflows
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Check if it's a 404 (task not found)
        if "404" in str(e) or "Not Found" in str(e):
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/tasks/callback")
async def handle_callback(data: dict):
    print(f"Callback: {data}")
    return {"status": "ok"}
