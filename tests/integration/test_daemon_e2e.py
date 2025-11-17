"""
End-to-end integration test that runs the CitraScope daemon with mock API and INDI simulator.

This test mimics the real-world usage where the daemon:
1. Connects to the API to authenticate and fetch telescope/ground station info
2. Connects to INDI server to find and use telescope/camera devices
3. Polls for tasks and executes them (slewing, tracking, imaging)
4. Uploads images and marks tasks complete
"""

import logging
import os
import threading
import time

import pytest

from citrascope.api.citra_api_client import CitraApiClient
from citrascope.citra_scope_daemon import CitraScopeDaemon
from citrascope.hardware.indi_adapter import IndiAdapter
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citrascope_settings import CitraScopeSettings


@pytest.mark.integration
def test_daemon_full_lifecycle(caplog):
    """
    Test the full daemon lifecycle: connect, poll tasks, execute, upload, complete.
    This should work identically in both devcontainer and Docker environments.
    """
    # Capture all log levels

    # Use environment variables like the real daemon does
    mock_server_url = os.environ.get("CITRASCOPE_API_URL", "http://localhost:8080")
    indi_host = os.environ.get("CITRASCOPE_INDI_SERVER_URL", "localhost")

    # Strip http:// or https:// from the mock server URL to get just the host
    api_host = mock_server_url.replace("http://", "").replace("https://", "")

    # Create settings with test values
    settings = CitraScopeSettings(
        host=api_host,
        personal_access_token="test-token",
        telescope_id="test-telescope-123",
        indi_server_url=indi_host,
        indi_server_port=7624,
        indi_telescope_name="Telescope Simulator",
        indi_camera_name="CCD Simulator",
        use_ssl=False,
    )

    # Create the daemon
    daemon = CitraScopeDaemon(settings)

    # Run the daemon in a separate thread so we can timeout
    daemon_exception = None

    def run_with_exception_capture():
        nonlocal daemon_exception
        try:
            daemon.run()
        except Exception as e:
            daemon_exception = e
            CITRASCOPE_LOGGER.error(f"Daemon raised exception: {e}", exc_info=True)

    daemon_thread = threading.Thread(target=run_with_exception_capture, daemon=True)
    daemon_thread.start()

    # Let the daemon run up to a timeout
    daemon_thread.join(timeout=60)

    # Get all captured log records
    log_output = "\n".join([f"{record.levelname}: {record.message}" for record in caplog.records])

    # Check if daemon raised any exceptions
    if daemon_exception:
        pytest.fail(f"Daemon raised exception: {daemon_exception}")

    # Assert on key log messages that indicate successful operation
    assert "INDI Server connected" in log_output, "Should connect to INDI server"
    assert "Found and connected to telescope: Telescope Simulator" in log_output, "Should find telescope"
    assert "Found and connected to camera: CCD Simulator" in log_output, "Should find camera"
    assert "Starting telescope task daemon" in log_output, "Should start task daemon"

    # Should NOT have these error messages
    assert "EQUATORIAL_EOD_COORD property not found" not in log_output, "Should not have EQUATORIAL_EOD_COORD errors"
    assert log_output.count("Could not read telescope coordinates") == 0, "Should not have coordinate read errors"

    # Check for task execution (if mock server provides tasks)
    if "Starting task" in log_output:
        print("\n✅ Task execution detected in logs")
        # If task started, we should see pointing or other task-related logs
        assert "Pointing ahead to RA:" in log_output or "Polled tasks" in log_output, "Should have task-related logs"

    # Verify the daemon actually executes tracking tasks
    assert "Added tasks:" in log_output, "Should find a task from the api"
    assert "Starting task" in log_output, "Should start the task"

    assert "Telescope slew done" in log_output, "Should complete telescope slew"
    assert "Current angular distance to satellite" in log_output, "Should track satellite position"
    assert "Taking 2.0 second exposure" in log_output, "Should take exposures during tracking"

    assert "Completed observation task" in log_output, "Should complete task"

    print("\n✅ Daemon test completed without crashes or critical errors")
