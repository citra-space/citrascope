"""Dummy hardware adapter for testing without real hardware."""

import logging
import shutil
import time
from pathlib import Path

import numpy as np
from astropy.io import fits

from citrascope.hardware.abstract_astro_hardware_adapter import (
    AbstractAstroHardwareAdapter,
    ObservationStrategy,
    SettingSchemaEntry,
)


class DummyAdapter(AbstractAstroHardwareAdapter):
    """
    Dummy hardware adapter that simulates hardware without requiring real devices.

    Perfect for testing, development, and demonstrations. All operations are logged
    and return realistic fake data.
    """

    def __init__(self, logger: logging.Logger, images_dir: Path, **kwargs):
        """Initialize dummy adapter.

        Args:
            logger: Logger instance
            images_dir: Path to images directory
            **kwargs: Additional settings including 'simulate_slow_operations'
        """
        super().__init__(images_dir, **kwargs)
        self.logger = logger
        self.simulate_slow = kwargs.get("simulate_slow_operations", False)
        self.slow_delay = kwargs.get("slow_delay_seconds", 2.0)

        # Fake hardware state
        self._connected = False
        self._telescope_connected = False
        self._camera_connected = False
        self._current_ra = 0.0  # degrees
        self._current_dec = 0.0  # degrees
        self._is_moving = False
        self._tracking_rate = (15.041, 0.0)  # arcsec/sec (sidereal rate)

        self.logger.info("DummyAdapter initialized")

    @classmethod
    def get_settings_schema(cls, **kwargs) -> list[SettingSchemaEntry]:
        """Return configuration schema for dummy adapter."""
        return [
            {
                "name": "simulate_slow_operations",
                "friendly_name": "Simulate Slow Operations",
                "type": "bool",
                "default": False,
                "description": "Add artificial delays to simulate slow hardware responses",
                "required": False,
                "group": "Testing",
            },
            {
                "name": "slow_delay_seconds",
                "friendly_name": "Delay Duration (seconds)",
                "type": "float",
                "default": 2.0,
                "min": 0.1,
                "max": 10.0,
                "description": "Duration of artificial delays when slow simulation is enabled",
                "required": False,
                "group": "Testing",
            },
        ]

    def get_observation_strategy(self) -> ObservationStrategy:
        """Dummy adapter uses manual strategy."""
        return ObservationStrategy.MANUAL

    def perform_observation_sequence(self, task, satellite_data) -> str:
        """Not used for manual strategy."""
        raise NotImplementedError("DummyAdapter uses MANUAL strategy")

    def connect(self) -> bool:
        """Simulate connection."""
        self.logger.info("DummyAdapter: Connecting...")
        self._simulate_delay()
        self._connected = True
        self._telescope_connected = True
        self._camera_connected = True
        self.logger.info("DummyAdapter: Connected successfully")
        return True

    def disconnect(self):
        """Simulate disconnection."""
        self.logger.info("DummyAdapter: Disconnecting...")
        self._connected = False
        self._telescope_connected = False
        self._camera_connected = False
        self.logger.info("DummyAdapter: Disconnected")

    def is_telescope_connected(self) -> bool:
        """Check fake telescope connection."""
        return self._telescope_connected

    def is_camera_connected(self) -> bool:
        """Check fake camera connection."""
        return self._camera_connected

    def list_devices(self) -> list[str]:
        """Return list of fake devices."""
        return ["Dummy Telescope", "Dummy Camera", "Dummy Filter Wheel", "Dummy Focuser"]

    def select_telescope(self, device_name: str) -> bool:
        """Simulate telescope selection."""
        self.logger.info(f"DummyAdapter: Selected telescope '{device_name}'")
        self._telescope_connected = True
        return True

    def _do_point_telescope(self, ra: float, dec: float):
        """Simulate telescope slew."""
        self.logger.info(f"DummyAdapter: Slewing to RA={ra:.4f}°, Dec={dec:.4f}°")
        self._is_moving = True
        self._simulate_delay()
        self._current_ra = ra
        self._current_dec = dec
        self._is_moving = False
        self.logger.info("DummyAdapter: Slew complete")

    def get_telescope_direction(self) -> tuple[float, float]:
        """Return current fake telescope position."""
        return (self._current_ra, self._current_dec)

    def telescope_is_moving(self) -> bool:
        """Check if fake telescope is moving."""
        return self._is_moving

    def select_camera(self, device_name: str) -> bool:
        """Simulate camera selection."""
        self.logger.info(f"DummyAdapter: Selected camera '{device_name}'")
        self._camera_connected = True
        return True

    def take_image(self, task_id: str, exposure_duration_seconds=1.0) -> str:
        """Simulate image capture using real FITS file."""
        self.logger.info(f"DummyAdapter: Starting {exposure_duration_seconds}s exposure for task {task_id}")
        self._simulate_delay(exposure_duration_seconds)

        # Use test FITS file from test_data directory (git-ignored, ~1MB)
        # Falls back to generating synthetic FITS if test file doesn't exist
        test_fits = Path(__file__).parent.parent.parent / "test_data" / "test_image_small.fits"

        # Create output filename
        timestamp = int(time.time())
        filename = f"dummy_{task_id}_{timestamp}.fits"
        filepath = self.images_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if test_fits.exists():
            # Copy real test FITS
            shutil.copy(test_fits, filepath)
            self.logger.info(f"DummyAdapter: Image saved to {filepath} (copied from test data)")
        else:
            # Generate synthetic FITS if test file not available
            self._create_synthetic_fits(filepath, exposure_duration_seconds)
            self.logger.info(f"DummyAdapter: Image saved to {filepath} (synthetic)")

        return str(filepath)

    def _create_synthetic_fits(self, filepath: Path, exposure_duration: float):
        """Generate synthetic FITS file for testing."""
        try:
            # Create realistic synthetic 16-bit image (small size for git/server)
            mean_signal = min(5000 * exposure_duration, 30000)
            image_data = np.random.normal(mean_signal, 1000, (512, 512)).astype(np.uint16)

            # Add some "stars" (bright spots)
            num_stars = np.random.randint(50, 200)
            for _ in range(num_stars):
                y, x = np.random.randint(10, 502, 2)
                brightness = np.random.randint(10000, 50000)
                image_data[y : y + 3, x : x + 3] = np.minimum(image_data[y : y + 3, x : x + 3] + brightness, 65535)

            # Save as FITS with basic header
            hdu = fits.PrimaryHDU(image_data)
            hdu.header["EXPTIME"] = exposure_duration
            hdu.header["DATE-OBS"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            hdu.header["OBSERVER"] = "DummyAdapter"
            hdu.writeto(filepath, overwrite=True)
        except ImportError:
            # Fallback: create minimal FITS if astropy not available
            filepath.write_text(f"DUMMY FITS IMAGE\nTask exposure: {exposure_duration}s\n")

    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        """Simulate setting tracking rate."""
        self.logger.info(f"DummyAdapter: Setting tracking rate RA={ra_rate} arcsec/s, Dec={dec_rate} arcsec/s")
        self._tracking_rate = (ra_rate, dec_rate)

    def get_tracking_rate(self) -> tuple[float, float]:
        """Return current fake tracking rate."""
        return self._tracking_rate

    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        """Simulate plate solving alignment."""
        self.logger.info(f"DummyAdapter: Performing alignment to RA={target_ra}°, Dec={target_dec}°")
        self._simulate_delay()
        # Simulate small correction
        self._current_ra = target_ra + 0.001
        self._current_dec = target_dec + 0.001
        self.logger.info("DummyAdapter: Alignment successful")
        return True

    def supports_autofocus(self) -> bool:
        """Dummy adapter supports autofocus."""
        return True

    def do_autofocus(self) -> None:
        """Simulate autofocus routine."""
        self.logger.info("DummyAdapter: Starting autofocus...")
        self._simulate_delay(3.0)
        self.logger.info("DummyAdapter: Autofocus complete")

    def supports_filter_management(self) -> bool:
        """Dummy adapter supports filter management."""
        return True

    def supports_direct_camera_control(self) -> bool:
        """Dummy adapter supports direct camera control."""
        return True

    def expose_camera(self, exposure_seconds: float = 1.0) -> str:
        """Simulate manual camera exposure."""
        return self.take_image("manual_test", exposure_seconds)

    def _simulate_delay(self, override_delay: float = None):
        """Add artificial delay if slow simulation is enabled."""
        if self.simulate_slow:
            delay = override_delay if override_delay is not None else self.slow_delay
            time.sleep(delay)
