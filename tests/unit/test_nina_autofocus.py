"""Unit tests for NINA adapter autofocus hardening (issue #204)."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from citrascope.hardware.nina.nina_adapter import NinaAdvancedHttpAdapter


@pytest.fixture
def adapter():
    """Create a NinaAdvancedHttpAdapter with mocked internals."""
    a = NinaAdvancedHttpAdapter(
        logger=MagicMock(),
        images_dir=Path("/tmp"),
        nina_api_path="http://nina:1888/v2/api",
    )
    # Fake event listener so _auto_focus_one_filter can run
    el = MagicMock()
    el.filter_changed = threading.Event()
    el.autofocus_finished = threading.Event()
    el.autofocus_error = threading.Event()
    el.on_af_point = None
    a._event_listener = el
    return a


def _mock_response(json_data):
    """Build a mock requests.Response that returns *json_data* from .json()."""
    m = MagicMock()
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m


# ---------- _get_current_filter_id ----------


class TestGetCurrentFilterId:
    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_returns_id_from_selected_filter(self, mock_get, adapter):
        mock_get.return_value = _mock_response(
            {
                "Success": True,
                "Response": {
                    "SelectedFilter": {"Name": "Blue", "Id": 2},
                    "AvailableFilters": [],
                },
            }
        )
        assert adapter._get_current_filter_id() == 2

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_returns_none_on_failure(self, mock_get, adapter):
        mock_get.return_value = _mock_response({"Success": False, "Error": "Not connected"})
        assert adapter._get_current_filter_id() is None

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_returns_none_on_missing_field(self, mock_get, adapter):
        mock_get.return_value = _mock_response({"Success": True, "Response": {}})
        assert adapter._get_current_filter_id() is None

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_returns_none_on_network_error(self, mock_get, adapter):
        mock_get.side_effect = ConnectionError("refused")
        assert adapter._get_current_filter_id() is None


# ---------- get_filter_position ----------


class TestGetFilterPosition:
    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_delegates_to_get_current_filter_id(self, mock_get, adapter):
        mock_get.return_value = _mock_response(
            {"Success": True, "Response": {"SelectedFilter": {"Name": "Ha", "Id": 4}}}
        )
        assert adapter.get_filter_position() == 4


# ---------- _auto_focus_one_filter — filter skip ----------


class TestAutoFocusFilterSkip:
    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_skips_change_when_already_on_filter(self, mock_get, adapter):
        """When _get_current_filter_id returns the target, skip the WS wait."""
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Clear", "Id": 0}}})
        focuser_move = _mock_response({"Success": True, "Response": "Focuser move started"})
        focuser_info = _mock_response({"Success": True, "Response": {"Position": 9000}})
        af_trigger = _mock_response({"Success": True, "Response": "Autofocus started"})
        last_af = _mock_response(
            {
                "Success": True,
                "Response": {
                    "CalculatedFocusPoint": {"Position": 8500, "Value": 1.75},
                },
            }
        )

        def route_get(url, **kwargs):
            if "filterwheel/info" in url:
                return fw_info
            if "change-filter" in url:
                pytest.fail("Should not call change-filter when already on target filter")
            if "focuser/move" in url:
                return focuser_move
            if "focuser/info" in url:
                return focuser_info
            if "focuser/auto-focus" in url:
                adapter._event_listener.autofocus_finished.set()
                return af_trigger
            if "focuser/last-af" in url:
                return last_af
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        result = adapter._auto_focus_one_filter(0, "Clear", 9000)
        assert result == 8500

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_changes_filter_when_different(self, mock_get, adapter):
        """When current filter differs from target, do the change+wait dance."""
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Red", "Id": 0}}})
        change_resp = _mock_response({"Success": True, "Response": "Filter changed"})
        focuser_move = _mock_response({"Success": True, "Response": "Focuser move started"})
        focuser_info = _mock_response({"Success": True, "Response": {"Position": 9000}})
        af_trigger = _mock_response({"Success": True, "Response": "Autofocus started"})
        last_af = _mock_response(
            {
                "Success": True,
                "Response": {
                    "CalculatedFocusPoint": {"Position": 8200, "Value": 1.65},
                },
            }
        )

        change_called = []

        def route_get(url, **kwargs):
            if "filterwheel/info" in url:
                return fw_info
            if "change-filter" in url:
                change_called.append(url)
                adapter._event_listener.filter_changed.set()
                return change_resp
            if "focuser/move" in url:
                return focuser_move
            if "focuser/info" in url:
                return focuser_info
            if "focuser/auto-focus" in url:
                adapter._event_listener.autofocus_finished.set()
                return af_trigger
            if "focuser/last-af" in url:
                return last_af
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        result = adapter._auto_focus_one_filter(2, "Blue", 9000)
        assert result == 8200
        assert len(change_called) == 1
        assert "filterId=2" in change_called[0]


# ---------- _auto_focus_one_filter — response validation ----------


class TestAutoFocusResponseValidation:
    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_raises_on_filter_change_rejected(self, mock_get, adapter):
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Red", "Id": 0}}})
        change_resp = _mock_response({"Success": False, "Error": "Filterwheel disconnected"})

        def route_get(url, **kwargs):
            if "filterwheel/info" in url:
                return fw_info
            if "change-filter" in url:
                return change_resp
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        with pytest.raises(RuntimeError, match=r"Filter change.*rejected"):
            adapter._auto_focus_one_filter(2, "Blue", 9000)

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_raises_on_focuser_move_rejected(self, mock_get, adapter):
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Blue", "Id": 2}}})
        focuser_move = _mock_response({"Success": False, "Error": "Focuser not connected"})

        def route_get(url, **kwargs):
            if "filterwheel/info" in url:
                return fw_info
            if "focuser/move" in url:
                return focuser_move
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        with pytest.raises(RuntimeError, match="Focuser move rejected"):
            adapter._auto_focus_one_filter(2, "Blue", 9000)

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_raises_on_focuser_move_rejected_different_filter(self, mock_get, adapter):
        """Focuser move rejection after a real filter change."""
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Red", "Id": 0}}})
        change_resp = _mock_response({"Success": True, "Response": "Filter changed"})
        focuser_move = _mock_response({"Success": False, "Error": "Focuser not connected"})

        def route_get(url, **kwargs):
            if "filterwheel/info" in url:
                return fw_info
            if "change-filter" in url:
                adapter._event_listener.filter_changed.set()
                return change_resp
            if "focuser/move" in url:
                return focuser_move
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        with pytest.raises(RuntimeError, match="Focuser move rejected"):
            adapter._auto_focus_one_filter(2, "Blue", 9000)

    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_raises_on_autofocus_trigger_rejected(self, mock_get, adapter):
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Blue", "Id": 2}}})
        focuser_move = _mock_response({"Success": True, "Response": "OK"})
        focuser_info = _mock_response({"Success": True, "Response": {"Position": 9000}})
        af_trigger = _mock_response({"Success": False, "Error": "Camera not ready"})

        def route_get(url, **kwargs):
            if "filterwheel/info" in url:
                return fw_info
            if "focuser/move" in url:
                return focuser_move
            if "focuser/info" in url:
                return focuser_info
            if "focuser/auto-focus" in url:
                return af_trigger
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        with pytest.raises(RuntimeError, match="Autofocus trigger rejected"):
            adapter._auto_focus_one_filter(2, "Blue", 9000)


# ---------- do_autofocus — slew hardening ----------


class TestDoAutofocusSlewHardening:
    @patch("citrascope.hardware.nina.nina_adapter.time.sleep")
    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_raises_on_slew_rejected(self, mock_get, mock_sleep, adapter):
        slew_resp = _mock_response({"Success": False, "Error": "Mount not connected"})
        slew_resp.raise_for_status.return_value = None

        mock_get.return_value = slew_resp
        adapter.filter_map = {0: {"name": "Clear", "enabled": True, "focus_position": 9000}}

        with pytest.raises(RuntimeError, match="Mount slew rejected"):
            adapter.do_autofocus(target_ra=37.95, target_dec=89.26)

    @patch("citrascope.hardware.nina.nina_adapter.time.sleep")
    @patch("citrascope.hardware.nina.nina_adapter.requests.get")
    def test_sleeps_before_polling_slew_status(self, mock_get, mock_sleep, adapter):
        """After a successful slew, should sleep(2) before polling telescope_is_moving."""
        slew_resp = _mock_response({"Success": True, "Response": "Slew started"})
        slew_resp.raise_for_status.return_value = None

        mount_info_not_slewing = _mock_response({"Success": True, "Response": {"Slewing": False}})
        fw_info = _mock_response({"Success": True, "Response": {"SelectedFilter": {"Name": "Clear", "Id": 0}}})
        focuser_move = _mock_response({"Success": True, "Response": "OK"})
        focuser_info = _mock_response({"Success": True, "Response": {"Position": 9000}})
        af_trigger = _mock_response({"Success": True, "Response": "Autofocus started"})
        last_af = _mock_response(
            {
                "Success": True,
                "Response": {"CalculatedFocusPoint": {"Position": 8500, "Value": 1.75}},
            }
        )

        adapter.filter_map = {0: {"name": "Clear", "enabled": True, "focus_position": 9000}}

        def route_get(url, **kwargs):
            if "slew?" in url:
                return slew_resp
            if "mount/info" in url:
                return mount_info_not_slewing
            if "filterwheel/info" in url:
                return fw_info
            if "change-filter" in url:
                adapter._event_listener.filter_changed.set()
                return _mock_response({"Success": True, "Response": "Filter changed"})
            if "focuser/move" in url:
                return focuser_move
            if "focuser/info" in url:
                return focuser_info
            if "focuser/auto-focus" in url:
                adapter._event_listener.autofocus_finished.set()
                return af_trigger
            if "focuser/last-af" in url:
                return last_af
            return _mock_response({"Success": True})

        mock_get.side_effect = route_get

        adapter.do_autofocus(target_ra=37.95, target_dec=89.26)

        # First sleep call should be the 2s post-slew delay
        assert mock_sleep.call_count >= 1
        assert mock_sleep.call_args_list[0].args[0] == 2
