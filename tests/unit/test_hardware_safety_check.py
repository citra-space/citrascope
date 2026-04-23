"""Tests for HardwareSafetyCheck — bridges external safety monitor into SafetyAction.

Fail-closed policy: both ``False`` (confirmed unsafe) and ``None``
(unknown / unreachable) return EMERGENCY.  Only an explicit ``True``
from the query function allows operations.
"""

from unittest.mock import MagicMock

from citrasense.safety.hardware_safety_check import HardwareSafetyCheck
from citrasense.safety.safety_monitor import SafetyAction


class TestHardwareSafetyCheck:
    def test_safe_returns_safe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: True)
        assert check.check() == SafetyAction.SAFE

    def test_unsafe_returns_emergency(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: False)
        assert check.check() == SafetyAction.EMERGENCY

    def test_none_returns_emergency(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: None)
        assert check.check() == SafetyAction.EMERGENCY

    def test_query_exception_returns_emergency(self):
        def raise_error():
            raise ConnectionError("NINA unreachable")

        check = HardwareSafetyCheck(MagicMock(), raise_error)
        assert check.check() == SafetyAction.EMERGENCY

    def test_slew_blocked_when_unsafe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: False)
        check.check()
        assert check.check_proposed_action("slew") is False

    def test_capture_blocked_when_unsafe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: False)
        check.check()
        assert check.check_proposed_action("capture") is False

    def test_slew_allowed_when_safe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: True)
        check.check()
        assert check.check_proposed_action("slew") is True

    def test_capture_allowed_when_safe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: True)
        check.check()
        assert check.check_proposed_action("capture") is True

    def test_slew_blocked_when_unknown(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: None)
        check.check()
        assert check.check_proposed_action("slew") is False

    def test_capture_blocked_when_unknown(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: None)
        check.check()
        assert check.check_proposed_action("capture") is False

    def test_other_actions_allowed_when_unsafe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: False)
        check.check()
        assert check.check_proposed_action("home") is True

    def test_other_actions_allowed_when_unknown(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: None)
        check.check()
        assert check.check_proposed_action("home") is True

    def test_name(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: True)
        assert check.name == "hardware_safety"

    def test_get_status_safe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: True)
        check.check()
        status = check.get_status()
        assert status["name"] == "hardware_safety"
        assert status["is_safe"] is True

    def test_get_status_unsafe(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: False)
        check.check()
        status = check.get_status()
        assert status["is_safe"] is False

    def test_get_status_unknown(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: None)
        check.check()
        status = check.get_status()
        assert status["is_safe"] is None

    def test_get_status_before_first_check(self):
        check = HardwareSafetyCheck(MagicMock(), lambda: True)
        status = check.get_status()
        assert status["name"] == "hardware_safety"
        assert status["is_safe"] is None

    def test_critical_logged_only_on_transition_to_unsafe(self):
        logger = MagicMock()
        check = HardwareSafetyCheck(logger, lambda: False)
        check.check()
        assert logger.critical.call_count == 1

        logger.critical.reset_mock()
        check.check()
        assert logger.critical.call_count == 0

    def test_critical_logged_on_transition_to_unreachable(self):
        state = {"safe": True}
        logger = MagicMock()
        check = HardwareSafetyCheck(logger, lambda: state["safe"])

        check.check()
        assert logger.critical.call_count == 0

        state["safe"] = None
        check.check()
        assert logger.critical.call_count == 1

        logger.critical.reset_mock()
        check.check()
        assert logger.critical.call_count == 0

    def test_critical_logged_again_after_recovery_and_re_trigger(self):
        state = {"safe": False}
        logger = MagicMock()
        check = HardwareSafetyCheck(logger, lambda: state["safe"])

        check.check()
        assert logger.critical.call_count == 1

        state["safe"] = True
        check.check()

        logger.critical.reset_mock()
        state["safe"] = False
        check.check()
        assert logger.critical.call_count == 1

    def test_recovery_from_unknown_to_safe(self):
        state = {"safe": None}
        check = HardwareSafetyCheck(MagicMock(), lambda: state["safe"])
        assert check.check() == SafetyAction.EMERGENCY

        state["safe"] = True
        assert check.check() == SafetyAction.SAFE
        assert check.check_proposed_action("slew") is True
