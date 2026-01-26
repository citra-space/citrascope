"""Abstract base class for all hardware device types."""

import logging
from abc import ABC, abstractmethod

from citrascope.hardware.abstract_astro_hardware_adapter import SettingSchemaEntry


class AbstractHardwareDevice(ABC):
    """Base class for all hardware devices (cameras, mounts, filter wheels, focusers).

    Provides common interface elements shared by all device types.
    """

    logger: logging.Logger

    def __init__(self, logger: logging.Logger, **kwargs):
        """Initialize the hardware device.

        Args:
            logger: Logger instance for this device
            **kwargs: Device-specific configuration parameters
        """
        self.logger = logger

    @classmethod
    @abstractmethod
    def get_friendly_name(cls) -> str:
        """Return human-readable name for this device.

        Returns:
            Friendly display name (e.g., 'ZWO ASI294MC Pro', 'Celestron CGX')
        """
        pass

    @classmethod
    @abstractmethod
    def get_dependencies(cls) -> dict[str, str | list[str]]:
        """Return required Python packages and installation info.

        Returns:
            Dict with keys:
                - packages: list of required package names
                - install_extra: pyproject.toml extra name for pip install
        """
        pass

    @classmethod
    @abstractmethod
    def get_settings_schema(cls) -> list[SettingSchemaEntry]:
        """Return schema describing configurable settings for this device.

        Returns:
            List of setting schema entries (without device-type prefix)
        """
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the hardware device.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the hardware device."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if device is connected and responsive.

        Returns:
            True if connected, False otherwise
        """
        pass
