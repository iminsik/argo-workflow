import os, asyncio, json, uuid
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kubernetes import config  # type: ignore
from kubernetes.client import CustomObjectsApi, CoreV1Api  # type: ignore
from kubernetes.stream import stream  # type: ignore
from sqlalchemy.orm import Session
from app.database import init_db, get_db, TaskLog, Task, TaskRun, SessionLocal, Flow, FlowRun, FlowStepRun, FlowStepLog  # type: ignore

# Hera SDK integration (required)
try:
    from app.workflow_hera import create_workflow_with_hera  # type: ignore
    from app.workflow_hera_flow import create_flow_workflow_with_hera, generate_flow_workflow_template  # type: ignore
except ImportError as e:
    raise ImportError(f"Hera SDK is required but not available: {e}. Please install hera: poetry add hera")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}. Logs will not be persisted.")
    
    # Initialize persistent PV pod for fast file operations
    try:
        pod = get_persistent_pv_pod()
        pod.create_pod()
        print("Persistent PV pod initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize persistent PV pod: {e}. File operations will be slower.")
    
    yield
    
    # Shutdown
    global _persistent_pv_pod
    if _persistent_pv_pod:
        try:
            _persistent_pv_pod.cleanup()
        except Exception as e:
            print(f"Error cleaning up persistent PV pod: {e}")


app = FastAPI(lifespan=lifespan)

# Configure CORS
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kubernetes configuration
# Supports both in-cluster config (when running in K8s) and external config (local dev or external cluster)
KUBERNETES_CLUSTER_TYPE = os.getenv("KUBERNETES_CLUSTER_TYPE", "auto")  # "auto", "kind", "eks", "external"
KUBECONFIG_PATH = os.getenv("KUBECONFIG", os.path.expanduser("~/.kube/config"))

try:
    config.load_incluster_config()
    print("Using in-cluster Kubernetes configuration")
except:
    # Load kubeconfig from specified path or default location
    if os.path.exists(KUBECONFIG_PATH):
        config.load_kube_config(config_file=KUBECONFIG_PATH)
        print(f"Loaded Kubernetes config from {KUBECONFIG_PATH}")
    else:
        config.load_kube_config()
        print("Loaded Kubernetes config from default location")
    
    # Get the configuration to check the server URL
    from kubernetes.client import Configuration
    configuration = Configuration.get_default_copy()
    
    # Determine if we should apply KinD patches
    # Check if explicitly set to kind, or auto-detect by checking if server is localhost
    is_explicit_kind = KUBERNETES_CLUSTER_TYPE == "kind"
    is_explicit_kind_flag = os.getenv("KIND_CLUSTER", "").lower() == "true"
    is_localhost = configuration.host and ('127.0.0.1' in configuration.host or 'localhost' in configuration.host)
    
    should_patch_kind = (
        is_explicit_kind or 
        (KUBERNETES_CLUSTER_TYPE == "auto" and (is_explicit_kind_flag or is_localhost))
    )
    
    if should_patch_kind:
        # Check if we're running inside Docker
        # Only patch to host.docker.internal if running inside Docker
        running_in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
        
        # Patch configuration for Docker: replace 127.0.0.1 with host.docker.internal
        # and disable SSL verification for development (kind uses self-signed certs)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        if configuration.host and ('127.0.0.1' in configuration.host or 'localhost' in configuration.host):
            if running_in_docker:
                # Replace both 127.0.0.1 and localhost with host.docker.internal (only when in Docker)
                configuration.host = configuration.host.replace('127.0.0.1', 'host.docker.internal')
                configuration.host = configuration.host.replace('localhost', 'host.docker.internal')
                print("Applied KinD-specific configuration patches (localhost -> host.docker.internal) for Docker")
            else:
                # Running locally, keep localhost but disable SSL verification for KinD
                print("Running locally, using localhost for KinD cluster")
            
            # Disable SSL verification for development (kind uses self-signed certs)
            configuration.verify_ssl = False
            Configuration.set_default(configuration)
    elif KUBERNETES_CLUSTER_TYPE in ("eks", "external"):
        # For external clusters (EKS, etc.), use standard configuration
        print(f"Using external Kubernetes cluster configuration (type: {KUBERNETES_CLUSTER_TYPE})")
    else:
        # Auto mode but not localhost - assume external cluster
        print(f"Auto-detected cluster type (server: {configuration.host})")

class TaskSubmitRequest(BaseModel):
    pythonCode: str = "print('Processing task in Kind...')"
    dependencies: str | None = None  # Space or comma-separated Python package names
    requirementsFile: str | None = None  # requirements.txt content
    systemDependencies: str | None = None  # Space or comma-separated Nix package names (e.g., "gcc make")
    useCache: bool = True  # Whether to use UV and Nix cache volumes
    taskId: str | None = None  # Optional: task ID for rerun (creates new run of existing task)


class FlowStepRequest(BaseModel):
    id: str
    name: str
    pythonCode: str
    dependencies: str | None = None
    requirementsFile: str | None = None
    position: dict  # {"x": number, "y": number}


class FlowEdgeRequest(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class FlowCreateRequest(BaseModel):
    name: str
    description: str | None = None
    steps: list[FlowStepRequest]
    edges: list[FlowEdgeRequest]


class FlowUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[FlowStepRequest] | None = None
    edges: list[FlowEdgeRequest] | None = None


# Persistent Pod Manager for PV file operations
class PersistentPVPod:
    """Manages a persistent pod for fast PV file operations."""
    
    def __init__(self):
        self.pod_name = f"pv-persistent-{uuid.uuid4().hex[:8]}"
        self.namespace = os.getenv("ARGO_NAMESPACE", "argo")
        self.core_api = None
        self._pod_ready = False
        
    def initialize(self):
        """Initialize Kubernetes API client."""
        self.core_api = CoreV1Api()
        
    def create_pod(self):
        """Create the persistent pod."""
        if not self.core_api:
            self.initialize()
            
        try:
            # Check if pod already exists
            try:
                existing = self.core_api.read_namespaced_pod(name=self.pod_name, namespace=self.namespace)
                if existing.status.phase in ["Running", "Pending"]:
                    print(f"Persistent PV pod {self.pod_name} already exists")
                    self._pod_ready = True
                    return
            except Exception:
                pass  # Pod doesn't exist, create it
            
            # Create persistent pod that stays running
            pod_manifest = {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": self.pod_name,
                    "namespace": self.namespace,
                },
                "spec": {
                    "restartPolicy": "Always",  # Keep pod running
                    "containers": [
                        {
                            "name": "pv-accessor",
                            "image": "python:3.11-slim",
                            "command": ["sleep", "infinity"],  # Keep container running
                            "volumeMounts": [
                                {
                                    "name": "task-results",
                                    "mountPath": "/mnt/results"
                                }
                            ]
                        }
                    ],
                    "volumes": [
                        {
                            "name": "task-results",
                            "persistentVolumeClaim": {
                                "claimName": "task-results-pvc"
                            }
                        }
                    ]
                }
            }
            
            self.core_api.create_namespaced_pod(namespace=self.namespace, body=pod_manifest)
            print(f"Created persistent PV pod: {self.pod_name}")
            
            # Wait for pod to be ready
            import time
            max_wait = 60
            waited = 0
            while waited < max_wait:
                try:
                    pod = self.core_api.read_namespaced_pod(name=self.pod_name, namespace=self.namespace)
                    if pod.status.phase == "Running":
                        # Check if container is ready
                        if pod.status.container_statuses:
                            if pod.status.container_statuses[0].ready:
                                self._pod_ready = True
                                print(f"Persistent PV pod {self.pod_name} is ready")
                                return
                except Exception as e:
                    pass
                time.sleep(1)
                waited += 1
            
            raise Exception(f"Pod {self.pod_name} did not become ready in time")
            
        except Exception as e:
            print(f"Error creating persistent PV pod: {e}")
            self._pod_ready = False
            raise
    
    def ensure_ready(self):
        """Ensure pod is ready, recreate if needed."""
        if not self._pod_ready or not self.core_api:
            self.create_pod()
            return
        
        # Check if pod is still running
        try:
            pod = self.core_api.read_namespaced_pod(name=self.pod_name, namespace=self.namespace)
            if pod.status.phase != "Running" or not (pod.status.container_statuses and pod.status.container_statuses[0].ready):
                print(f"Persistent PV pod {self.pod_name} is not ready, recreating...")
                self._pod_ready = False
                try:
                    self.core_api.delete_namespaced_pod(name=self.pod_name, namespace=self.namespace)
                except:
                    pass
                self.create_pod()
        except Exception as e:
            print(f"Error checking pod status: {e}, recreating...")
            self._pod_ready = False
            try:
                self.core_api.delete_namespaced_pod(name=self.pod_name, namespace=self.namespace)
            except:
                pass
            self.create_pod()
    
    def exec_command(self, command: str) -> str:
        """Execute a command in the persistent pod and return output."""
        self.ensure_ready()
        
        try:
            # Execute command using stream API
            resp = stream(
                self.core_api.connect_get_namespaced_pod_exec,
                self.pod_name,
                self.namespace,
                command=["sh", "-c", command],
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            # Stream API returns string directly
            return resp if isinstance(resp, str) else resp.decode('utf-8') if isinstance(resp, bytes) else str(resp)
        except Exception as e:
            # If exec fails, pod might be dead, try to recreate
            print(f"Error executing command in pod: {e}, attempting to recreate pod...")
            self._pod_ready = False
            try:
                self.core_api.delete_namespaced_pod(name=self.pod_name, namespace=self.namespace)
            except:
                pass
            self.create_pod()
            # Retry once
            resp = stream(
                self.core_api.connect_get_namespaced_pod_exec,
                self.pod_name,
                self.namespace,
                command=["sh", "-c", command],
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            return resp if isinstance(resp, str) else resp.decode('utf-8') if isinstance(resp, bytes) else str(resp)
    
    def cleanup(self):
        """Clean up the persistent pod."""
        if not self.core_api:
            return
            
        try:
            self.core_api.delete_namespaced_pod(name=self.pod_name, namespace=self.namespace)
            print(f"Cleaned up persistent PV pod: {self.pod_name}")
        except Exception as e:
            print(f"Error cleaning up persistent PV pod: {e}")


# Global persistent pod instance
_persistent_pv_pod: PersistentPVPod | None = None


def get_persistent_pv_pod() -> PersistentPVPod:
    """Get or create the persistent PV pod."""
    global _persistent_pv_pod
    if _persistent_pv_pod is None:
        _persistent_pv_pod = PersistentPVPod()
        _persistent_pv_pod.initialize()
    return _persistent_pv_pod


def fetch_logs_from_kubernetes(task_id: str, namespace: str | None = None) -> list:
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


def save_logs_to_database(run_id: int, logs: list, db: Session, task_id: str | None = None, workflow_id: str | None = None):
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
                # Old schema: use task_id, but filter by workflow_id when checking/updating
                # Join with task_runs to ensure we're working with logs for the correct run
                if workflow_id:
                    # In old schema, we need to ensure logs are associated with the specific run
                    # Since task_logs only has task_id, we need to use pod_name to distinguish runs
                    # Pod names in Argo usually contain the workflow_id, so we can use that
                    # Check if log exists for this specific workflow_id (run) by matching pod_name pattern
                    existing = db.execute(
                        text("""
                            SELECT tl.id FROM task_logs tl
                            WHERE tl.task_id = :task_id 
                            AND tl.node_id = :node_id 
                            AND (tl.pod_name = :pod_name OR tl.pod_name LIKE :workflow_pattern)
                        """),
                        {
                            "task_id": task_id, 
                            "node_id": log_entry["node"], 
                            "pod_name": log_entry["pod"],
                            "workflow_pattern": f"%{workflow_id}%"
                        }
                    ).fetchone()
                    
                    if existing:
                        # Update existing entry
                        db.execute(
                            text("UPDATE task_logs SET logs = :logs, phase = :phase, updated_at = :updated_at WHERE id = :id"),
                            {
                                "logs": log_entry["logs"], 
                                "phase": log_entry["phase"], 
                                "id": existing[0],
                                "updated_at": datetime.utcnow()
                            }
                        )
                    else:
                        # Create new entry (pod_name should be unique per workflow/run)
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
                    # Fallback: if no workflow_id, use task_id (less precise)
                    existing = db.execute(
                        text("SELECT id FROM task_logs WHERE task_id = :task_id AND node_id = :node_id AND pod_name = :pod_name"),
                        {"task_id": task_id, "node_id": log_entry["node"], "pod_name": log_entry["pod"]}
                    ).fetchone()
                    
                    if existing:
                        # Update existing entry
                        db.execute(
                            text("UPDATE task_logs SET logs = :logs, phase = :phase, updated_at = :updated_at WHERE id = :id"),
                            {
                                "logs": log_entry["logs"], 
                                "phase": log_entry["phase"], 
                                "id": existing[0],
                                "updated_at": datetime.utcnow()
                            }
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


def get_logs_from_database(run_id: int, db: Session, task_id: str | None = None, workflow_id: str | None = None) -> list:
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
            # New schema: use run_id with ORM
            db_logs = db.query(TaskLog).filter(
                TaskLog.run_id == run_id
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
        elif has_task_id and task_id:
            # Old schema: filter by workflow_id by joining with task_runs
            # This ensures each run shows its own logs, not all logs for the task
            if workflow_id:
                # Join with task_runs to filter by workflow_id
                # Also filter by pod_name pattern that matches the workflow_id to ensure we only get logs for this specific run
                log_rows = db.execute(
                    text("""
                        SELECT DISTINCT tl.node_id, tl.pod_name, tl.phase, tl.logs 
                        FROM task_logs tl
                        INNER JOIN task_runs tr ON tl.task_id = tr.task_id
                        WHERE tr.workflow_id = :workflow_id
                        AND (tl.pod_name LIKE :workflow_pattern OR tl.node_id = :workflow_id)
                        ORDER BY tl.created_at
                    """),
                    {
                        "workflow_id": workflow_id,
                        "workflow_pattern": f"%{workflow_id}%"
                    }
                ).fetchall()
            else:
                # Fallback: if no workflow_id, use task_id (will show all runs' logs)
                log_rows = db.execute(
                    text("SELECT node_id, pod_name, phase, logs FROM task_logs WHERE task_id = :task_id ORDER BY created_at"),
                    {"task_id": task_id}
                ).fetchall()
            
            return [
                {
                    "node": getattr(row, 'node_id', row[0] if len(row) > 0 else ""),
                    "pod": getattr(row, 'pod_name', row[1] if len(row) > 1 else ""),
                    "phase": getattr(row, 'phase', row[2] if len(row) > 2 else "Pending"),
                    "logs": getattr(row, 'logs', row[3] if len(row) > 3 else "")
                }
                for row in log_rows
            ]
        else:
            # No matching schema or missing task_id
            return []
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

def create_and_submit_workflow(
    python_code: str,
    dependencies: str | None = None,
    requirements_file: str | None = None,
    system_dependencies: str | None = None,
    use_cache: bool = True,
    namespace: str = "argo"
) -> str:
    """
    Helper function to create and submit an Argo Workflow using Hera SDK.
    Returns the workflow ID.
    
    Args:
        python_code: Python code to execute
        dependencies: Python package names (space or comma-separated)
        requirements_file: requirements.txt content
        system_dependencies: Nix package names (space or comma-separated, e.g., "gcc make")
        use_cache: Whether to use UV and Nix cache volumes
        namespace: Kubernetes namespace
    """
    # Check if PVC exists and is bound before creating workflow
    core_api = CoreV1Api()
    required_pvcs = ["task-results-pvc"]
    if use_cache:
        required_pvcs.extend(["uv-cache-pvc", "nix-store-pvc"])
    
    for pvc_name in required_pvcs:
        try:
            pvc = core_api.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace
            )
            pvc_status = pvc.status.phase if pvc.status else "Unknown"
            if pvc_status != "Bound":
                raise HTTPException(
                    status_code=400, 
                    detail=f"PVC '{pvc_name}' is not bound. Current status: {pvc_status}. Please ensure the PV is available."
                )
        except Exception as pvc_error:
            # If PVC doesn't exist, that's also a problem
            if "404" in str(pvc_error) or "Not Found" in str(pvc_error):
                raise HTTPException(
                    status_code=400,
                    detail=f"PVC '{pvc_name}' not found. Please create it first using: kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml"
                )
            # Re-raise if it's our HTTPException
            if isinstance(pvc_error, HTTPException):
                raise pvc_error
            # Otherwise log and continue (might be a transient issue)
            print(f"Warning: Could not verify PVC '{pvc_name}' status: {pvc_error}")
    
    # Create workflow using Hera SDK
    workflow_id = create_workflow_with_hera(
        python_code=python_code,
        dependencies=dependencies,
        requirements_file=requirements_file,
        system_dependencies=system_dependencies,
        use_cache=use_cache,
        namespace=namespace
    )
    
    if not workflow_id or workflow_id == "unknown":
        raise HTTPException(
            status_code=500,
            detail="Failed to extract workflow ID from created workflow"
        )
    
    return workflow_id


@app.post("/api/v1/tasks/submit")
async def submit_task(request: TaskSubmitRequest = TaskSubmitRequest()):
    """
    Submit a task to be saved in the database without running it.
    The task will have status 'Not Started' until it is explicitly run.
    """
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
        
        # Only save the task to database, don't create workflow yet
        db = next(get_db())
        try:
            # Determine task_id: use provided taskId for rerun, or generate new one
            if request.taskId:
                # Rerun: update existing task
                task = db.query(Task).filter(Task.id == request.taskId).first()
                if not task:
                    raise HTTPException(status_code=404, detail=f"Task {request.taskId} not found")
                
                # Update task code and dependencies
                task.python_code = request.pythonCode
                task.dependencies = request.dependencies if request.dependencies else None
                task.requirements_file = request.requirementsFile if request.requirementsFile else None
                task.system_dependencies = request.systemDependencies if request.systemDependencies else None
                task.updated_at = datetime.utcnow()
                db.commit()
                task_id = request.taskId
            else:
                # New task: create Task record
                task_id = f"task-{uuid.uuid4().hex[:12]}"
                task = Task(
                    id=task_id,
                    python_code=request.pythonCode,
                    dependencies=request.dependencies if request.dependencies else None,
                    requirements_file=request.requirementsFile if request.requirementsFile else None,
                    system_dependencies=request.systemDependencies if request.systemDependencies else None
                )
                db.add(task)
                db.commit()
            
            return {
                "id": task_id,
                "message": "Task saved successfully. Use /api/v1/tasks/{task_id}/run to execute it."
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as db_error:
            db.rollback()
            print(f"Error saving task to database: {db_error}")
            raise HTTPException(status_code=500, detail=f"Failed to save task: {str(db_error)}")
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        # Print full error for debugging
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class TaskRunRequest(BaseModel):
    systemDependencies: str | None = None  # Optional system dependencies for this run
    useCache: bool = True  # Whether to use cache volumes

@app.post("/api/v1/tasks/{task_id}/run")
async def run_task(task_id: str, run_request: TaskRunRequest | None = None):
    """
    Execute a task that was previously saved.
    Creates the workflow and starts execution.
    
    Optional request body can include:
    - systemDependencies: System dependencies (Nix packages) for this run
    - useCache: Whether to use cache volumes (default: true)
    """
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # Load task from database
        db = next(get_db())
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            
            # Check if task already has a running workflow
            from sqlalchemy import inspect as sql_inspect, text
            from app.database import engine
            inspector = sql_inspect(engine)
            task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
            has_python_code = 'python_code' in task_runs_columns
            
            if has_python_code:
                latest_run = db.query(TaskRun).filter(
                    TaskRun.task_id == task_id
                ).order_by(TaskRun.run_number.desc()).first()
            else:
                result = db.execute(
                    text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                    {"task_id": task_id}
                ).fetchone()
                latest_run = result
            
            # Check if latest run is still running
            if latest_run:
                latest_phase = latest_run.phase if has_python_code else (latest_run[4] if isinstance(latest_run, tuple) else latest_run.phase)
                if latest_phase in ["Running", "Pending"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Task {task_id} already has a running workflow (run #{latest_run.run_number if has_python_code else (latest_run[3] if isinstance(latest_run, tuple) else latest_run.run_number)}). Please wait for it to complete or cancel it first."
                    )
            
            # Get system dependencies - priority: request > latest run > task > None
            system_deps = None
            if run_request and run_request.systemDependencies:
                # Use system dependencies from request
                system_deps = run_request.systemDependencies
            elif has_python_code and latest_run:
                # Try to get from latest run (if it was stored there from a previous run)
                system_deps = getattr(latest_run, 'system_dependencies', None)
            
            # If still None, try to get from task
            if system_deps is None:
                system_deps = getattr(task, 'system_dependencies', None)
            
            # Get use_cache setting
            use_cache = run_request.useCache if run_request else True
            
            # Create and submit workflow
            workflow_id = create_and_submit_workflow(
                python_code=task.python_code,
                dependencies=task.dependencies,
                requirements_file=task.requirements_file,
                system_dependencies=system_deps,
                use_cache=use_cache,
                namespace=namespace
            )
            
            # Get next run number
            if has_python_code:
                max_run = db.query(TaskRun).filter(TaskRun.task_id == task_id).order_by(TaskRun.run_number.desc()).first()
                next_run_number = (max_run.run_number + 1) if max_run else 1
            else:
                result = db.execute(
                    text("SELECT run_number FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                    {"task_id": task_id}
                ).fetchone()
                if result:
                    next_run_number = (getattr(result, 'run_number', result[0]) + 1) if result else 1
                else:
                    next_run_number = 1
            
            # Create TaskRun record
            if has_python_code:
                task_run = TaskRun(
                    task_id=task_id,
                    workflow_id=workflow_id,
                    run_number=next_run_number,
                    phase="Pending",
                    python_code=task.python_code,
                    dependencies=task.dependencies,
                    requirements_file=task.requirements_file,
                    system_dependencies=system_deps,  # Will be None for now, but field exists
                    started_at=datetime.utcnow()
                )
                db.add(task_run)
                db.commit()
            else:
                # Old schema: Try to add columns dynamically if they don't exist
                try:
                    existing_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                    
                    if 'python_code' not in existing_columns:
                        db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS python_code TEXT"))
                        db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS dependencies TEXT"))
                        db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS requirements_file TEXT"))
                        db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS system_dependencies TEXT"))
                        db.commit()
                        inspector = sql_inspect(engine)
                        existing_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                    elif 'system_dependencies' not in existing_columns:
                        # Add system_dependencies column if it doesn't exist
                        db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS system_dependencies TEXT"))
                        db.commit()
                        inspector = sql_inspect(engine)
                        existing_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                    
                    if 'python_code' in existing_columns:
                        # Check if system_dependencies column exists
                        has_system_deps_col = 'system_dependencies' in existing_columns
                        if has_system_deps_col:
                            result = db.execute(
                                text("""
                                    INSERT INTO task_runs (task_id, workflow_id, run_number, phase, python_code, dependencies, requirements_file, system_dependencies, started_at, created_at)
                                    VALUES (:task_id, :workflow_id, :run_number, :phase, :python_code, :dependencies, :requirements_file, :system_dependencies, :started_at, :created_at)
                                    RETURNING id
                                """),
                                {
                                    "task_id": task_id,
                                    "workflow_id": workflow_id,
                                    "run_number": next_run_number,
                                    "phase": "Pending",
                                    "python_code": task.python_code,
                                    "dependencies": task.dependencies,
                                    "requirements_file": task.requirements_file,
                                    "system_dependencies": system_deps,
                                    "started_at": datetime.utcnow(),
                                    "created_at": datetime.utcnow()
                                }
                            )
                        else:
                            result = db.execute(
                                text("""
                                    INSERT INTO task_runs (task_id, workflow_id, run_number, phase, python_code, dependencies, requirements_file, started_at, created_at)
                                    VALUES (:task_id, :workflow_id, :run_number, :phase, :python_code, :dependencies, :requirements_file, :started_at, :created_at)
                                    RETURNING id
                                """),
                                {
                                    "task_id": task_id,
                                    "workflow_id": workflow_id,
                                    "run_number": next_run_number,
                                    "phase": "Pending",
                                    "python_code": task.python_code,
                                    "dependencies": task.dependencies,
                                    "requirements_file": task.requirements_file,
                                    "started_at": datetime.utcnow(),
                                    "created_at": datetime.utcnow()
                                }
                            )
                        db.commit()
                    else:
                        result = db.execute(
                            text("""
                                INSERT INTO task_runs (task_id, workflow_id, run_number, phase, started_at, created_at)
                                VALUES (:task_id, :workflow_id, :run_number, :phase, :started_at, :created_at)
                                RETURNING id
                            """),
                            {
                                "task_id": task_id,
                                "workflow_id": workflow_id,
                                "run_number": next_run_number,
                                "phase": "Pending",
                                "started_at": datetime.utcnow(),
                                "created_at": datetime.utcnow()
                            }
                        )
                        db.commit()
                except Exception as e:
                    print(f"Warning: Could not add code columns to task_runs: {e}")
                    result = db.execute(
                        text("""
                            INSERT INTO task_runs (task_id, workflow_id, run_number, phase, started_at, created_at)
                            VALUES (:task_id, :workflow_id, :run_number, :phase, :started_at, :created_at)
                            RETURNING id
                        """),
                        {
                            "task_id": task_id,
                            "workflow_id": workflow_id,
                            "run_number": next_run_number,
                            "phase": "Pending",
                            "started_at": datetime.utcnow(),
                            "created_at": datetime.utcnow()
                        }
                    )
                    db.commit()
            
            return {
                "id": task_id,
                "workflowId": workflow_id,
                "runNumber": next_run_number,
                "message": f"Task {task_id} started successfully (run #{next_run_number})"
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as db_error:
            db.rollback()
            print(f"Error saving task run to database: {db_error}")
            raise HTTPException(status_code=500, detail=f"Failed to save task run: {str(db_error)}")
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        # Print full error for debugging
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/tasks")
async def list_tasks():
    """
    List all tasks from database with their latest run information.
    Syncs phase from Kubernetes for the latest run.
    """
    try:
        db = next(get_db())
        try:
            # Get all tasks
            tasks = db.query(Task).all()
            
            namespace = os.getenv("ARGO_NAMESPACE", "argo")
            api_instance = CustomObjectsApi()
            
            # Get latest run for each task and sync phase from Kubernetes
            task_list = []
            for task in tasks:
                # Get latest run
                from sqlalchemy import inspect as sql_inspect, text
                from app.database import engine
                inspector = sql_inspect(engine)
                task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                has_python_code = 'python_code' in task_runs_columns
                has_system_deps = 'system_dependencies' in task_runs_columns
                
                # Ensure system_dependencies column exists if python_code exists
                if has_python_code and not has_system_deps:
                    try:
                        db.execute(text("ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS system_dependencies TEXT"))
                        db.commit()
                        has_system_deps = True
                    except Exception as e:
                        print(f"Warning: Could not add system_dependencies column: {e}")
                
                if has_python_code:
                    latest_run = db.query(TaskRun).filter(
                        TaskRun.task_id == task.id
                    ).order_by(TaskRun.run_number.desc()).first()
                else:
                    result = db.execute(
                        text("SELECT id, task_id, workflow_id, run_number, phase, started_at, finished_at, created_at FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                        {"task_id": task.id}
                    ).fetchone()
                    latest_run = result
                
                # Determine phase
                phase = "Not Started"
                started_at = None
                finished_at = None
                
                if latest_run:
                    # Sync phase from Kubernetes if workflow_id exists
                    if has_python_code and latest_run.workflow_id:
                        try:
                            workflow = api_instance.get_namespaced_custom_object(
                                group="argoproj.io",
                                version="v1alpha1",
                                namespace=namespace,
                                plural="workflows",
                                name=latest_run.workflow_id
                            )
                            status = workflow.get("status", {})
                            phase = determine_workflow_phase(status)
                            
                            # Update phase in database if it changed
                            if latest_run.phase != phase:
                                latest_run.phase = phase
                                db.commit()
                            
                            # Get timestamps from workflow
                            if status.get("startedAt"):
                                started_at = status["startedAt"]
                            if status.get("finishedAt"):
                                finished_at = status["finishedAt"]
                        except Exception as e:
                            # Workflow might not exist anymore, use database phase
                            phase = latest_run.phase if has_python_code else (latest_run[4] if isinstance(latest_run, tuple) else latest_run.phase)
                            started_at = latest_run.started_at.isoformat() if has_python_code and latest_run.started_at else (latest_run[5] if isinstance(latest_run, tuple) and len(latest_run) > 5 else None)
                            finished_at = latest_run.finished_at.isoformat() if has_python_code and latest_run.finished_at else (latest_run[6] if isinstance(latest_run, tuple) and len(latest_run) > 6 else None)
                    else:
                        # Use database phase
                        phase = latest_run.phase if has_python_code else (latest_run[4] if isinstance(latest_run, tuple) else latest_run.phase)
                        started_at = latest_run.started_at.isoformat() if has_python_code and latest_run.started_at else (latest_run[5] if isinstance(latest_run, tuple) and len(latest_run) > 5 else None)
                        finished_at = latest_run.finished_at.isoformat() if has_python_code and latest_run.finished_at else (latest_run[6] if isinstance(latest_run, tuple) and len(latest_run) > 6 else None)
                
                task_list.append({
                    "id": task.id,
                    "phase": phase,
                    "startedAt": started_at,
                    "finishedAt": finished_at,
                    "createdAt": task.created_at.isoformat() if task.created_at else None
                })
            
            return {"tasks": task_list}
        finally:
            db.close()
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
                    "systemDependencies": getattr(run, 'system_dependencies', None) or "",
                    "startedAt": run.started_at.isoformat() if run.started_at else "",
                    "finishedAt": run.finished_at.isoformat() if run.finished_at else "",
                    "createdAt": run.created_at.isoformat()
                }
            else:
                # Old schema: run is a Row object
                # NOTE: In old schema, code is NOT saved per run, so all runs show Task's code
                # This is expected behavior until database is migrated to add python_code column to task_runs
                # SQLAlchemy Row objects support column name access
                run_data = {
                    "id": getattr(run, 'id', run[0]),
                    "runNumber": getattr(run, 'run_number', run[3] if len(run) > 3 else 0),
                    "workflowId": getattr(run, 'workflow_id', run[2] if len(run) > 2 else ""),
                    "phase": getattr(run, 'phase', run[4] if len(run) > 4 else "Pending"),
                    "pythonCode": task.python_code,  # In old schema, code is only in Task, not TaskRun
                    "dependencies": task.dependencies or "",
                    "requirementsFile": task.requirements_file or "",
                    "systemDependencies": "",  # Old schema doesn't have system_dependencies
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
                "systemDependencies": getattr(latest_run, 'system_dependencies', None) or "",
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
                "systemDependencies": getattr(task, 'system_dependencies', None) or "",
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
async def get_task_logs(task_id: str, run_number: int | None = None, db: Session = Depends(get_db)):
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
                        log_count = db.execute(text("DELETE FROM task_logs WHERE run_id = :run_id"), {"run_id": run_id}).rowcount  # type: ignore
                        deleted_logs += log_count
            elif has_task_id:
                # Old schema: delete logs via task_id
                deleted_logs = db.execute(text("DELETE FROM task_logs WHERE task_id = :task_id"), {"task_id": task_id}).rowcount  # type: ignore
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


# PV File Manager APIs
@app.get("/api/v1/pv/files")
async def list_pv_files(path: str = "/mnt/results"):
    """
    List files and directories in the PV.
    Returns data in format compatible with SVAR Svelte File Manager.
    Uses persistent pod for fast execution.
    """
    # Validate path to prevent directory traversal
    # Allow /mnt (parent) and /mnt/results (PV mount point) and subdirectories
    if not (path == "/mnt" or path.startswith("/mnt/results")):
        raise HTTPException(status_code=400, detail="Path must be /mnt or within /mnt/results")
    
    try:
        # Use persistent pod for fast execution
        pod = get_persistent_pv_pod()
        
        # Escape path for shell command
        escaped_path = path.replace("'", "'\"'\"'")
        
        # Execute Python script in persistent pod
        python_script = f"""
import os
import json
import stat
from datetime import datetime

path = '{escaped_path}'

if not os.path.exists(path):
    print(json.dumps({{"error": f"Path does not exist: {{path}}"}}))
    exit(1)

if not os.path.isdir(path):
    print(json.dumps({{"error": f"Path is not a directory: {{path}}"}}))
    exit(1)

items = []
for item in sorted(os.listdir(path)):
    item_path = os.path.join(path, item)
    try:
        stat_info = os.stat(item_path)
        is_dir = os.path.isdir(item_path)
        
        # Format date
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        date_str = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        items.append({{
            "id": item_path,
            "name": item,
            "type": "folder" if is_dir else "file",
            "size": stat_info.st_size if not is_dir else 0,
            "date": date_str
        }})
    except Exception as e:
        # Skip items we can't access
        continue

print(json.dumps({{"items": items}}))
"""
        
        # Execute command - write script to temp file to avoid shell escaping issues
        import base64
        script_b64 = base64.b64encode(python_script.encode('utf-8')).decode('utf-8')
        command = f"echo {script_b64} | base64 -d > /tmp/script.py && python3 /tmp/script.py"
        output = pod.exec_command(command)
        
        # Parse JSON from output
        try:
            # Clean up the output - remove any leading/trailing whitespace
            output_lines = output.strip().split('\n')
            # Find the JSON line (should be the last line or the one with {})
            json_str = None
            for line in reversed(output_lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    json_str = line
                    break
            
            if not json_str:
                # Try to extract JSON from the entire output
                import re
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
            
            if not json_str:
                raise HTTPException(status_code=500, detail=f"No JSON found in output: {output[:200]}")
            
            # Try to parse as JSON first
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to parse as Python dict (handle single quotes)
                import ast
                try:
                    # Use ast.literal_eval to safely parse Python dict syntax
                    result = ast.literal_eval(json_str)
                except (ValueError, SyntaxError):
                    # Last resort: try to fix common issues
                    # Replace single quotes with double quotes (simple approach)
                    fixed_json = json_str.replace("'", '"')
                    result = json.loads(fixed_json)
            
            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])
            
            # Return in SVAR File Manager format
            return {"data": result.get("items", [])}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse output: {str(e)}. Output: {output[:500]}")
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error accessing PV: {str(e)}")


@app.get("/api/v1/pv/file")
async def read_pv_file(path: str):
    """
    Read file content from the PV.
    Returns file content as text or base64 for binary files.
    Uses persistent pod for fast execution.
    """
    # Validate path
    if not path.startswith("/mnt/results"):
        raise HTTPException(status_code=400, detail="Path must be within /mnt/results")
    
    try:
        # Use persistent pod for fast execution
        pod = get_persistent_pv_pod()
        
        # Escape path for shell command
        escaped_path = path.replace("'", "'\"'\"'")
        
        # Execute Python script in persistent pod
        python_script = f"""
import os
import json
import base64

path = '{escaped_path}'

if not os.path.exists(path):
    print(json.dumps({{"error": f"File does not exist: {{path}}"}}))
    exit(1)

if os.path.isdir(path):
    print(json.dumps({{"error": f"Path is a directory: {{path}}"}}))
    exit(1)

# Try to read as text first
try:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    print(json.dumps({{"content": content, "encoding": "text"}}))
except (UnicodeDecodeError, UnicodeError):
    # If text decoding fails, read as binary and encode as base64
    with open(path, "rb") as f:
        content_bytes = f.read()
        content_base64 = base64.b64encode(content_bytes).decode("utf-8")
    print(json.dumps({{"content": content_base64, "encoding": "base64"}}))
"""
        
        # Execute command - write script to temp file to avoid shell escaping issues
        import base64
        script_b64 = base64.b64encode(python_script.encode('utf-8')).decode('utf-8')
        command = f"echo {script_b64} | base64 -d > /tmp/script.py && python3 /tmp/script.py"
        output = pod.exec_command(command)
        
        # Parse JSON from output
        try:
            # Clean up the output
            output_lines = output.strip().split('\n')
            json_str = None
            for line in reversed(output_lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    json_str = line
                    break
            
            if not json_str:
                import re
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
            
            if not json_str:
                raise HTTPException(status_code=500, detail=f"No JSON found in output: {output[:200]}")
            
            # Try to parse as JSON first
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError:
                import ast
                try:
                    result = ast.literal_eval(json_str)
                except (ValueError, SyntaxError):
                    fixed_json = json_str.replace("'", '"')
                    result = json.loads(fixed_json)
            
            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])
            
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse output: {str(e)}. Output: {output[:500]}")
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@app.get("/api/v1/pv/preview")
async def preview_pv_file(path: str, width: int | None = None, height: int | None = None):
    """
    Preview file content from the PV, optimized for images.
    Returns file content as binary for images, or text for other files.
    Uses persistent pod for fast execution.
    """
    # Validate path
    if not (path == "/mnt" or path.startswith("/mnt/results")):
        raise HTTPException(status_code=400, detail="Path must be /mnt or within /mnt/results")
    
    # Check if file is an image
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico'}
    is_image = any(path.lower().endswith(ext) for ext in image_extensions)
    
    try:
        # Use persistent pod for fast execution
        pod = get_persistent_pv_pod()
        
        # Escape path for shell command
        escaped_path = path.replace("'", "'\"'\"'")
        
        if is_image:
            # For images, return binary content directly
            python_script = f"""
import os
import json
import base64

path = '{escaped_path}'

if not os.path.exists(path):
    print(json.dumps({{"error": f"File does not exist: {{path}}"}}))
    exit(1)

if os.path.isdir(path):
    print(json.dumps({{"error": f"Path is a directory: {{path}}"}}))
    exit(1)

# Read as binary and encode as base64
with open(path, "rb") as f:
    content_bytes = f.read()
    content_base64 = base64.b64encode(content_bytes).decode("utf-8")
print(json.dumps({{"content": content_base64, "encoding": "base64", "mime_type": "image"}}))
"""
        else:
            # For non-images, return text or base64
            python_script = f"""
import os
import json
import base64

path = '{escaped_path}'

if not os.path.exists(path):
    print(json.dumps({{"error": f"File does not exist: {{path}}"}}))
    exit(1)

if os.path.isdir(path):
    print(json.dumps({{"error": f"Path is a directory: {{path}}"}}))
    exit(1)

# Try to read as text first
try:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    print(json.dumps({{"content": content, "encoding": "text"}}))
except (UnicodeDecodeError, UnicodeError):
    # If text decoding fails, read as binary and encode as base64
    with open(path, "rb") as f:
        content_bytes = f.read()
        content_base64 = base64.b64encode(content_bytes).decode("utf-8")
    print(json.dumps({{"content": content_base64, "encoding": "base64"}}))
"""
        
        # Execute command - write script to temp file to avoid shell escaping issues
        import base64
        script_b64 = base64.b64encode(python_script.encode('utf-8')).decode('utf-8')
        command = f"echo {script_b64} | base64 -d > /tmp/preview_script.py && python3 /tmp/preview_script.py"
        output = pod.exec_command(command)
        
        # Parse JSON from output
        try:
            # Clean up the output
            output_lines = output.strip().split('\n')
            json_str = None
            for line in reversed(output_lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    json_str = line
                    break
            
            if not json_str:
                import re
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', output, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
            
            if not json_str:
                raise HTTPException(status_code=500, detail=f"No JSON found in output: {output[:200]}")
            
            # Try to parse as JSON first
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError:
                import ast
                try:
                    result = ast.literal_eval(json_str)
                except (ValueError, SyntaxError):
                    fixed_json = json_str.replace("'", '"')
                    result = json.loads(fixed_json)
            
            if "error" in result:
                raise HTTPException(status_code=404, detail=result["error"])
            
            # For images, return binary content with proper headers
            if is_image and result.get("encoding") == "base64":
                import base64
                image_bytes = base64.b64decode(result["content"])
                
                # Determine content type based on extension
                content_type = "image/png"  # default
                if path.lower().endswith('.jpg') or path.lower().endswith('.jpeg'):
                    content_type = "image/jpeg"
                elif path.lower().endswith('.gif'):
                    content_type = "image/gif"
                elif path.lower().endswith('.svg'):
                    content_type = "image/svg+xml"
                elif path.lower().endswith('.webp'):
                    content_type = "image/webp"
                elif path.lower().endswith('.bmp'):
                    content_type = "image/bmp"
                elif path.lower().endswith('.ico'):
                    content_type = "image/x-icon"
                
                from fastapi.responses import Response
                return Response(content=image_bytes, media_type=content_type)
            
            # For non-images, return JSON
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse output: {str(e)}. Output: {output[:500]}")
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@app.post("/api/v1/pv/copy")
async def copy_pv_file(source_path: str, destination_path: str):
    """
    Copy a file within the PV.
    Uses persistent pod for fast execution.
    """
    # Validate paths
    if not source_path.startswith("/mnt/results") or not destination_path.startswith("/mnt/results"):
        raise HTTPException(status_code=400, detail="Paths must be within /mnt/results")
    
    try:
        # Use persistent pod for fast execution
        pod = get_persistent_pv_pod()
        
        # Escape paths for shell command
        escaped_source = source_path.replace("'", "'\"'\"'")
        escaped_dest = destination_path.replace("'", "'\"'\"'")
        
        # Execute copy command and set permissions to be readable by all
        copy_command = f"cp '{escaped_source}' '{escaped_dest}' && chmod 644 '{escaped_dest}'"
        output = pod.exec_command(copy_command)
        
        # Check if copy was successful (cp doesn't output on success, but errors go to stderr)
        if output and "error" in output.lower():
            raise HTTPException(status_code=500, detail=f"Copy failed: {output}")
        
        return {"status": "success", "source": source_path, "destination": destination_path}
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error copying file: {str(e)}")


@app.post("/api/v1/pv/upload")
async def upload_pv_file(
    file: UploadFile = File(...),
    path: str = Form(...)  # Target directory path (SVAR recommended format)
):
    """
    Upload a file to the PV.
    Uses persistent pod for fast execution.
    Following SVAR's recommended API format.
    """
    # Use path parameter (SVAR recommended)
    dest_path = path
    
    # Validate destination path
    if not dest_path.startswith("/mnt/results"):
        # If target is a relative path, make it absolute
        if not dest_path.startswith("/"):
            dest_path = f"/mnt/results/{dest_path.lstrip('/')}"
        else:
            raise HTTPException(status_code=400, detail="Destination path must be within /mnt/results")
    
    try:
        # Use persistent pod for fast execution
        pod = get_persistent_pv_pod()
        
        # Determine final file path
        filename = file.filename or "uploaded_file"
        print(f"Upload request: filename={filename}, dest_path={dest_path}")
        
        # Ensure dest_path is a directory (ends with /) or handle it
        if dest_path.endswith("/"):
            final_path = f"{dest_path}{filename}"
        else:
            # Check if dest_path is a file or directory
            # For simplicity, assume it's a directory if it doesn't have an extension
            # or if it's a known directory path
            final_path = f"{dest_path}/{filename}"
        
        print(f"Final file path: {final_path}")
        
        # Escape path for shell command
        escaped_path = final_path.replace("'", "'\"'\"'")
        
        # Check if file already exists and handle duplicates
        check_command = f"test -f '{escaped_path}' && echo 'exists' || echo 'not_exists'"
        check_output = pod.exec_command(check_command).strip()
        
        if check_output == "exists":
            # File exists, add number suffix
            base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            extension = '.' + filename.rsplit('.', 1)[1] if '.' in filename else ''
            counter = 1
            while True:
                new_filename = f"{base_name}_{counter}{extension}"
                # Use dest_path (which may have been normalized) instead of destination_path
                dir_part = dest_path.rstrip('/') if not dest_path.endswith('/') else dest_path.rstrip('/')
                new_path = f"{dir_part}/{new_filename}"
                escaped_new_path = new_path.replace("'", "'\"'\"'")
                check_output = pod.exec_command(f"test -f '{escaped_new_path}' && echo 'exists' || echo 'not_exists'").strip()
                if check_output != "exists":
                    final_path = new_path
                    escaped_path = escaped_new_path
                    break
                counter += 1
        
        # Read file content
        file_content = await file.read()
        print(f"File size: {len(file_content)} bytes")
        
        # Encode file content as base64 for safe transfer through shell
        import base64
        file_content_b64 = base64.b64encode(file_content).decode('utf-8')
        print(f"Base64 encoded size: {len(file_content_b64)} characters")
        
        # Create directory if it doesn't exist
        dir_path = '/'.join(final_path.split('/')[:-1])
        escaped_dir = dir_path.replace("'", "'\"'\"'")
        pod.exec_command(f"mkdir -p '{escaped_dir}'")
        
        # Write file using base64 decode in the pod
        # Use a two-step approach: first write base64 to temp file, then decode it
        # This avoids shell command line length limits
        b64_temp_path = f"/tmp/upload_{uuid.uuid4().hex[:8]}.b64"
        escaped_b64_temp = b64_temp_path.replace("'", "'\"'\"'")
        
        # Step 1: Write base64 data to temp file in pod using heredoc
        # This is more reliable than embedding in Python script for large files
        write_b64_cmd = f"cat > '{escaped_b64_temp}' << 'EOFB64'\n{file_content_b64}\nEOFB64"
        print(f"Writing base64 data to temp file in pod...")
        write_output = pod.exec_command(write_b64_cmd)
        if write_output and "error" in write_output.lower():
            print(f"Warning writing base64 file: {write_output}")
        
        # Step 2: Decode base64 and write actual file
        decode_script = f"""
import base64
import os

b64_file = '{escaped_b64_temp}'
file_path = '{escaped_path}'

try:
    with open(b64_file, 'r') as f:
        file_content_b64 = f.read()
    
    file_content = base64.b64decode(file_content_b64)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    # Set permissions to be readable by all (644 = rw-r--r--)
    os.chmod(file_path, 0o644)
    
    # Clean up temp file
    os.remove(b64_file)
    print("success")
except Exception as e:
    print(f"error: {{str(e)}}")
    # Try to clean up temp file even on error
    try:
        os.remove(b64_file)
    except:
        pass
    import sys
    sys.exit(1)
"""
        script_b64 = base64.b64encode(decode_script.encode('utf-8')).decode('utf-8')
        upload_command = f"echo {script_b64} | base64 -d > /tmp/upload_script.py && python3 /tmp/upload_script.py"
        print(f"Executing upload command in pod...")
        output = pod.exec_command(upload_command)
        print(f"Upload command output: {output[:500]}")  # Log first 500 chars
        
        # Check for errors in output
        if "success" not in output:
            # Check if file was actually created despite the message
            verify_command = f"test -f '{escaped_path}' && echo 'file_exists' || echo 'file_not_exists'"
            verify_output = pod.exec_command(verify_command).strip()
            if verify_output != "file_exists":
                print(f"Upload script output: {output}")
                print(f"File path attempted: {final_path}")
                raise HTTPException(status_code=500, detail=f"Upload failed: {output}")
            else:
                # File exists, so upload succeeded despite message
                print(f"Upload succeeded (file exists), but script output: {output}")
        else:
            # Verify file was created
            verify_command = f"test -f '{escaped_path}' && echo 'file_exists' || echo 'file_not_exists'"
            verify_output = pod.exec_command(verify_command).strip()
            if verify_output != "file_exists":
                raise HTTPException(status_code=500, detail=f"Upload reported success but file not found at {final_path}")
        
        # Return in SVAR recommended format
        return {
            "name": filename,
            "path": final_path,
            "size": len(file_content)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


# ============================================================================
# Flow Management API Endpoints
# ============================================================================

@app.post("/api/v1/flows")
async def create_flow(request: FlowCreateRequest, db: Session = Depends(get_db)):
    """Create a new flow definition."""
    try:
        # Generate flow ID
        flow_id = f"flow-{uuid.uuid4().hex[:12]}"
        
        # Debug logging
        print(f"Creating flow: {request.name}")
        print(f"Number of steps received: {len(request.steps)}")
        print(f"Number of edges received: {len(request.edges)}")
        if request.steps:
            print(f"First step: {request.steps[0].model_dump()}")
        
        # Build definition from request
        definition = {
            "steps": [step.model_dump() for step in request.steps],
            "edges": [edge.model_dump() for edge in request.edges]
        }
        
        # Create flow record
        flow = Flow(
            id=flow_id,
            name=request.name,
            description=request.description,
            definition=definition,
            status="draft"
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)
        
        return {
            "id": flow_id,
            "name": flow.name,
            "description": flow.description,
            "steps": definition["steps"],
            "edges": definition["edges"],
            "status": flow.status,
            "createdAt": flow.created_at.isoformat(),
            "updatedAt": flow.updated_at.isoformat()
        }
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create flow: {str(e)}")
    finally:
        db.close()


@app.get("/api/v1/flows")
async def list_flows(db: Session = Depends(get_db)):
    """List all flows."""
    try:
        flows = db.query(Flow).order_by(Flow.updated_at.desc()).all()
        return {
            "flows": [
                {
                    "id": flow.id,
                    "name": flow.name,
                    "description": flow.description,
                    "status": flow.status,
                    "createdAt": flow.created_at.isoformat(),
                    "updatedAt": flow.updated_at.isoformat(),
                    "stepCount": len(flow.definition.get("steps", [])) if isinstance(flow.definition, dict) else 0
                }
                for flow in flows
            ]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list flows: {str(e)}")
    finally:
        db.close()


@app.get("/api/v1/flows/{flow_id}")
async def get_flow(flow_id: str, db: Session = Depends(get_db)):
    """Get flow definition."""
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        definition = flow.definition if isinstance(flow.definition, dict) else {}
        
        return {
            "id": flow.id,
            "name": flow.name,
            "description": flow.description,
            "steps": definition.get("steps", []),
            "edges": definition.get("edges", []),
            "status": flow.status,
            "createdAt": flow.created_at.isoformat(),
            "updatedAt": flow.updated_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get flow: {str(e)}")
    finally:
        db.close()


@app.put("/api/v1/flows/{flow_id}")
async def update_flow(flow_id: str, request: FlowUpdateRequest, db: Session = Depends(get_db)):
    """Update flow definition."""
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        # Update fields if provided
        if request.name is not None:
            flow.name = request.name
        if request.description is not None:
            flow.description = request.description
        
        # Update definition if steps or edges provided
        if request.steps is not None or request.edges is not None:
            # Debug logging
            print(f"Updating flow: {flow_id}")
            print(f"Number of steps received: {len(request.steps) if request.steps else 0}")
            print(f"Number of edges received: {len(request.edges) if request.edges else 0}")
            if request.steps:
                print(f"First step: {request.steps[0].model_dump()}")
            
            definition = flow.definition if isinstance(flow.definition, dict) else {}
            if request.steps is not None:
                definition["steps"] = [step.model_dump() for step in request.steps]
            if request.edges is not None:
                definition["edges"] = [edge.model_dump() for edge in request.edges]
            flow.definition = definition
        
        flow.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(flow)
        
        definition = flow.definition if isinstance(flow.definition, dict) else {}
        
        return {
            "id": flow.id,
            "name": flow.name,
            "description": flow.description,
            "steps": definition.get("steps", []),
            "edges": definition.get("edges", []),
            "status": flow.status,
            "createdAt": flow.created_at.isoformat(),
            "updatedAt": flow.updated_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update flow: {str(e)}")
    finally:
        db.close()


@app.delete("/api/v1/flows/{flow_id}")
async def delete_flow(flow_id: str, db: Session = Depends(get_db)):
    """Delete flow."""
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        db.delete(flow)
        db.commit()
        
        return {"message": f"Flow {flow_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete flow: {str(e)}")
    finally:
        db.close()


# ============================================================================
# Flow Template Preview API Endpoints
# ============================================================================

@app.post("/api/v1/flows/preview-template")
async def preview_flow_template(request: FlowCreateRequest):
    """Generate a preview Argo Workflow template from a flow definition without saving or running it."""
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # Build flow definition from request
        flow_definition = {
            "steps": [step.model_dump() for step in (request.steps or [])],
            "edges": [edge.model_dump() for edge in (request.edges or [])]
        }
        
        # Import the template generation function
        from app.workflow_hera_flow import generate_flow_workflow_template
        
        # Generate workflow template
        workflow_dict = generate_flow_workflow_template(
            flow_definition=flow_definition,
            namespace=namespace
        )
        
        # Convert to YAML format
        try:
            import yaml
            yaml_str = yaml.dump(workflow_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)
        except ImportError:
            # Fallback to JSON if PyYAML is not available
            import json
            yaml_str = json.dumps(workflow_dict, indent=2, default=str)
        
        return {
            "yaml": yaml_str
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate template: {str(e)}")


# ============================================================================
# Flow Execution API Endpoints
# ============================================================================

@app.post("/api/v1/flows/{flow_id}/run")
async def run_flow(flow_id: str, db: Session = Depends(get_db)):
    """Run entire flow."""
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # Load flow from database
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        # Check if flow already has a running workflow
        latest_run = db.query(FlowRun).filter(
            FlowRun.flow_id == flow_id
        ).order_by(FlowRun.run_number.desc()).first()
        
        if latest_run and latest_run.phase in ["Running", "Pending"]:
            raise HTTPException(
                status_code=400,
                detail=f"Flow {flow_id} already has a running workflow (run #{latest_run.run_number}). Please wait for it to complete or cancel it first."
            )
        
        # Get flow definition
        definition = flow.definition if isinstance(flow.definition, dict) else {}
        if not definition:
            raise HTTPException(
                status_code=400,
                detail="Flow definition is empty"
            )
        
        # Create and submit workflow
        workflow_id = create_flow_workflow_with_hera(
            flow_definition=definition,
            namespace=namespace
        )
        
        # Get next run number
        max_run = db.query(FlowRun).filter(FlowRun.flow_id == flow_id).order_by(FlowRun.run_number.desc()).first()
        next_run_number = (max_run.run_number + 1) if max_run else 1
        
        # Create FlowRun record
        flow_run = FlowRun(
            flow_id=flow_id,
            workflow_id=workflow_id,
            run_number=next_run_number,
            phase="Pending",
            started_at=datetime.utcnow()
        )
        db.add(flow_run)
        db.commit()
        db.refresh(flow_run)
        
        # Create FlowStepRun records for each step
        steps = definition.get("steps", [])
        for step in steps:
            step_id = step.get("id")
            if step_id:
                # Argo workflow node name is typically the step ID
                step_run = FlowStepRun(
                    flow_run_id=flow_run.id,
                    step_id=step_id,
                    workflow_node_id=step_id,
                    phase="Pending"
                )
                db.add(step_run)
        
        db.commit()
        
        return {
            "id": flow_run.id,
            "flowId": flow_id,
            "workflowId": workflow_id,
            "runNumber": next_run_number,
            "phase": "Pending",
            "message": f"Flow {flow_id} started successfully (run #{next_run_number})"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to run flow: {str(e)}")
    finally:
        db.close()


@app.post("/api/v1/flows/{flow_id}/steps/{step_id}/run")
async def run_flow_step(flow_id: str, step_id: str, db: Session = Depends(get_db)):
    """Run a single step from a flow (for testing)."""
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # Load flow from database
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        # Get flow definition
        definition = flow.definition if isinstance(flow.definition, dict) else {}
        steps = definition.get("steps", [])
        
        # Find the step
        step = next((s for s in steps if s.get("id") == step_id), None)
        if not step:
            raise HTTPException(status_code=404, detail=f"Step {step_id} not found in flow {flow_id}")
        
        # Create a single-step workflow for this step
        python_code = step.get("pythonCode", "")
        dependencies = step.get("dependencies")
        requirements_file = step.get("requirementsFile")
        
        # Create workflow using single-step function
        workflow_id = create_workflow_with_hera(
            python_code=python_code,
            dependencies=dependencies,
            requirements_file=requirements_file,
            namespace=namespace
        )
        
        return {
            "workflowId": workflow_id,
            "stepId": step_id,
            "message": f"Step {step_id} from flow {flow_id} started successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to run step: {str(e)}")
    finally:
        db.close()


@app.get("/api/v1/flows/{flow_id}/runs")
async def list_flow_runs(flow_id: str, db: Session = Depends(get_db)):
    """List all runs for a flow."""
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        runs = db.query(FlowRun).filter(
            FlowRun.flow_id == flow_id
        ).order_by(FlowRun.run_number.desc()).all()
        
        # Update phases for runs that are still pending or running
        try:
            custom_api = CustomObjectsApi()
            for run in runs:
                if run.phase in ["Pending", "Running"]:
                    try:
                        workflow = custom_api.get_namespaced_custom_object(
                            group="argoproj.io",
                            version="v1alpha1",
                            namespace=namespace,
                            plural="workflows",
                            name=run.workflow_id
                        )
                        status = workflow.get("status", {})
                        current_workflow_phase = determine_workflow_phase(status)
                        
                        if run.phase != current_workflow_phase:
                            run.phase = current_workflow_phase
                            if status.get("startedAt"):
                                run.started_at = datetime.fromisoformat(status.get("startedAt").replace("Z", "+00:00"))
                            if status.get("finishedAt"):
                                run.finished_at = datetime.fromisoformat(status.get("finishedAt").replace("Z", "+00:00"))
                    except Exception as e:
                        print(f"Could not fetch workflow status for {run.workflow_id}: {e}")
                        # Continue with database value if workflow query fails
            
            db.commit()
        except Exception as e:
            print(f"Error updating flow run statuses: {e}")
            # Continue with database values if update fails
        
        return {
            "runs": [
                {
                    "id": run.id,
                    "runNumber": run.run_number,
                    "workflowId": run.workflow_id,
                    "phase": run.phase,
                    "startedAt": run.started_at.isoformat() if run.started_at else None,
                    "finishedAt": run.finished_at.isoformat() if run.finished_at else None,
                    "createdAt": run.created_at.isoformat()
                }
                for run in runs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list flow runs: {str(e)}")
    finally:
        db.close()


@app.get("/api/v1/flows/{flow_id}/runs/{run_number}")
async def get_flow_run(flow_id: str, run_number: int, db: Session = Depends(get_db)):
    """Get flow run details."""
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        flow_run = db.query(FlowRun).filter(
            FlowRun.flow_id == flow_id,
            FlowRun.run_number == run_number
        ).first()
        
        if not flow_run:
            raise HTTPException(
                status_code=404,
                detail=f"Flow run {run_number} not found for flow {flow_id}"
            )
        
        # Update flow run phase from Argo Workflows
        try:
            from kubernetes.client import CustomObjectsApi
            custom_api = CustomObjectsApi()
            
            workflow = custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=flow_run.workflow_id
            )
            status = workflow.get("status", {})
            current_workflow_phase = determine_workflow_phase(status)
            
            # Update flow run phase if changed
            if flow_run.phase != current_workflow_phase:
                flow_run.phase = current_workflow_phase
                if status.get("startedAt"):
                    flow_run.started_at = datetime.fromisoformat(status.get("startedAt").replace("Z", "+00:00"))
                if status.get("finishedAt"):
                    flow_run.finished_at = datetime.fromisoformat(status.get("finishedAt").replace("Z", "+00:00"))
                db.commit()
            
            # Update step run phases from workflow nodes
            nodes = status.get("nodes", {})
            step_runs = db.query(FlowStepRun).filter(
                FlowStepRun.flow_run_id == flow_run.id
            ).all()
            
            # Debug: print available node IDs
            if nodes:
                print(f"Available workflow node IDs: {list(nodes.keys())[:10]}")
            
            for step_run in step_runs:
                # Find corresponding node in workflow
                # Try multiple matching strategies:
                # 1. Direct match with workflow_node_id
                # 2. Match with workflow name prefix: {workflow_id}.{step_id}
                # 3. Match by template name (node displayName or templateRef)
                node_id = step_run.workflow_node_id
                node_info = None
                
                # Strategy 1: Direct match
                if node_id in nodes:
                    node_info = nodes[node_id]
                else:
                    # Strategy 2: Try with workflow name prefix
                    prefixed_id = f"{flow_run.workflow_id}.{node_id}"
                    if prefixed_id in nodes:
                        node_info = nodes[prefixed_id]
                        # Update workflow_node_id for future lookups
                        step_run.workflow_node_id = prefixed_id
                    else:
                        # Strategy 3: Search by template name or displayName
                        for node_key, node_data in nodes.items():
                            template_name = node_data.get("templateName", "")
                            display_name = node_data.get("displayName", "")
                            # Check if this node corresponds to our step
                            if template_name == node_id or display_name == node_id or node_key.endswith(f".{node_id}"):
                                node_info = node_data
                                # Update workflow_node_id for future lookups
                                step_run.workflow_node_id = node_key
                                print(f"Matched step {node_id} to workflow node {node_key}")
                                break
                
                if node_info:
                    node_phase = node_info.get("phase", "Pending")
                    
                    # Map Argo phases to our phases
                    if node_phase in ["Succeeded"]:
                        mapped_phase = "Succeeded"
                    elif node_phase in ["Failed", "Error"]:
                        mapped_phase = "Failed"
                    elif node_phase == "Running":
                        mapped_phase = "Running"
                    else:
                        mapped_phase = "Pending"
                    
                    if step_run.phase != mapped_phase:
                        print(f"Updating step {step_run.step_id} phase from {step_run.phase} to {mapped_phase}")
                        step_run.phase = mapped_phase
                        if node_info.get("startedAt"):
                            step_run.started_at = datetime.fromisoformat(node_info.get("startedAt").replace("Z", "+00:00"))
                        if node_info.get("finishedAt"):
                            step_run.finished_at = datetime.fromisoformat(node_info.get("finishedAt").replace("Z", "+00:00"))
                else:
                    print(f"Warning: Could not find workflow node for step {step_run.step_id} (looking for {node_id})")
            
            db.commit()
        except Exception as e:
            print(f"Could not fetch workflow status for {flow_run.workflow_id}: {e}")
            # Continue with database values if workflow query fails
        
        # Refresh step runs after potential updates
        step_runs = db.query(FlowStepRun).filter(
            FlowStepRun.flow_run_id == flow_run.id
        ).all()
        
        return {
            "id": flow_run.id,
            "flowId": flow_id,
            "runNumber": flow_run.run_number,
            "workflowId": flow_run.workflow_id,
            "phase": flow_run.phase,
            "startedAt": flow_run.started_at.isoformat() if flow_run.started_at else None,
            "finishedAt": flow_run.finished_at.isoformat() if flow_run.finished_at else None,
            "createdAt": flow_run.created_at.isoformat(),
            "stepRuns": [
                {
                    "id": sr.id,
                    "stepId": sr.step_id,
                    "workflowNodeId": sr.workflow_node_id,
                    "phase": sr.phase,
                    "startedAt": sr.started_at.isoformat() if sr.started_at else None,
                    "finishedAt": sr.finished_at.isoformat() if sr.finished_at else None,
                }
                for sr in step_runs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get flow run: {str(e)}")
    finally:
        db.close()


@app.get("/api/v1/flows/{flow_id}/runs/{run_number}/logs")
async def get_flow_run_logs(flow_id: str, run_number: int, db: Session = Depends(get_db)):
    """Get logs for a flow run."""
    try:
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        flow_run = db.query(FlowRun).filter(
            FlowRun.flow_id == flow_id,
            FlowRun.run_number == run_number
        ).first()
        
        if not flow_run:
            raise HTTPException(
                status_code=404,
                detail=f"Flow run {run_number} not found for flow {flow_id}"
            )
        
        # Get step runs and their logs
        step_runs = db.query(FlowStepRun).filter(
            FlowStepRun.flow_run_id == flow_run.id
        ).all()
        
        logs = []
        for step_run in step_runs:
            step_logs = db.query(FlowStepLog).filter(
                FlowStepLog.step_run_id == step_run.id
            ).order_by(FlowStepLog.created_at).all()
            
            for log_entry in step_logs:
                logs.append({
                    "stepId": step_run.step_id,
                    "node": log_entry.node_id,
                    "pod": log_entry.pod_name,
                    "phase": log_entry.phase,
                    "logs": log_entry.logs
                })
        
        return {"logs": logs}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get flow run logs: {str(e)}")
    finally:
        db.close()


@app.get("/api/v1/flows/{flow_id}/runs/{run_number}/template")
async def get_flow_run_template(flow_id: str, run_number: int, db: Session = Depends(get_db)):
    """Get the Argo Workflow YAML template for a flow run."""
    try:
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        flow = db.query(Flow).filter(Flow.id == flow_id).first()
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow {flow_id} not found")
        
        flow_run = db.query(FlowRun).filter(
            FlowRun.flow_id == flow_id,
            FlowRun.run_number == run_number
        ).first()
        
        if not flow_run:
            raise HTTPException(
                status_code=404,
                detail=f"Flow run {run_number} not found for flow {flow_id}"
            )
        
        if not flow_run.workflow_id:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow ID not found for flow run {run_number}"
            )
        
        # Fetch workflow from Kubernetes
        try:
            from kubernetes.client import CustomObjectsApi
            custom_api = CustomObjectsApi()
            
            workflow = custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=namespace,
                plural="workflows",
                name=flow_run.workflow_id
            )
            
            # Convert to YAML format
            try:
                import yaml
                yaml_str = yaml.dump(workflow, default_flow_style=False, sort_keys=False, allow_unicode=True)
            except ImportError:
                # Fallback to JSON if PyYAML is not available
                import json
                yaml_str = json.dumps(workflow, indent=2, default=str)
            
            return {
                "workflowId": flow_run.workflow_id,
                "yaml": yaml_str
            }
        except Exception as k8s_error:
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch workflow from Kubernetes: {str(k8s_error)}"
            )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get flow run template: {str(e)}")
    finally:
        db.close()
