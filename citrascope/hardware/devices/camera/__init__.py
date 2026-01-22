"""Camera device adapters."""

from citrascope.hardware.devices.camera.abstract_camera import AbstractCamera
from citrascope.hardware.devices.camera.ximea_camera import XimeaHyperspectralCamera

__all__ = [
    "AbstractCamera",
    "XimeaHyperspectralCamera",
]
