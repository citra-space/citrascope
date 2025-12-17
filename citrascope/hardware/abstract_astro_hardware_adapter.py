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


class ObservationStrategy(Enum):
    MANUAL = 1
    SEQUENCE_TO_CONTROLLER = 2


class AbstractAstroHardwareAdapter(ABC):
    logger: logging.Logger  # Logger instance, must be provided by subclasses
    images_dir: Path  # Path to images directory, must be provided during initialization

    _slew_min_distance_deg: float = 2.0
    scope_slew_rate_degrees_per_second: float = 0.0

    def __init__(self, images_dir: Path):
        """Initialize the adapter with images directory.

        Args:
            images_dir: Path to the images directory
        """
        self.images_dir = images_dir

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
