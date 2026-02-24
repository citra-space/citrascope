"""Tests for ZWO AM mount protocol — command generation and response parsing.

These are pure-function tests that need no hardware.  Command strings and
response formats are validated against the ZWO protocol spec and the
jmcguigs/zwo-control-rs reference implementation.
"""

import pytest

from citrascope.hardware.devices.mount.zwo_am_protocol import (
    Direction,
    MountMode,
    SlewRate,
    TrackingRate,
    ZwoAmCommands,
    ZwoAmResponseParser,
)

# ===================================================================
# Command generation
# ===================================================================


class TestZwoAmCommands:
    # --- target coordinate setters ---

    def test_set_target_ra(self):
        assert ZwoAmCommands.set_target_ra(12, 30, 45) == ":Sr12:30:45#"

    def test_set_target_ra_decimal(self):
        assert ZwoAmCommands.set_target_ra_decimal(12.5) == ":Sr12:30:00#"

    def test_set_target_ra_decimal_zero(self):
        assert ZwoAmCommands.set_target_ra_decimal(0.0) == ":Sr00:00:00#"

    def test_set_target_dec(self):
        assert ZwoAmCommands.set_target_dec(45, 30, 15) == ":Sd+45*30:15#"

    def test_set_target_dec_negative(self):
        assert ZwoAmCommands.set_target_dec(-23, 26, 21) == ":Sd-23*26:21#"

    def test_set_target_dec_decimal(self):
        assert ZwoAmCommands.set_target_dec_decimal(45.5) == ":Sd+45*30:00#"

    def test_set_target_dec_decimal_negative(self):
        assert ZwoAmCommands.set_target_dec_decimal(-23.5) == ":Sd-23*30:00#"

    def test_set_target_dec_decimal_zero(self):
        assert ZwoAmCommands.set_target_dec_decimal(0.0) == ":Sd+00*00:00#"

    # --- azimuth / altitude ---

    def test_set_target_azimuth_decimal(self):
        assert ZwoAmCommands.set_target_azimuth_decimal(180.0) == ":Sz180*00:00#"

    def test_set_target_azimuth_decimal_fraction(self):
        assert ZwoAmCommands.set_target_azimuth_decimal(90.5) == ":Sz090*30:00#"

    def test_set_target_azimuth_decimal_negative_wraps(self):
        assert ZwoAmCommands.set_target_azimuth_decimal(-90.0) == ":Sz270*00:00#"

    def test_set_target_altitude_decimal_positive(self):
        assert ZwoAmCommands.set_target_altitude_decimal(45.0) == ":Sa+45*00:00#"

    def test_set_target_altitude_decimal_negative(self):
        assert ZwoAmCommands.set_target_altitude_decimal(-10.5) == ":Sa-10*30:00#"

    # --- slew / motion ---

    def test_set_slew_rate_max(self):
        assert ZwoAmCommands.set_slew_rate(SlewRate(9)) == ":R9#"

    def test_set_slew_rate_guide(self):
        assert ZwoAmCommands.set_slew_rate(SlewRate(0)) == ":R0#"

    def test_set_slew_rate_int(self):
        assert ZwoAmCommands.set_slew_rate(5) == ":R5#"

    def test_set_slew_rate_clamps(self):
        assert ZwoAmCommands.set_slew_rate(99) == ":R9#"

    # --- guide pulse ---

    def test_guide_pulse_north(self):
        assert ZwoAmCommands.guide_pulse(Direction.NORTH, 500) == ":Mgn0500#"

    def test_guide_pulse_east(self):
        assert ZwoAmCommands.guide_pulse(Direction.EAST, 150) == ":Mge0150#"

    def test_guide_pulse_clamps_max(self):
        assert ZwoAmCommands.guide_pulse(Direction.WEST, 99999) == ":Mgw9999#"

    # --- tracking ---

    def test_tracking_sidereal(self):
        assert ZwoAmCommands.set_tracking_rate(TrackingRate.SIDEREAL) == ":TQ#"

    def test_tracking_lunar(self):
        assert ZwoAmCommands.set_tracking_rate(TrackingRate.LUNAR) == ":TL#"

    def test_tracking_solar(self):
        assert ZwoAmCommands.set_tracking_rate(TrackingRate.SOLAR) == ":TS#"

    def test_tracking_off(self):
        assert ZwoAmCommands.set_tracking_rate(TrackingRate.OFF) == ":Td#"

    def test_tracking_on(self):
        assert ZwoAmCommands.tracking_on() == ":Te#"

    def test_tracking_off_cmd(self):
        assert ZwoAmCommands.tracking_off() == ":Td#"

    # --- site location ---

    def test_set_latitude_positive(self):
        assert ZwoAmCommands.set_latitude(46.5) == ":St+46*30#"

    def test_set_latitude_negative(self):
        assert ZwoAmCommands.set_latitude(-33.75) == ":St-33*45#"

    def test_set_longitude_positive(self):
        assert ZwoAmCommands.set_longitude(6.25) == ":Sg006*15#"

    def test_set_longitude_negative_wraps(self):
        assert ZwoAmCommands.set_longitude(-118.5) == ":Sg241*30#"

    # --- guide rate ---

    def test_set_guide_rate(self):
        assert ZwoAmCommands.set_guide_rate(0.5) == ":Rg0.5#"

    def test_set_guide_rate_clamps(self):
        assert ZwoAmCommands.set_guide_rate(1.5) == ":Rg0.9#"

    # --- goto / sync / stop ---

    def test_goto(self):
        assert ZwoAmCommands.goto() == ":MS#"

    def test_sync(self):
        assert ZwoAmCommands.sync() == ":CM#"

    def test_stop_all(self):
        assert ZwoAmCommands.stop_all() == ":Q#"

    # --- motion directions ---

    def test_move_directions(self):
        assert ZwoAmCommands.move_direction(Direction.NORTH) == ":Mn#"
        assert ZwoAmCommands.move_direction(Direction.SOUTH) == ":Ms#"
        assert ZwoAmCommands.move_direction(Direction.EAST) == ":Me#"
        assert ZwoAmCommands.move_direction(Direction.WEST) == ":Mw#"

    def test_stop_directions(self):
        assert ZwoAmCommands.stop_direction(Direction.NORTH) == ":Qn#"
        assert ZwoAmCommands.stop_direction(Direction.SOUTH) == ":Qs#"
        assert ZwoAmCommands.stop_direction(Direction.EAST) == ":Qe#"
        assert ZwoAmCommands.stop_direction(Direction.WEST) == ":Qw#"

    # --- home / park ---

    def test_park(self):
        assert ZwoAmCommands.goto_park() == ":hP#"

    def test_unpark(self):
        assert ZwoAmCommands.unpark() == ":hR#"

    def test_find_home(self):
        assert ZwoAmCommands.find_home() == ":hC#"

    # --- mount mode ---

    def test_altaz_mode(self):
        assert ZwoAmCommands.set_altaz_mode() == ":AA#"

    def test_polar_mode(self):
        assert ZwoAmCommands.set_polar_mode() == ":AP#"

    # --- getters ---

    def test_getter_commands(self):
        assert ZwoAmCommands.get_ra() == ":GR#"
        assert ZwoAmCommands.get_dec() == ":GD#"
        assert ZwoAmCommands.get_status() == ":GU#"
        assert ZwoAmCommands.get_mount_model() == ":GVP#"
        assert ZwoAmCommands.get_version() == ":GV#"
        assert ZwoAmCommands.get_azimuth() == ":GZ#"
        assert ZwoAmCommands.get_altitude() == ":GA#"

    # --- date / time ---

    def test_set_date(self):
        assert ZwoAmCommands.set_date(3, 15, 2026) == ":SC03/15/26#"

    def test_set_time(self):
        assert ZwoAmCommands.set_time(22, 5, 30) == ":SL22:05:30#"

    def test_set_timezone(self):
        assert ZwoAmCommands.set_timezone(-5) == ":SG-05#"
        assert ZwoAmCommands.set_timezone(2) == ":SG+02#"


# ===================================================================
# Response parsing
# ===================================================================


class TestZwoAmResponseParser:
    # --- boolean ---

    def test_parse_bool_true(self):
        assert ZwoAmResponseParser.parse_bool("1#") is True

    def test_parse_bool_false(self):
        assert ZwoAmResponseParser.parse_bool("0#") is False

    def test_parse_bool_no_hash(self):
        assert ZwoAmResponseParser.parse_bool("1") is True

    def test_parse_bool_invalid(self):
        assert ZwoAmResponseParser.parse_bool("invalid") is None

    # --- RA ---

    def test_parse_ra_hms(self):
        result = ZwoAmResponseParser.parse_ra("12:30:45#")
        assert result is not None
        h, m, s = result
        assert h == 12
        assert m == 30
        assert abs(s - 45.0) < 0.001

    def test_parse_ra_hm_fraction(self):
        result = ZwoAmResponseParser.parse_ra("12:30.5#")
        assert result is not None
        h, m, s = result
        assert h == 12
        assert m == 30
        assert abs(s - 30.0) < 0.1

    def test_parse_ra_invalid(self):
        assert ZwoAmResponseParser.parse_ra("garbage") is None

    # --- Dec ---

    def test_parse_dec_positive(self):
        result = ZwoAmResponseParser.parse_dec("+45*30:15#")
        assert result is not None
        d, m, s = result
        assert d == 45
        assert m == 30
        assert abs(s - 15.0) < 0.001

    def test_parse_dec_negative(self):
        result = ZwoAmResponseParser.parse_dec("-23*26:21#")
        assert result is not None
        d, m, s = result
        assert d == -23
        assert m == 26
        assert abs(s - 21.0) < 0.001

    def test_parse_dec_no_seconds(self):
        result = ZwoAmResponseParser.parse_dec("+45*30#")
        assert result is not None
        d, m, s = result
        assert d == 45
        assert m == 30
        assert s == 0.0

    def test_parse_dec_degree_symbol(self):
        result = ZwoAmResponseParser.parse_dec("+45°30:15#")
        assert result is not None
        assert result[0] == 45

    def test_parse_dec_invalid(self):
        assert ZwoAmResponseParser.parse_dec("garbage") is None

    # --- azimuth ---

    def test_parse_azimuth(self):
        result = ZwoAmResponseParser.parse_azimuth("180*30:45#")
        assert result is not None
        d, m, s = result
        assert d == 180
        assert m == 30
        assert abs(s - 45.0) < 0.001

    # --- goto response ---

    def test_parse_goto_success(self):
        assert ZwoAmResponseParser.parse_goto_response("0#") is None

    def test_parse_goto_below_horizon(self):
        result = ZwoAmResponseParser.parse_goto_response("1#")
        assert result is not None
        assert "horizon" in result.lower()

    def test_parse_goto_pier_limit(self):
        result = ZwoAmResponseParser.parse_goto_response("7#")
        assert result is not None
        assert "pier" in result.lower()

    def test_parse_goto_e7(self):
        result = ZwoAmResponseParser.parse_goto_response("e7#")
        assert result is not None
        assert "pier" in result.lower()

    def test_parse_goto_unknown(self):
        result = ZwoAmResponseParser.parse_goto_response("99#")
        assert result is not None
        assert "unknown" in result.lower()

    # --- status flags ---

    def test_parse_status_tracking_equatorial(self):
        tracking, slewing, at_home, mode = ZwoAmResponseParser.parse_status("NG#")
        assert tracking is True
        assert slewing is False
        assert at_home is False
        assert mode == MountMode.EQUATORIAL

    def test_parse_status_idle_home_altaz(self):
        tracking, slewing, at_home, mode = ZwoAmResponseParser.parse_status("nNHZ#")
        assert tracking is False
        assert slewing is False
        assert at_home is True
        assert mode == MountMode.ALTAZ

    def test_parse_status_slewing(self):
        tracking, slewing, at_home, mode = ZwoAmResponseParser.parse_status("G#")
        assert tracking is True
        assert slewing is True
        assert at_home is False
        assert mode == MountMode.EQUATORIAL

    # --- coordinate helpers ---

    def test_hms_to_decimal_hours(self):
        result = ZwoAmResponseParser.hms_to_decimal_hours(12, 30, 0)
        assert abs(result - 12.5) < 0.0001

    def test_hms_to_decimal_hours_zero(self):
        assert ZwoAmResponseParser.hms_to_decimal_hours(0, 0, 0) == 0.0

    def test_dms_to_decimal_degrees_positive(self):
        result = ZwoAmResponseParser.dms_to_decimal_degrees(45, 30, 0)
        assert abs(result - 45.5) < 0.0001

    def test_dms_to_decimal_degrees_negative(self):
        result = ZwoAmResponseParser.dms_to_decimal_degrees(-23, 30, 0)
        assert abs(result - (-23.5)) < 0.0001


# ===================================================================
# Enums
# ===================================================================


class TestEnums:
    def test_direction_opposite(self):
        assert Direction.NORTH.opposite == Direction.SOUTH
        assert Direction.SOUTH.opposite == Direction.NORTH
        assert Direction.EAST.opposite == Direction.WEST
        assert Direction.WEST.opposite == Direction.EAST

    def test_slew_rate_clamp(self):
        assert SlewRate(10).value == 9
        assert SlewRate(-1).value == 0
        assert SlewRate(5).value == 5

    def test_slew_rate_equality(self):
        assert SlewRate(3) == SlewRate(3)
        assert SlewRate(3) != SlewRate(5)

    def test_slew_rate_constants(self):
        assert SlewRate.GUIDE == 0
        assert SlewRate.CENTER == 3
        assert SlewRate.FIND == 6
        assert SlewRate.MAX == 9


# ===================================================================
# RA degree ↔ hour conversion boundary
# ===================================================================


class TestRaConversionBoundary:
    """Validates the RA degrees → hours → command → parse → hours → degrees
    round-trip that happens at the ZwoAmMount boundary."""

    @pytest.mark.parametrize(
        "ra_deg",
        [0.0, 45.0, 90.0, 180.0, 270.0, 359.0, 187.5],
    )
    def test_ra_roundtrip(self, ra_deg: float):
        ra_hours = ra_deg / 15.0
        cmd = ZwoAmCommands.set_target_ra_decimal(ra_hours)
        # The command encodes hours as HH:MM:SS — parse that back
        # Strip the :Sr prefix and # suffix to get "HH:MM:SS"
        inner = cmd[3:-1]
        parts = inner.split(":")
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        recovered_hours = ZwoAmResponseParser.hms_to_decimal_hours(h, m, s)
        recovered_deg = recovered_hours * 15.0
        # 1-second resolution → worst case 15 arcsec = 0.00417°
        assert abs(recovered_deg - ra_deg) < 0.01, f"{ra_deg}° → {recovered_deg}°"

    @pytest.mark.parametrize(
        "dec_deg",
        [0.0, 45.5, -23.5, 90.0, -90.0, -0.5],
    )
    def test_dec_roundtrip(self, dec_deg: float):
        cmd = ZwoAmCommands.set_target_dec_decimal(dec_deg)
        inner = cmd[3:-1]  # strip :Sd and #
        parsed = ZwoAmResponseParser.parse_dec(inner + "#")
        assert parsed is not None
        recovered = ZwoAmResponseParser.dms_to_decimal_degrees(*parsed)
        assert abs(recovered - dec_deg) < 0.01, f"{dec_deg}° → {recovered}°"
