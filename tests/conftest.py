"""Shared pytest fixtures available to all test directories."""

from __future__ import annotations

import pytest

from tests.unit.sensor_bus_helpers import InMemoryCaptureBus
from tests.unit.utils import DummyLogger, MockCitraApiClient


@pytest.fixture
def dummy_logger() -> DummyLogger:
    return DummyLogger()


@pytest.fixture
def mock_api_client() -> MockCitraApiClient:
    return MockCitraApiClient()


@pytest.fixture
def capture_bus() -> InMemoryCaptureBus:
    return InMemoryCaptureBus()
