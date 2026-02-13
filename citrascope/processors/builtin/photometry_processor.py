"""Photometric calibration processor using APASS catalog."""

import time

import pandas as pd

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult


class PhotometryProcessor(AbstractImageProcessor):
    """
    Photometric calibration processor using APASS catalog.

    Queries APASS all-sky catalog, cross-matches detected sources with catalog stars,
    and calculates magnitude zero point. Requires source extraction to have run.

    Typical processing time: 2-5 seconds.
    """

    name = "photometry"
    friendly_name = "Photometry Calibrator"
    description = "Photometric calibration via APASS catalog (requires source extraction)"

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with photometric calibration.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with photometry outcome
        """
        start_time = time.time()

        # Check if sources were extracted
        catalog_path = context.working_dir / "output.cat"
        if not catalog_path.exists():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="Source catalog not found (source extraction must run first)",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            from .msi_utils.apass import calibrate_photometry

            # Load source catalog
            sources_df = pd.read_csv(catalog_path, delim_whitespace=True, comment="#")

            # Get filter name
            filter_name = context.task.assigned_filter_name if context.task else "Clear"

            # Calibrate
            zero_point, num_matched = calibrate_photometry(sources_df, context.working_image_path, filter_name)

            elapsed = time.time() - start_time

            return ProcessorResult(
                should_upload=True,
                extracted_data={
                    "zero_point": zero_point,
                    "num_calibration_stars": num_matched,
                    "filter": filter_name,
                },
                confidence=1.0 if num_matched >= 10 else 0.5,
                reason=f"Calibrated with {num_matched} stars (ZP={zero_point:.2f}) in {elapsed:.1f}s",
                processing_time_seconds=elapsed,
                processor_name=self.name,
            )

        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Photometry failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
