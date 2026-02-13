"""Astrometry.net wrapper for plate solving."""

import subprocess
from pathlib import Path
from typing import Optional


def solve_field(image_path: Path, timeout: int = 40, index_path: Optional[str] = None) -> Path:
    """Run Astrometry.net solve-field on image.

    Args:
        image_path: Path to FITS image to solve
        timeout: CPU time limit in seconds (default: 40)
        index_path: Optional path to astrometry index files directory

    Returns:
        Path to .new file with WCS in header

    Raises:
        RuntimeError: If plate solving fails
        TimeoutError: If plate solving times out
    """
    cmd = [
        "solve-field",
        str(image_path),
        "--cpulimit",
        str(timeout),
        "--overwrite",
        "--no-plots",
    ]

    # Add index path if specified
    if index_path:
        cmd.extend(["--dir", str(index_path)])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 10  # Allow extra time for subprocess overhead
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Plate solving timed out after {timeout}s")

    if result.returncode != 0:
        raise RuntimeError(f"Plate solving failed: {result.stderr}")

    # Check that .new file was created
    new_file = image_path.with_suffix(".new")
    if not new_file.exists():
        raise RuntimeError("Plate solving did not produce .new file")

    return new_file
