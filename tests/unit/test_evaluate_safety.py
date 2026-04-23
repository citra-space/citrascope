"""Tests for TaskManager._evaluate_safety — emergency imaging queue clear (#315)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from citrasense.safety.safety_monitor import SafetyAction, SafetyCheck, SafetyMonitor


class _StubCheck(SafetyCheck):
    def __init__(self, name: str, action: SafetyAction = SafetyAction.SAFE):
        self._name = name
        self._action = action

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> SafetyAction:
        return self._action


def _make_task_manager(safety_monitor):
    """Build a minimal TaskManager with mocked dependencies."""
    with (
        patch("citrasense.tasks.imaging_queue.ImagingQueue.__init__", return_value=None),
        patch("citrasense.tasks.processing_queue.ProcessingQueue.__init__", return_value=None),
        patch("citrasense.tasks.upload_queue.UploadQueue.__init__", return_value=None),
    ):
        from citrasense.tasks.runner import TaskManager

        tm = TaskManager(
            api_client=MagicMock(),
            logger=MagicMock(),
            hardware_adapter=MagicMock(),
            settings=MagicMock(),
            processor_registry=MagicMock(),
            safety_monitor=safety_monitor,
        )
    tm.imaging_queue = MagicMock()
    return tm


class TestEvaluateSafetyEmergencyClear:
    def test_emergency_clears_imaging_queue_on_first_transition(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("hw", SafetyAction.EMERGENCY)])
        tm = _make_task_manager(monitor)

        result = tm._evaluate_safety()

        assert result is True
        tm.imaging_queue.clear.assert_called_once()

    def test_emergency_does_not_clear_on_subsequent_polls(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("hw", SafetyAction.EMERGENCY)])
        tm = _make_task_manager(monitor)

        tm._evaluate_safety()
        tm.imaging_queue.clear.reset_mock()

        tm._evaluate_safety()
        tm.imaging_queue.clear.assert_not_called()

    def test_safe_does_not_clear_imaging_queue(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("hw", SafetyAction.SAFE)])
        tm = _make_task_manager(monitor)

        result = tm._evaluate_safety()

        assert result is False
        tm.imaging_queue.clear.assert_not_called()

    def test_queue_stop_does_not_clear_imaging_queue(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("hw", SafetyAction.QUEUE_STOP)])
        tm = _make_task_manager(monitor)

        result = tm._evaluate_safety()

        assert result is True
        tm.imaging_queue.clear.assert_not_called()

    def test_emergency_recovery_then_re_emergency_clears_again(self):
        check = _StubCheck("hw", SafetyAction.EMERGENCY)
        monitor = SafetyMonitor(MagicMock(), [check])
        tm = _make_task_manager(monitor)

        tm._evaluate_safety()
        tm.imaging_queue.clear.assert_called_once()
        tm.imaging_queue.clear.reset_mock()

        check._action = SafetyAction.SAFE
        tm._evaluate_safety()

        check._action = SafetyAction.EMERGENCY
        tm._evaluate_safety()
        tm.imaging_queue.clear.assert_called_once()

    def test_emergency_calls_abort_slew(self):
        monitor = SafetyMonitor(MagicMock(), [_StubCheck("hw", SafetyAction.EMERGENCY)])
        tm = _make_task_manager(monitor)

        tm._evaluate_safety()

        tm.hardware_adapter.abort_slew.assert_called()
