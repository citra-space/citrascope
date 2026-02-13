"""SExtractor wrapper for source detection."""

import subprocess
from pathlib import Path

import pandas as pd


def extract_sources(image_path: Path, config_dir: Path, working_dir: Path) -> pd.DataFrame:
    """Run SExtractor and parse catalog.

    Args:
        image_path: Path to FITS image (should be plate-solved with WCS)
        config_dir: Path to directory containing SExtractor config files
        working_dir: Directory for temporary files (catalog will be written here)

    Returns:
        DataFrame with columns: ra, dec, mag, magerr, fwhm

    Raises:
        RuntimeError: If SExtractor fails
    """
    # Ensure paths are absolute
    image_path = image_path.resolve()
    config_dir = config_dir.resolve()
    working_dir = working_dir.resolve()

    # Catalog will be written to working directory with relative name
    catalog_name = f"{image_path.stem}.cat"
    catalog_path = working_dir / catalog_name

    # Build SExtractor command (will run from working_dir)
    cmd = [
        "sex",  # Standard command name from Homebrew/most installations
        str(image_path),  # Absolute path to image
        "-c",
        str(config_dir / "default.sex"),  # Absolute path to config
        "-PARAMETERS_NAME",
        str(config_dir / "default.param"),  # Absolute path
        "-FILTER_NAME",
        str(config_dir / "default.conv"),  # Absolute path
        "-STARNNW_NAME",
        str(config_dir / "default.nnw"),  # Absolute path
        "-CATALOG_NAME",
        catalog_name,  # Relative to cwd (working_dir)
    ]

    # Try 'sex' command first (most common)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(working_dir))

        # If sex not found, try 'source-extractor' alias
        if result.returncode == 127 or "not found" in result.stderr.lower():
            cmd[0] = "source-extractor"
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(working_dir))
    except FileNotFoundError:
        # Command doesn't exist, try alternate name
        cmd[0] = "source-extractor"
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(working_dir))
        except FileNotFoundError:
            raise RuntimeError("SExtractor not found. Install with: brew install sextractor")

    if result.returncode != 0:
        raise RuntimeError(f"SExtractor failed: {result.stderr}")

    # Parse catalog
    sources = parse_sex_catalog(catalog_path)
    return sources


def parse_sex_catalog(catalog_path: Path) -> pd.DataFrame:
    """Parse SExtractor catalog into DataFrame.

    Based on generate_obs.py lines 29-37, the catalog columns are:
    - Column 4: MAG_AUTO (magnitude)
    - Column 5: MAGERR_AUTO (magnitude error)
    - Column 8: ALPHA_J2000 (RA)
    - Column 9: DELTA_J2000 (Dec)
    - Column 10: FWHM_IMAGE (FWHM in pixels)

    Args:
        catalog_path: Path to SExtractor catalog file

    Returns:
        DataFrame with columns: ra, dec, mag, magerr, fwhm
    """
    sources = []

    with open(catalog_path, "r") as f:
        for line in f:
            # Skip comment lines
            if line.startswith("#"):
                continue

            cols = line.split()
            if len(cols) < 11:
                continue

            try:
                sources.append(
                    {
                        "ra": float(cols[8]),  # ALPHA_J2000
                        "dec": float(cols[9]),  # DELTA_J2000
                        "mag": float(cols[4]),  # MAG_AUTO
                        "magerr": float(cols[5]),  # MAGERR_AUTO
                        "fwhm": float(cols[10]),  # FWHM_IMAGE
                    }
                )
            except (ValueError, IndexError):
                # Skip malformed lines
                continue

    return pd.DataFrame(sources)
