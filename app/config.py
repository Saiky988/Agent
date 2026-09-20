import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Gemini
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Agent execution limits
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "30"))
    MAX_RUNTIME_SECONDS: int = int(os.getenv("MAX_RUNTIME_SECONDS", "600"))
    MAX_TOOL_OUTPUT_BYTES: int = int(os.getenv("MAX_TOOL_OUTPUT_BYTES", "100000"))
    DEFAULT_COMMAND_TIMEOUT_SECONDS: int = int(os.getenv("DEFAULT_COMMAND_TIMEOUT_SECONDS", "60"))

    # Storage paths
    WORKSPACE_ROOT: Path = Path(os.getenv("WORKSPACE_ROOT", str(BASE_DIR / "data" / "workspaces"))).resolve()
    TASK_ROOT: Path = Path(os.getenv("TASK_ROOT", str(BASE_DIR / "data" / "tasks"))).resolve()
    FRONTEND_DIR: Path = (BASE_DIR / "frontend").resolve()

    def ensure_directories(self) -> None:
        self.WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        self.TASK_ROOT.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()

