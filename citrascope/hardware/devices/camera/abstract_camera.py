"""Abstract camera device interface."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class AbstractCamera(ABC):
    """Abstract base class for camera devices.

    Provides a common interface for controlling imaging cameras including
    CCDs, CMOS sensors, and hyperspectral cameras.
    """

    logger: logging.Logger

    def __init__(self, logger: logging.Logger, **kwargs):
        """Initialize the camera device.

        Args:
            logger: Logger instance for this device
            **kwargs: Device-specific configuration parameters
        """
        self.logger = logger

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the camera device.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the camera device."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if camera is connected and responsive.

        Returns:
            True if connected, False otherwise
        """
        pass

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
