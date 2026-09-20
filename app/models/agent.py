"""Task and agent state schemas."""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class TaskCreateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Instruction or prompt for the agent")

class TaskSummary(BaseModel):
    task_id: str
    status: TaskStatus
    user_prompt: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_step: int = 0
    error: Optional[str] = None

class TaskDetail(TaskSummary):
    workspace: str
    final_response: Optional[str] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)

