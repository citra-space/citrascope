"""Abstract focuser device interface."""

import logging
from abc import ABC, abstractmethod
from typing import Optional


class AbstractFocuser(ABC):
    """Abstract base class for focuser devices.

    Provides a common interface for controlling motorized focusers.
    """

    logger: logging.Logger

    def __init__(self, logger: logging.Logger, **kwargs):
        """Initialize the focuser device.

        Args:
            logger: Logger instance for this device
            **kwargs: Device-specific configuration parameters
        """
        self.logger = logger

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the focuser device.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the focuser device."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if focuser is connected and responsive.

        Returns:
            True if connected, False otherwise
        """
        pass

    @abstractmethod
    def move_absolute(self, position: int) -> bool:
        """Move to absolute focuser position.

        Args:
            position: Target position in steps

        Returns:
            True if move initiated successfully, False otherwise
        """
        pass

    @abstractmethod
    def move_relative(self, steps: int) -> bool:
        """Move focuser by relative number of steps.

        Args:
            steps: Number of steps to move (positive=outward, negative=inward)

        Returns:
            True if move initiated successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_position(self) -> Optional[int]:
        """Get current focuser position.

        Returns:
            Current position in steps, or None if unavailable
        """
        pass

    @abstractmethod
    def is_moving(self) -> bool:
        """Check if focuser is currently moving.

        Returns:
            True if moving, False if stationary
        """
        pass

    @abstractmethod
    def abort_move(self):
        """Stop the current focuser movement."""
        pass

    @abstractmethod
    def get_max_position(self) -> Optional[int]:
        """Get the maximum focuser position.

        Returns:
            Maximum position in steps, or None if unlimited/unknown
        """
        pass

    @abstractmethod
    def get_temperature(self) -> Optional[float]:
        """Get focuser temperature reading if available.

        Returns:
            Temperature in degrees Celsius, or None if not available
        """
        pass
