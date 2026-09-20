"""Entrypoint to run the Web Agent application."""
import socket
import uvicorn
from app.config import settings

def get_bind_host(configured_host: str) -> str:
    """
    Returns a bindable host address. If an external IP is specified
    (e.g. 5.189.132.216 under NAT or container), binds to 0.0.0.0
    to ensure the socket accepts all incoming traffic on the configured port.
    """
    if configured_host in ("127.0.0.1", "localhost", "0.0.0.0"):
        return configured_host
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((configured_host, 0))
        s.close()
        return configured_host
    except OSError:
        return "0.0.0.0"

if __name__ == "__main__":
    bind_host = get_bind_host(settings.HOST)
    uvicorn.run(
        "app.main:app",
        host=bind_host,
        port=settings.PORT,
        reload=settings.APP_ENV == "development"
    )
