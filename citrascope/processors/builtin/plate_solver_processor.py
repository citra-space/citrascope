"""Plate solving processor using Astrometry.net."""

import time

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult


class PlateSolverProcessor(AbstractImageProcessor):
    """
    Plate solving processor using Astrometry.net.

    Determines exact telescope pointing and embeds WCS (World Coordinate System)
    into FITS header. Updates context.working_image_path to point to .new file.

    Typical processing time: 30-40 seconds.
    """

    name = "plate_solver"
    friendly_name = "Plate Solver"
    description = "Astrometric calibration via Astrometry.net (determines exact pointing and WCS)"

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with plate solving.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with plate solving outcome
        """
        start_time = time.time()

        # Check dependencies
        from .msi_utils.dependencies import check_astrometry

        if not check_astrometry():
            return ProcessorResult(
                should_upload=True,  # Fail-open
                extracted_data={},
                confidence=0.0,
                reason="Astrometry.net not installed",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            from .msi_utils.astrometry import solve_field

            # Run plate solver
            wcs_image_path = solve_field(
                context.working_image_path,
                timeout=context.settings.plate_solve_timeout,
                index_path=context.settings.astrometry_index_path,
            )

            # Update working image path for subsequent processors
            context.working_image_path = wcs_image_path

            # Extract WCS info from solved image
            from astropy.io import fits

            with fits.open(wcs_image_path) as hdul:
                header = hdul[0].header
                ra_center = header.get("CRVAL1")
                dec_center = header.get("CRVAL2")
                pixel_scale = header.get("CDELT1", 0) * 3600  # arcsec/pixel

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

        except TimeoutError:
            return ProcessorResult(
                should_upload=True,  # Fail-open
                extracted_data={"plate_solved": False},
                confidence=0.0,
                reason="Plate solving timed out",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
        except Exception as e:
            return ProcessorResult(
                should_upload=True,  # Fail-open
                extracted_data={"plate_solved": False},
                confidence=0.0,
                reason=f"Plate solving failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
