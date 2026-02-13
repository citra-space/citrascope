"""Plate solving processor using Astrometry.net."""

import subprocess
import time
from pathlib import Path
from typing import Optional

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

    def _solve_field(self, image_path: Path, timeout: int = 40, index_path: Optional[str] = None) -> Path:
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

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with plate solving.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with plate solving outcome
        """
        start_time = time.time()

        # Check dependencies
        from .processor_dependencies import check_astrometry

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
            # Run plate solver
            wcs_image_path = self._solve_field(
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
