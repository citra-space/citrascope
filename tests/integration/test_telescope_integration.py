import os

import pytest
import requests

# Use mock-citra-server hostname in Docker, localhost otherwise
MOCK_SERVER_URL = os.environ.get("CITRASCOPE_API_URL", "http://localhost:8080")


@pytest.mark.integration
def test_mock_citra_server_health():
    """Test that the mock Citra server is reachable."""
    response = requests.get(f"{MOCK_SERVER_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.integration
def test_mock_citra_server_tasks():
    """Test that the mock Citra server returns tasks."""
    response = requests.get(f"{MOCK_SERVER_URL}/tasks")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert len(data["tasks"]) > 0
