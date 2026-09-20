"""FastAPI application factory and lifecycle."""
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("web_agent")

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_directories()
    logger.info(f"Web Agent v1 started. Env: {settings.APP_ENV}, Model: {settings.GEMINI_MODEL}")
    yield
    logger.info("Web Agent v1 shutting down...")

app = FastAPI(
    title="Web Agent v1",
    description="Autonomous coding web agent with FastAPI, WebSockets, and Gemini API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API and WS routes
app.include_router(router)

# Mount frontend static assets
frontend_dir = settings.FRONTEND_DIR
if frontend_dir.exists():
    # Route root path to index.html
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(frontend_dir / "index.html")

    # Mount remaining static files (/style.css, /script.js, /assets)
    app.mount("/", StaticFiles(directory=str(frontend_dir)), name="frontend")

