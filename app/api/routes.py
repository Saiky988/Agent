"""REST and WebSocket routes."""
import json
import logging
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from app.models.agent import TaskCreateRequest, TaskDetail
from app.models.response import (
    HealthResponse,
    TaskCreateResponse,
    TaskCancelResponse,
    TaskListResponse
)
from app.services.tasks import task_manager

logger = logging.getLogger("web_agent.api")
router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint for reverse proxy, systemd, and monitoring."""
    return HealthResponse(status="ok")

@router.post("/api/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
async def create_task(req: TaskCreateRequest):
    """Creates a new agent task asynchronously."""
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    summary = task_manager.create_task(prompt)
    return TaskCreateResponse(task_id=summary.task_id, status=summary.status)

@router.get("/api/tasks", response_model=TaskListResponse, tags=["Tasks"])
async def list_tasks():
    """Returns list of tasks in memory/storage."""
    tasks = task_manager.list_tasks()
    return TaskListResponse(tasks=tasks)

@router.get("/api/tasks/{task_id}", response_model=TaskDetail, tags=["Tasks"])
async def get_task(task_id: str):
    """Retrieves current state and full event history for a task."""
    detail = task_manager.get_task(task_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail

@router.post("/api/tasks/{task_id}/cancel", response_model=TaskCancelResponse, tags=["Tasks"])
async def cancel_task(task_id: str):
    """Requests immediate cancellation of a running or queued task."""
    detail = task_manager.get_task(task_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Task not found")
    
    success = task_manager.cancel_task(task_id)
    updated = task_manager.get_task(task_id)
    
    return TaskCancelResponse(
        task_id=task_id,
        status=updated.status if updated else detail.status,
        message="Task cancelled successfully" if success else f"Task is already {detail.status.value}"
    )

@router.websocket("/ws/tasks/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task event streaming.
    Supports client disconnect/reconnect and sends current state on initial connect.
    """
    await websocket.accept()
    
    task = task_manager.get_task(task_id)
    if not task:
        await websocket.send_text(json.dumps({
            "type": "error",
            "error": f"Task '{task_id}' not found"
        }))
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Register as subscriber
    record = task_manager.register_subscriber(task_id, websocket)

    # Send initial recovery payload with existing task state and past events
    await websocket.send_text(json.dumps({
        "type": "task_sync",
        "task_id": task.task_id,
        "status": task.status.value,
        "prompt": task.user_prompt,
        "current_step": task.current_step,
        "events": task.events,
        "final_response": task.final_response,
        "error": task.error
    }))

    try:
        while True:
            data = await websocket.receive_text()
            # Parse client messages if any (e.g. ping or cancel)
            try:
                msg = json.loads(data)
                if msg.get("action") == "cancel":
                    task_manager.cancel_task(task_id)
                elif msg.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for task {task_id}")
    finally:
        task_manager.unregister_subscriber(task_id, websocket)

