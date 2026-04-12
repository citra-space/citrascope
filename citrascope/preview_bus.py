"""Thread-safe single-slot bus for pushing preview images to the web UI.

Any backend component can call ``push(data_url, source)`` and the image
will be broadcast to all connected WebSocket clients within ~1 second.
Only the latest frame is kept — a new push overwrites any unpopped frame.
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path


class PreviewBus:
    """Single-slot preview image bus.

    Thread-safe: producers call :meth:`push` from any thread; the web
    server's broadcast loop calls :meth:`pop` from the asyncio event loop
    thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: tuple[str, str] | None = None

    def push(self, data_url: str, source: str = "") -> None:
        """Store a preview frame, overwriting any previous unpopped frame."""
        with self._lock:
            self._frame = (data_url, source)

    def pop(self) -> tuple[str, str] | None:
        """Return and clear the current frame, or None if empty."""
        with self._lock:
            frame = self._frame
            self._frame = None
            return frame

    def clear(self) -> None:
        """Discard the current frame without returning it."""
        with self._lock:
            self._frame = None

    def push_file(self, path: str | Path, source: str = "") -> None:
        """Read a JPEG/PNG file from disk and push it as a data URL."""
        p = Path(path)
        if not p.exists():
            return
        suffix = p.suffix.lower()
        mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
        raw = p.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        self.push(f"data:{mime};base64,{b64}", source)
