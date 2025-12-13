"""Integration tests for INDI adapter auto-detection functionality."""

import logging
import time

import pytest

from citrascope.hardware.indi_adapter import IndiAdapter


@pytest.mark.integration
def test_indi_auto_detection():
    """Test auto-detection of telescope and camera devices."""

    # Create a logger for the test
    logger = logging.getLogger("test_indi_autodetect")

    # Create adapter WITHOUT specifying telescope_name or camera_name
    # This will trigger auto-detection
    adapter = IndiAdapter(
        logger=logger,
        host="localhost",
        port=7624,
        telescope_name="",  # Empty string to test auto-detection
        camera_name="",  # Empty string to test auto-detection
    )

    # Connect to INDI server
    logger.info("Connecting to INDI server at localhost:7624...")
    if not adapter.connect():
        pytest.fail("Failed to connect to INDI server. Make sure INDI server is running.")

    logger.info("✓ Connected to INDI server")

    # Wait a moment for devices to stabilize
    time.sleep(2)

    # List available devices
    devices = adapter.list_devices()
    logger.info(f"Available devices: {devices}")

    # Check if telescope was auto-detected
    if hasattr(adapter, "our_scope") and adapter.our_scope:
        telescope_name = adapter.our_scope.getDeviceName()
        logger.info(f"✓ Telescope auto-detected: {telescope_name}")

        # Try to get telescope position
        ra, dec = adapter.get_telescope_direction()
        logger.info(f"  Current position: RA={ra:.2f}°, DEC={dec:.2f}°")
        assert ra is not None and dec is not None

        # Try to point telescope
        logger.info("  Testing telescope pointing to RA=180°, DEC=45°...")
        adapter.point_telescope(12.0, 45.0)  # 12 hours = 180 degrees

        # Wait for slew to complete
        for i in range(10):
            if not adapter.telescope_is_moving():
                break
            logger.info(f"  Telescope moving... ({i+1}/10)")
            time.sleep(1)

        new_ra, new_dec = adapter.get_telescope_direction()
        logger.info(f"  New position: RA={new_ra:.2f}°, DEC={new_dec:.2f}°")
        assert new_ra is not None and new_dec is not None
        assert abs(new_ra - 180.0) < 1.0
        assert abs(new_dec - 45.0) < 1.0
    else:
        pytest.skip("No telescope was auto-detected")

    # Check if camera was auto-detected
    if hasattr(adapter, "our_camera") and adapter.our_camera:
        camera_name = adapter.our_camera.getDeviceName()
        logger.info(f"✓ Camera auto-detected: {camera_name}")
    else:
        logger.warning("✗ No camera was auto-detected")

    # Disconnect
    adapter.disconnect()
    logger.info("✓ Disconnected from INDI server")
