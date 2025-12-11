"""FastAPI web application for CitraScope monitoring and configuration."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from citrascope.logging import CITRASCOPE_LOGGER


class SystemStatus(BaseModel):
    """Current system status."""

    telescope_connected: bool = False
    camera_connected: bool = False
    current_task: Optional[str] = None
    tasks_pending: int = 0
    hardware_adapter: str = "unknown"
    telescope_ra: Optional[float] = None
    telescope_dec: Optional[float] = None
    ground_station_id: Optional[str] = None
    ground_station_name: Optional[str] = None
    ground_station_url: Optional[str] = None
    last_update: str = ""


class HardwareConfig(BaseModel):
    """Hardware configuration settings."""

    adapter: str
    indi_server_url: Optional[str] = None
    indi_server_port: Optional[int] = None
    indi_telescope_name: Optional[str] = None
    indi_camera_name: Optional[str] = None
    nina_url_prefix: Optional[str] = None


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        CITRASCOPE_LOGGER.info(f"WebSocket client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        CITRASCOPE_LOGGER.info(f"WebSocket client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                CITRASCOPE_LOGGER.warning(f"Failed to send to WebSocket client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast_text(self, message: str):
        """Broadcast text message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                CITRASCOPE_LOGGER.warning(f"Failed to send to WebSocket client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


class CitraScopeWebApp:
    """Web application for CitraScope."""

    def __init__(self, daemon=None, web_log_handler=None):
        self.app = FastAPI(title="CitraScope", description="Telescope Control and Monitoring")
        self.daemon = daemon
        self.connection_manager = ConnectionManager()
        self.status = SystemStatus()
        self.web_log_handler = web_log_handler

        # Configure CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Mount static files
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # Register routes
        self._setup_routes()

    def set_daemon(self, daemon):
        """Set the daemon instance after initialization."""
        self.daemon = daemon

    def _setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """Serve the main dashboard page."""
            template_path = Path(__file__).parent / "templates" / "dashboard.html"
            if template_path.exists():
                return template_path.read_text()
            else:
                return HTMLResponse(
                    content="<h1>CitraScope Dashboard</h1><p>Template file not found</p>", status_code=500
                )

        @self.app.get("/api/status")
        async def get_status():
            """Get current system status."""
            if self.daemon:
                self._update_status_from_daemon()
            return self.status

        @self.app.get("/api/config")
        async def get_config():
            """Get current configuration."""
            if not self.daemon or not self.daemon.settings:
                return JSONResponse({"error": "Configuration not available"}, status_code=503)

            settings = self.daemon.settings
            return {
                "hardware_adapter": settings.hardware_adapter,
                "telescope_id": settings.telescope_id,
                "host": settings.host,
                "log_level": settings.log_level,
                "keep_images": settings.keep_images,
                "bypass_autofocus": settings.bypass_autofocus,
                "indi_server_url": settings.indi_server_url,
                "indi_server_port": settings.indi_server_port,
                "indi_telescope_name": settings.indi_telescope_name,
                "indi_camera_name": settings.indi_camera_name,
                "nina_url_prefix": settings.nina_url_prefix,
            }

        @self.app.post("/api/config")
        async def update_config(config: Dict[str, Any]):
            """Update configuration (requires restart to take effect)."""
            # This would typically update environment variables or config file
            return {"status": "success", "message": "Configuration updated. Restart required to take effect."}

        @self.app.get("/api/tasks")
        async def get_tasks():
            """Get current task queue."""
            if not self.daemon or not hasattr(self.daemon, "task_manager") or self.daemon.task_manager is None:
                return []

            task_manager = self.daemon.task_manager
            tasks = []

            with task_manager.heap_lock:
                for start_time, stop_time, task_id, task in task_manager.task_heap:
                    tasks.append(
                        {
                            "id": task_id,
                            "start_time": datetime.fromtimestamp(start_time).isoformat(),
                            "stop_time": datetime.fromtimestamp(stop_time).isoformat() if stop_time else None,
                            "status": task.status,
                            "target": getattr(task, "target", "unknown"),
                        }
                    )

            return tasks

        @self.app.get("/api/logs")
        async def get_logs(limit: int = 100):
            """Get recent log entries."""
            if self.web_log_handler:
                logs = self.web_log_handler.get_recent_logs(limit)
                return {"logs": logs}
            return {"logs": []}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await self.connection_manager.connect(websocket)
            try:
                # Send initial status
                if self.daemon:
                    self._update_status_from_daemon()
                await websocket.send_json({"type": "status", "data": self.status.dict()})

                # Keep connection alive and listen for client messages
                while True:
                    data = await websocket.receive_text()
                    # Handle client requests if needed
                    await websocket.send_json({"type": "pong", "data": data})

            except WebSocketDisconnect:
                self.connection_manager.disconnect(websocket)
            except Exception as e:
                CITRASCOPE_LOGGER.error(f"WebSocket error: {e}")
                self.connection_manager.disconnect(websocket)

    def _update_status_from_daemon(self):
        """Update status from daemon state."""
        if not self.daemon:
            return

        try:
            self.status.hardware_adapter = self.daemon.settings.hardware_adapter

            if hasattr(self.daemon, "hardware_adapter") and self.daemon.hardware_adapter:
                # Try to get telescope position
                try:
                    ra, dec = self.daemon.hardware_adapter.get_telescope_direction()
                    self.status.telescope_ra = ra
                    self.status.telescope_dec = dec
                    self.status.telescope_connected = True
                except Exception:
                    self.status.telescope_connected = False

            if hasattr(self.daemon, "task_manager") and self.daemon.task_manager:
                task_manager = self.daemon.task_manager
                self.status.current_task = task_manager.current_task_id
                with task_manager.heap_lock:
                    self.status.tasks_pending = len(task_manager.task_heap)

            # Get ground station information from daemon (available after API validation)
            if hasattr(self.daemon, "ground_station") and self.daemon.ground_station:
                gs_record = self.daemon.ground_station
                gs_id = gs_record.get("id")
                gs_name = gs_record.get("name", "Unknown")

                # Build the URL based on the API host (dev vs prod)
                api_host = self.daemon.settings.host
                if "dev." in api_host:
                    base_url = "https://dev.app.citra.space"
                else:
                    base_url = "https://app.citra.space"

                self.status.ground_station_id = gs_id
                self.status.ground_station_name = gs_name
                self.status.ground_station_url = f"{base_url}/ground-stations/{gs_id}" if gs_id else None

            self.status.last_update = datetime.now().isoformat()

        except Exception as e:
            CITRASCOPE_LOGGER.error(f"Error updating status: {e}")

    async def broadcast_status(self):
        """Broadcast current status to all connected clients."""
        if self.daemon:
            self._update_status_from_daemon()
        await self.connection_manager.broadcast({"type": "status", "data": self.status.dict()})

    async def broadcast_log(self, log_entry: dict):
        """Broadcast log entry to all connected clients."""
        await self.connection_manager.broadcast({"type": "log", "data": log_entry})
