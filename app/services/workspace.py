"""Workspace isolation service for tasks."""
import os
from pathlib import Path
from app.config import settings

class WorkspaceError(Exception):
    """Raised when an operation violates workspace security boundaries."""
    pass

class WorkspaceManager:
    """Manages isolated filesystem workspaces per task."""

    def __init__(self, root_dir: Path = settings.WORKSPACE_ROOT):
        self.root_dir = root_dir.resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def get_workspace_dir(self, task_id: str) -> Path:
        """Returns the absolute directory path for a task's workspace."""
        safe_task_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_"))
        if not safe_task_id:
            raise WorkspaceError("Invalid task_id")
        workspace = (self.root_dir / safe_task_id).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def resolve_path(self, task_id: str, relative_path: str) -> Path:
        """
        Resolves a relative file path safely within the task's workspace.
        Raises WorkspaceError on path traversal attempts or attempts to escape workspace.
        """
        workspace = self.get_workspace_dir(task_id)
        
        # Clean and strip leading slashes/backslashes to ensure path is relative
        clean_path = str(relative_path or "").strip()
        if not clean_path:
            clean_path = "."
        
        # Prevent absolute paths or UNC paths from overriding root
        if os.path.isabs(clean_path) or clean_path.startswith("/") or clean_path.startswith("\\"):
            clean_path = clean_path.lstrip("/\\")

        target = (workspace / clean_path).resolve()

        # Ensure target is strictly inside workspace
        try:
            target.relative_to(workspace)
        except ValueError:
            raise WorkspaceError(
                f"Path traversal detected: '{relative_path}' attempts to access files outside workspace"
            )

        return target

workspace_manager = WorkspaceManager()

