"""Task manager service managing background workers, persistence, and WebSocket broadcasting."""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from fastapi import WebSocket

from app.config import settings
from app.models.agent import TaskStatus, TaskDetail, TaskSummary
from app.services.workspace import workspace_manager
from app.agent.loop import AgentLoop

logger = logging.getLogger("web_agent.tasks")

class TaskRecord:
    """In-memory representation of a task."""
    def __init__(self, task_id: str, prompt: str, workspace_path: str):
        now = datetime.now(timezone.utc).isoformat()
        self.task_id = task_id
        self.prompt = prompt
        self.status = TaskStatus.QUEUED
        self.created_at = now
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.current_step: int = 0
        self.workspace = workspace_path
        self.final_response: Optional[str] = None
        self.error: Optional[str] = None
        self.events: List[Dict[str, Any]] = []
        
        # Runtime references
        self.asyncio_task: Optional[asyncio.Task] = None
        self.subscribers: Set[WebSocket] = set()

    def to_detail(self) -> TaskDetail:
        return TaskDetail(
            task_id=self.task_id,
            status=self.status,
            user_prompt=self.prompt,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            current_step=self.current_step,
            workspace=self.workspace,
            final_response=self.final_response,
            error=self.error,
            events=self.events
        )

    def to_summary(self) -> TaskSummary:
        return TaskSummary(
            task_id=self.task_id,
            status=self.status,
            user_prompt=self.prompt,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            current_step=self.current_step,
            error=self.error
        )

    def to_dict(self) -> Dict[str, Any]:
        return self.to_detail().model_dump()


class TaskManager:
    """Manages task lifecycle, background queue, persistence, and WebSocket broadcasting."""

    def __init__(self):
        self._tasks: Dict[str, TaskRecord] = {}
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
        self.storage_dir = settings.TASK_ROOT
        self._load_persisted_tasks()

    def _load_persisted_tasks(self) -> None:
        """Loads previous task metadata from disk on startup."""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            for file_path in self.storage_dir.glob("*.json"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    task_id = data.get("task_id")
                    if task_id:
                        record = TaskRecord(
                            task_id=task_id,
                            prompt=data.get("user_prompt", ""),
                            workspace_path=data.get("workspace", "")
                        )
                        record.status = TaskStatus(data.get("status", TaskStatus.FAILED))
                        record.created_at = data.get("created_at", record.created_at)
                        record.started_at = data.get("started_at")
                        record.finished_at = data.get("finished_at")
                        record.current_step = data.get("current_step", 0)
                        record.final_response = data.get("final_response")
                        record.error = data.get("error")
                        record.events = data.get("events", [])
                        
                        # If a task was running when server stopped, mark failed
                        if record.status in (TaskStatus.RUNNING, TaskStatus.QUEUED):
                            record.status = TaskStatus.FAILED
                            record.error = "Server restarted during execution"
                        
                        self._tasks[task_id] = record
                except Exception as e:
                    logger.warning(f"Could not load persisted task from {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error accessing task storage: {e}")

    def _save_task(self, record: TaskRecord) -> None:
        """Persists task record to disk."""
        try:
            target = self.storage_dir / f"{record.task_id}.json"
            with open(target, "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to persist task {record.task_id}: {e}")

    async def broadcast_event(self, task_id: str, event: Dict[str, Any]) -> None:
        """Sends an event to all connected WebSocket clients for this task."""
        record = self._tasks.get(task_id)
        if not record:
            return

        record.events.append(event)
        payload = json.dumps(event)
        
        dead_sockets = set()
        for ws in record.subscribers:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_sockets.add(ws)

        for ws in dead_sockets:
            record.subscribers.discard(ws)

        # Save after important events
        if event.get("type") in ("task_status", "task_completed", "task_cancelled", "error"):
            self._save_task(record)

    def create_task(self, prompt: str) -> TaskSummary:
        """Creates a new queued task and launches the background worker."""
        task_id = uuid.uuid4().hex[:8]
        workspace_dir = workspace_manager.get_workspace_dir(task_id)
        
        record = TaskRecord(
            task_id=task_id,
            prompt=prompt,
            workspace_path=str(workspace_dir)
        )
        self._tasks[task_id] = record
        self._save_task(record)

        # Launch background execution task
        bg_task = asyncio.create_task(self._task_worker(task_id))
        record.asyncio_task = bg_task

        return record.to_summary()

    async def _task_worker(self, task_id: str) -> None:
        """Worker loop enforcing concurrency limits and executing the agent loop."""
        record = self._tasks.get(task_id)
        if not record:
            return

        async with self._semaphore:
            if record.status == TaskStatus.CANCELLED:
                return

            record.status = TaskStatus.RUNNING
            record.started_at = datetime.now(timezone.utc).isoformat()
            self._save_task(record)

            await self.broadcast_event(task_id, {
                "type": "task_status",
                "task_id": task_id,
                "status": record.status.value,
                "started_at": record.started_at
            })

            async def handle_loop_event(event: Dict[str, Any]) -> None:
                if "step" in event:
                    record.current_step = event["step"]
                await self.broadcast_event(task_id, event)

            agent = AgentLoop(task_id=task_id, event_callback=handle_loop_event)

            try:
                result = await agent.run(prompt=record.prompt)
                record.status = TaskStatus.COMPLETED
                record.finished_at = datetime.now(timezone.utc).isoformat()
                record.final_response = result.get("final_response")
                
                await self.broadcast_event(task_id, {
                    "type": "task_completed",
                    "task_id": task_id,
                    "status": record.status.value,
                    "result": result,
                    "finished_at": record.finished_at
                })

            except asyncio.CancelledError:
                record.status = TaskStatus.CANCELLED
                record.finished_at = datetime.now(timezone.utc).isoformat()
                record.error = "Task cancelled by user"
                await self.broadcast_event(task_id, {
                    "type": "task_cancelled",
                    "task_id": task_id,
                    "status": record.status.value,
                    "finished_at": record.finished_at
                })

            except TimeoutError as e:
                record.status = TaskStatus.TIMEOUT
                record.finished_at = datetime.now(timezone.utc).isoformat()
                record.error = str(e)
                await self.broadcast_event(task_id, {
                    "type": "task_status",
                    "task_id": task_id,
                    "status": record.status.value,
                    "error": str(e),
                    "finished_at": record.finished_at
                })

            except Exception as e:
                record.status = TaskStatus.FAILED
                record.finished_at = datetime.now(timezone.utc).isoformat()
                record.error = str(e)
                await self.broadcast_event(task_id, {
                    "type": "task_status",
                    "task_id": task_id,
                    "status": record.status.value,
                    "error": str(e),
                    "finished_at": record.finished_at
                })

            finally:
                self._save_task(record)

    def cancel_task(self, task_id: str) -> bool:
        """Cancels a queued or running task."""
        record = self._tasks.get(task_id)
        if not record:
            return False

        if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT):
            return False

        record.status = TaskStatus.CANCELLED
        record.finished_at = datetime.now(timezone.utc).isoformat()
        record.error = "Task cancelled by user"
        self._save_task(record)

        if record.asyncio_task and not record.asyncio_task.done():
            record.asyncio_task.cancel()

        return True

    def get_task(self, task_id: str) -> Optional[TaskDetail]:
        record = self._tasks.get(task_id)
        return record.to_detail() if record else None

    def list_tasks(self) -> List[TaskSummary]:
        # Return sorted by created_at desc
        return [
            t.to_summary() for t in sorted(
                self._tasks.values(),
                key=lambda x: x.created_at,
                reverse=True
            )
        ]

    def register_subscriber(self, task_id: str, ws: WebSocket) -> Optional[TaskRecord]:
        record = self._tasks.get(task_id)
        if record:
            record.subscribers.add(ws)
            return record
        return None

    def unregister_subscriber(self, task_id: str, ws: WebSocket) -> None:
        record = self._tasks.get(task_id)
        if record:
            record.subscribers.discard(ws)

task_manager = TaskManager()
