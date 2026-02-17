"""Plate solving processor using Pixelemon (Tetra3)."""

import time
from pathlib import Path
from typing import Optional

from astropy.io import fits
from astropy.wcs import WCS

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult

from .processor_dependencies import check_pixelemon


def _build_telescope_for_image(image_path: Path):
    """Build a Telescope (sensor + optics) matching the image dimensions in the FITS file."""
    from pixelemon import Telescope
    from pixelemon.optics._base_optical_assembly import BaseOpticalAssembly
    from pixelemon.sensors._base_sensor import BaseSensor

    with fits.open(image_path) as hdul:
        header = hdul[0].header
        nx = int(header.get("NAXIS1", 1280))
        ny = int(header.get("NAXIS2", 1024))

    # Default pixel size (um) and optics; can be made configurable via settings
    sensor = BaseSensor(
        x_pixel_count=nx,
        y_pixel_count=ny,
        pixel_width=5.86,
        pixel_height=5.86,
    )
    optics = BaseOpticalAssembly(
        image_circle_diameter=9.61,
        focal_length=300,
        focal_ratio=6,
    )
    return Telescope(sensor=sensor, optics=optics)


def _fits_has_observer_location(header: fits.Header) -> bool:
    """True if FITS has full observer location (Pixelemon expects SITELAT/SITELONG/SITEALT or equivalents)."""
    if "SITELAT" in header and "SITELONG" in header and "SITEALT" in header:
        return True
    if "OBSGEO-L" in header and "OBSGEO-B" in header and "OBSGEO-H" in header:
        return True
    if "LAT-OBS" in header and "LONG-OBS" in header:
        return True
    return False


def _ensure_fits_has_observer_location(image_path: Path, context: ProcessingContext, working_dir: Path) -> Path:
    """If FITS lacks observer location and context has it, write a copy with SITELAT/SITELONG/SITEALT. Return path to use."""
    with fits.open(image_path) as hdul:
        header = hdul[0].header
        if _fits_has_observer_location(header):
            return image_path
        location = None
        try:
            # Runtime: use context.daemon (set by ProcessingQueue). Tests: can use context.daemon or settings.daemon.
            daemon = context.daemon or getattr(context.settings, "daemon", None)
            if daemon and getattr(daemon, "location_service", None):
                location = daemon.location_service.get_current_location()
        except Exception:
            pass
        if not location or not isinstance(location, dict):
            return image_path
        lat = location.get("latitude")
        lon = location.get("longitude")
        alt = location.get("altitude", 0)
        if lat is None or lon is None:
            return image_path
        out_path = working_dir / image_path.name
        if out_path.resolve() == image_path.resolve():
            return image_path
        new_header = header.copy()
        new_header["SITELAT"] = float(lat)
        new_header["SITELONG"] = float(lon)
        new_header["SITEALT"] = float(alt)
        fits.writeto(out_path, hdul[0].data, new_header, overwrite=True)
        return out_path


def _solution_to_wcs_header(solution, naxis1: int, naxis2: int) -> fits.Header:
    """Build a FITS header with WCS from a Pixelemon plate solve solution."""
    ra_deg = float(solution.right_ascension)
    dec_deg = float(solution.declination)
    fov_deg = float(getattr(solution, "estimated_horizontal_fov", 1.0))
    if fov_deg <= 0:
        fov_deg = 1.0

    # Pixel scale in deg/pixel (RA typically negative)
    scale_deg = fov_deg / max(naxis1, 1)
    cdelt1 = -scale_deg
    cdelt2 = scale_deg

    w = WCS(naxis=2)
    w.wcs.crpix = [naxis1 / 2.0 + 0.5, naxis2 / 2.0 + 0.5]
    w.wcs.crval = [ra_deg, dec_deg]
    w.wcs.cdelt = [cdelt1, cdelt2]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return w.to_header()


class PlateSolverProcessor(AbstractImageProcessor):
    """
    Plate solving processor using Pixelemon (Tetra3).

    Determines exact telescope pointing and embeds WCS (World Coordinate System)
    into a .new FITS file. Updates context.working_image_path to point to that file.

    Typical processing time: a few seconds (Tetra3).
    """

    name = "plate_solver"
    friendly_name = "Plate Solver"
    description = "Astrometric calibration via Pixelemon/Tetra3 (determines exact pointing and WCS)"

    def _solve_with_pixelemon(self, image_path: Path, context: Optional[ProcessingContext] = None) -> Path:
        """Run Pixelemon (Tetra3) plate solve and write WCS to a .new file.

        Args:
            image_path: Path to FITS image to solve
            context: Optional processing context (unused; for API consistency)

        Returns:
            Path to .new file with WCS in header

        Raises:
            RuntimeError: If plate solving fails or solution is None
        """
        from pixelemon import TelescopeImage, TetraSolver

        TetraSolver.high_memory()
        telescope = _build_telescope_for_image(image_path)
        image = TelescopeImage.from_fits_file(image_path, telescope)
        solve = image.plate_solve

        if solve is None:
            raise RuntimeError("Pixelemon plate solving returned no solution")

        with fits.open(image_path) as hdul:
            naxis1 = hdul[0].header.get("NAXIS1", 0)
            naxis2 = hdul[0].header.get("NAXIS2", 0)
            if naxis1 <= 0 or naxis2 <= 0:
                raise RuntimeError("FITS image has invalid dimensions")

            wcs_header = _solution_to_wcs_header(solve, naxis1, naxis2)
            new_header = hdul[0].header.copy()
            new_header.update(wcs_header)
            new_file = image_path.with_suffix(".new")
            fits.writeto(new_file, hdul[0].data, new_header, overwrite=True)

        return new_file

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with plate solving.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with plate solving outcome
        """
        start_time = time.time()

        if not check_pixelemon():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="Pixelemon not available",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            path_to_solve = _ensure_fits_has_observer_location(context.working_image_path, context, context.working_dir)
            context.working_image_path = path_to_solve
            wcs_image_path = self._solve_with_pixelemon(path_to_solve, context)
            context.working_image_path = wcs_image_path

            with fits.open(wcs_image_path) as hdul:
                header = hdul[0].header
                ra_center = header.get("CRVAL1")
                dec_center = header.get("CRVAL2")
                pixel_scale = abs(header.get("CDELT1", 0)) * 3600  # arcsec/pixel

            elapsed = time.time() - start_time

            return ProcessorResult(
                should_upload=True,
                extracted_data={
                    "plate_solved": True,
                    "ra_center": ra_center,
                    "dec_center": dec_center,
                    "pixel_scale": pixel_scale,
                    "wcs_image_path": str(wcs_image_path),
                },
                confidence=1.0,
                reason=f"Plate solved in {elapsed:.1f}s",
                processing_time_seconds=elapsed,
                processor_name=self.name,
            )

        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={"plate_solved": False},
                confidence=0.0,
                reason=f"Plate solving failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
