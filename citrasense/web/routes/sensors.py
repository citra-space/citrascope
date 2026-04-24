"""Sensor enumeration, detail, connect/disconnect endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from citrasense.logging import CITRASENSE_LOGGER

if TYPE_CHECKING:
    from citrasense.web.app import CitraSenseWebApp


def build_sensors_router(ctx: CitraSenseWebApp) -> APIRouter:
    """Endpoints under ``/api/sensors``."""
    router = APIRouter(prefix="/api/sensors", tags=["sensors"])

    @router.get("")
    async def list_sensors():
        """Return all registered sensors with basic metadata."""
        if not ctx.daemon or not ctx.daemon.sensor_manager:
            return JSONResponse({"error": "Sensor manager not available"}, status_code=503)
        sensors = []
        for s in ctx.daemon.sensor_manager:
            sensors.append(
                {
                    "id": s.sensor_id,
                    "type": s.sensor_type,
                    "connected": s.is_connected(),
                    "name": getattr(s, "name", s.sensor_id),
                }
            )
        return {"sensors": sensors}

    @router.get("/{sensor_id}")
    async def sensor_detail(sensor_id: str):
        """Return detailed status for a single sensor."""
        if not ctx.daemon or not ctx.daemon.sensor_manager:
            return JSONResponse({"error": "Sensor manager not available"}, status_code=503)
        sensor = ctx.daemon.sensor_manager.get_sensor(sensor_id)
        if sensor is None:
            return JSONResponse({"error": f"Unknown sensor: {sensor_id}"}, status_code=404)
        detail: dict = {
            "id": sensor.sensor_id,
            "type": sensor.sensor_type,
            "connected": sensor.is_connected(),
            "name": getattr(sensor, "name", sensor.sensor_id),
        }
        if hasattr(sensor, "adapter") and sensor.adapter:
            detail["adapter_type"] = type(sensor.adapter).__name__
        return detail

    @router.post("/{sensor_id}/connect")
    async def connect_sensor(sensor_id: str):
        """Connect a sensor's hardware adapter."""
        if not ctx.daemon or not ctx.daemon.sensor_manager:
            return JSONResponse({"error": "Sensor manager not available"}, status_code=503)
        sensor = ctx.daemon.sensor_manager.get_sensor(sensor_id)
        if sensor is None:
            return JSONResponse({"error": f"Unknown sensor: {sensor_id}"}, status_code=404)
        try:
            ok = sensor.connect()
            if ok:
                return {"success": True, "message": f"Sensor {sensor_id} connected"}
            return JSONResponse({"error": "Connection failed"}, status_code=500)
        except Exception as e:
            CITRASENSE_LOGGER.error("Sensor %s connect error: %s", sensor_id, e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)

    @router.post("/{sensor_id}/disconnect")
    async def disconnect_sensor(sensor_id: str):
        """Disconnect a sensor's hardware adapter."""
        if not ctx.daemon or not ctx.daemon.sensor_manager:
            return JSONResponse({"error": "Sensor manager not available"}, status_code=503)
        sensor = ctx.daemon.sensor_manager.get_sensor(sensor_id)
        if sensor is None:
            return JSONResponse({"error": f"Unknown sensor: {sensor_id}"}, status_code=404)
        try:
            sensor.disconnect()
            return {"success": True, "message": f"Sensor {sensor_id} disconnected"}
        except Exception as e:
            CITRASENSE_LOGGER.error("Sensor %s disconnect error: %s", sensor_id, e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)

    return router
