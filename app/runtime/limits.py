"""Execution limits and truncation helpers."""
from app.config import settings

def truncate_output(text: str, max_bytes: int = settings.MAX_TOOL_OUTPUT_BYTES) -> str:
    """Truncates output safely to prevent exceeding context window or byte limits."""
    if not text:
        return ""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + f"\n... [Output truncated: exceeded {max_bytes} bytes]"

