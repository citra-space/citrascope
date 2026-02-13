"""Dependency checking for MSI science processors."""

import shutil
from pathlib import Path
from typing import Optional

import requests


def check_all_dependencies(settings) -> dict:
    """Check for all required external tools and data files.

    Args:
        settings: CitraScopeSettings instance

    Returns:
        Dictionary with dependency check results
    """
    return {
        "astrometry": check_astrometry(),
        "sextractor": check_sextractor(),
        "ephemeris": check_ephemeris(),
        "index_files": check_astrometry_indices(settings.astrometry_index_path),
    }


def check_astrometry() -> bool:
    """Check if Astrometry.net is installed.

    Returns:
        True if solve-field command is available
    """
    return shutil.which("solve-field") is not None


def check_sextractor() -> bool:
    """Check if SExtractor is installed.

    Returns:
        True if source-extractor or sex command is available
    """
    return shutil.which("source-extractor") is not None or shutil.which("sex") is not None


def check_ephemeris() -> bool:
    """Check if de421.bsp exists, download if missing.

    Returns:
        True if ephemeris file exists or was successfully downloaded
    """
    ephemeris_path = Path(__file__).parent.parent.parent / "data" / "ephemeris" / "de421.bsp"

    if ephemeris_path.exists():
        return True

    # Auto-download on first run
    try:
        download_ephemeris(ephemeris_path)
        return True
    except Exception:
        return False


def download_ephemeris(dest_path: Path) -> None:
    """Download de421.bsp ephemeris file from NASA NAIF.

    Args:
        dest_path: Destination path for the ephemeris file

    Raises:
        Exception: If download fails
    """
    url = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de421.bsp"
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def check_astrometry_indices(index_path: Optional[str]) -> bool:
    """Check if astrometry index files exist.

    Args:
        index_path: Path to directory containing index files

    Returns:
        True if at least one 4100-series index file exists
    """
    if not index_path:
        return False

    path = Path(index_path)
    if not path.exists():
        return False

    # Check for at least one 4100-series index file
    indices = list(path.glob("index-41*.fits"))
    return len(indices) > 0
