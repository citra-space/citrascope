"""Calibration suite generators — build job lists for one-click calibration.

Pure functions that produce ordered lists of capture-parameter dicts
from a CalibrationProfile and settings.  No side effects, no hardware calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from citrascope.hardware.devices.camera.abstract_camera import CalibrationProfile

SUITE_MAX_BINNING = 2


def bias_and_dark_suite(
    profile: CalibrationProfile,
    exposure_seconds: float,
    frame_count: int,
) -> list[dict[str, Any]]:
    """Generate ordered job list: all biases first, then all darks.

    Biases are instant (0 s, shutter closed) so they run first without
    waiting for temperature.  Darks follow, sharing a single temp-wait
    gate in CalibrationManager.

    Binning is limited to <= SUITE_MAX_BINNING (1x1, 2x2) since higher
    binnings are rarely used for satellite photometry.
    """
    jobs: list[dict[str, Any]] = []
    gain = profile.current_gain or 0
    suite_binnings = sorted(b for b in profile.supported_binning if b <= SUITE_MAX_BINNING)

    for binning in suite_binnings:
        jobs.append({"frame_type": "bias", "count": frame_count, "gain": gain, "binning": binning})
    for binning in suite_binnings:
        jobs.append(
            {
                "frame_type": "dark",
                "count": frame_count,
                "gain": gain,
                "binning": binning,
                "exposure_time": exposure_seconds,
            }
        )
    return jobs


def all_flats_suite(
    profile: CalibrationProfile,
    filters: list[dict[str, Any]],
    frame_count: int,
    initial_exposure: float = 1.0,
) -> list[dict[str, Any]]:
    """Generate one flat job per enabled filter at current binning.

    Auto-expose runs independently for each filter so the operator just
    needs a uniform light source (twilight sky, flat panel, etc.).
    """
    jobs: list[dict[str, Any]] = []
    gain = profile.current_gain or 0
    binning = profile.current_binning
    for f in filters:
        jobs.append(
            {
                "frame_type": "flat",
                "count": frame_count,
                "gain": gain,
                "binning": binning,
                "exposure_time": initial_exposure,
                "filter_position": f["position"],
                "filter_name": f["name"],
            }
        )
    return jobs
