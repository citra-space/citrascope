from unittest.mock import MagicMock

import pytest

from citrascope.api.citra_api_client import AbstractCitraApiClient, CitraApiClient

from .utils import DummyLogger, MockCitraApiClient


# Test MockCitraApiClient functionality
def test_mock_api_client():
    mock_client = MockCitraApiClient()

    assert mock_client.does_api_server_accept_key() is True

    telescope = mock_client.get_telescope("1234")
    assert telescope["id"] == "1234"
    assert telescope["name"] == "Mock Telescope"

    satellite = mock_client.get_satellite("5678")
    assert satellite["id"] == "5678"
    assert satellite["name"] == "Mock Satellite"

    tasks = mock_client.get_telescope_tasks("1234")
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == 1
    assert tasks[0]["description"] == "Mock Task"

    ground_station = mock_client.get_ground_station("91011")
    assert ground_station["id"] == "91011"
    assert ground_station["name"] == "Mock Ground Station"
