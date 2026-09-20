"""Subprocess executor with timeouts, limits, and safe cancellation."""
import asyncio
import os
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import settings
from app.runtime.limits import truncate_output

# Environment keys that should NOT be passed into user workspaces
SENSITIVE_ENV_VARS = {
    "GEMINI_API_KEY",
    "SSH_AUTH_SOCK",
    "SSH_AGENT_PID",
    "SECRET_KEY",
    "DATABASE_URL",
}

def get_clean_env() -> Dict[str, str]:
    """Returns a copy of os.environ with sensitive secrets removed."""
    clean = {}
    for k, v in os.environ.items():
        if k not in SENSITIVE_ENV_VARS and not k.startswith("SSH_") and not "KEY" in k and not "SECRET" in k:
            clean[k] = v
    clean["PYTHONUNBUFFERED"] = "1"
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    return clean

class ProcessExecutor:
    """Executes commands safely in a background subprocess."""

    @staticmethod
    async def run(
        command: str,
        cwd: Path,
        timeout: int = settings.DEFAULT_COMMAND_TIMEOUT_SECONDS,
        is_python: bool = False,
        env_override: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        
        env = get_clean_env()
        if env_override:
            env.update(env_override)

        # Build command if python
        cmd_str = command
        if is_python:
            # If the user command already starts with python / python3, run it; otherwise prefix
            parts = command.strip().split()
            if parts and parts[0] in ("python", "python3", sys.executable):
                cmd_str = command
            else:
                cmd_str = f"{sys.executable} {command}"

        # Setup process group on Unix for clean tree termination
        is_unix = sys.platform != "win32"
        preexec = os.setsid if is_unix else None

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd_str,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                preexec_fn=preexec
            )
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Failed to spawn process: {str(e)}",
                "duration_ms": int((time.time() - start_time) * 1000)
            }

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout)
            )
            duration_ms = int((time.time() - start_time) * 1000)
            stdout = stdout_data.decode("utf-8", errors="replace")
            stderr = stderr_data.decode("utf-8", errors="replace")
            
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": truncate_output(stdout),
                "stderr": truncate_output(stderr),
                "duration_ms": duration_ms
            }

        except asyncio.TimeoutError:
            # Kill process tree
            try:
                if is_unix and proc.pid:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass
            
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds.",
                "duration_ms": duration_ms
            }

        except asyncio.CancelledError:
            # Task cancelled by user
            try:
                if is_unix and proc.pid:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                pass
            raise

