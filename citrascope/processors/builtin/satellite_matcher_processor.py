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

from .processor_dependencies import check_ephemeris, get_ephemeris_path


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

        Uses elset hot list from daemon.elset_cache when available (multi-TLE); otherwise
        uses context.task.most_recent_elset (single TLE).
        """
        # Separate stars from satellites by FWHM based on tracking mode
        if tracking_mode == "rate":
            potential_sats = sources[sources["fwhm"] < 1.5].copy()
        else:
            potential_sats = sources[sources["fwhm"] >= 1.5].copy()

        if potential_sats.empty:
            return []

        # Get observer location
        try:
            daemon = context.daemon or getattr(context.settings, "daemon", None)
            if not daemon or not getattr(daemon, "location_service", None):
                raise RuntimeError("No location service available (daemon.location_service)")
            location = daemon.location_service.get_current_location()
            observer = wgs84.latlon(location["latitude"], location["longitude"], location.get("altitude", 0))
        except Exception as e:
            raise RuntimeError(f"Failed to get observer location: {e}")

        # Load ephemeris and get image time/center from FITS
        ephemeris_path = get_ephemeris_path()
        eph = load(str(ephemeris_path))
        ts = load.timescale()
        with fits.open(context.working_image_path) as hdul:
            header = hdul[0].header
            timestamp_str = header.get("DATE-OBS")
            if not timestamp_str:
                raise RuntimeError("No DATE-OBS in FITS header")
            ra_center = float(header.get("CRVAL1", 0.0))
            dec_center = float(header.get("CRVAL2", 0.0))
        t = self._parse_fits_timestamp(timestamp_str, ts)
        sun, earth = eph["sun"], eph["earth"]

        # Hot list path: use all elsets from daemon.elset_cache when available
        elset_cache = getattr(daemon, "elset_cache", None) if daemon else None
        elsets = (elset_cache.get_elsets() if elset_cache else []) or []

        if elsets:
            return self._match_satellites_multi_tle(
                potential_sats, observer, t, sun, earth, ts, elsets, ra_center, dec_center, context, timestamp_str
            )
        # Fallback: single TLE from task
        return self._match_satellites_single_tle(potential_sats, observer, t, sun, earth, ts, context, timestamp_str)

    def _match_satellites_multi_tle(
        self,
        potential_sats: pd.DataFrame,
        observer,
        t,
        sun,
        earth,
        ts,
        elsets: List[Dict[str, Any]],
        ra_center: float,
        dec_center: float,
        context: ProcessingContext,
        timestamp_str: str,
    ) -> List[Dict[str, Any]]:
        """Match using hot list: propagate all TLEs, keep in-field (~2 deg), KDTree match."""
        in_field_deg = 2.0
        predictions = []  # list of dicts: ra, dec, satellite_id, name, phase_angle
        for elset in elsets:
            tle = elset.get("tle") or []
            if len(tle) < 2:
                continue
            sat_id = elset.get("satellite_id") or "unknown"
            name = elset.get("name") or sat_id
            try:
                satellite = EarthSatellite(tle[0], tle[1], name, ts)
                topocentric = (satellite - observer).at(t)
                ra, dec, _ = topocentric.radec()
                ra_deg = ra.hours * 15.0
                dec_deg = dec.degrees
                if abs(ra_center - ra_deg) >= in_field_deg or abs(dec_center - dec_deg) >= in_field_deg:
                    continue
                geosat = earth + satellite
                phase_angle = geosat.at(t).observe(sun).separation_from(geosat.at(t).observe(earth)).degrees
                predictions.append(
                    {"ra": ra_deg, "dec": dec_deg, "satellite_id": sat_id, "name": name, "phase_angle": phase_angle}
                )
            except Exception:
                continue
        if not predictions:
            return []
        pred_ra_dec = [[p["ra"], p["dec"]] for p in predictions]
        tree = KDTree(pred_ra_dec)
        distances, indices = tree.query(potential_sats[["ra", "dec"]].values, distance_upper_bound=1.0 / 60.0)
        valid_mask = distances < 1.0 / 60.0
        if not valid_mask.any():
            return []
        observations = []
        filter_name = (context.task.assigned_filter_name if context.task else None) or "Clear"
        for i in range(len(potential_sats)):
            if not valid_mask[i]:
                continue
            idx = int(indices[i]) if hasattr(indices[i], "__int__") else indices[i]
            if idx < 0 or idx >= len(predictions):
                continue
            p = predictions[idx]
            row = potential_sats.iloc[i]
            observations.append(
                {
                    "norad_id": p["satellite_id"],
                    "name": p["name"],
                    "ra": row["ra"],
                    "dec": row["dec"],
                    "mag": row["mag"],
                    "filter": filter_name,
                    "timestamp": timestamp_str,
                    "phase_angle": round(p["phase_angle"], 1),
                    "fwhm": row["fwhm"],
                }
            )
        return observations

    def _match_satellites_single_tle(
        self,
        potential_sats: pd.DataFrame,
        observer,
        t,
        sun,
        earth,
        ts,
        context: ProcessingContext,
        timestamp_str: str,
    ) -> List[Dict[str, Any]]:
        """Match using single TLE from context.task.most_recent_elset."""
        if not context.task:
            raise RuntimeError("No task context available for satellite matching")
        most_recent_elset = getattr(context.task, "most_recent_elset", None)
        if not most_recent_elset:
            raise RuntimeError("No TLE data available in task")
        tle_data = most_recent_elset.get("tle", [])
        if len(tle_data) < 2:
            raise RuntimeError("Invalid TLE format")
        satellite_name = context.task.satelliteName
        satellite_id = context.task.satelliteId
        satellite = EarthSatellite(tle_data[0], tle_data[1], satellite_name, ts)
        topocentric = (satellite - observer).at(t)
        ra, dec, _ = topocentric.radec()
        ra_deg, dec_deg = ra.hours * 15.0, dec.degrees
        geosat = earth + satellite
        phase_angle = geosat.at(t).observe(sun).separation_from(geosat.at(t).observe(earth)).degrees
        predicted_pos = [[ra_deg, dec_deg]]
        tree = KDTree(predicted_pos)
        distances, indices = tree.query(potential_sats[["ra", "dec"]].values, distance_upper_bound=1.0 / 60.0)
        valid_mask = distances < 1.0 / 60.0
        if not valid_mask.any():
            return []
        observations = []
        filter_name = context.task.assigned_filter_name or "Clear"
        for _, row in potential_sats[valid_mask].iterrows():
            observations.append(
                {
                    "norad_id": satellite_id,
                    "name": satellite_name,
                    "ra": row["ra"],
                    "dec": row["dec"],
                    "mag": row["mag"],
                    "filter": filter_name,
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
            # Load sources (SExtractor format: no header, cols 4=mag 5=magerr 8=ra 9=dec 10=fwhm)
            sources_df = pd.read_csv(
                catalog_path,
                sep=r"\s+",
                comment="#",
                header=None,
                usecols=[4, 5, 8, 9, 10],
                names=["mag", "magerr", "ra", "dec", "fwhm"],
            )

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
