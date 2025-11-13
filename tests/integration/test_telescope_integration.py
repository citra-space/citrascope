import os
import time

import PyIndi
import pytest
import requests

from citrascope.hardware.indi_adapter import IndiAdapter

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


@pytest.mark.integration
def test_move_telescope():
    """Test that we can move an indi scope"""
    import logging

    # Create a simple logger for the test
    logger = logging.getLogger("test_indi")

    # Get INDI server hostname (test_indi in Docker, localhost otherwise)
    indi_host = os.environ.get("CITRASCOPE_INDI_SERVER_URL", "localhost")
    indi_port = 7624

    indi_hw = IndiAdapter(logger, indi_host, indi_port)

    # Connect to INDI server
    indi_hw.setServer(indi_host, indi_port)
    if not indi_hw.connectServer():
        pytest.fail(f"Failed to connect to INDI server at {indi_host}:{indi_port}")

    # Give it time to discover devices
    time.sleep(5)

    # List available devices
    devices = indi_hw.list_devices()
    logger.info(f"Available devices: {devices}")

    # Select the telescope simulator
    if not indi_hw.select_telescope("Telescope Simulator"):
        pytest.fail("Failed to find 'Telescope Simulator' device")

    # Connect the telescope device explicitly (test-only step)
    connect_prop = indi_hw.our_scope.getSwitch("CONNECTION")
    if connect_prop:
        connect_prop[0].setState(PyIndi.ISS_ON)  # CONNECT
        connect_prop[1].setState(PyIndi.ISS_OFF)  # DISCONNECT
        indi_hw.sendNewSwitch(connect_prop)
        logger.info("Sent connection request to telescope")

        # Wait for connection and EQUATORIAL_EOD_COORD property
        for i in range(20):
            time.sleep(0.5)
            telescope_radec = indi_hw.our_scope.getNumber("EQUATORIAL_EOD_COORD")
            if telescope_radec and len(telescope_radec) >= 2:
                logger.info("Telescope EQUATORIAL_EOD_COORD property is ready")
                break
        else:
            pytest.fail("Timeout waiting for EQUATORIAL_EOD_COORD property")

    # Basic assertion - we connected successfully
    assert indi_hw.isServerConnected()

    ra, dec = indi_hw.get_telescope_direction()

    assert ra is not None and dec is not None
    target_ra_hours = 12.0
    target_dec = 45.0
    indi_hw.point_telescope(target_ra_hours, target_dec)

    while indi_hw.telescope_is_moving():
        logger.info("Telescope is moving...")
        time.sleep(1.0)

    new_ra, new_dec = indi_hw.get_telescope_direction()

    assert new_ra is not None and new_dec is not None
    assert new_ra != ra and new_dec != dec
    assert abs(new_ra - target_ra_hours * 15.0) < 1.0
    assert abs(new_dec - target_dec) < 1.0

    # Cleanup
    indi_hw.disconnectServer()
