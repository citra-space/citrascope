"""ZWO AM3/AM5/AM7 serial protocol — command generation and response parsing.

The protocol is a modified Meade LX200 text protocol.  Commands are sent as
``:XX#`` strings; responses (when expected) are ``#``-terminated.

This module contains **only** pure functions and enums — no I/O, no state.
It is safe to import and unit-test without any hardware present.

Reference material:
  - ZWO Mount Serial Communication Protocol v2.1 (official)
  - Undocumented commands catalogue from INDIGO project
  - jmcguigs/zwo-control-rs  (Rust reference implementation)
"""

from __future__ import annotations

import math
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    """Cardinal direction for manual-motion and guide-pulse commands."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"

    @property
    def opposite(self) -> Direction:
        _opposites = {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.EAST: Direction.WEST,
            Direction.WEST: Direction.EAST,
        }
        return _opposites[self]


class TrackingRate(str, Enum):
    """Tracking-rate presets understood by the mount firmware."""

    SIDEREAL = "sidereal"
    LUNAR = "lunar"
    SOLAR = "solar"
    OFF = "off"


class MountMode(str, Enum):
    """Physical mount operating mode."""

    ALTAZ = "altaz"
    EQUATORIAL = "equatorial"
    UNKNOWN = "unknown"


class SlewRate:
    """Slew-speed preset on a 0-9 scale.

    Rate mappings (approximate):
      0       — guide rate  (~0.5× sidereal)
      1-3     — centering    (1-8× sidereal)
      4-6     — find         (16-64× sidereal)
      7-9     — slew         (up to 1440× sidereal)
    """

    GUIDE = 0
    CENTER = 3
    FIND = 6
    MAX = 9

    def __init__(self, value: int = 6) -> None:
        self.value = max(0, min(9, value))

    def __repr__(self) -> str:
        return f"SlewRate({self.value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SlewRate):
            return self.value == other.value
        return NotImplemented


# ---------------------------------------------------------------------------
# Command generation — returns the raw command string to send.
# ---------------------------------------------------------------------------


class ZwoAmCommands:
    """Pure-function command builders for the ZWO AM serial protocol."""

    # --- Getters (expect a response) ---

    @staticmethod
    def get_version() -> str:
        return ":GV#"

    @staticmethod
    def get_mount_model() -> str:
        return ":GVP#"

    @staticmethod
    def get_ra() -> str:
        """Response: ``HH:MM:SS#``"""
        return ":GR#"

    @staticmethod
    def get_dec() -> str:
        """Response: ``sDD*MM:SS#``"""
        return ":GD#"

    @staticmethod
    def get_azimuth() -> str:
        return ":GZ#"

    @staticmethod
    def get_altitude() -> str:
        return ":GA#"

    @staticmethod
    def get_sidereal_time() -> str:
        return ":GS#"

    @staticmethod
    def get_latitude() -> str:
        return ":Gt#"

    @staticmethod
    def get_longitude() -> str:
        return ":Gg#"

    @staticmethod
    def get_guide_rate() -> str:
        return ":Ggr#"

    @staticmethod
    def get_tracking_status() -> str:
        """Response: ``0#`` or ``1#``."""
        return ":GAT#"

    @staticmethod
    def get_status() -> str:
        """Response: status flags — ``n`` not tracking, ``N`` not slewing,
        ``H`` at home, ``G`` equatorial, ``Z`` altaz."""
        return ":GU#"

    @staticmethod
    def get_pier_side() -> str:
        return ":Gm#"

    @staticmethod
    def get_meridian_settings() -> str:
        return ":GTa#"

    # --- Target-coordinate setters (return ``1``/``0``) ---

    @staticmethod
    def set_target_ra(hours: int, minutes: int, seconds: int) -> str:
        return f":Sr{hours:02d}:{minutes:02d}:{seconds:02d}#"

    @staticmethod
    def set_target_ra_decimal(ra_hours: float) -> str:
        """Build ``:SrHH:MM:SS#`` from decimal hours."""
        total_seconds = round(ra_hours * 3600.0)
        h = (total_seconds // 3600) % 24
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f":Sr{h:02d}:{m:02d}:{s:02d}#"

    @staticmethod
    def set_target_dec(degrees: int, minutes: int, seconds: int) -> str:
        sign = "+" if degrees >= 0 else "-"
        return f":Sd{sign}{abs(degrees):02d}*{minutes:02d}:{seconds:02d}#"

    @staticmethod
    def set_target_dec_decimal(dec_degrees: float) -> str:
        """Build ``:SdsDD*MM:SS#`` from decimal degrees."""
        sign = "+" if dec_degrees >= 0.0 else "-"
        total_arcsec = round(abs(dec_degrees) * 3600.0)
        d = total_arcsec // 3600
        m = (total_arcsec % 3600) // 60
        s = total_arcsec % 60
        return f":Sd{sign}{d:02d}*{m:02d}:{s:02d}#"

    @staticmethod
    def set_target_azimuth_decimal(az_degrees: float) -> str:
        az = az_degrees % 360.0 if az_degrees >= 0 else (az_degrees + 360.0)
        total_arcsec = round(az * 3600.0)
        d = (total_arcsec // 3600) % 360
        m = (total_arcsec % 3600) // 60
        s = total_arcsec % 60
        return f":Sz{d:03d}*{m:02d}:{s:02d}#"

    @staticmethod
    def set_target_altitude_decimal(alt_degrees: float) -> str:
        sign = "+" if alt_degrees >= 0.0 else "-"
        total_arcsec = round(abs(alt_degrees) * 3600.0)
        d = total_arcsec // 3600
        m = (total_arcsec % 3600) // 60
        s = total_arcsec % 60
        return f":Sa{sign}{d}*{m:02d}:{s:02d}#"

    # --- GoTo / Sync ---

    @staticmethod
    def goto() -> str:
        """Initiate slew to previously-set target.
        Response: ``0`` success, ``1``-``7`` various errors."""
        return ":MS#"

    @staticmethod
    def sync() -> str:
        """Sync mount model to previously-set target coordinates."""
        return ":CM#"

    @staticmethod
    def stop_all() -> str:
        return ":Q#"

    # --- Manual motion (fire-and-forget) ---

    @staticmethod
    def move_direction(direction: Direction) -> str:
        _cmds = {
            Direction.NORTH: ":Mn#",
            Direction.SOUTH: ":Ms#",
            Direction.EAST: ":Me#",
            Direction.WEST: ":Mw#",
        }
        return _cmds[direction]

    @staticmethod
    def stop_direction(direction: Direction) -> str:
        _cmds = {
            Direction.NORTH: ":Qn#",
            Direction.SOUTH: ":Qs#",
            Direction.EAST: ":Qe#",
            Direction.WEST: ":Qw#",
        }
        return _cmds[direction]

    @staticmethod
    def set_slew_rate(rate: SlewRate | int) -> str:
        v = rate.value if isinstance(rate, SlewRate) else max(0, min(9, rate))
        return f":R{v}#"

    # --- Guiding (fire-and-forget) ---

    @staticmethod
    def set_guide_rate(rate: float) -> str:
        """Rate is a fraction of sidereal, 0.1 – 0.9."""
        clamped = max(0.1, min(0.9, rate))
        return f":Rg{clamped:.1f}#"

    @staticmethod
    def guide_pulse(direction: Direction, duration_ms: int) -> str:
        suffix = {
            Direction.NORTH: "n",
            Direction.SOUTH: "s",
            Direction.EAST: "e",
            Direction.WEST: "w",
        }[direction]
        ms = max(0, min(9999, duration_ms))
        return f":Mg{suffix}{ms:04d}#"

    # --- Tracking (fire-and-forget) ---

    @staticmethod
    def tracking_on() -> str:
        return ":Te#"

    @staticmethod
    def tracking_off() -> str:
        return ":Td#"

    @staticmethod
    def set_tracking_rate(rate: TrackingRate) -> str:
        _cmds = {
            TrackingRate.SIDEREAL: ":TQ#",
            TrackingRate.LUNAR: ":TL#",
            TrackingRate.SOLAR: ":TS#",
            TrackingRate.OFF: ":Td#",
        }
        return _cmds[rate]

    # --- Home / Park (fire-and-forget) ---

    @staticmethod
    def find_home() -> str:
        return ":hC#"

    @staticmethod
    def goto_park() -> str:
        return ":hP#"

    @staticmethod
    def unpark() -> str:
        return ":hR#"

    @staticmethod
    def clear_alignment() -> str:
        return ":SRC#"

    # --- Mount mode (fire-and-forget) ---

    @staticmethod
    def set_altaz_mode() -> str:
        return ":AA#"

    @staticmethod
    def set_polar_mode() -> str:
        return ":AP#"

    # --- Site / time setters (return ``1``/``0``) ---

    @staticmethod
    def set_latitude(latitude: float) -> str:
        sign = "+" if latitude >= 0.0 else "-"
        total_arcmin = round(abs(latitude) * 60.0)
        d = total_arcmin // 60
        m = total_arcmin % 60
        return f":St{sign}{d}*{m:02d}#"

    @staticmethod
    def set_longitude(longitude: float) -> str:
        lon = longitude + 360.0 if longitude < 0.0 else longitude
        total_arcmin = round(lon * 60.0)
        d = total_arcmin // 60
        m = total_arcmin % 60
        return f":Sg{d:03d}*{m:02d}#"

    @staticmethod
    def set_date(month: int, day: int, year: int) -> str:
        return f":SC{month:02d}/{day:02d}/{year % 100:02d}#"

    @staticmethod
    def set_time(hour: int, minute: int, second: int) -> str:
        return f":SL{hour:02d}:{minute:02d}:{second:02d}#"

    @staticmethod
    def set_timezone(offset: int) -> str:
        sign = "+" if offset >= 0 else "-"
        return f":SG{sign}{abs(offset):02d}#"

    # --- Meridian / buzzer ---

    @staticmethod
    def set_meridian_action(action: int) -> str:
        """0 = stop at meridian, 1 = flip."""
        return f":STa{min(1, action)}#"

    @staticmethod
    def set_buzzer_volume(volume: int) -> str:
        return f":SBu{min(2, volume)}#"


# ---------------------------------------------------------------------------
# Response parsing — all methods accept the raw ``#``-terminated response.
# ---------------------------------------------------------------------------


class ZwoAmResponseParser:
    """Pure-function parsers for ZWO AM mount responses."""

    @staticmethod
    def parse_bool(response: str) -> bool | None:
        """Parse ``0#`` / ``1#`` (or without ``#``)."""
        trimmed = response.strip().rstrip("#")
        if trimmed == "1":
            return True
        if trimmed == "0":
            return False
        return None

    @staticmethod
    def parse_ra(response: str) -> tuple[int, int, float] | None:
        """Parse ``HH:MM:SS#`` → (hours, minutes, seconds)."""
        trimmed = response.strip().rstrip("#")
        parts = trimmed.split(":")
        try:
            if len(parts) >= 3:
                return int(parts[0]), int(parts[1]), float(parts[2])
            if len(parts) == 2:
                h = int(parts[0])
                min_frac = float(parts[1])
                m = int(min_frac)
                s = (min_frac - m) * 60.0
                return h, m, s
        except ValueError:
            pass
        return None

    @staticmethod
    def parse_dec(response: str) -> tuple[float, int, float] | None:
        """Parse Dec response → (signed_degrees, minutes, seconds).

        Accepts both ``sDD*MM:SS#`` (standard LX200) and ``sDD:MM:SS#``
        (colon-only variant seen on some ZWO firmware versions).

        Degrees is a float so the sign survives even when degrees == 0
        (e.g. ``-00*30:00`` → ``-0.0, 30, 0.0``).
        """
        trimmed = response.strip().rstrip("#")

        sign: float = 1.0
        rest = trimmed
        if trimmed.startswith("+"):
            rest = trimmed[1:]
        elif trimmed.startswith("-"):
            sign = -1.0
            rest = trimmed[1:]

        rest = rest.replace("°", "*")
        star_parts = rest.split("*")
        if len(star_parts) >= 2:
            try:
                degrees = int(star_parts[0])
                min_sec = star_parts[1].split(":")
                minutes = int(min_sec[0])
                seconds = float(min_sec[1]) if len(min_sec) > 1 else 0.0
                return sign * float(degrees), minutes, seconds
            except (ValueError, IndexError):
                return None

        colon_parts = rest.split(":")
        if len(colon_parts) >= 2:
            try:
                degrees = int(colon_parts[0])
                minutes = int(colon_parts[1])
                seconds = float(colon_parts[2]) if len(colon_parts) > 2 else 0.0
                return sign * float(degrees), minutes, seconds
            except (ValueError, IndexError):
                return None

        return None

    @staticmethod
    def parse_azimuth(response: str) -> tuple[int, int, float] | None:
        """Parse ``DDD*MM:SS#`` → (degrees, minutes, seconds)."""
        trimmed = response.strip().rstrip("#").replace("°", "*")
        star_parts = trimmed.split("*")
        if len(star_parts) < 2:
            return None
        try:
            degrees = int(star_parts[0])
            min_sec = star_parts[1].split(":")
            minutes = int(min_sec[0])
            seconds = float(min_sec[1]) if len(min_sec) > 1 else 0.0
            return degrees, minutes, seconds
        except (ValueError, IndexError):
            return None

    @staticmethod
    def parse_goto_response(response: str) -> str | None:
        """Parse GoTo response.  Returns ``None`` on success, error string otherwise."""
        trimmed = response.strip().rstrip("#")
        _errors = {
            "0": None,
            "1": "Object below horizon",
            "2": "Object below minimum elevation",
            "4": "Position unreachable",
            "5": "Not aligned",
            "6": "Outside limits",
            "7": "Pier side limit",
            "e1": "Object below horizon",
            "e2": "Object below minimum elevation",
            "e4": "Position unreachable",
            "e5": "Not aligned",
            "e6": "Outside limits",
            "e7": "Pier side limit",
        }
        return _errors.get(trimmed, f"Unknown goto error: {trimmed}")

    @staticmethod
    def parse_status(response: str) -> tuple[bool, bool, bool, MountMode]:
        """Parse ``:GU#`` flags → (tracking, slewing, at_home, mount_mode)."""
        flags = response.strip().rstrip("#")
        tracking = "n" not in flags
        slewing = "N" not in flags
        at_home = "H" in flags
        if "G" in flags:
            mode = MountMode.EQUATORIAL
        elif "Z" in flags:
            mode = MountMode.ALTAZ
        else:
            mode = MountMode.UNKNOWN
        return tracking, slewing, at_home, mode

    # --- Coordinate helpers ---

    @staticmethod
    def hms_to_decimal_hours(hours: int, minutes: int, seconds: float) -> float:
        """Convert H:M:S to decimal hours."""
        return hours + minutes / 60.0 + seconds / 3600.0

    @staticmethod
    def dms_to_decimal_degrees(degrees: float, minutes: int, seconds: float) -> float:
        """Convert signed-D:M:S to decimal degrees.

        Uses ``math.copysign`` so that ``-0.0`` from the Dec parser
        correctly yields a negative result.
        """
        sign = math.copysign(1.0, degrees)
        return sign * (abs(degrees) + minutes / 60.0 + seconds / 3600.0)
