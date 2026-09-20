"""Subprocess executor with timeouts, limits, and safe cancellation."""
import asyncio
import os
import subprocess
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
    # Preserve essential Windows system environment variables
    if sys.platform == "win32":
        for essential in ("SystemRoot", "SystemDrive", "PATH", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
            if essential in os.environ and essential not in clean:
                clean[essential] = os.environ[essential]
    clean["PYTHONUNBUFFERED"] = "1"
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    return clean

class ProcessExecutor:
    """Executes commands safely in a background subprocess."""

    @staticmethod
    def _run_sync(cmd_str: str, cwd: Path, env: Dict[str, str], timeout: float):
        proc = subprocess.Popen(
            cmd_str,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            shell=True
        )
        try:
            stdout_data, stderr_data = proc.communicate(timeout=timeout)
            return proc.returncode, stdout_data, stderr_data, False
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.communicate(timeout=2)
            except Exception:
                pass
            return -1, b"", b"Execution timed out", True

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
            parts = command.strip().split()
            if parts and parts[0] in ("python", "python3"):
                cmd_str = f'"{sys.executable}" ' + " ".join(parts[1:])
            elif parts and parts[0] == sys.executable:
                cmd_str = command
            else:
                cmd_str = f'"{sys.executable}" {command}'

        try:
            returncode, stdout_bytes, stderr_bytes, is_timeout = await asyncio.to_thread(
                ProcessExecutor._run_sync,
                cmd_str,
                cwd,
                env,
                float(timeout)
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if is_timeout:
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Execution timed out after {timeout} seconds.",
                    "duration_ms": duration_ms
                }

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            
            return {
                "success": returncode == 0,
                "exit_code": returncode,
                "stdout": truncate_output(stdout),
                "stderr": truncate_output(stderr),
                "duration_ms": duration_ms
            }

        except asyncio.CancelledError:
            raise
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Failed to execute command: {type(e).__name__}: {str(e)}",
                "duration_ms": int((time.time() - start_time) * 1000)
            }
