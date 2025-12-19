"""FastAPI web application for CitraScope monitoring and configuration."""

import asyncio
import json
import os
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from citrascope.constants import (
    DEV_API_HOST,
    DEV_APP_URL,
    PROD_API_HOST,
    PROD_APP_URL,
)
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
            # Determine app URL based on API host
            app_url = DEV_APP_URL if settings.host == DEV_API_HOST else PROD_APP_URL

            # Get config file path
            config_path = str(settings.config_manager.get_config_path())

            # Get current log file path
            log_file_path = (
                str(settings.config_manager.get_current_log_path()) if settings.file_logging_enabled else None
            )

            # Get images directory path
            images_dir_path = str(settings.get_images_dir())

            return {
                "host": settings.host,
                "port": settings.port,
                "use_ssl": settings.use_ssl,
                "personal_access_token": settings.personal_access_token,
                "telescope_id": settings.telescope_id,
                "hardware_adapter": settings.hardware_adapter,
                "adapter_settings": settings.adapter_settings,
                "log_level": settings.log_level,
                "keep_images": settings.keep_images,
                "max_task_retries": settings.max_task_retries,
                "initial_retry_delay_seconds": settings.initial_retry_delay_seconds,
                "max_retry_delay_seconds": settings.max_retry_delay_seconds,
                "app_url": app_url,
                "config_file_path": config_path,
                "log_file_path": log_file_path,
                "images_dir_path": images_dir_path,
            }

        @self.app.get("/api/config/status")
        async def get_config_status():
            """Get configuration status."""
            if not self.daemon or not self.daemon.settings:
                return {"configured": False, "error": "Settings not available"}

            return {
                "configured": self.daemon.settings.is_configured(),
                "error": getattr(self.daemon, "configuration_error", None),
            }

        @self.app.get("/api/version")
        async def get_version():
            """Get CitraScope version."""
            try:
                pkg_version = version("citrascope")
                return {"version": pkg_version}
            except PackageNotFoundError:
                return {"version": "development"}

        @self.app.get("/api/hardware-adapters")
        async def get_hardware_adapters():
            """Get list of available hardware adapters."""
            from citrascope.hardware.adapter_registry import list_adapters

            adapters_info = list_adapters()
            return {
                "adapters": list(adapters_info.keys()),
                "descriptions": {name: info["description"] for name, info in adapters_info.items()},
            }

        @self.app.get("/api/hardware-adapters/{adapter_name}/schema")
        async def get_adapter_schema(adapter_name: str):
            """Get configuration schema for a specific hardware adapter."""
            from citrascope.hardware.adapter_registry import get_adapter_schema as get_schema

            try:
                schema = get_schema(adapter_name)
                return {"schema": schema}
            except ValueError as e:
                # Invalid adapter name
                return JSONResponse({"error": str(e)}, status_code=404)
            except Exception as e:
                CITRASCOPE_LOGGER.error(f"Error getting schema for {adapter_name}: {e}", exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/config")
        async def update_config(config: Dict[str, Any]):
            """Update configuration and trigger hot-reload."""
            try:
                if not self.daemon:
                    return JSONResponse({"error": "Daemon not available"}, status_code=503)

                # Validate required fields
                required_fields = ["personal_access_token", "telescope_id", "hardware_adapter"]
                for field in required_fields:
                    if field not in config or not config[field]:
                        return JSONResponse(
                            {"error": f"Missing required field: {field}"},
                            status_code=400,
                        )

                # Validate adapter_settings against schema if adapter is specified
                adapter_name = config.get("hardware_adapter")
                adapter_settings = config.get("adapter_settings", {})

                if adapter_name:
                    # Get schema for validation
                    schema_response = await get_adapter_schema(adapter_name)
                    if isinstance(schema_response, JSONResponse):
                        return schema_response  # Error getting schema

                    schema = schema_response.get("schema", [])

                    # Validate required fields in adapter settings
                    for field_schema in schema:
                        field_name = field_schema.get("name")
                        is_required = field_schema.get("required", False)

                        if is_required and field_name not in adapter_settings:
                            return JSONResponse(
                                {"error": f"Missing required adapter setting: {field_name}"},
                                status_code=400,
                            )

                        # Validate type and constraints if present
                        if field_name in adapter_settings:
                            value = adapter_settings[field_name]
                            field_type = field_schema.get("type")

                            # Type validation
                            if field_type == "int":
                                try:
                                    value = int(value)
                                    adapter_settings[field_name] = value
                                except (ValueError, TypeError):
                                    return JSONResponse(
                                        {"error": f"Field '{field_name}' must be an integer"},
                                        status_code=400,
                                    )

                                # Range validation
                                if "min" in field_schema and value < field_schema["min"]:
                                    return JSONResponse(
                                        {"error": f"Field '{field_name}' must be >= {field_schema['min']}"},
                                        status_code=400,
                                    )
                                if "max" in field_schema and value > field_schema["max"]:
                                    return JSONResponse(
                                        {"error": f"Field '{field_name}' must be <= {field_schema['max']}"},
                                        status_code=400,
                                    )

                            elif field_type == "float":
                                try:
                                    value = float(value)
                                    adapter_settings[field_name] = value
                                except (ValueError, TypeError):
                                    return JSONResponse(
                                        {"error": f"Field '{field_name}' must be a number"},
                                        status_code=400,
                                    )

                # Save configuration to file
                from citrascope.settings.settings_file_manager import SettingsFileManager

                config_manager = SettingsFileManager()
                config_manager.save_config(config)

                # Trigger hot-reload
                success, error = self.daemon.reload_configuration()

                if success:
                    return {
                        "status": "success",
                        "message": "Configuration updated and reloaded successfully",
                    }
                else:
                    return JSONResponse(
                        {
                            "status": "error",
                            "message": f"Configuration saved but reload failed: {error}",
                            "error": error,
                        },
                        status_code=500,
                    )

            except Exception as e:
                CITRASCOPE_LOGGER.error(f"Error updating config: {e}", exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)

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
                            "start_time": datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
                            "stop_time": (
                                datetime.fromtimestamp(stop_time, tz=timezone.utc).isoformat() if stop_time else None
                            ),
                            "status": task.status,
                            "target": getattr(task, "satelliteName", getattr(task, "target", "unknown")),
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
                # Check telescope connection status
                try:
                    self.status.telescope_connected = self.daemon.hardware_adapter.is_telescope_connected()
                    if self.status.telescope_connected:
                        # If connected, try to get position
                        ra, dec = self.daemon.hardware_adapter.get_telescope_direction()
                        self.status.telescope_ra = ra
                        self.status.telescope_dec = dec
                except Exception:
                    self.status.telescope_connected = False

                # Check camera connection status
                try:
                    self.status.camera_connected = self.daemon.hardware_adapter.is_camera_connected()
                except Exception:
                    self.status.camera_connected = False

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
                base_url = DEV_APP_URL if "dev." in api_host else PROD_APP_URL

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

    async def broadcast_tasks(self):
        """Broadcast current task queue to all connected clients."""
        if not self.daemon or not hasattr(self.daemon, "task_manager") or self.daemon.task_manager is None:
            return

        task_manager = self.daemon.task_manager
        tasks = []

        with task_manager.heap_lock:
            for start_time, stop_time, task_id, task in task_manager.task_heap:
                tasks.append(
                    {
                        "id": task_id,
                        "start_time": datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
                        "stop_time": (
                            datetime.fromtimestamp(stop_time, tz=timezone.utc).isoformat() if stop_time else None
                        ),
                        "status": task.status,
                        "target": getattr(task, "satelliteName", getattr(task, "target", "unknown")),
                    }
                )

        await self.connection_manager.broadcast({"type": "tasks", "data": tasks})

    async def broadcast_log(self, log_entry: dict):
        """Broadcast log entry to all connected clients."""
        await self.connection_manager.broadcast({"type": "log", "data": log_entry})
