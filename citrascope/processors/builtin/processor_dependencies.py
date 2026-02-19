"""Dependency checking for MSI science processors."""

import shutil
from pathlib import Path

import requests


def normalize_fits_timestamp(timestamp: str) -> str:
    """Truncate FITS DATE-OBS fractional seconds to 6 digits (microseconds).

    NINA on Windows writes DATE-OBS with 7 fractional digits using Windows
    FILETIME (100ns) resolution, e.g. "2025-11-12T01:38:11.1054519".
    Python 3.10's datetime.fromisoformat() only accepts up to 6 fractional
    digits; 3.11+ relaxed this restriction. Truncate here so any downstream
    fromisoformat() call is safe on all supported Python versions.
    """
    if timestamp and "." in timestamp:
        dot = timestamp.index(".")
        return timestamp[: dot + 7]  # dot + 6 digits = microseconds
    return timestamp


def check_pixelemon() -> bool:
    """Check if Pixelemon (Tetra3) plate solving is available.

    Returns:
        True if pixelemon can be imported and provides Telescope, TelescopeImage, TetraSolver
    """
    try:
        from pixelemon import Telescope, TelescopeImage, TetraSolver  # noqa: F401

        return True
    except Exception:
        return False


def check_all_dependencies(settings) -> dict:
    """Check for all required external tools and data files.

    Args:
        settings: CitraScopeSettings instance

    Returns:
        Dictionary with dependency check results
    """
    return {
        "pixelemon": check_pixelemon(),
        "sextractor": check_sextractor(),
        "ephemeris": check_ephemeris(),
    }


def check_sextractor() -> bool:
    """Check if SExtractor is installed.

    Returns:
        True if source-extractor or sex command is available
    """
    return shutil.which("source-extractor") is not None or shutil.which("sex") is not None


def get_ephemeris_path() -> Path:
    """Return path to de421.bsp: first location that exists, otherwise canonical (for download).

    Checked in order: citrascope/data/ephemeris/de421.bsp, then repo-root de421.bsp.
    """
    canonical = Path(__file__).parent.parent.parent / "data" / "ephemeris" / "de421.bsp"
    if canonical.exists():
        return canonical
    repo_root = Path(__file__).parent.parent.parent.parent
    if (repo_root / "de421.bsp").exists():
        return repo_root / "de421.bsp"
    return canonical


def check_ephemeris() -> bool:
    """Check if de421.bsp exists; download from NASA NAIF at runtime if missing.

    File is used for phase-angle (Sun/Earth) in the satellite matcher. Not committed;
    see .gitignore. Looks in data/ephemeris/ then repo root.

    Returns:
        True if ephemeris file exists or was successfully downloaded
    """
    path = get_ephemeris_path()
    if path.exists():
        return True

    canonical = Path(__file__).parent.parent.parent / "data" / "ephemeris" / "de421.bsp"
    try:
        download_ephemeris(canonical)
        return True
    except Exception:
        return False


def download_ephemeris(dest_path: Path) -> None:
    """Download de421.bsp ephemeris file from NASA NAIF (Sun/Moon/planets for phase angle).

    Args:
        dest_path: Destination path for the ephemeris file (e.g. .../data/ephemeris/de421.bsp)

    Raises:
        Exception: If download fails (network, timeout, or write error)
    """
    url = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de421.bsp"
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
