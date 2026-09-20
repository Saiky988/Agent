"""File tools for inspecting and modifying files in task workspaces."""
import os
import aiofiles
from pathlib import Path
from typing import Dict, Any, List
from app.services.workspace import workspace_manager, WorkspaceError
from app.runtime.limits import truncate_output

async def list_files(task_id: str, path: str = ".") -> Dict[str, Any]:
    """Lists files and directories inside the workspace relative to path."""
    try:
        target_dir = workspace_manager.resolve_path(task_id, path)
        if not target_dir.exists():
            return {"success": False, "error": f"Path '{path}' does not exist"}
        if not target_dir.is_dir():
            return {"success": False, "error": f"Path '{path}' is a file, not a directory"}

        items = []
        for entry in sorted(os.scandir(target_dir), key=lambda e: (not e.is_dir(), e.name.lower())):
            try:
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size_bytes": stat.st_size if entry.is_file() else 0
                })
            except OSError:
                continue

        return {
            "success": True,
            "path": path,
            "items": items,
            "total": len(items)
        }
    except WorkspaceError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to list directory: {str(e)}"}


async def read_file(task_id: str, path: str) -> Dict[str, Any]:
    """Reads file content from workspace safely."""
    try:
        target_file = workspace_manager.resolve_path(task_id, path)
        if not target_file.exists():
            return {"success": False, "error": f"File '{path}' does not exist"}
        if target_file.is_dir():
            return {"success": False, "error": f"'{path}' is a directory, not a file"}

        async with aiofiles.open(target_file, mode="r", encoding="utf-8", errors="replace") as f:
            content = await f.read()

        truncated = truncate_output(content)
        return {
            "success": True,
            "path": path,
            "content": truncated,
            "size_bytes": len(content.encode("utf-8"))
        }
    except WorkspaceError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to read file: {str(e)}"}


async def write_file(task_id: str, path: str, content: str) -> Dict[str, Any]:
    """Writes content to a file in workspace, creating parent directories if necessary."""
    try:
        target_file = workspace_manager.resolve_path(task_id, path)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(target_file, mode="w", encoding="utf-8") as f:
            await f.write(content)

        size = len(content.encode("utf-8"))
        return {
            "success": True,
            "path": path,
            "bytes_written": size,
            "message": f"Successfully wrote {size} bytes to '{path}'"
        }
    except WorkspaceError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to write file: {str(e)}"}


async def edit_file(task_id: str, path: str, old_text: str, new_text: str) -> Dict[str, Any]:
    """Replaces old_text with new_text in the target file."""
    try:
        target_file = workspace_manager.resolve_path(task_id, path)
        if not target_file.exists():
            return {"success": False, "error": f"File '{path}' does not exist"}
        if target_file.is_dir():
            return {"success": False, "error": f"'{path}' is a directory"}

        async with aiofiles.open(target_file, mode="r", encoding="utf-8") as f:
            content = await f.read()

        if old_text not in content:
            return {
                "success": False,
                "error": f"Target string 'old_text' was not found in '{path}'. Please inspect the file using read_file first."
            }

        # Perform replacement
        updated_content = content.replace(old_text, new_text, 1)

        async with aiofiles.open(target_file, mode="w", encoding="utf-8") as f:
            await f.write(updated_content)

        return {
            "success": True,
            "path": path,
            "message": f"Successfully updated '{path}'"
        }
    except WorkspaceError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Failed to edit file: {str(e)}"}

