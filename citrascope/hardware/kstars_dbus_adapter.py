import logging
import time
from pathlib import Path

import dbus

from citrascope.hardware.abstract_astro_hardware_adapter import (
    AbstractAstroHardwareAdapter,
    ObservationStrategy,
    SettingSchemaEntry,
)


class KStarsDBusAdapter(AbstractAstroHardwareAdapter):
    """
    Adapter for controlling astronomical equipment through KStars via DBus.

    DBus Interface Documentation (from introspection):

    Mount Interface (org.kde.kstars.Ekos.Mount):
      Methods:
        - slew(double RA, double DEC) -> bool: Slew telescope to coordinates
        - sync(double RA, double DEC) -> bool: Sync telescope at coordinates
        - abort() -> bool: Abort current slew
        - park() -> bool: Park telescope
        - unpark() -> bool: Unpark telescope

      Properties:
        - equatorialCoords (ad): Current RA/Dec as list of doubles [RA, Dec]
        - slewStatus (i): Current slew status (0=idle, others=slewing)
        - status (i): Mount status enumeration
        - canPark (b): Whether mount supports parking

    Scheduler Interface (org.kde.kstars.Ekos.Scheduler):
      Methods:
        - loadScheduler(string fileURL) -> bool: Load ESL scheduler file
        - setSequence(string sequenceFileURL): Set sequence file (ESQ)
        - start(): Start scheduler execution
        - stop(): Stop scheduler
        - removeAllJobs(): Clear all jobs
        - resetAllJobs(): Reset job states

      Properties:
        - status (i): Scheduler state enumeration
        - currentJobName (s): Name of currently executing job
        - jsonJobs (s): JSON representation of all jobs

      Signals:
        - newStatus(int status): Emitted when scheduler state changes
    """

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
        self.bus_name = kwargs.get("bus_name") or "org.kde.kstars"
        self.bus: dbus.SessionBus | None = None
        self.kstars: dbus.Interface | None = None
        self.ekos: dbus.Interface | None = None
        self.mount: dbus.Interface | None = None
        self.camera: dbus.Interface | None = None
        self.scheduler: dbus.Interface | None = None

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
                "description": "D-Bus service name for KStars (default: org.kde.kstars)",
                "required": False,
                "placeholder": "org.kde.kstars",
            }
        ]

    def _do_point_telescope(self, ra: float, dec: float):
        """
        Point the telescope to the specified RA/Dec coordinates.

        Args:
            ra: Right Ascension in degrees
            dec: Declination in degrees

        Raises:
            RuntimeError: If mount is not connected or slew fails
        """
        if not self.mount:
            raise RuntimeError("Mount interface not connected. Call connect() first.")

        try:
            # Convert RA from degrees to hours for KStars (KStars expects RA in hours)
            ra_hours = ra / 15.0

            self.logger.info(f"Slewing telescope to RA={ra_hours:.4f}h ({ra:.4f}°), Dec={dec:.4f}°")

            # Call the slew method via DBus
            success = self.mount.slew(ra_hours, dec)

            if not success:
                raise RuntimeError(f"Mount slew command failed for RA={ra_hours}h, Dec={dec}°")

            self.logger.info("Slew command sent successfully")

        except Exception as e:
            self.logger.error(f"Failed to slew telescope: {e}")
            raise RuntimeError(f"Telescope slew failed: {e}")

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
        """
        Get the current telescope pointing direction.

        Returns:
            tuple[float, float]: Current (RA, Dec) in degrees

        Raises:
            RuntimeError: If mount is not connected or position query fails
        """
        if not self.mount:
            raise RuntimeError("Mount interface not connected. Call connect() first.")

        assert self.bus is not None

        try:
            # Get the mount object for property access
            mount_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos/Mount")
            props = dbus.Interface(mount_obj, "org.freedesktop.DBus.Properties")

            # Get equatorial coordinates property (returns list [RA in hours, Dec in degrees])
            coords = props.Get("org.kde.kstars.Ekos.Mount", "equatorialCoords")

            if not coords or len(coords) < 2:
                raise RuntimeError("Failed to retrieve valid coordinates from mount")

            # coords[0] is RA in hours, coords[1] is Dec in degrees
            ra_hours = float(coords[0])
            dec_deg = float(coords[1])

            # Convert RA from hours to degrees
            ra_deg = ra_hours * 15.0

            self.logger.debug(f"Current telescope position: RA={ra_deg:.4f}° ({ra_hours:.4f}h), Dec={dec_deg:.4f}°")

            return (ra_deg, dec_deg)

        except Exception as e:
            self.logger.error(f"Failed to get telescope position: {e}")
            raise RuntimeError(f"Failed to get telescope position: {e}")

    def telescope_is_moving(self) -> bool:
        """
        Check if the telescope is currently slewing.

        Returns:
            bool: True if telescope is slewing, False if idle or tracking

        Raises:
            RuntimeError: If mount is not connected or status query fails
        """
        if not self.mount:
            raise RuntimeError("Mount interface not connected. Call connect() first.")

        assert self.bus is not None

        try:
            # Get the mount object for property access
            mount_obj = self.bus.get_object(self.bus_name, "/KStars/Ekos/Mount")
            props = dbus.Interface(mount_obj, "org.freedesktop.DBus.Properties")

            # Get slewStatus property (0 = idle, non-zero = slewing)
            slew_status = props.Get("org.kde.kstars.Ekos.Mount", "slewStatus")

            is_slewing = int(slew_status) != 0

            self.logger.debug(f"Mount slew status: {slew_status} (is_slewing={is_slewing})")

            return is_slewing

        except Exception as e:
            self.logger.error(f"Failed to get telescope slew status: {e}")
            raise RuntimeError(f"Failed to get telescope slew status: {e}")

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
