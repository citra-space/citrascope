"""Telescope-specific task implementations."""

from citrasense.sensors.telescope.tasks.base_telescope_task import AbstractBaseTelescopeTask
from citrasense.sensors.telescope.tasks.sidereal_telescope_task import SiderealTelescopeTask
from citrasense.sensors.telescope.tasks.tracking_telescope_task import TrackingTelescopeTask

__all__ = [
    "AbstractBaseTelescopeTask",
    "SiderealTelescopeTask",
    "TrackingTelescopeTask",
]
