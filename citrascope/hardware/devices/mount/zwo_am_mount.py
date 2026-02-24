"""Concrete mount device for ZWO AM3/AM5/AM7 mounts.

Communicates over USB serial or WiFi TCP using the ZWO LX200-variant
protocol.  All public coordinate APIs use **degrees** (project convention);
the RA hours ↔ degrees conversion happens at this boundary.
"""

from __future__ import annotations

import logging
from typing import Any

from citrascope.hardware.abstract_astro_hardware_adapter import SettingSchemaEntry
from citrascope.hardware.devices.mount.abstract_mount import AbstractMount
from citrascope.hardware.devices.mount.zwo_am_protocol import (
    Direction,
    MountMode,
    TrackingRate,
    ZwoAmCommands,
    ZwoAmResponseParser,
)
from citrascope.hardware.devices.mount.zwo_am_transport import (
    DEFAULT_BAUD_RATE,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT_S,
    SerialTransport,
    TcpTransport,
    ZwoAmTransport,
)

_TRACKING_RATE_MAP: dict[str, TrackingRate] = {
    "sidereal": TrackingRate.SIDEREAL,
    "lunar": TrackingRate.LUNAR,
    "solar": TrackingRate.SOLAR,
}

_ZWO_USB_VID = 0x03C3

_KNOWN_USB_VENDORS: dict[int, str] = {
    _ZWO_USB_VID: "ZWO",
    0x0403: "FTDI",
    0x067B: "Prolific",
    0x10C4: "Silicon Labs",
    0x1A86: "QinHeng",
}


class ZwoAmMount(AbstractMount):
    """ZWO AM3/AM5/AM7 mount controlled via serial (USB) or TCP (WiFi).

    Configuration kwargs:
        connection_type: ``"serial"`` (default) or ``"tcp"``
        port:            Serial device path, e.g. ``/dev/ttyUSB0`` or ``COM3``
        baud_rate:       Serial baud rate (default 9600)
        tcp_host:        WiFi hostname/IP when connection_type is ``tcp``
        tcp_port:        WiFi TCP port when connection_type is ``tcp``
        timeout:         Command timeout in seconds (default 2.0)
        retry_count:     Retries per command (default 3)
    """

    _port_cache: list[dict[str, str]] | None = None
    _port_cache_timestamp: float = 0
    _port_cache_ttl: float = 1.0

    @classmethod
    def _detect_serial_ports(cls) -> list[dict[str, str]]:
        """Enumerate serial ports with friendly labels.

        ZWO devices (VID 0x03C3) are labelled with their USB product name.
        Other common astronomy USB-serial adapters get vendor-tagged labels.
        Results are cached briefly to avoid repeated USB enumeration.
        """
        import time

        cache_age = time.time() - cls._port_cache_timestamp
        if cls._port_cache is not None and cache_age < cls._port_cache_ttl:
            return cls._port_cache

        ports: list[dict[str, str]] = []
        try:
            from serial.tools.list_ports import comports  # type: ignore[reportMissingImports]

            for info in sorted(comports()):
                vendor = _KNOWN_USB_VENDORS.get(info.vid) if info.vid else None
                product = info.product or ""

                if info.vid == _ZWO_USB_VID:
                    if product and not product.upper().startswith("ZWO"):
                        label = f"ZWO {product} ({info.device})"
                    elif product:
                        label = f"{product} ({info.device})"
                    else:
                        label = f"ZWO Device ({info.device})"
                elif vendor and product:
                    label = f"{product} ({info.device})"
                elif vendor:
                    label = f"{vendor} Adapter ({info.device})"
                elif info.description and info.description != "n/a":
                    label = f"{info.description} ({info.device})"
                else:
                    label = info.device

                ports.append({"value": info.device, "label": label})

        except ImportError:
            pass
        except Exception:
            pass

        if not ports:
            ports.append({"value": "/dev/ttyUSB0", "label": "/dev/ttyUSB0 (default)"})

        cls._port_cache = ports
        cls._port_cache_timestamp = time.time()
        return ports

    def __init__(self, logger: logging.Logger, **kwargs) -> None:
        super().__init__(logger=logger, **kwargs)

        conn_type = kwargs.get("connection_type", "serial")
        timeout = float(kwargs.get("timeout", DEFAULT_TIMEOUT_S))
        retries = int(kwargs.get("retry_count", DEFAULT_RETRY_COUNT))

        self._transport: ZwoAmTransport
        if conn_type == "tcp":
            host = str(kwargs.get("tcp_host", "10.0.0.1"))
            port = int(kwargs.get("tcp_port", 4030))
            self._transport = TcpTransport(host=host, port=port, timeout_s=timeout, retry_count=retries)
        else:
            serial_port = str(kwargs.get("port", "/dev/ttyUSB0"))
            baud = int(kwargs.get("baud_rate", DEFAULT_BAUD_RATE))
            self._transport = SerialTransport(port=serial_port, baud_rate=baud, timeout_s=timeout, retry_count=retries)

        self._model: str = ""
        self._firmware: str = ""

    # ------------------------------------------------------------------
    # AbstractHardwareDevice
    # ------------------------------------------------------------------

    @classmethod
    def get_friendly_name(cls) -> str:
        return "ZWO AM3/AM5/AM7 Mount"

    @classmethod
    def get_dependencies(cls) -> dict[str, str | list[str]]:
        return {
            "packages": ["serial"],
            "install_extra": "zwo-mount",
        }

    @classmethod
    def get_settings_schema(cls) -> list[SettingSchemaEntry]:
        schema: list[Any] = [
            {
                "name": "connection_type",
                "friendly_name": "Connection Type",
                "type": "str",
                "default": "serial",
                "description": "How to connect to the mount",
                "required": True,
                "options": [
                    {"value": "serial", "label": "USB Serial"},
                    {"value": "tcp", "label": "WiFi (TCP)"},
                ],
                "group": "Mount",
            },
            {
                "name": "port",
                "friendly_name": "Serial Port",
                "type": "str",
                "default": cls._detect_serial_ports()[0]["value"],
                "description": "Serial port for the mount",
                "required": False,
                "options": cls._detect_serial_ports(),
                "group": "Mount",
                "visible_when": {"field": "connection_type", "value": "serial"},
            },
            {
                "name": "baud_rate",
                "friendly_name": "Baud Rate",
                "type": "int",
                "default": str(DEFAULT_BAUD_RATE),
                "description": "Serial baud rate (ZWO default is 9600)",
                "required": False,
                "group": "Mount",
                "visible_when": {"field": "connection_type", "value": "serial"},
            },
            {
                "name": "tcp_host",
                "friendly_name": "WiFi Host",
                "type": "str",
                "default": "10.0.0.1",
                "description": "Mount WiFi IP address or hostname",
                "required": False,
                "group": "Mount",
                "visible_when": {"field": "connection_type", "value": "tcp"},
            },
            {
                "name": "tcp_port",
                "friendly_name": "WiFi Port",
                "type": "int",
                "default": "4030",
                "description": "TCP port for WiFi serial bridge",
                "required": False,
                "group": "Mount",
                "visible_when": {"field": "connection_type", "value": "tcp"},
            },
            {
                "name": "timeout",
                "friendly_name": "Command Timeout",
                "type": "float",
                "default": str(DEFAULT_TIMEOUT_S),
                "description": "Seconds to wait for a command response",
                "required": False,
                "group": "Mount",
            },
            {
                "name": "retry_count",
                "friendly_name": "Retry Count",
                "type": "int",
                "default": str(DEFAULT_RETRY_COUNT),
                "description": "Number of retries for failed commands",
                "required": False,
                "group": "Mount",
            },
        ]
        return schema

    def connect(self) -> bool:
        try:
            self._transport.open()
        except Exception as exc:
            self.logger.error("Failed to open transport: %s", exc)
            return False

        try:
            self._model = self._transport.send_command_with_retry(ZwoAmCommands.get_mount_model()).rstrip("#")
            self.logger.info("Connected to mount: %s", self._model)
        except Exception as exc:
            self.logger.error("Mount handshake failed: %s", exc)
            self._transport.close()
            return False

        try:
            self._firmware = self._transport.send_command_with_retry(ZwoAmCommands.get_version()).rstrip("#")
            self.logger.info("Firmware version: %s", self._firmware)
        except Exception:
            self.logger.warning("Could not read firmware version")

        return True

    def disconnect(self) -> None:
        self._transport.close()
        self.logger.info("Mount disconnected")

    def is_connected(self) -> bool:
        return self._transport.is_open()

    # ------------------------------------------------------------------
    # Core mount operations  (AbstractMount abstract methods)
    # ------------------------------------------------------------------

    def slew_to_radec(self, ra: float, dec: float) -> bool:
        ra_hours = ra / 15.0

        ra_cmd = ZwoAmCommands.set_target_ra_decimal(ra_hours)
        if not self._transport.send_command_bool_with_retry(ra_cmd):
            self.logger.error("Mount rejected RA target %.4f°", ra)
            return False

        dec_cmd = ZwoAmCommands.set_target_dec_decimal(dec)
        if not self._transport.send_command_bool_with_retry(dec_cmd):
            self.logger.error("Mount rejected Dec target %.4f°", dec)
            return False

        response = self._transport.send_command_with_retry(ZwoAmCommands.goto())
        error = ZwoAmResponseParser.parse_goto_response(response)
        if error is not None:
            self.logger.error("GoTo failed: %s", error)
            return False

        self.logger.info("Slewing to RA=%.4f° Dec=%.4f°", ra, dec)
        return True

    def is_slewing(self) -> bool:
        _, slewing, _, _ = self._get_status_flags()
        return slewing

    def abort_slew(self) -> None:
        self._transport.send_command_no_response(ZwoAmCommands.stop_all())
        self.logger.info("Slew aborted")

    def get_radec(self) -> tuple[float, float]:
        ra_resp = self._transport.send_command_with_retry(ZwoAmCommands.get_ra())
        parsed_ra = ZwoAmResponseParser.parse_ra(ra_resp)
        if parsed_ra is None:
            raise RuntimeError(f"Failed to parse RA response: {ra_resp!r}")
        ra_hours = ZwoAmResponseParser.hms_to_decimal_hours(*parsed_ra)
        ra_deg = ra_hours * 15.0

        dec_resp = self._transport.send_command_with_retry(ZwoAmCommands.get_dec())
        parsed_dec = ZwoAmResponseParser.parse_dec(dec_resp)
        if parsed_dec is None:
            raise RuntimeError(f"Failed to parse Dec response: {dec_resp!r}")
        dec_deg = ZwoAmResponseParser.dms_to_decimal_degrees(*parsed_dec)

        return ra_deg, dec_deg

    def start_tracking(self, rate: str | None = "sidereal") -> bool:
        rate_str = rate or "sidereal"
        track_rate = _TRACKING_RATE_MAP.get(rate_str.lower())
        if track_rate is None:
            self.logger.warning("Unknown tracking rate %r, using sidereal", rate)
            track_rate = TrackingRate.SIDEREAL

        self._transport.send_command_no_response(ZwoAmCommands.set_tracking_rate(track_rate))
        self._transport.send_command_no_response(ZwoAmCommands.tracking_on())
        self.logger.info("Tracking started: %s", track_rate.value)
        return True

    def stop_tracking(self) -> bool:
        self._transport.send_command_no_response(ZwoAmCommands.tracking_off())
        self.logger.info("Tracking stopped")
        return True

    def is_tracking(self) -> bool:
        tracking, _, _, _ = self._get_status_flags()
        return tracking

    def park(self) -> bool:
        self._transport.send_command_no_response(ZwoAmCommands.goto_park())
        self.logger.info("Park initiated")
        return True

    def unpark(self) -> bool:
        self._transport.send_command_no_response(ZwoAmCommands.unpark())
        self.logger.info("Unparked")
        return True

    def is_parked(self) -> bool:
        _, _, at_home, _ = self._get_status_flags()
        return at_home

    def get_mount_info(self) -> dict:
        _, _, _, mode = self._get_status_flags()
        return {
            "model": self._model,
            "firmware": self._firmware,
            "mount_mode": mode.value,
            "supports_sync": True,
            "supports_guide_pulse": True,
            "supports_custom_tracking": False,
        }

    # ------------------------------------------------------------------
    # Optional capabilities (concrete overrides)
    # ------------------------------------------------------------------

    def sync_to_radec(self, ra: float, dec: float) -> bool:
        ra_hours = ra / 15.0

        ra_cmd = ZwoAmCommands.set_target_ra_decimal(ra_hours)
        self._transport.send_command_bool_with_retry(ra_cmd)

        dec_cmd = ZwoAmCommands.set_target_dec_decimal(dec)
        self._transport.send_command_bool_with_retry(dec_cmd)

        self._transport.send_command_with_retry(ZwoAmCommands.sync())
        self.logger.info("Synced to RA=%.4f° Dec=%.4f°", ra, dec)
        return True

    def guide_pulse(self, direction: str, duration_ms: int) -> bool:
        try:
            d = Direction(direction.lower())
        except ValueError:
            self.logger.error("Invalid guide direction: %s", direction)
            return False
        self._transport.send_command_no_response(ZwoAmCommands.guide_pulse(d, duration_ms))
        self.logger.debug("Guide pulse %s %dms", d.value, duration_ms)
        return True

    def set_site_location(self, latitude: float, longitude: float, altitude: float) -> bool:
        lat_cmd = ZwoAmCommands.set_latitude(latitude)
        if not self._transport.send_command_bool_with_retry(lat_cmd):
            self.logger.error("Mount rejected latitude %.4f", latitude)
            return False

        lon_cmd = ZwoAmCommands.set_longitude(longitude)
        if not self._transport.send_command_bool_with_retry(lon_cmd):
            self.logger.error("Mount rejected longitude %.4f", longitude)
            return False

        self.logger.info("Site location set: lat=%.4f° lon=%.4f° alt=%.0fm", latitude, longitude, altitude)
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_status_flags(self) -> tuple[bool, bool, bool, MountMode]:
        resp = self._transport.send_command_with_retry(ZwoAmCommands.get_status())
        return ZwoAmResponseParser.parse_status(resp)
