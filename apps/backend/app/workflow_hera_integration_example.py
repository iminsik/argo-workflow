"""
Example: How to integrate Hera SDK into the existing start_task endpoint

This shows a minimal change to replace the complex workflow creation
with the Hera SDK implementation.
"""

from fastapi import FastAPI, HTTPException
from app.workflow_hera_poc import create_workflow_with_hera
from app.database import get_db, Task, TaskRun
from datetime import datetime
import uuid
import os


# This is how the start_task endpoint would look with Hera SDK
@app.post("/api/v1/tasks/submit")
async def start_task_with_hera(request: TaskSubmitRequest = TaskSubmitRequest()):
    """
    Simplified start_task endpoint using Hera SDK.
    
    This replaces ~270 lines of complex YAML template manipulation
    with a clean function call.
    """
    try:
        # Validation (unchanged from current implementation)
        if request.dependencies:
            if len(request.dependencies) > 10000:
                raise HTTPException(
                    status_code=400,
                    detail="Dependencies string is too long (max 10000 characters)"
                )
            dangerous_patterns = [';', '&&', '||', '`', '$(']
            for pattern in dangerous_patterns:
                if pattern in request.dependencies:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid character in dependencies: {pattern}"
                    )
        
        if request.requirementsFile:
            if len(request.requirementsFile) > 50000:
                raise HTTPException(
                    status_code=400,
                    detail="Requirements file is too long (max 50000 characters)"
                )
        
        namespace = os.getenv("ARGO_NAMESPACE", "argo")
        
        # ============================================================
        # WORKFLOW CREATION - REPLACES ~270 LINES WITH ONE CALL!
        # ============================================================
        workflow_id = create_workflow_with_hera(
            python_code=request.pythonCode,
            dependencies=request.dependencies,
            requirements_file=request.requirementsFile,
            namespace=namespace
        )
        # ============================================================
        
        # Database operations (unchanged from current implementation)
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
                
                # Get next run number
                from sqlalchemy import inspect as sql_inspect
                from app.database import engine
                inspector = sql_inspect(engine)
                task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
                has_python_code = 'python_code' in task_runs_columns
                
                if has_python_code:
                    max_run = db.query(TaskRun).filter(
                        TaskRun.task_id == request.taskId
                    ).order_by(TaskRun.run_number.desc()).first()
                    next_run_number = (max_run.run_number + 1) if max_run else 1
                else:
                    from sqlalchemy import text
                    result = db.execute(
                        text("SELECT run_number FROM task_runs WHERE task_id = :task_id ORDER BY run_number DESC LIMIT 1"),
                        {"task_id": request.taskId}
                    ).fetchone()
                    next_run_number = (getattr(result, 'run_number', result[0]) + 1) if result else 1
                
                task_id = request.taskId
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
                db.commit()
            
            # Create TaskRun record
            from sqlalchemy import inspect as sql_inspect, text
            from app.database import engine
            inspector = sql_inspect(engine)
            task_runs_columns = [col['name'] for col in inspector.get_columns('task_runs')]
            has_python_code = 'python_code' in task_runs_columns
            
            if has_python_code:
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
                # Old schema handling (same as current implementation)
                # ... existing code ...
                pass
            
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
            return {"id": workflow_id, "workflowId": workflow_id}
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMPARISON: Lines of Code
# ============================================================================
#
# Current start_task() endpoint:
#   - Workflow creation logic: ~270 lines (lines 876-1091)
#   - Database operations: ~170 lines (lines 1095-1257)
#   - Total: ~440 lines
#
# With Hera SDK:
#   - Workflow creation logic: ~1 function call (delegated to create_workflow_with_hera)
#   - Database operations: ~170 lines (unchanged)
#   - Total: ~170 lines + helper function (~80 lines) = ~250 lines
#
# Reduction: ~190 lines (43% reduction in endpoint, 70% reduction in workflow logic)
# ============================================================================

