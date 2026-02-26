"""Tests for SafetyMonitor framework."""

import time
from unittest.mock import MagicMock

from citrascope.safety.safety_monitor import SafetyAction, SafetyCheck, SafetyMonitor


class _StubCheck(SafetyCheck):
    def __init__(self, name: str, action: SafetyAction = SafetyAction.SAFE):
        self._name = name
        self._action = action

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> SafetyAction:
        return self._action


class _BlockingCheck(SafetyCheck):
    """Check that blocks a specific action type."""

    @property
    def name(self) -> str:
        return "blocker"

    def check(self) -> SafetyAction:
        return SafetyAction.SAFE

    def check_proposed_action(self, action_type: str, **kwargs) -> bool:
        return action_type != "slew"


class _ExplodingCheck(SafetyCheck):
    """Check that raises on every call (both check and pre-action gate)."""

    @property
    def name(self) -> str:
        return "exploding"

    def check(self) -> SafetyAction:
        raise RuntimeError("boom")

    def check_proposed_action(self, action_type: str, **kwargs) -> bool:
        raise RuntimeError("boom")


class TestSafetyMonitorEvaluate:
    def test_empty_checks_is_safe(self):
        monitor = SafetyMonitor(MagicMock(), [])
        action, check = monitor.evaluate()
        assert action == SafetyAction.SAFE
        assert check is None

    def test_all_safe_returns_safe(self):
        checks = [_StubCheck("a"), _StubCheck("b")]
        monitor = SafetyMonitor(MagicMock(), checks)
        action, check = monitor.evaluate()
        assert action == SafetyAction.SAFE
        assert check is None

    def test_returns_most_severe(self):
        checks = [
            _StubCheck("safe", SafetyAction.SAFE),
            _StubCheck("warn", SafetyAction.WARN),
            _StubCheck("stop", SafetyAction.QUEUE_STOP),
        ]
        monitor = SafetyMonitor(MagicMock(), checks)
        action, check = monitor.evaluate()
        assert action == SafetyAction.QUEUE_STOP
        assert check is not None
        assert check.name == "stop"

    def test_emergency_trumps_queue_stop(self):
        checks = [
            _StubCheck("stop", SafetyAction.QUEUE_STOP),
            _StubCheck("emergency", SafetyAction.EMERGENCY),
        ]
        monitor = SafetyMonitor(MagicMock(), checks)
        action, check = monitor.evaluate()
        assert action == SafetyAction.EMERGENCY
        assert check.name == "emergency"

    def test_exploding_check_treated_as_queue_stop(self):
        """A check that raises is treated as QUEUE_STOP (fail-closed)."""
        checks = [_ExplodingCheck(), _StubCheck("ok", SafetyAction.WARN)]
        monitor = SafetyMonitor(MagicMock(), checks)
        action, _check = monitor.evaluate()
        assert action == SafetyAction.QUEUE_STOP

    def test_exploding_check_alone_is_queue_stop(self):
        checks = [_ExplodingCheck()]
        monitor = SafetyMonitor(MagicMock(), checks)
        action, _check = monitor.evaluate()
        assert action == SafetyAction.QUEUE_STOP


class TestSafetyMonitorPreActionGate:
    def test_all_safe_allows_action(self):
        checks = [_StubCheck("a"), _StubCheck("b")]
        monitor = SafetyMonitor(MagicMock(), checks)
        assert monitor.is_action_safe("slew", ra=10, dec=20) is True

    def test_blocker_rejects_action(self):
        checks = [_BlockingCheck()]
        monitor = SafetyMonitor(MagicMock(), checks)
        assert monitor.is_action_safe("slew") is False
        assert monitor.is_action_safe("capture") is True

    def test_exploding_check_blocks_action(self):
        """A check that raises during pre-action gate blocks the action (fail-closed)."""
        checks = [_ExplodingCheck()]
        monitor = SafetyMonitor(MagicMock(), checks)
        assert monitor.is_action_safe("slew") is False


class TestSafetyMonitorWatchdog:
    def test_watchdog_starts_and_stops(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("a")])
        monitor.start_watchdog(interval_seconds=0.1)
        time.sleep(0.3)
        assert monitor.watchdog_healthy is True
        monitor.stop_watchdog()

    def test_watchdog_fires_abort_on_emergency(self):
        abort = MagicMock()
        checks = [_StubCheck("crit", SafetyAction.EMERGENCY)]
        monitor = SafetyMonitor(MagicMock(), checks, abort_callback=abort)
        monitor.start_watchdog(interval_seconds=0.1)
        time.sleep(0.3)
        monitor.stop_watchdog()
        assert abort.called

    def test_watchdog_survives_exploding_check(self):
        checks = [_ExplodingCheck()]
        monitor = SafetyMonitor(MagicMock(), checks)
        monitor.start_watchdog(interval_seconds=0.1)
        time.sleep(0.3)
        assert monitor.watchdog_healthy is True
        monitor.stop_watchdog()

    def test_watchdog_healthy_false_before_start(self):
        monitor = SafetyMonitor(MagicMock(), [])
        assert monitor.watchdog_healthy is False


class TestSafetyMonitorGetStatus:
    def test_get_status_uses_cached_action(self):
        """get_status() must use _last_action from evaluate(), not call check() again."""
        call_count = 0

        class _CountingCheck(SafetyCheck):
            @property
            def name(self) -> str:
                return "counting"

            def check(self) -> SafetyAction:
                nonlocal call_count
                call_count += 1
                return SafetyAction.WARN

        checks = [_CountingCheck()]
        monitor = SafetyMonitor(MagicMock(), checks)
        monitor.evaluate()
        assert call_count == 1
        status = monitor.get_status()
        assert call_count == 1
        assert status["checks"][0]["action"] == "warn"

    def test_get_status_before_evaluate_defaults_safe(self):
        checks = [_StubCheck("a", SafetyAction.EMERGENCY)]
        monitor = SafetyMonitor(MagicMock(), checks)
        status = monitor.get_status()
        assert status["checks"][0]["action"] == "safe"


class TestSafetyMonitorGetCheck:
    def test_get_check_found(self):
        checks = [_StubCheck("a"), _StubCheck("b")]
        monitor = SafetyMonitor(MagicMock(), checks)
        assert monitor.get_check("b") is checks[1]

    def test_get_check_not_found(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("a")])
        assert monitor.get_check("missing") is None
