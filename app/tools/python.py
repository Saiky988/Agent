"""Python execution tool."""
from typing import Dict, Any
from app.services.workspace import workspace_manager, WorkspaceError
from app.runtime.executor import ProcessExecutor
from app.config import settings

async def run_python(task_id: str, command: str) -> Dict[str, Any]:
    """
    Executes Python scripts/commands inside the task workspace.
    Input example: {"command": "python main.py"} or {"command": "main.py"}
    """
    try:
        workspace = workspace_manager.get_workspace_dir(task_id)
        result = await ProcessExecutor.run(
            command=command,
            cwd=workspace,
            timeout=settings.DEFAULT_COMMAND_TIMEOUT_SECONDS,
            is_python=True
        )
        return result
    except WorkspaceError as e:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": str(e), "duration_ms": 0}
    except Exception as e:
        return {"success": False, "exit_code": -1, "stdout": "", "stderr": f"Error running Python: {str(e)}", "duration_ms": 0}

