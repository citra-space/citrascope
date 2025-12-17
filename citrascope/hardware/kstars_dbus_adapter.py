import base64
import logging
import time
from pathlib import Path

from citrascope.hardware.abstract_astro_hardware_adapter import (
    AbstractAstroHardwareAdapter,
    ObservationStrategy,
    SettingSchemaEntry,
)


class KStarsDBusAdapter(AbstractAstroHardwareAdapter):
    """Adapter for controlling astronomical equipment through KStars via DBus."""

    def __init__(self, logger: logging.Logger, images_dir: Path, **kwargs):
        """
        Initialize the KStars DBus adapter.

        Args:
            logger: Logger instance for logging messages
            images_dir: Path to the images directory
            **kwargs: Configuration including bus_name
        """
        super().__init__(images_dir=images_dir)
        self.logger: logging.Logger = logger
        self.bus_name = kwargs.get("bus_name", "org.kde.kstars")
        self.bus = None
        self.kstars = None
        self.ekos = None
        self.mount = None
        self.camera = None
        self.scheduler = None

    @classmethod
    def get_settings_schema(cls) -> list[SettingSchemaEntry]:
        """
        Return a schema describing configurable settings for the KStars DBus adapter.
        """
        return [
            {
                "name": "bus_name",
                "friendly_name": "D-Bus Service Name",
                "type": "str",
                "default": "org.kde.kstars",
                "description": "D-Bus service name for KStars",
                "required": True,
                "placeholder": "org.kde.kstars",
            }
        ]

    def _do_point_telescope(self, ra: float, dec: float):
        raise NotImplementedError

    def get_observation_strategy(self) -> ObservationStrategy:
        return ObservationStrategy.SEQUENCE_TO_CONTROLLER

    def perform_observation_sequence(self, task_id, satellite_data) -> str:
        raise NotImplementedError

    def connect(self) -> bool:
        """
        Connect to KStars via DBus and initialize the Ekos session.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Import dbus here to make it an optional dependency
            try:
                import dbus
            except ImportError:
                self.logger.error("dbus-python is not installed. Install with: pip install dbus-python")
                return False

            # Connect to the session bus
            self.logger.info("Connecting to DBus session bus...")
            self.bus = dbus.SessionBus()

            # Get the KStars service
            try:
                kstars_obj = self.bus.get_object(self.bus_name, "/KStars")
                self.kstars = dbus.Interface(kstars_obj, dbus_interface="org.kde.kstars")
                self.logger.info("Connected to KStars DBus interface")
            except dbus.DBusException as e:
                self.logger.error(f"Failed to connect to KStars: {e}")
                self.logger.error("Make sure KStars is running and DBus is enabled")
                return False

            # Get the Ekos interface
            try:
                ekos_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos")
                self.ekos = dbus.Interface(ekos_obj, dbus_interface="org.kde.kstars.Ekos")
                self.logger.info("Connected to Ekos interface")
            except dbus.DBusException as e:
                self.logger.warning(f"Failed to connect to Ekos interface: {e}")
                self.logger.warning("Attempting to start Ekos...")

                # Try to start Ekos if it's not running
                try:
                    self.kstars.startEkos()
                    time.sleep(2)  # Give Ekos time to start
                    ekos_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos")
                    self.ekos = dbus.Interface(ekos_obj, dbus_interface="org.kde.kstars.Ekos")
                    self.logger.info("Started and connected to Ekos interface")
                except Exception as start_error:
                    self.logger.error(f"Failed to start Ekos: {start_error}")
                    return False

            # Get Mount interface
            try:
                mount_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos/Mount")
                self.mount = dbus.Interface(mount_obj, dbus_interface="org.kde.kstars.Ekos.Mount")
                self.logger.info("Connected to Mount interface")
            except dbus.DBusException as e:
                self.logger.warning(f"Mount interface not available: {e}")

            # Get Camera interface
            try:
                camera_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos/Camera")
                self.camera = dbus.Interface(camera_obj, dbus_interface="org.kde.kstars.Ekos.Camera")
                self.logger.info("Connected to Camera interface")
            except dbus.DBusException as e:
                self.logger.warning(f"Camera interface not available: {e}")

            # Get Scheduler/Sequence interface
            try:
                scheduler_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos/Scheduler")
                self.scheduler = dbus.Interface(scheduler_obj, dbus_interface="org.kde.kstars.Ekos.Scheduler")
                self.logger.info("Connected to Scheduler interface")
            except dbus.DBusException as e:
                self.logger.warning(f"Scheduler interface not available: {e}")

            self.logger.info("Successfully connected to KStars via DBus")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to KStars via DBus: {e}")
            return False

    def disconnect(self):
        raise NotImplementedError

    def is_telescope_connected(self) -> bool:
        """Check if telescope is connected and responsive."""
        # KStars adapter is incomplete - return False for now
        return self.mount is not None

    def is_camera_connected(self) -> bool:
        """Check if camera is connected and responsive."""
        # KStars adapter is incomplete - return False for now
        return self.camera is not None

    def list_devices(self) -> list[str]:
        raise NotImplementedError

    def select_telescope(self, device_name: str) -> bool:
        raise NotImplementedError

    def get_telescope_direction(self) -> tuple[float, float]:
        raise NotImplementedError

    def telescope_is_moving(self) -> bool:
        raise NotImplementedError

    def select_camera(self, device_name: str) -> bool:
        raise NotImplementedError

    def take_image(self, task_id: str, exposure_duration_seconds=1) -> str:
        raise NotImplementedError

    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        raise NotImplementedError

    def get_tracking_rate(self) -> tuple[float, float]:
        raise NotImplementedError

    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        raise NotImplementedError
