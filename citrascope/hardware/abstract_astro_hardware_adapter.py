import logging
import math
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TypedDict


class SettingSchemaEntry(TypedDict, total=False):
    name: str
    friendly_name: str  # Human-readable display name for UI
    type: str  # e.g., 'float', 'int', 'str', 'bool'
    default: Optional[Any]
    description: str
    required: bool  # Whether this field is required
    placeholder: str  # Placeholder text for UI inputs
    min: float  # Minimum value for numeric types
    max: float  # Maximum value for numeric types
    pattern: str  # Regex pattern for string validation
    options: list[str]  # List of valid options for select/dropdown inputs


class FilterConfig(TypedDict):
    """Type definition for filter configuration.

    Attributes:
        name: Human-readable filter name (e.g., 'Luminance', 'Red', 'Ha')
        focus_position: Focuser position for this filter in steps
        enabled: Whether this filter is enabled for observations (default: True)
    """

    name: str
    focus_position: int
    enabled: bool


class ObservationStrategy(Enum):
    MANUAL = 1
    SEQUENCE_TO_CONTROLLER = 2


class AbstractAstroHardwareAdapter(ABC):
    logger: logging.Logger  # Logger instance, must be provided by subclasses
    images_dir: Path  # Path to images directory, must be provided during initialization

    _slew_min_distance_deg: float = 2.0
    scope_slew_rate_degrees_per_second: float = 0.0
    DEFAULT_FOCUS_POSITION: int = 0  # Default focus position, can be overridden by subclasses

    def __init__(self, images_dir: Path, **kwargs):
        """Initialize the adapter with images directory and optional filter configuration.

        Args:
            images_dir: Path to the images directory
            **kwargs: Additional configuration including 'filters' dict
        """
        self.images_dir = images_dir
        self.filter_map = {}

        # Load filter configuration from settings if available
        saved_filters = kwargs.get("filters", {})
        for filter_id, filter_data in saved_filters.items():
            try:
                # Default enabled to True for backward compatibility
                if "enabled" not in filter_data:
                    filter_data["enabled"] = True
                self.filter_map[int(filter_id)] = filter_data
            except (ValueError, TypeError):
                pass  # Skip invalid filter IDs

    @classmethod
    @abstractmethod
    def get_settings_schema(cls) -> list[SettingSchemaEntry]:
        """
        Return a schema describing configurable settings for this hardware adapter.

        Each setting is described as a SettingSchemaEntry TypedDict with keys:
            - name (str): The setting's name
            - type (str): The expected Python type (e.g., 'float', 'int', 'str', 'bool')
            - default (optional): The default value
            - description (str): Human-readable description of the setting

        Returns:
            list[SettingSchemaEntry]: List of setting schema entries.
        """
        pass

    def point_telescope(self, ra: float, dec: float):
        """Point the telescope to the specified RA/Dec coordinates."""
        # separated out to allow pre/post processing if needed
        self._do_point_telescope(ra, dec)

    @abstractmethod
    def _do_point_telescope(self, ra: float, dec: float):
        """Hardware-specific implementation to point the telescope."""
        pass

    def angular_distance(
        self, ra1_degrees: float, dec1_degrees: float, ra2_degrees: float, dec2_degrees: float
    ) -> float:  # TODO: move this out of the hardware adapter... this isn't hardware stuff
        """Compute angular distance between two (RA hours, Dec deg) points in degrees."""

        # Convert to radians
        ra1_rad = math.radians(ra1_degrees)
        ra2_rad = math.radians(ra2_degrees)
        dec1_rad = math.radians(dec1_degrees)
        dec2_rad = math.radians(dec2_degrees)
        # Spherical law of cosines
        cos_angle = math.sin(dec1_rad) * math.sin(dec2_rad) + math.cos(dec1_rad) * math.cos(dec2_rad) * math.cos(
            ra1_rad - ra2_rad
        )
        # Clamp for safety
        cos_angle = min(1.0, max(-1.0, cos_angle))
        angle_rad = math.acos(cos_angle)
        return math.degrees(angle_rad)

    """
    Abstract base class for controlling astrophotography hardware.

    This adapter provides a common interface for interacting with telescopes, cameras,
    filter wheels, focus dials, and other astrophotography devices.
    """

    @abstractmethod
    def get_observation_strategy(self) -> ObservationStrategy:
        """Get the current observation strategy from the hardware."""
        pass

    @abstractmethod
    def perform_observation_sequence(self, task_id, satellite_data) -> str:
        """For hardware driven by sequences, perform the observation sequence and return image path."""
        pass

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the hardware server."""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect from the hardware server."""
        pass

    @abstractmethod
    def is_telescope_connected(self) -> bool:
        """Check if telescope is connected and responsive."""
        pass

    @abstractmethod
    def is_camera_connected(self) -> bool:
        """Check if camera is connected and responsive."""
        pass

    @abstractmethod
    def list_devices(self) -> list[str]:
        """List all connected devices."""
        pass

    @abstractmethod
    def select_telescope(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        pass

    @abstractmethod
    def get_telescope_direction(self) -> tuple[float, float]:
        """Read the current telescope direction (RA degrees, DEC degrees)."""
        pass

    @abstractmethod
    def telescope_is_moving(self) -> bool:
        """Check if the telescope is currently moving."""
        pass

    @abstractmethod
    def select_camera(self, device_name: str) -> bool:
        """Select a specific camera by name."""
        pass

    @abstractmethod
    def take_image(self, task_id: str, exposure_duration_seconds=1.0) -> str:
        """Capture an image with the currently selected camera. Returns the file path of the saved image."""
        pass

    @abstractmethod
    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        """Set the tracking rate for the telescope in RA and Dec (arcseconds per second)."""
        pass

    @abstractmethod
    def get_tracking_rate(self) -> tuple[float, float]:
        """Get the current tracking rate for the telescope in RA and Dec (arcseconds per second)."""
        pass

    @abstractmethod
    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        """
        Perform plate-solving-based alignment to adjust the telescope's position.

        Args:
            target_ra (float): The target Right Ascension (RA) in degrees.
            target_dec (float): The target Declination (Dec) in degrees.

        Returns:
            bool: True if alignment was successful, False otherwise.
        """
        pass

    def do_autofocus(self) -> None:
        """Perform autofocus routine for all filters.

        This is an optional method for adapters that support filter management.
        Default implementation raises NotImplementedError. Override in subclasses
        that support autofocus.

        Raises:
            NotImplementedError: If the adapter doesn't support autofocus
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support autofocus")

    def supports_autofocus(self) -> bool:
        """Indicates whether this adapter supports autofocus functionality.

        Returns:
            bool: True if the adapter can perform autofocus, False otherwise.
        """
        return False

    def supports_filter_management(self) -> bool:
        """Indicates whether this adapter supports filter/focus management.

        Returns:
            bool: True if the adapter manages filters and focus positions, False otherwise.
        """
        return False

    def get_filter_config(self) -> dict[str, FilterConfig]:
        """Get the current filter configuration including focus positions.

        Returns:
            dict: Dictionary mapping filter IDs (as strings) to FilterConfig.
                  Each FilterConfig contains:
                  - name (str): Filter name
                  - focus_position (int): Focuser position for this filter
                  - enabled (bool): Whether filter is enabled for observations

        Example:
            {
                "1": {"name": "Luminance", "focus_position": 9000, "enabled": True},
                "2": {"name": "Red", "focus_position": 9050, "enabled": False}
            }
        """
        return {
            str(filter_id): {
                "name": filter_data["name"],
                "focus_position": filter_data["focus_position"],
                "enabled": filter_data.get("enabled", True),
            }
            for filter_id, filter_data in self.filter_map.items()
        }

    def update_filter_focus(self, filter_id: str, focus_position: int) -> bool:
        """Update the focus position for a specific filter.

        Args:
            filter_id: Filter ID as string
            focus_position: New focus position in steps

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            filter_id_int = int(filter_id)
            if filter_id_int in self.filter_map:
                self.filter_map[filter_id_int]["focus_position"] = focus_position
                return True
            return False
        except (ValueError, KeyError):
            return False

    def update_filter_enabled(self, filter_id: str, enabled: bool) -> bool:
        """Update the enabled state for a specific filter.

        Args:
            filter_id: Filter ID as string
            enabled: New enabled state

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            filter_id_int = int(filter_id)
            if filter_id_int in self.filter_map:
                self.filter_map[filter_id_int]["enabled"] = enabled
                return True
            return False
        except (ValueError, KeyError):
            return False
