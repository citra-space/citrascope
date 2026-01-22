"""Abstract filter wheel device interface."""

import logging
from abc import ABC, abstractmethod
from typing import Optional


class AbstractFilterWheel(ABC):
    """Abstract base class for filter wheel devices.

    Provides a common interface for controlling motorized filter wheels.
    """

    logger: logging.Logger

    def __init__(self, logger: logging.Logger, **kwargs):
        """Initialize the filter wheel device.

        Args:
            logger: Logger instance for this device
            **kwargs: Device-specific configuration parameters
        """
        self.logger = logger

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the filter wheel device.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the filter wheel device."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if filter wheel is connected and responsive.

        Returns:
            True if connected, False otherwise
        """
        pass

    @abstractmethod
    def set_filter_position(self, position: int) -> bool:
        """Move to specified filter position.

        Args:
            position: Filter position (0-indexed)

        Returns:
            True if move initiated successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_filter_position(self) -> Optional[int]:
        """Get current filter position.

        Returns:
            Current filter position (0-indexed), or None if unavailable
        """
        pass

    @abstractmethod
    def is_moving(self) -> bool:
        """Check if filter wheel is currently moving.

        Returns:
            True if moving, False if stationary
        """
        pass

    @abstractmethod
    def get_filter_count(self) -> int:
        """Get the number of filter positions.

        Returns:
            Number of available filter positions
        """
        pass

    @abstractmethod
    def get_filter_names(self) -> list[str]:
        """Get the names of all filters.

        Returns:
            List of filter names for each position
        """
        pass

    @abstractmethod
    def set_filter_names(self, names: list[str]) -> bool:
        """Set the names for all filter positions.

        Args:
            names: List of filter names (must match filter count)

        Returns:
            True if names set successfully, False otherwise
        """
        pass
