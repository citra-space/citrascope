"""APASS catalog query and photometric calibration."""

from io import StringIO
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import requests
from astropy.io import fits
from astropy.wcs import WCS
from scipy.spatial import KDTree


def calibrate_photometry(sources: pd.DataFrame, image_path: Path, filter_name: str) -> Tuple[float, int]:
    """Query APASS catalog and calculate magnitude zero point.

    Args:
        sources: DataFrame with detected sources (columns: ra, dec, mag)
        image_path: Path to FITS image (for WCS info)
        filter_name: Filter name (Clear, g, r, i)

    Returns:
        Tuple of (zero_point, num_matched_stars)

    Raises:
        RuntimeError: If calibration fails
    """
    # Get field center from WCS
    with fits.open(image_path) as hdul:
        wcs = WCS(hdul[0].header)
        header = hdul[0].header
        nx, ny = header["NAXIS1"], header["NAXIS2"]
        center = wcs.pixel_to_world(nx / 2, ny / 2)
        ra_center, dec_center = center.ra.deg, center.dec.deg

    # Query APASS catalog
    apass_stars = query_apass(ra_center, dec_center, radius=2.0)

    if apass_stars.empty:
        raise RuntimeError("No APASS stars found in field")

    # Cross-match detected sources with APASS
    matched = cross_match_catalogs(sources, apass_stars, max_separation=1.0 / 60.0)

    if matched.empty or len(matched) < 3:
        raise RuntimeError(f"Insufficient matched stars for calibration: {len(matched)}")

    # Calculate zero point for specified filter
    filter_col = {"Clear": "Johnson_V (V)", "g": "Sloan_g (SG)", "r": "Sloan_r (SR)", "i": "Sloan_i (SI)"}.get(
        filter_name, "Johnson_V (V)"
    )

    # Convert to numeric and drop NaN
    matched["mag"] = pd.to_numeric(matched["mag"], errors="coerce")
    matched[filter_col] = pd.to_numeric(matched[filter_col], errors="coerce")
    matched_clean = matched.dropna(subset=["mag", filter_col])

    if len(matched_clean) < 3:
        raise RuntimeError(f"Insufficient valid stars after cleaning: {len(matched_clean)}")

    # Calculate zero point (median difference between catalog and instrumental mags)
    zero_point = np.nanmedian(matched_clean[filter_col] - matched_clean["mag"])

    return zero_point, len(matched_clean)


def query_apass(ra: float, dec: float, radius: float = 2.0) -> pd.DataFrame:
    """Query APASS catalog via AAVSO.

    Args:
        ra: Right ascension in degrees
        dec: Declination in degrees
        radius: Search radius in degrees (default: 2.0)

    Returns:
        DataFrame with APASS stars

    Raises:
        RuntimeError: If query fails
    """
    url = "https://www.aavso.org/cgi-bin/apass_dr10_download.pl"

    form_data = {
        "ra": str(ra),
        "dec": str(dec),
        "radius": str(radius),
        "outtype": "1",  # CSV format
    }

    try:
        response = requests.post(url, data=form_data, timeout=30)
        response.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"APASS query failed: {e}")

    # Parse CSV response
    try:
        # APASS returns CSV with header
        apass_df = pd.read_csv(StringIO(response.text))

        # Check if we got valid data
        if apass_df.empty:
            raise RuntimeError("APASS query returned no results")

        return apass_df

    except Exception as e:
        raise RuntimeError(f"Failed to parse APASS response: {e}")


def cross_match_catalogs(sources: pd.DataFrame, catalog: pd.DataFrame, max_separation: float) -> pd.DataFrame:
    """Cross-match two catalogs using KDTree.

    Args:
        sources: DataFrame with detected sources (columns: ra, dec)
        catalog: DataFrame with catalog stars (columns: radeg, decdeg)
        max_separation: Maximum separation in degrees

    Returns:
        DataFrame with matched sources and catalog data concatenated
    """
    # Build KDTree from catalog coordinates
    coords_catalog = catalog[["radeg", "decdeg"]].values
    tree = KDTree(coords_catalog)

    # Query tree with source coordinates
    coords_sources = sources[["ra", "dec"]].values
    distances, indices = tree.query(coords_sources, distance_upper_bound=max_separation)

    # Filter to valid matches
    valid = distances < max_separation

    if not valid.any():
        return pd.DataFrame()

    # Concatenate matched rows
    matched = pd.concat(
        [sources.iloc[valid].reset_index(drop=True), catalog.iloc[indices[valid]].reset_index(drop=True)], axis=1
    )

    return matched
