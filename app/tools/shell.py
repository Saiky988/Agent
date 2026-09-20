"""Shell execution tool."""
from typing import Dict, Any
from app.services.workspace import workspace_manager, WorkspaceError
from app.runtime.executor import ProcessExecutor
from app.config import settings

async def run_shell(task_id: str, command: str) -> Dict[str, Any]:
    """
    Executes shell commands inside the task workspace.
    Input example: {"command": "ls -la"}
    """
    try:
        workspace = workspace_manager.get_workspace_dir(task_id)
        result = await ProcessExecutor.run(
            command=command,
            cwd=workspace,
            timeout=settings.DEFAULT_COMMAND_TIMEOUT_SECONDS,
            is_python=False
        )
        return result
    except WorkspaceError as e:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": str(e), "duration_ms": 0}
    except Exception as e:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": f"Error running shell: {str(e)}", "duration_ms": 0}

