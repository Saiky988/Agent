"""API response models."""
from typing import Optional, List
from pydantic import BaseModel
from app.models.agent import TaskStatus, TaskSummary

class HealthResponse(BaseModel):
    status: str = "ok"

class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus

class TaskCancelResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str

class TaskListResponse(BaseModel):
    tasks: List[TaskSummary]

