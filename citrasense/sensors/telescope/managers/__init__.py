"""Telescope-specific hardware managers."""

from citrasense.sensors.telescope.managers.alignment_manager import AlignmentManager
from citrasense.sensors.telescope.managers.autofocus_manager import AutofocusManager
from citrasense.sensors.telescope.managers.calibration_manager import CalibrationManager
from citrasense.sensors.telescope.managers.homing_manager import HomingManager

__all__ = [
    "AlignmentManager",
    "AutofocusManager",
    "CalibrationManager",
    "HomingManager",
]
