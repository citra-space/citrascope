"""Satellite association processor using TLE propagation."""

import math
import time
from datetime import datetime, timezone
from typing import Any

import astropy.units as u
import pandas as pd
from astropy.coordinates import get_body_barycentric_posvel
from astropy.io import fits
from astropy.time import Time as AstropyTime
from keplemon import time as ktime
from keplemon.bodies import Observatory, Satellite
from keplemon.elements import TLE
from keplemon.enums import ReferenceFrame
from scipy.spatial import KDTree

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult

from .processor_dependencies import normalize_fits_timestamp


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

    def _parse_fits_timestamp(self, timestamp_str: str) -> ktime.Epoch:
        """Parse FITS DATE-OBS timestamp into a Keplemon Epoch.

        Args:
            timestamp_str: Timestamp string from FITS header (ISO format)

        Returns:
            ktime.Epoch in UTC
        """
        dt = datetime.fromisoformat(normalize_fits_timestamp(timestamp_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return ktime.Epoch.from_datetime(dt)

    def _match_satellites(
        self, sources: pd.DataFrame, context: ProcessingContext, tracking_mode: str = "rate"
    ) -> list[dict[str, Any]]:
        """Propagate TLEs and match detected sources with predicted satellite positions.

        Prefers the elset cache when populated; falls back to the single TLE on the task.
        """
        # Separate stars from satellites by FWHM based on tracking mode
        if tracking_mode == "rate":
            potential_sats = sources[sources["fwhm"] < 1.5].copy()
        else:
            potential_sats = sources[sources["fwhm"] >= 1.5].copy()

        if potential_sats.empty:
            return []

        # Observer location
        try:
            if not context.location_service:
                raise RuntimeError("No location service available")
            location = context.location_service.get_current_location()
            obs = Observatory(location["latitude"], location["longitude"], location.get("altitude", 0) / 1000.0)
        except Exception as e:
            raise RuntimeError(f"Failed to get observer location: {e}")

        # Image metadata from FITS header
        with fits.open(context.working_image_path) as hdul:
            header = hdul[0].header
            timestamp_str = header.get("DATE-OBS")
            if not timestamp_str:
                raise RuntimeError("No DATE-OBS in FITS header")
            ra_center = float(header.get("CRVAL1", 0.0))
            dec_center = float(header.get("CRVAL2", 0.0))
        epoch = self._parse_fits_timestamp(timestamp_str)

        # Sun position (km, J2000/ECI) via astropy ERFA — no external ephemeris file required
        _t = AstropyTime(epoch.to_datetime())
        _sun_bary, _ = get_body_barycentric_posvel("sun", _t)
        _earth_bary, _ = get_body_barycentric_posvel("earth", _t)
        sun_pos_km = (_sun_bary.xyz - _earth_bary.xyz).to(u.km).value

        # Observer position (km, J2000)
        obs_state = obs.get_state_at_epoch(epoch).to_frame(ReferenceFrame.J2000)
        obs_pos = obs_state.position

        # Build elset list: prefer cache, fall back to the task's single TLE
        elsets = (context.elset_cache.get_elsets() if context.elset_cache else []) or []
        if not elsets:
            if not context.task:
                raise RuntimeError("No task context available for satellite matching")
            most_recent_elset = getattr(context.task, "most_recent_elset", None)
            if not most_recent_elset:
                raise RuntimeError("No TLE data available in task")
            tle_data = most_recent_elset.get("tle", [])
            if len(tle_data) < 2:
                raise RuntimeError("Invalid TLE format")
            elsets = [{"satellite_id": context.task.satelliteId, "name": context.task.satelliteName, "tle": tle_data}]

        # Propagate all TLEs, keep only those within the field, collect predictions
        in_field_deg = 2.0
        predictions = []
        for elset in elsets:
            tle = elset.get("tle") or []
            if len(tle) < 2:
                continue
            sat_id = elset.get("satellite_id") or "unknown"
            name = elset.get("name") or sat_id
            try:
                kep_tle = TLE.from_lines(tle[0], tle[1])
                satellite = Satellite.from_tle(kep_tle)
                topo = obs.get_topocentric_to_satellite(epoch, satellite, ReferenceFrame.J2000)
                ra_deg = topo.right_ascension
                dec_deg = topo.declination
                if abs(ra_center - ra_deg) >= in_field_deg or abs(dec_center - dec_deg) >= in_field_deg:
                    continue

                # Phase angle: Sun–Satellite–Observer (angle at satellite between sat→sun and sat→observer)
                sat_state = satellite.get_state_at_epoch(epoch).to_frame(ReferenceFrame.J2000)
                sat_pos = sat_state.position
                sat_to_sun = [sun_pos_km[i] - [sat_pos.x, sat_pos.y, sat_pos.z][i] for i in range(3)]
                sat_to_obs = [
                    [obs_pos.x, obs_pos.y, obs_pos.z][i] - [sat_pos.x, sat_pos.y, sat_pos.z][i] for i in range(3)
                ]
                dot = sum(sat_to_sun[i] * sat_to_obs[i] for i in range(3))
                mag_a = math.sqrt(sum(x * x for x in sat_to_sun))
                mag_b = math.sqrt(sum(x * x for x in sat_to_obs))
                cos_angle = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
                phase_angle = math.degrees(math.acos(cos_angle))

                predictions.append(
                    {"ra": ra_deg, "dec": dec_deg, "satellite_id": sat_id, "name": name, "phase_angle": phase_angle}
                )
            except Exception:
                continue

        if not predictions:
            return []

        # KDTree spatial match: 1 arcminute radius
        tree = KDTree([[p["ra"], p["dec"]] for p in predictions])
        distances, indices = tree.query(potential_sats[["ra", "dec"]].values, distance_upper_bound=1.0 / 60.0)
        valid_mask = distances < 1.0 / 60.0
        if not valid_mask.any():
            return []

        filter_name = (context.task.assigned_filter_name if context.task else None) or "Clear"
        observations = []
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
