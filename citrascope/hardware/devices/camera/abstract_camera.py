"""Abstract camera device interface."""

from abc import abstractmethod
from pathlib import Path
from typing import Optional

from citrascope.hardware.devices.abstract_hardware_device import AbstractHardwareDevice


class AbstractCamera(AbstractHardwareDevice):
    """Abstract base class for camera devices.

    Provides a common interface for controlling imaging cameras including
    CCDs, CMOS sensors, and hyperspectral cameras.
    """

    @abstractmethod
    def take_exposure(
        self,
        duration: float,
        gain: Optional[int] = None,
        offset: Optional[int] = None,
        binning: int = 1,
        save_path: Optional[Path] = None,
    ) -> Path:
        """Capture an image exposure.

        Args:
            duration: Exposure duration in seconds
            gain: Camera gain setting (device-specific units)
            offset: Camera offset/black level setting
            binning: Pixel binning factor (1=no binning, 2=2x2, etc.)
            save_path: Optional path to save the image (if None, use default)

        Returns:
            Path to the saved image file
        """
        pass

    @abstractmethod
    def abort_exposure(self):
        """Abort the current exposure if one is in progress."""
        pass

    @abstractmethod
    def get_temperature(self) -> Optional[float]:
        """Get the current camera sensor temperature.

        Returns:
            Temperature in degrees Celsius, or None if not available
        """
        pass

    @abstractmethod
    def set_temperature(self, temperature: float) -> bool:
        """Set the target camera sensor temperature.

        Args:
            temperature: Target temperature in degrees Celsius

        Returns:
            True if temperature setpoint accepted, False otherwise
        """
        pass

    @abstractmethod
    def start_cooling(self) -> bool:
        """Enable camera cooling system.

        Returns:
            True if cooling started successfully, False otherwise
        """
        pass

    @abstractmethod
    def stop_cooling(self) -> bool:
        """Disable camera cooling system.

        Returns:
            True if cooling stopped successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_camera_info(self) -> dict:
        """Get camera capabilities and information.

        Returns:
            Dictionary containing camera specs (resolution, pixel size, bit depth, etc.)
        """
        pass
