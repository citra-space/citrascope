"""Tests for CableWrapCheck — shortest-arc math, accumulation, limits, persistence."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from citrascope.safety.cable_wrap_check import (
    HARD_LIMIT_DEG,
    SOFT_LIMIT_DEG,
    CableWrapCheck,
    _shortest_arc,
)
from citrascope.safety.safety_monitor import SafetyAction

# ------------------------------------------------------------------
# Shortest-arc math
# ------------------------------------------------------------------


class TestShortestArc:
    def test_zero_delta(self):
        assert _shortest_arc(100.0, 100.0) == 0.0

    def test_small_cw(self):
        assert _shortest_arc(10.0, 20.0) == pytest.approx(10.0)

    def test_small_ccw(self):
        assert _shortest_arc(20.0, 10.0) == pytest.approx(-10.0)

    def test_wrap_cw(self):
        assert _shortest_arc(350.0, 10.0) == pytest.approx(20.0)

    def test_wrap_ccw(self):
        assert _shortest_arc(10.0, 350.0) == pytest.approx(-20.0)

    def test_half_circle(self):
        result = _shortest_arc(0.0, 180.0)
        assert result == pytest.approx(180.0) or result == pytest.approx(-180.0)

    def test_large_cw_through_zero(self):
        assert _shortest_arc(300.0, 60.0) == pytest.approx(120.0)


# ------------------------------------------------------------------
# CableWrapCheck
# ------------------------------------------------------------------


def _make_mount(mode: str = "altaz", azimuths: list[float] | None = None):
    mount = MagicMock()
    mount.get_mount_mode.return_value = mode
    if azimuths is not None:
        mount.get_azimuth.side_effect = list(azimuths)
    else:
        mount.get_azimuth.return_value = None
    mount.start_move.return_value = True
    mount.stop_move.return_value = True
    mount.stop_tracking.return_value = True
    mount.get_radec.side_effect = Exception("not wired")
    return mount


class TestCableWrapCheckBasics:
    def test_equatorial_mode_always_safe(self):
        mount = _make_mount(mode="equatorial", azimuths=[100.0])
        check = CableWrapCheck(MagicMock(), mount)
        assert check.check() == SafetyAction.SAFE

    def test_no_azimuth_warns_in_altaz(self):
        """Lost azimuth in alt-az mode is WARN (fail-closed)."""
        mount = _make_mount(mode="altaz")
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        assert check.check() == SafetyAction.WARN

    def test_initial_reading_is_safe(self):
        mount = _make_mount(azimuths=[10.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        assert check.check() == SafetyAction.SAFE
        assert check._cumulative_deg == 0.0

    def test_accumulation_basic(self):
        mount = _make_mount(azimuths=[10.0, 30.0, 50.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._observe_once()
        check._observe_once()
        assert check._cumulative_deg == pytest.approx(40.0)

    def test_check_is_pure_read(self):
        """Calling check() multiple times doesn't change internal state."""
        mount = _make_mount(azimuths=[10.0, 30.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._observe_once()
        cumulative_before = check._cumulative_deg
        check.check()
        check.check()
        check.check()
        assert check._cumulative_deg == cumulative_before


class TestCableWrapCheckLimits:
    def test_soft_limit_triggers_queue_stop(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = SOFT_LIMIT_DEG
        assert check.check() == SafetyAction.QUEUE_STOP

    def test_hard_limit_triggers_emergency(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = HARD_LIMIT_DEG
        assert check.check() == SafetyAction.EMERGENCY

    def test_below_soft_limit_is_safe(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = SOFT_LIMIT_DEG - 1
        assert check.check() == SafetyAction.SAFE

    def test_negative_cumulative_soft_limit(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = -SOFT_LIMIT_DEG
        assert check.check() == SafetyAction.QUEUE_STOP


class TestCableWrapCheckReset:
    def test_reset_clears_state(self):
        mount = _make_mount(azimuths=[0.0, 100.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._observe_once()
        assert check._cumulative_deg != 0.0
        check.reset()
        assert check._cumulative_deg == 0.0
        assert check._last_az is None


class TestCableWrapCheckPersistence:
    def test_save_and_load(self, tmp_path: Path):
        state_file = tmp_path / "wrap.json"
        mount = _make_mount(azimuths=[0.0, 100.0])

        check = CableWrapCheck(MagicMock(), mount, state_file=state_file)
        check._observe_once()
        check._last_save_time = 0.0
        check._observe_once()
        assert state_file.exists()

        data = json.loads(state_file.read_text())
        assert data["cumulative_deg"] == pytest.approx(100.0)

        mount2 = _make_mount(azimuths=[100.0])
        check2 = CableWrapCheck(MagicMock(), mount2, state_file=state_file)
        assert check2._cumulative_deg == pytest.approx(100.0)

    def test_missing_state_file_warns(self, tmp_path: Path):
        state_file = tmp_path / "nonexistent.json"
        logger = MagicMock()
        mount = _make_mount(azimuths=[0.0])
        CableWrapCheck(logger, mount, state_file=state_file)
        logger.warning.assert_called_once()


class TestCableWrapCheckProposedAction:
    def test_slew_allowed_with_plenty_of_headroom(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        assert check.check_proposed_action("slew") is True

    def test_slew_blocked_at_soft_limit(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = SOFT_LIMIT_DEG
        assert check.check_proposed_action("slew") is False

    def test_slew_allowed_just_below_soft_limit(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = SOFT_LIMIT_DEG - 1
        assert check.check_proposed_action("slew") is True

    def test_slew_blocked_during_unwind(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._unwinding = True
        assert check.check_proposed_action("slew") is False

    def test_non_slew_allowed_during_unwind(self):
        """Non-slew actions are still blocked during unwind (safety blanket)."""
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._unwinding = True
        assert check.check_proposed_action("capture") is False

    def test_capture_allowed_below_soft_limit(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        assert check.check_proposed_action("capture") is True


class TestCableWrapCheckUnwindBehavior:
    def test_check_returns_queue_stop_during_unwind(self):
        """During unwind, check() returns QUEUE_STOP (not EMERGENCY) so the
        watchdog doesn't fire abort_slew and fight the unwind."""
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._unwinding = True
        assert check.check() == SafetyAction.QUEUE_STOP

    def test_execute_action_guards_double_entry(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._unwinding = True
        check.execute_action()
        mount.stop_tracking.assert_not_called()

    def test_observe_once_yields_during_unwind(self):
        """Observer thread should not accumulate while unwind is active."""
        mount = _make_mount(azimuths=[10.0, 30.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._unwinding = True
        check._observe_once()
        assert check._cumulative_deg == 0.0


class TestCableWrapStallDetection:
    """Stall detection during unwind must handle the 0/360 azimuth boundary."""

    def test_stall_detected_near_zero_boundary(self):
        """Readings like [359.5, 0.0, 0.5] span only 1° of real motion
        but 359.5° of raw difference. The stall detector must use wrapped
        deltas, not raw span, to correctly identify this as movement."""
        azimuths = [
            0.0,  # initial baseline for _observe_once()
            0.0,  # start logging get_azimuth
            0.0,  # first poll
            359.5,
            0.0,
            0.5,
            0.5,  # end logging get_azimuth
        ]
        mount = _make_mount(azimuths=azimuths)
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = 280.0

        check.execute_action()
        mount.stop_move.assert_called_once()

    def test_real_motion_not_flagged_as_stall(self):
        """Readings with >1° steps should NOT trigger stall detection,
        even near the 0/360 boundary."""
        azimuths = [
            10.0,  # baseline for _observe_once()
            10.0,  # start logging get_azimuth
            10.0,  # first poll
            7.0,
            4.0,
            1.0,
            1.0,  # end logging get_azimuth
        ]
        mount = _make_mount(azimuths=azimuths)
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = 8.0

        check.execute_action()
        mount.stop_move.assert_called_once()
        logger = check._logger
        for call in logger.error.call_args_list:
            assert "stall" not in str(call).lower()


class TestCableWrapCheckUnwindReset:
    """Unwind should only reset cumulative on convergence, not on failure."""

    def test_convergence_resets_cumulative(self):
        """When the unwind converges, cumulative is reset to 0."""
        azimuths = [
            10.0,  # baseline for _observe_once()
            10.0,  # _do_unwind: start_az
            10.0,  # poll 1
            7.0,  # poll 2
            4.0,  # poll 3 — cumulative drops below _CONVERGENCE_DEG
            4.0,  # finally: end_az
        ]
        mount = _make_mount(azimuths=azimuths)
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = 8.0

        check.execute_action()
        assert check._cumulative_deg == 0.0

    def test_stall_preserves_cumulative(self):
        """When unwind stalls, cumulative is NOT reset."""
        azimuths = [
            0.0,  # baseline for _observe_once()
            0.0,  # _do_unwind: start_az
            0.0,  # poll 1
            0.0,  # poll 2
            0.0,  # poll 3 — stall detected (0° max step over 3 readings)
            0.0,  # finally: end_az
        ]
        mount = _make_mount(azimuths=azimuths)
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = 250.0

        check.execute_action()
        assert check._cumulative_deg == pytest.approx(250.0)

    def test_lost_azimuth_preserves_cumulative(self):
        """When azimuth reading is lost during unwind, cumulative is preserved."""
        azimuths = [
            10.0,  # baseline for _observe_once()
            10.0,  # _do_unwind: start_az
            None,  # poll 1 — lost azimuth
            None,  # finally: end_az
        ]
        mount = _make_mount(azimuths=azimuths)
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        check._cumulative_deg = 250.0

        check.execute_action()
        assert check._cumulative_deg == pytest.approx(250.0)


class TestCableWrapCheckStatus:
    def test_get_status(self):
        mount = _make_mount(azimuths=[0.0])
        check = CableWrapCheck(MagicMock(), mount)
        check._observe_once()
        status = check.get_status()
        assert status["name"] == "cable_wrap"
        assert "cumulative_deg" in status
        assert status["soft_limit"] == SOFT_LIMIT_DEG
        assert status["hard_limit"] == HARD_LIMIT_DEG


class TestCableWrapObserverLifecycle:
    def test_start_stop(self):
        mount = _make_mount(azimuths=[10.0] * 100)
        check = CableWrapCheck(MagicMock(), mount)
        check.start()
        assert check._observe_thread is not None
        assert check._observe_thread.is_alive()
        check.stop()
        assert check._observe_thread is None

    def test_start_is_idempotent(self):
        mount = _make_mount(azimuths=[10.0] * 100)
        check = CableWrapCheck(MagicMock(), mount)
        check.start()
        thread = check._observe_thread
        check.start()
        assert check._observe_thread is thread
        check.stop()
