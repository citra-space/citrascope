"""Satellite association processor using TLE propagation."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from astropy.io import fits
from scipy.spatial import KDTree
from skyfield.api import load, wgs84
from skyfield.sgp4lib import EarthSatellite

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult

from .processor_dependencies import check_ephemeris


class SatelliteMatcherProcessor(AbstractImageProcessor):
    """
    Satellite association processor using TLE propagation.

    Propagates TLEs for target satellite, predicts position at image timestamp,
    and matches detected sources with predicted positions. Requires all previous
    processors to have run successfully.

    Typical processing time: 1-2 seconds.
    """

    name = "satellite_matcher"
    friendly_name = "Satellite Matcher"
    description = "Match detected sources with TLE predictions (requires full pipeline)"

    def _parse_fits_timestamp(self, timestamp_str: str, ts) -> Any:
        """Parse FITS DATE-OBS timestamp into Skyfield Time object.

        Args:
            timestamp_str: Timestamp string from FITS header (ISO format)
            ts: Skyfield timescale object

        Returns:
            Skyfield Time object
        """
        # Parse ISO format: YYYY-MM-DDTHH:MM:SS.ssssss
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # Convert to Skyfield time
        t = ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)

        return t

    def _match_satellites(
        self, sources: pd.DataFrame, context: ProcessingContext, tracking_mode: str = "rate"
    ) -> List[Dict[str, Any]]:
        """Propagate TLEs and match detected sources with predicted satellite positions.

        Args:
            sources: DataFrame with detected sources (columns: ra, dec, mag, fwhm)
            context: Processing context with task, settings, and image info
            tracking_mode: Tracking mode ("rate" or "sidereal")

        Returns:
            List of matched satellite observations with NORAD ID, position, magnitude, etc.

        Raises:
            RuntimeError: If matching fails
        """
        # Separate stars from satellites by FWHM based on tracking mode
        # In rate tracking: stars are streaked (high FWHM), satellites are sharp (low FWHM)
        # In sidereal tracking: opposite
        if tracking_mode == "rate":
            stars = sources[sources["fwhm"] >= 1.5].copy()
            potential_sats = sources[sources["fwhm"] < 1.5].copy()
        else:
            stars = sources[sources["fwhm"] < 1.5].copy()
            potential_sats = sources[sources["fwhm"] >= 1.5].copy()

        if potential_sats.empty:
            return []

        # Get observer location from context
        # Note: This assumes location service is available in daemon
        try:
            location = context.settings.daemon.location_service.get_current_location()
            observer = wgs84.latlon(location["latitude"], location["longitude"], location.get("altitude", 0))
        except Exception as e:
            raise RuntimeError(f"Failed to get observer location: {e}")

        # Get satellite TLE from task
        if not context.task:
            raise RuntimeError("No task context available for satellite matching")

        satellite_name = context.task.satelliteName
        satellite_id = context.task.satelliteId

        # Get most recent elset from task
        most_recent_elset = getattr(context.task, "most_recent_elset", None)
        if not most_recent_elset:
            raise RuntimeError("No TLE data available in task")

        # Extract TLE lines
        tle_data = most_recent_elset.get("tle", [])
        if len(tle_data) < 2:
            raise RuntimeError("Invalid TLE format")

        # Load ephemeris and timescale
        ephemeris_path = Path(__file__).parent.parent.parent / "data" / "ephemeris" / "de421.bsp"
        eph = load(str(ephemeris_path))
        ts = load.timescale()

        # Get image timestamp from FITS header
        with fits.open(context.working_image_path) as hdul:
            header = hdul[0].header
            timestamp_str = header.get("DATE-OBS")
            if not timestamp_str:
                raise RuntimeError("No DATE-OBS in FITS header")

        # Parse timestamp
        t = self._parse_fits_timestamp(timestamp_str, ts)

        # Create satellite object and propagate
        satellite = EarthSatellite(tle_data[0], tle_data[1], satellite_name, ts)
        topocentric = (satellite - observer).at(t)
        ra, dec, _ = topocentric.radec()
        ra_deg, dec_deg = ra.hours * 15.0, dec.degrees

        # Calculate phase angle
        sun = eph["sun"]
        earth = eph["earth"]
        geosat = earth + satellite
        phase_angle = geosat.at(t).observe(sun).separation_from(geosat.at(t).observe(earth)).degrees

        # Match potential satellites with predicted position
        predicted_pos = [[ra_deg, dec_deg]]
        tree = KDTree(predicted_pos)
        distances, indices = tree.query(
            potential_sats[["ra", "dec"]].values, distance_upper_bound=1.0 / 60.0
        )  # 1 arcmin

        valid_mask = distances < 1.0 / 60.0
        if not valid_mask.any():
            return []

        # Build matched observations
        matched = potential_sats[valid_mask].copy()
        observations = []

        for _, row in matched.iterrows():
            observations.append(
                {
                    "norad_id": satellite_id,
                    "name": satellite_name,
                    "ra": row["ra"],
                    "dec": row["dec"],
                    "mag": row["mag"],  # Note: Zero point should be applied before this
                    "filter": context.task.assigned_filter_name if context.task.assigned_filter_name else "Clear",
                    "timestamp": timestamp_str,
                    "phase_angle": round(phase_angle, 1),
                    "fwhm": row["fwhm"],
                }
            )

        return observations

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with satellite matching.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with satellite matching outcome
        """
        start_time = time.time()

        # Check prerequisites
        catalog_path = context.working_dir / "output.cat"
        if not catalog_path.exists():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="Source catalog not found",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        # Check for ephemeris
        if not check_ephemeris():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="Ephemeris file missing (de421.bsp)",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            # Load sources
            sources_df = pd.read_csv(catalog_path, delim_whitespace=True, comment="#")

            # Match satellites
            satellite_observations = self._match_satellites(
                sources_df, context, tracking_mode="rate"  # Could make this configurable
            )

            elapsed = time.time() - start_time

            return ProcessorResult(
                should_upload=True,
                extracted_data={
                    "num_satellites_detected": len(satellite_observations),
                    "satellite_observations": satellite_observations,
                },
                confidence=1.0 if satellite_observations else 0.5,
                reason=f"Matched {len(satellite_observations)} satellite(s) in {elapsed:.1f}s",
                processing_time_seconds=elapsed,
                processor_name=self.name,
            )

        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Satellite matching failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
