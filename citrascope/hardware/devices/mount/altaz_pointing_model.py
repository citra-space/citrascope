"""Alt-az pointing model from plate-solve feedback.

Fits the standard 5-term alt-az mount error model to calibration data
collected via plate solving at multiple sky positions.  Applies corrections
to goto commands so the mount lands closer to the intended target.

Error model (alt-az terms)::

    dAz  = CA·sec(alt) + NPAE·tan(alt) + AN·sin(az)·tan(alt) − AW·cos(az)·tan(alt)
    dAlt = IE − AN·cos(az) − AW·sin(az)

Terms:
    AN   — Azimuth axis tilt in N-S direction (leveling error)
    AW   — Azimuth axis tilt in E-W direction (leveling error)
    IE   — Index error in elevation (altitude zero-point offset)
    CA   — Collimation error (optical axis vs altitude axis)
    NPAE — Non-perpendicularity of altitude and azimuth axes

Graceful degradation:
    0-2 points  → passthrough (no correction)
    3-7 points  → 3-term fit (AN, AW, IE)
    8+  points  → full 5-term fit
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from skyfield.api import load

_logger = logging.getLogger(__name__)

_TS = load.timescale()

_MIN_POINTS_3TERM = 3
_MIN_POINTS_5TERM = 8
_HEALTH_WINDOW = 5
_HEALTH_DEGRADED_FACTOR = 3.0


# ---------------------------------------------------------------------------
# Coordinate conversion utilities
# ---------------------------------------------------------------------------


def _skyfield_gast() -> float:
    """Greenwich Apparent Sidereal Time in degrees via Skyfield."""
    return float(_TS.now().gast) * 15.0  # type: ignore[arg-type]


def lst_deg(longitude_deg: float, *, _gast_override: float | None = None) -> float:
    """Local Sidereal Time in degrees for the given longitude.

    Args:
        longitude_deg: Observer longitude in degrees.
        _gast_override: If provided, use this GAST (degrees) instead of
            computing a fresh one.  Callers that need two conversions at
            the same instant should capture ``_skyfield_gast()`` once and
            pass it to both calls.
    """
    gast = _gast_override if _gast_override is not None else _skyfield_gast()
    return (gast + longitude_deg) % 360.0


def radec_to_altaz(
    ra_deg: float,
    dec_deg: float,
    lat_deg: float,
    lon_deg: float,
    *,
    _gast_override: float | None = None,
) -> tuple[float, float]:
    """Convert RA/Dec to (azimuth, altitude) in degrees.

    Uses standard spherical trigonometry with LST from Skyfield.

    Args:
        ra_deg: Right Ascension in degrees.
        dec_deg: Declination in degrees.
        lat_deg: Observer latitude in degrees.
        lon_deg: Observer longitude in degrees.
        _gast_override: Frozen GAST in degrees for paired conversions.

    Returns:
        (azimuth_deg, altitude_deg) — azimuth measured from north through east.
    """
    lat = math.radians(lat_deg)
    local_lst = lst_deg(lon_deg, _gast_override=_gast_override)
    ha = math.radians((local_lst - ra_deg) % 360.0)
    dec = math.radians(dec_deg)

    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(ha)
    alt = math.asin(max(-1.0, min(1.0, sin_alt)))

    cos_alt = math.cos(alt)
    if cos_alt < 1e-10:
        return 0.0, math.degrees(alt)

    cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / (cos_alt * math.cos(lat) + 1e-10)
    az_raw = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    az = (360.0 - az_raw) if math.sin(ha) > 0 else az_raw

    return az, math.degrees(alt)


def altaz_to_radec(
    az_deg: float,
    alt_deg: float,
    lat_deg: float,
    lon_deg: float,
    *,
    _gast_override: float | None = None,
) -> tuple[float, float]:
    """Convert (azimuth, altitude) to RA/Dec in degrees.

    Inverse of :func:`radec_to_altaz`.

    Args:
        az_deg: Azimuth in degrees (north=0, east=90).
        alt_deg: Altitude in degrees.
        lat_deg: Observer latitude in degrees.
        lon_deg: Observer longitude in degrees.
        _gast_override: Frozen GAST in degrees for paired conversions.

    Returns:
        (ra_deg, dec_deg).
    """
    lat = math.radians(lat_deg)
    az = math.radians(az_deg)
    alt = math.radians(alt_deg)

    sin_dec = math.sin(alt) * math.sin(lat) + math.cos(alt) * math.cos(lat) * math.cos(az)
    dec = math.asin(max(-1.0, min(1.0, sin_dec)))

    cos_dec = math.cos(dec)
    if cos_dec < 1e-10:
        return lst_deg(lon_deg, _gast_override=_gast_override), math.degrees(dec)

    cos_ha = (math.sin(alt) - math.sin(dec) * math.sin(lat)) / (cos_dec * math.cos(lat) + 1e-10)
    ha_abs = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    ha = -ha_abs if math.sin(az) > 0 else ha_abs

    ra = (lst_deg(lon_deg, _gast_override=_gast_override) - ha) % 360.0
    return ra, math.degrees(dec)


# ---------------------------------------------------------------------------
# Calibration grid generation
# ---------------------------------------------------------------------------


def generate_calibration_grid(
    current_az_deg: float,
    cable_wrap_cumulative_deg: float,
    horizon_limit_deg: float = 15.0,
    overhead_limit_deg: float = 89.0,
    lat_deg: float = 0.0,
    lon_deg: float = 0.0,
    n_points: int = 10,
    cable_wrap_soft_limit_deg: float = 240.0,
) -> list[tuple[float, float]]:
    """Generate well-distributed sky positions for a calibration run.

    Returns an ordered list of ``(ra_deg, dec_deg)`` targets that:
    - Stay within mount altitude limits
    - Respect cable-wrap budget via boustrophedon azimuth ordering
    - Provide good sky coverage for fitting the 5-term model

    Args:
        current_az_deg: Mount's current azimuth in degrees.
        cable_wrap_cumulative_deg: Current cable-wrap cumulative rotation.
        horizon_limit_deg: Minimum altitude above horizon.
        overhead_limit_deg: Maximum altitude (avoid zenith singularity).
        lat_deg: Observer latitude in degrees.
        lon_deg: Observer longitude in degrees.
        n_points: Desired number of calibration points.
        cable_wrap_soft_limit_deg: Cable-wrap soft limit for budget calculation.

    Returns:
        Ordered list of (ra_deg, dec_deg) targets.
    """
    budget_deg = cable_wrap_soft_limit_deg - abs(cable_wrap_cumulative_deg)
    if budget_deg < 60.0:
        _logger.warning(
            "Cable wrap budget only %.0f° — calibration grid will be narrow. Consider unwinding first.",
            budget_deg,
        )

    usable_range = min(budget_deg * 0.8, 300.0)
    half_range = usable_range / 2.0

    alt_bands = [alt for alt in [30.0, 45.0, 60.0, 75.0] if horizon_limit_deg <= alt <= overhead_limit_deg]
    if not alt_bands:
        alt_bands = [(horizon_limit_deg + overhead_limit_deg) / 2.0]

    n_az = max(3, n_points // len(alt_bands))
    az_start = current_az_deg - half_range
    az_step = usable_range / max(n_az - 1, 1)

    grid_altaz: list[tuple[float, float]] = []
    for i, alt in enumerate(alt_bands):
        az_positions = [(az_start + j * az_step) % 360.0 for j in range(n_az)]
        if i % 2 == 1:
            az_positions.reverse()
        for az in az_positions:
            grid_altaz.append((az, alt))

    if len(grid_altaz) > n_points:
        step = len(grid_altaz) / n_points
        grid_altaz = [grid_altaz[int(i * step)] for i in range(n_points)]

    targets: list[tuple[float, float]] = []
    for az, alt in grid_altaz:
        ra, dec = altaz_to_radec(az, alt, lat_deg, lon_deg)
        targets.append((ra, dec))

    return targets


# ---------------------------------------------------------------------------
# Pointing model
# ---------------------------------------------------------------------------


class AltAzPointingModel:
    """5-term alt-az pointing error model with least-squares fitting.

    Owns calibration data, fitted terms, and health monitoring state.
    Persists to a JSON state file (like ``CableWrapCheck``).
    """

    def __init__(self, state_file: Path | None = None) -> None:
        self._state_file = state_file
        self._lock = threading.Lock()

        # Calibration data: list of (az, alt, d_az, d_alt) in degrees
        self._points: list[tuple[float, float, float, float]] = []

        # Fitted terms (degrees)
        self._AN: float = 0.0
        self._AW: float = 0.0
        self._IE: float = 0.0
        self._CA: float = 0.0
        self._NPAE: float = 0.0

        self._rms_arcmin: float = 0.0
        self._fit_timestamp: float | None = None
        self._n_terms: int = 0

        # Health monitoring: rolling window of recent verification residuals
        self._recent_residuals: deque[float] = deque(maxlen=_HEALTH_WINDOW)
        self._health: str = "unknown"  # "good", "degraded", "unknown"

        self._load_state()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_trained(self) -> bool:
        """True when the full 5-term model has been fitted (8+ points)."""
        return self._n_terms == 5

    @property
    def is_active(self) -> bool:
        """True when any correction is available (3+ points fitted)."""
        return self._n_terms >= 3

    @property
    def point_count(self) -> int:
        return len(self._points)

    @property
    def rms_arcmin(self) -> float:
        return self._rms_arcmin

    @property
    def health(self) -> str:
        return self._health

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def add_point(
        self,
        mount_ra: float,
        mount_dec: float,
        solved_ra: float,
        solved_dec: float,
        site_lat: float,
        site_lon: float,
    ) -> None:
        """Record a (mount-reported, plate-solved) calibration pair.

        Converts both positions to alt/az and stores the error.
        Automatically triggers a refit when enough points are available.

        Args:
            mount_ra: Mount-reported RA in degrees.
            mount_dec: Mount-reported Dec in degrees.
            solved_ra: Plate-solved RA in degrees.
            solved_dec: Plate-solved Dec in degrees.
            site_lat: Observer latitude in degrees.
            site_lon: Observer longitude in degrees.
        """
        gast = _skyfield_gast()
        mount_az, mount_alt = radec_to_altaz(mount_ra, mount_dec, site_lat, site_lon, _gast_override=gast)
        solved_az, solved_alt = radec_to_altaz(solved_ra, solved_dec, site_lat, site_lon, _gast_override=gast)

        d_az = mount_az - solved_az
        if d_az > 180.0:
            d_az -= 360.0
        elif d_az < -180.0:
            d_az += 360.0

        d_alt = mount_alt - solved_alt

        with self._lock:
            self._points.append((solved_az, solved_alt, d_az, d_alt))
            n_points = len(self._points)

        _logger.info(
            "Pointing model: added point #%d — az=%.1f° alt=%.1f° dAz=%.2f' dAlt=%.2f'",
            n_points,
            solved_az,
            solved_alt,
            d_az * 60.0,
            d_alt * 60.0,
        )

        if n_points >= _MIN_POINTS_3TERM:
            self.fit()

    # ------------------------------------------------------------------
    # Model fitting
    # ------------------------------------------------------------------

    def fit(self) -> None:
        """Fit error terms to accumulated calibration points via least-squares.

        Selects 3-term (AN, AW, IE) or 5-term (+ CA, NPAE) based on point count.
        """
        with self._lock:
            n = len(self._points)
            if n < _MIN_POINTS_3TERM:
                _logger.info("Pointing model: only %d points, need %d for fit", n, _MIN_POINTS_3TERM)
                return

            use_5term = n >= _MIN_POINTS_5TERM
            points_snapshot = list(self._points)

        rows_az = []
        rows_alt = []
        obs_az = []
        obs_alt = []

        for az_deg, alt_deg, d_az, d_alt in points_snapshot:
            az = math.radians(az_deg)
            alt = math.radians(alt_deg)

            sin_az = math.sin(az)
            cos_az = math.cos(az)
            tan_alt = math.tan(alt) if abs(math.cos(alt)) > 1e-10 else 0.0
            sec_alt = 1.0 / math.cos(alt) if abs(math.cos(alt)) > 1e-10 else 0.0

            if use_5term:
                rows_az.append([sin_az * tan_alt, -cos_az * tan_alt, 0.0, sec_alt, tan_alt])
            else:
                rows_az.append([sin_az * tan_alt, -cos_az * tan_alt, 0.0])
            obs_az.append(d_az)

            if use_5term:
                rows_alt.append([-cos_az, -sin_az, 1.0, 0.0, 0.0])
            else:
                rows_alt.append([-cos_az, -sin_az, 1.0])
            obs_alt.append(d_alt)

        A = np.array(rows_az + rows_alt)
        b = np.array(obs_az + obs_alt)

        result, _residuals, _rank, _sv = np.linalg.lstsq(A, b, rcond=None)

        # Compute RMS of fit residuals
        predicted = A @ result
        fit_residuals = b - predicted
        rms_deg = float(np.sqrt(np.mean(fit_residuals**2)))

        with self._lock:
            self._AN = float(result[0])
            self._AW = float(result[1])
            self._IE = float(result[2])
            if use_5term:
                self._CA = float(result[3])
                self._NPAE = float(result[4])
                self._n_terms = 5
            else:
                self._CA = 0.0
                self._NPAE = 0.0
                self._n_terms = 3

            self._rms_arcmin = rms_deg * 60.0
            self._fit_timestamp = time.time()
            self._health = "good"
            self._recent_residuals.clear()

            tilt_mag = math.sqrt(self._AN**2 + self._AW**2)
            tilt_dir = math.degrees(math.atan2(self._AW, self._AN)) % 360.0

        _logger.info(
            "Pointing model fit (%d-term, %d points): AN=%.4f° AW=%.4f° IE=%.4f° CA=%.4f° NPAE=%.4f° "
            "| tilt=%.3f° toward %.0f° | RMS=%.1f'",
            self._n_terms,
            n,
            self._AN,
            self._AW,
            self._IE,
            self._CA,
            self._NPAE,
            tilt_mag,
            tilt_dir,
            self._rms_arcmin,
        )

        self._save_state()

    # ------------------------------------------------------------------
    # Correction
    # ------------------------------------------------------------------

    def correct(
        self,
        ra_deg: float,
        dec_deg: float,
        site_lat: float,
        site_lon: float,
    ) -> tuple[float, float]:
        """Apply pointing model correction to a goto target.

        Returns corrected (ra, dec) that should be sent to the mount.
        Returns the original coordinates unchanged if the model is not active.

        Args:
            ra_deg: Target RA in degrees.
            dec_deg: Target Dec in degrees.
            site_lat: Observer latitude in degrees.
            site_lon: Observer longitude in degrees.

        Returns:
            (corrected_ra_deg, corrected_dec_deg).
        """
        if not self.is_active:
            return ra_deg, dec_deg

        gast = _skyfield_gast()
        az, alt = radec_to_altaz(ra_deg, dec_deg, site_lat, site_lon, _gast_override=gast)

        with self._lock:
            d_az, d_alt = self._predict_error_altaz(az, alt)

        corrected_az = az - d_az
        corrected_alt = alt - d_alt
        corrected_ra, corrected_dec = altaz_to_radec(
            corrected_az, corrected_alt, site_lat, site_lon, _gast_override=gast
        )

        return corrected_ra, corrected_dec

    def predict_error(
        self,
        ra_deg: float,
        dec_deg: float,
        site_lat: float,
        site_lon: float,
    ) -> float:
        """Predicted pointing error magnitude in arcmin at the given position.

        Returns ``sqrt((dAz * cos(alt))^2 + dAlt^2) * 60`` so the azimuth
        component is projected onto the sky.  Used by callers to compare
        against observed residuals for health checks.
        Returns 0.0 if the model is not active.
        """
        if not self.is_active:
            return 0.0
        az, alt = radec_to_altaz(ra_deg, dec_deg, site_lat, site_lon)
        with self._lock:
            d_az, d_alt = self._predict_error_altaz(az, alt)
        cos_alt = math.cos(math.radians(alt))
        return math.sqrt((d_az * cos_alt) ** 2 + d_alt**2) * 60.0

    def _predict_error_altaz(self, az_deg: float, alt_deg: float) -> tuple[float, float]:
        """Predicted (dAz, dAlt) error in degrees at the given alt/az."""
        az = math.radians(az_deg)
        alt = math.radians(alt_deg)

        sin_az = math.sin(az)
        cos_az = math.cos(az)
        tan_alt = math.tan(alt) if abs(math.cos(alt)) > 1e-10 else 0.0
        sec_alt = 1.0 / math.cos(alt) if abs(math.cos(alt)) > 1e-10 else 0.0

        d_az = self._CA * sec_alt + self._NPAE * tan_alt + self._AN * sin_az * tan_alt - self._AW * cos_az * tan_alt
        d_alt = self._IE - self._AN * cos_az - self._AW * sin_az

        return d_az, d_alt

    # ------------------------------------------------------------------
    # Health monitoring
    # ------------------------------------------------------------------

    def record_verification_residual(self, residual_arcmin: float) -> None:
        """Record a post-slew plate-solve residual for health monitoring.

        Called by the adapter after a plate-solve-after-slew verification
        (not during calibration).  Tracks a rolling window and degrades
        the health status if residuals consistently exceed expectations.
        """
        with self._lock:
            self._recent_residuals.append(residual_arcmin)
            if len(self._recent_residuals) < _HEALTH_WINDOW:
                return

            threshold = self._rms_arcmin * _HEALTH_DEGRADED_FACTOR if self._rms_arcmin > 0 else 5.0
            above = sum(1 for r in self._recent_residuals if r > threshold)
            if above >= _HEALTH_WINDOW:
                if self._health != "degraded":
                    _logger.warning(
                        "Pointing model health DEGRADED: last %d residuals exceeded %.1f' threshold (3x RMS)",
                        _HEALTH_WINDOW,
                        threshold,
                    )
                self._health = "degraded"
            else:
                self._health = "good"

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all calibration data and fitted terms."""
        with self._lock:
            self._points.clear()
            self._AN = self._AW = self._IE = self._CA = self._NPAE = 0.0
            self._rms_arcmin = 0.0
            self._fit_timestamp = None
            self._n_terms = 0
            self._recent_residuals.clear()
            self._health = "unknown"
        self._save_state()
        _logger.info("Pointing model reset")

    # ------------------------------------------------------------------
    # Status / display
    # ------------------------------------------------------------------

    def _compass_label(self, bearing_deg: float) -> str:
        """Convert a bearing in degrees to an 8-point compass label."""
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        idx = int((bearing_deg + 22.5) % 360.0 / 45.0) % 8
        return dirs[idx]

    def status(self) -> dict[str, Any]:
        """Build a status dict for the web UI."""
        with self._lock:
            if self._n_terms == 0:
                state = "untrained"
            elif self._n_terms == 3:
                state = "partial"
            else:
                state = "trained"

            tilt_mag_deg = math.sqrt(self._AN**2 + self._AW**2)
            tilt_bearing_deg = math.degrees(math.atan2(self._AW, self._AN)) % 360.0

            return {
                "state": state,
                "health": self._health,
                "point_count": len(self._points),
                "n_terms": self._n_terms,
                "tilt_deg": round(tilt_mag_deg, 3),
                "tilt_direction_deg": round(tilt_bearing_deg, 1),
                "tilt_direction_label": self._compass_label(tilt_bearing_deg) if tilt_mag_deg > 0.001 else "",
                "pointing_accuracy_arcmin": round(self._rms_arcmin, 1),
                "fit_timestamp": self._fit_timestamp,
                "terms": {
                    "AN": round(self._AN, 5),
                    "AW": round(self._AW, 5),
                    "IE": round(self._IE, 5),
                    "CA": round(self._CA, 5),
                    "NPAE": round(self._NPAE, 5),
                },
            }

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize model state for persistence."""
        with self._lock:
            return {
                "points": list(self._points),
                "terms": {
                    "AN": self._AN,
                    "AW": self._AW,
                    "IE": self._IE,
                    "CA": self._CA,
                    "NPAE": self._NPAE,
                },
                "n_terms": self._n_terms,
                "rms_arcmin": self._rms_arcmin,
                "fit_timestamp": self._fit_timestamp,
            }

    def _apply_dict(self, data: dict[str, Any]) -> None:
        """Apply serialized state to this instance (no lock — caller must hold it if needed)."""
        self._points = [tuple(p) for p in data.get("points", [])]
        terms = data.get("terms", {})
        self._AN = terms.get("AN", 0.0)
        self._AW = terms.get("AW", 0.0)
        self._IE = terms.get("IE", 0.0)
        self._CA = terms.get("CA", 0.0)
        self._NPAE = terms.get("NPAE", 0.0)
        self._n_terms = data.get("n_terms", 0)
        self._rms_arcmin = data.get("rms_arcmin", 0.0)
        self._fit_timestamp = data.get("fit_timestamp")
        if self._n_terms > 0:
            self._health = "good"

    @classmethod
    def from_dict(cls, data: dict[str, Any], state_file: Path | None = None) -> AltAzPointingModel:
        """Restore a model from a serialized dict."""
        model = cls.__new__(cls)
        model._state_file = state_file
        model._lock = threading.Lock()
        model._points = []
        model._AN = model._AW = model._IE = model._CA = model._NPAE = 0.0
        model._rms_arcmin = 0.0
        model._fit_timestamp = None
        model._n_terms = 0
        model._recent_residuals = deque(maxlen=_HEALTH_WINDOW)
        model._health = "unknown"
        model._apply_dict(data)
        return model

    # ------------------------------------------------------------------
    # File persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        if self._state_file is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self.to_dict()), encoding="utf-8")
        except Exception:
            _logger.debug("Failed to persist pointing model state", exc_info=True)

    def _load_state(self) -> None:
        if self._state_file is None:
            return
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._apply_dict(data)
            _logger.info(
                "Loaded pointing model: %d-term, %d points, RMS=%.1f'",
                self._n_terms,
                len(self._points),
                self._rms_arcmin,
            )
        except Exception:
            _logger.warning("Failed to load pointing model state", exc_info=True)
