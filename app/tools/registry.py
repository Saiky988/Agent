"""Tool registry and dispatcher for AI function calling."""
from typing import Dict, Any, Callable, Awaitable
from google.genai import types

from app.tools.files import list_files, read_file, write_file, edit_file
from app.tools.python import run_python
from app.tools.shell import run_shell

TOOL_DEFINITIONS = [
    {
        "name": "list_files",
        "description": "List files and directories inside the workspace relative to path.",
        "parameters": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative directory path to list. Defaults to '.' (workspace root)."
                )
            },
            required=[]
        ),
        "handler": list_files
    },
    {
        "name": "read_file",
        "description": "Read content of a file in the workspace.",
        "parameters": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path of file to read."
                )
            },
            required=["path"]
        ),
        "handler": read_file
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the workspace. Creates parent directories if needed.",
        "parameters": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path of file to write."
                ),
                "content": types.Schema(
                    type=types.Type.STRING,
                    description="Full content to write into file."
                )
            },
            required=["path", "content"]
        ),
        "handler": write_file
    },
    {
        "name": "edit_file",
        "description": "Replace an exact block of old_text with new_text in an existing workspace file.",
        "parameters": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path of file to edit."
                ),
                "old_text": types.Schema(
                    type=types.Type.STRING,
                    description="Exact text snippet to replace."
                ),
                "new_text": types.Schema(
                    type=types.Type.STRING,
                    description="New replacement text."
                )
            },
            required=["path", "old_text", "new_text"]
        ),
        "handler": edit_file
    },
    {
        "name": "run_python",
        "description": "Execute a Python script or command inside the task workspace as a subprocess.",
        "parameters": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "command": types.Schema(
                    type=types.Type.STRING,
                    description="Python command to execute, e.g. 'main.py' or 'python script.py --arg'."
                )
            },
            required=["command"]
        ),
        "handler": run_python
    },
    {
        "name": "run_shell",
        "description": "Execute a shell command inside the task workspace as a subprocess.",
        "parameters": types.Schema(
            type=types.Type.OBJECT,
            properties={
                "command": types.Schema(
                    type=types.Type.STRING,
                    description="Shell command to execute, e.g. 'cat output.txt' or 'npm test'."
                )
            },
            required=["command"]
        ),
        "handler": run_shell
    }
]

class ToolRegistry:
    """Manages tool execution and schema generation."""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {
            t["name"]: t for t in TOOL_DEFINITIONS
        }

    def get_gemini_tools(self) -> types.Tool:
        """Returns types.Tool object containing function declarations for Gemini."""
        declarations = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"]
            )
            for t in self._tools.values()
        ]
        return types.Tool(function_declarations=declarations)

    async def execute_tool(self, task_id: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches tool execution safely with error handling."""
        if tool_name not in self._tools:
            return {
                "success": False,
                "error": f"Unknown tool '{tool_name}'. Available tools: {list(self._tools.keys())}"
            }
        
        handler = self._tools[tool_name]["handler"]
        try:
            result = await handler(task_id=task_id, **arguments)
            return result
        except TypeError as e:
            return {
                "success": False,
                "error": f"Invalid arguments for tool '{tool_name}': {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error running tool '{tool_name}': {str(e)}"
            }

tool_registry = ToolRegistry()

