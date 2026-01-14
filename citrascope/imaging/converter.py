"""FITS to preview image converter for web display."""

import io
import logging
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

logger = logging.getLogger(__name__)


def convert_fits_to_preview_bytes(fits_path: Path, max_width: int = 800) -> bytes | None:
    """Convert a FITS file to PNG preview image bytes.

    Reads a FITS file, applies basic linear stretch (min/max scaling),
    and returns PNG bytes suitable for web display.

    Args:
        fits_path: Path to the input FITS file
        max_width: Maximum width of the output image in pixels (height scaled proportionally)

    Returns:
        bytes | None: PNG image bytes if conversion succeeded, None otherwise
    """
    try:
        # Read FITS file
        with fits.open(fits_path) as hdul:
            # Get the primary image data
            data = hdul[0].data
            if data is None:
                logger.error(f"No image data found in FITS file: {fits_path}")
                return None

            # Handle different data shapes (2D image, 3D cube, etc.)
            if data.ndim == 3:
                # If 3D, take the first slice (common for some capture software)
                data = data[0]
            elif data.ndim > 3:
                logger.error(f"Unsupported FITS data dimensions: {data.ndim}")
                return None

            # Convert to float for processing
            data = data.astype(np.float64)

            # Apply simple min/max linear stretch
            min_val = np.min(data)
            max_val = np.max(data)

            if max_val == min_val:
                # Flat image, just make it gray
                stretched = np.full_like(data, 128, dtype=np.uint8)
            else:
                # Scale to 0-255 range
                stretched = ((data - min_val) / (max_val - min_val) * 255).astype(np.uint8)

            # Create PIL image
            img = Image.fromarray(stretched, mode="L")

            # Resize if necessary
            if img.width > max_width:
                aspect_ratio = img.height / img.width
                new_height = int(max_width * aspect_ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

            # Save to bytes buffer
            buffer = io.BytesIO()
            img.save(buffer, "PNG", optimize=False, compress_level=0)
            png_bytes = buffer.getvalue()

            logger.info(f"Created preview image from {fits_path} ({len(png_bytes)} bytes)")
            return png_bytes

    except Exception as e:
        logger.error(f"Failed to convert FITS to preview: {e}", exc_info=True)
        return None
