"""FITS metadata enrichment for observation context.

Adds contextual metadata (location, target, observatory info) to FITS files
before upload. This centralizes metadata management and keeps cameras focused
on capture-time intrinsic metadata (DATE-OBS, EXPTIME, etc.).
"""

from pathlib import Path

from citrascope.logging import CITRASCOPE_LOGGER


def enrich_fits_metadata(
    filepath: str,
    task=None,
    daemon=None,
) -> None:
    """
    Enrich FITS file with observation context metadata before upload.

    Adds contextual metadata while preserving camera-intrinsic metadata
    (DATE-OBS, EXPTIME, GAIN, etc.) that must be captured at exposure time.

    Args:
        filepath: Path to FITS file to enrich
        task: Task object with observation details (optional for manual captures)
        daemon: CitraScopeDaemon instance for location/record lookup (optional)

    FITS Keywords Added:
        Location (from GPS or ground station):
            - SITELAT: Observatory latitude (degrees)
            - SITELONG: Observatory longitude (degrees)
            - SITEELEV: Observatory elevation (meters)
            - COMMENT: Location source (gps/ground_station)

        Observation Context (from task):
            - OBJECT: Target name (satellite)
            - OBSERVER: Ground station name
            - TELESCOP: Telescope name
            - FILTER: Filter name (if assigned)
            - ORIGIN: "Citra.space"

        Traceability (from task):
            - TASKID: Task UUID for database linking

    Note:
        This function modifies FITS files in-place and fails gracefully.
        Missing metadata is skipped without raising exceptions.
    """
    try:
        from astropy.io import fits
    except ImportError:
        CITRASCOPE_LOGGER.error("astropy not installed. Cannot enrich FITS metadata.")
        return

    if not Path(filepath).exists():
        CITRASCOPE_LOGGER.warning(f"FITS file not found: {filepath}")
        return

    # Extract records from daemon
    telescope_record = daemon.telescope_record if daemon else None
    ground_station = daemon.ground_station if daemon else None

    try:
        # Open FITS file in update mode
        with fits.open(filepath, mode="update") as hdul:
            primary = hdul[0]
            assert isinstance(primary, fits.PrimaryHDU)
            header = primary.header

            # Check if already enriched (idempotency)
            if task and hasattr(task, "id") and task.id:
                if "TASKID" in header:
                    CITRASCOPE_LOGGER.debug(f"FITS file already enriched (TASKID present): {filepath}")
                    return

            # Add location metadata (GPS preferred, ground station fallback)
            _add_location_metadata(header, daemon, ground_station)

            # Add observation context from task
            if task:
                _add_task_metadata(header, task, telescope_record, ground_station)

            # Add origin
            header["ORIGIN"] = ("Citra.space", "Data origin")

            # Changes are automatically saved on context exit (mode="update")

        CITRASCOPE_LOGGER.debug(f"Enriched FITS metadata: {filepath}")

    except Exception as e:
        # Fail gracefully - enrichment failures shouldn't block uploads
        CITRASCOPE_LOGGER.warning(f"Failed to enrich FITS metadata for {filepath}: {e}")


def _add_location_metadata(header, daemon, ground_station_record: dict | None) -> None:
    """
    Add observatory location metadata to FITS header.

    Tries GPS first (if daemon available), falls back to ground station.
    """
    location = None

    # Try to get location from location service (GPS or ground station)
    if daemon and daemon.location_service:
        try:
            location = daemon.location_service.get_current_location()
        except Exception as e:
            CITRASCOPE_LOGGER.debug(f"Could not get location from location service: {e}")

    # Fallback to ground station record if daemon unavailable
    if not location and ground_station_record:
        location = {
            "latitude": ground_station_record.get("latitude"),
            "longitude": ground_station_record.get("longitude"),
            "altitude": ground_station_record.get("altitude"),
            "source": "ground_station",
        }

    # Add location keywords if available
    if location and location.get("latitude") is not None:
        header["SITELAT"] = (location["latitude"], "Observatory latitude (deg)")
        header["SITELONG"] = (location["longitude"], "Observatory longitude (deg)")
        header["SITEELEV"] = (location["altitude"], "Observatory elevation (m)")
        header["COMMENT"] = f"Location source: {location['source']}"


def _add_task_metadata(
    header,
    task,
    telescope_record: dict | None,
    ground_station_record: dict | None,
) -> None:
    """
    Add task-related observation context to FITS header.

    Includes target name, observatory info, filter, and task ID for traceability.
    """
    # Target name (satellite being observed)
    if hasattr(task, "satelliteName") and task.satelliteName:
        header["OBJECT"] = (task.satelliteName, "Target name")

    # Observatory/Ground station name
    if hasattr(task, "groundStationName") and task.groundStationName:
        header["OBSERVER"] = (task.groundStationName, "Ground station name")
    elif ground_station_record and ground_station_record.get("name"):
        header["OBSERVER"] = (ground_station_record["name"], "Ground station name")

    # Telescope name
    if hasattr(task, "telescopeName") and task.telescopeName:
        header["TELESCOP"] = (task.telescopeName, "Telescope name")
    elif telescope_record and telescope_record.get("name"):
        header["TELESCOP"] = (telescope_record["name"], "Telescope name")

    # Filter (if assigned to this observation)
    if hasattr(task, "assigned_filter_name") and task.assigned_filter_name:
        header["FILTER"] = (task.assigned_filter_name, "Filter name")

    # Task ID for database traceability
    if hasattr(task, "id") and task.id:
        header["TASKID"] = (task.id, "Citra.space task UUID")
