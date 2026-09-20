"""Automated tests for Web Agent v1 core functionality."""
import asyncio
import os
import shutil
from pathlib import Path

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Setup environment before importing app
os.environ["APP_ENV"] = "testing"
os.environ["WORKSPACE_ROOT"] = "./data/test_workspaces"
os.environ["TASK_ROOT"] = "./data/test_tasks"

from app.services.workspace import workspace_manager, WorkspaceError
from app.tools.files import write_file, read_file, edit_file, list_files
from app.tools.python import run_python
from app.tools.shell import run_shell
from app.services.tasks import task_manager
from app.models.agent import TaskStatus

async def test_workspace_isolation():
    print("Testing workspace isolation...")
    task_id = "test_iso_1"
    ws = workspace_manager.get_workspace_dir(task_id)
    assert ws.exists(), "Workspace dir should exist"

    # Valid path
    p = workspace_manager.resolve_path(task_id, "hello.py")
    assert str(p).startswith(str(ws)), "Resolved path must be inside workspace"

    # Path traversal attack
    try:
        workspace_manager.resolve_path(task_id, "../../etc/passwd")
        assert False, "Should raise WorkspaceError on path traversal"
    except WorkspaceError:
        print("  [OK] Path traversal attempt successfully blocked!")

async def test_file_tools():
    print("Testing file tools...")
    task_id = "test_files_1"
    
    # Write file
    w_res = await write_file(task_id, "test.txt", "Hello World 123")
    assert w_res["success"], f"write_file failed: {w_res}"
    print("  [OK] write_file succeeded")

    # Read file
    r_res = await read_file(task_id, "test.txt")
    assert r_res["success"], f"read_file failed: {r_res}"
    assert "Hello World 123" in r_res["content"]
    print("  [OK] read_file succeeded")

    # Edit file
    e_res = await edit_file(task_id, "test.txt", "123", "456")
    assert e_res["success"], f"edit_file failed: {e_res}"
    r_res2 = await read_file(task_id, "test.txt")
    assert "Hello World 456" in r_res2["content"]
    print("  [OK] edit_file succeeded")

    # List files
    l_res = await list_files(task_id, ".")
    assert l_res["success"]
    assert any(item["name"] == "test.txt" for item in l_res["items"])
    print("  [OK] list_files succeeded")

async def test_execution_tools():
    print("Testing execution tools...")
    task_id = "test_exec_1"
    
    # Write python script
    await write_file(task_id, "calc.py", "import sys\nprint('Computed:', 21 * 2)")
    py_res = await run_python(task_id, "calc.py")
    assert py_res["success"], f"run_python failed: {py_res}"
    assert "Computed: 42" in py_res["stdout"]
    print("  [OK] run_python executed script and captured stdout successfully")

    # Shell execution
    sh_res = await run_shell(task_id, "echo SHELL_OK")
    assert sh_res["success"], f"run_shell failed: {sh_res}"
    assert "SHELL_OK" in sh_res["stdout"]
    print("  [OK] run_shell executed command successfully")

async def test_task_manager():
    print("Testing task manager and background execution...")
    task = task_manager.create_task("Test task")
    assert task.status == TaskStatus.QUEUED
    assert task.task_id
    print(f"  [OK] Task {task.task_id} created in queued state")

    # Get task detail
    detail = task_manager.get_task(task.task_id)
    assert detail is not None
    print("  [OK] Task retrieval succeeded")

    # Cancel task
    cancelled = task_manager.cancel_task(task.task_id)
    assert cancelled
    updated = task_manager.get_task(task.task_id)
    assert updated.status == TaskStatus.CANCELLED
    print("  [OK] Task cancellation succeeded")

async def main():
    try:
        await test_workspace_isolation()
        await test_file_tools()
        await test_execution_tools()
        await test_task_manager()
        print("\nAll core automated unit tests PASSED successfully! [SUCCESS]")
    finally:
        # Cleanup test directories
        for p in ["./data/test_workspaces", "./data/test_tasks"]:
            if Path(p).exists():
                shutil.rmtree(p, ignore_errors=True)

if __name__ == "__main__":
    asyncio.run(main())
