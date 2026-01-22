"""Ximea hyperspectral imaging camera adapter."""

import logging
import time
from pathlib import Path
from typing import Optional, cast

from citrascope.hardware.abstract_astro_hardware_adapter import SettingSchemaEntry
from citrascope.hardware.devices.camera import AbstractCamera


class XimeaHyperspectralCamera(AbstractCamera):
    """Adapter for Ximea hyperspectral imaging cameras.

    Supports Ximea MQ series cameras with snapshot mosaic hyperspectral sensors.
    Requires ximea-api package (xiAPI Python wrapper).

    Configuration:
        serial_number (str): Camera serial number for multi-camera setups
        default_gain (float): Default gain in dB
        default_exposure_ms (float): Default exposure time in milliseconds
        spectral_bands (int): Number of spectral bands (e.g., 25 for MQ022HG-IM-SM5X5)
        output_format (str): Output format - 'raw', 'demosaiced', 'datacube'
    """

    @classmethod
    def get_friendly_name(cls) -> str:
        """Return human-readable name for this camera device.

        Returns:
            Friendly display name
        """
        return "Ximea Hyperspectral Camera (MQ Series)"

    @classmethod
    def get_dependencies(cls) -> dict[str, str | list[str]]:
        """Return required Python packages.

        Returns:
            Dict with packages and install extra
        """
        return {
            "packages": ["ximea"],
            "install_extra": "ximea",
        }

    @classmethod
    def get_settings_schema(cls) -> list[SettingSchemaEntry]:
        """Return schema for Ximea camera settings.

        Returns:
            List of setting schema entries (without 'camera_' prefix)
        """
        schema = [
            {
                "name": "serial_number",
                "friendly_name": "Camera Serial Number",
                "type": "str",
                "default": "",
                "description": "Camera serial number (for multi-camera setups)",
                "required": False,
                "placeholder": "Leave empty to auto-detect",
                "group": "Camera",
            },
            {
                "name": "default_gain",
                "friendly_name": "Default Gain (dB)",
                "type": "float",
                "default": 0.0,
                "description": "Default camera gain setting in dB",
                "required": False,
                "min": 0.0,
                "max": 24.0,
                "group": "Camera",
            },
            {
                "name": "default_exposure_ms",
                "friendly_name": "Default Exposure (ms)",
                "type": "float",
                "default": 100.0,
                "description": "Default exposure time in milliseconds",
                "required": False,
                "min": 0.1,
                "max": 10000.0,
                "group": "Camera",
            },
            {
                "name": "spectral_bands",
                "friendly_name": "Spectral Bands",
                "type": "int",
                "default": 25,
                "description": "Number of spectral bands (e.g., 25 for MQ022HG-IM-SM5X5)",
                "required": False,
                "min": 1,
                "max": 500,
                "group": "Camera",
            },
            {
                "name": "output_format",
                "friendly_name": "Output Format",
                "type": "str",
                "default": "raw",
                "description": "Output format for hyperspectral data",
                "required": False,
                "options": ["raw", "demosaiced", "datacube"],
                "group": "Camera",
            },
        ]
        return cast(list[SettingSchemaEntry], schema)

    def __init__(self, logger: logging.Logger, **kwargs):
        """Initialize the Ximea camera.

        Args:
            logger: Logger instance for this device
            **kwargs: Configuration including serial_number, default_gain, etc.
        """
        super().__init__(logger, **kwargs)

        self.serial_number: Optional[str] = kwargs.get("serial_number")
        self.default_gain: float = kwargs.get("default_gain", 0.0)
        self.default_exposure_ms: float = kwargs.get("default_exposure_ms", 100.0)
        self.spectral_bands: int = kwargs.get("spectral_bands", 25)
        self.output_format: str = kwargs.get("output_format", "raw")

        # Camera handle (will be initialized on connect)
        self._camera = None
        self._is_connected = False

        # Camera info cache
        self._camera_info = {}

    def connect(self) -> bool:
        """Connect to the Ximea camera.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Import ximea API (lazy import to avoid hard dependency)
            try:
                from ximea import xiapi
            except ImportError:
                self.logger.error("ximea-api package not installed. Install with: pip install ximea-api")
                return False

            self.logger.info("Connecting to Ximea hyperspectral camera...")

            # Create camera instance
            self._camera = xiapi.Camera()

            # Open camera (by serial number if specified)
            if self.serial_number:
                self.logger.info(f"Opening camera with serial number: {self.serial_number}")
                self._camera.open_device_by_SN(self.serial_number)
            else:
                self.logger.info("Opening first available Ximea camera")
                self._camera.open_device()

            # Configure camera
            self._configure_camera()

            # Cache camera info
            self._camera_info = self._read_camera_info()

            self._is_connected = True
            self.logger.info(
                f"Connected to Ximea camera: {self._camera_info.get('model', 'Unknown')} "
                f"(SN: {self._camera_info.get('serial_number', 'Unknown')})"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Ximea camera: {e}")
            self._is_connected = False
            return False

    def disconnect(self):
        """Disconnect from the Ximea camera."""
        if self._camera is not None:
            try:
                self.logger.info("Disconnecting from Ximea camera...")
                self._camera.close_device()
                self._is_connected = False
                self.logger.info("Ximea camera disconnected")
            except Exception as e:
                self.logger.error(f"Error disconnecting from Ximea camera: {e}")
            finally:
                self._camera = None

    def is_connected(self) -> bool:
        """Check if camera is connected and responsive.

        Returns:
            True if connected, False otherwise
        """
        return self._is_connected and self._camera is not None

    def take_exposure(
        self,
        duration: float,
        gain: Optional[int] = None,
        offset: Optional[int] = None,
        binning: int = 1,
        save_path: Optional[Path] = None,
    ) -> Path:
        """Capture a hyperspectral image exposure.

        Args:
            duration: Exposure duration in seconds
            gain: Camera gain in dB (if None, use default)
            offset: Not used for Ximea cameras
            binning: Pixel binning factor (1=no binning, 2=2x2, etc.)
            save_path: Optional path to save the image

        Returns:
            Path to the saved image file
        """
        if not self.is_connected():
            raise RuntimeError("Camera not connected")

        try:
            from ximea import xiapi
        except ImportError:
            raise RuntimeError("ximea-api package not installed")

        self.logger.info(
            f"Starting hyperspectral exposure: {duration}s, "
            f"gain={gain if gain is not None else self.default_gain}dB, "
            f"binning={binning}x{binning}"
        )

        # Configure exposure parameters
        exposure_ms = duration * 1000.0
        self._camera.set_exposure(int(exposure_ms))

        if gain is not None:
            self._camera.set_gain(float(gain))

        if binning > 1:
            self._camera.set_downsampling(str(binning))

        # Create image buffer
        img = xiapi.Image()

        # Start acquisition
        self._camera.start_acquisition()

        try:
            # Get image
            self._camera.get_image(img, timeout=int(exposure_ms + 5000))

            # Generate save path
            if save_path is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                save_path = Path(f"ximea_hyperspectral_{timestamp}.tiff")

            # Save image (format depends on output_format setting)
            self._save_hyperspectral_image(img, save_path)

            self.logger.info(f"Hyperspectral image saved to: {save_path}")
            return save_path

        finally:
            # Stop acquisition
            self._camera.stop_acquisition()

            # Reset binning if changed
            if binning > 1:
                self._camera.set_downsampling("1")

    def abort_exposure(self):
        """Abort the current exposure if one is in progress."""
        if self.is_connected() and self._camera is not None:
            try:
                self._camera.stop_acquisition()
                self.logger.info("Ximea exposure aborted")
            except Exception as e:
                self.logger.error(f"Error aborting exposure: {e}")

    def get_temperature(self) -> Optional[float]:
        """Get the current camera sensor temperature.

        Returns:
            Temperature in degrees Celsius, or None if not available
        """
        if not self.is_connected():
            return None

        try:
            # Ximea cameras report temperature in Celsius
            temp = self._camera.get_temp()
            return float(temp)
        except Exception as e:
            self.logger.warning(f"Could not read camera temperature: {e}")
            return None

    def set_temperature(self, temperature: float) -> bool:
        """Set the target camera sensor temperature.

        Note: Most Ximea cameras do not support active cooling.

        Args:
            temperature: Target temperature in degrees Celsius

        Returns:
            False (Ximea cameras typically don't support temperature control)
        """
        self.logger.warning("Ximea cameras do not support temperature control")
        return False

    def start_cooling(self) -> bool:
        """Enable camera cooling system.

        Returns:
            False (Ximea cameras typically don't have active cooling)
        """
        self.logger.warning("Ximea cameras do not have active cooling")
        return False

    def stop_cooling(self) -> bool:
        """Disable camera cooling system.

        Returns:
            False (Ximea cameras typically don't have active cooling)
        """
        return False

    def get_camera_info(self) -> dict:
        """Get camera capabilities and information.

        Returns:
            Dictionary containing camera specs
        """
        return self._camera_info.copy()

    # Helper methods

    def _configure_camera(self):
        """Configure camera with default settings."""
        if self._camera is None:
            return

        try:
            # Set default exposure
            self._camera.set_exposure(int(self.default_exposure_ms))

            # Set default gain
            self._camera.set_gain(self.default_gain)

            # Set image format
            # For hyperspectral, typically use RAW16 or RAW8
            self._camera.set_imgdataformat("XI_RAW16")

            self.logger.info("Ximea camera configured with default settings")

        except Exception as e:
            self.logger.warning(f"Error configuring camera settings: {e}")

    def _read_camera_info(self) -> dict:
        """Read camera information and capabilities."""
        info = {}

        if self._camera is None:
            return info

        try:
            info["model"] = (
                self._camera.get_device_name().decode()
                if hasattr(self._camera.get_device_name(), "decode")
                else str(self._camera.get_device_name())
            )
            info["serial_number"] = (
                self._camera.get_device_sn().decode()
                if hasattr(self._camera.get_device_sn(), "decode")
                else str(self._camera.get_device_sn())
            )
            info["width"] = self._camera.get_width()
            info["height"] = self._camera.get_height()
            info["pixel_size_um"] = 3.45  # MQ series typically 3.45µm
            info["bit_depth"] = 12  # MQ series typically 12-bit
            info["spectral_bands"] = self.spectral_bands
            info["type"] = "hyperspectral"

        except Exception as e:
            self.logger.warning(f"Error reading camera info: {e}")

        return info

    def _save_hyperspectral_image(self, img, save_path: Path):
        """Save hyperspectral image data.

        Args:
            img: Ximea image object
            save_path: Path to save the image
        """
        # This is a stub - actual implementation would depend on desired output format
        # Options:
        # - Raw mosaic TIFF (single 2D image with spectral mosaic pattern)
        # - Demosaiced datacube (3D array: width x height x spectral_bands)
        # - ENVI format for hyperspectral software compatibility

        import numpy as np

        # Get image data as numpy array
        data = img.get_image_data_numpy()

        # TODO: Implement proper hyperspectral data handling based on output_format
        # For now, save as simple TIFF
        try:
            from PIL import Image

            pil_img = Image.fromarray(data)
            pil_img.save(save_path)
        except ImportError:
            # Fallback: save as numpy array
            np.save(save_path.with_suffix(".npy"), data)
            self.logger.warning("PIL not available, saved as .npy instead of TIFF")
