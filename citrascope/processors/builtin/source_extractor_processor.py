"""Source extraction processor using SExtractor."""

import time
from pathlib import Path

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult


class SourceExtractorProcessor(AbstractImageProcessor):
    """
    Source extraction processor using SExtractor.

    Detects all sources (stars and satellites) in the image and extracts
    their positions, magnitudes, and FWHM. Requires plate-solved image with WCS.

    Typical processing time: 2-5 seconds.
    """

    name = "source_extractor"
    friendly_name = "Source Extractor"
    description = "Detect stars and satellites via SExtractor (requires plate-solved image)"

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with source extraction.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with source extraction outcome
        """
        start_time = time.time()

        # Check if image has WCS (requires plate solver to have run)
        from astropy.io import fits

        try:
            with fits.open(context.working_image_path) as hdul:
                if "CRVAL1" not in hdul[0].header:
                    return ProcessorResult(
                        should_upload=True,
                        extracted_data={},
                        confidence=0.0,
                        reason="Image not plate-solved (WCS missing)",
                        processing_time_seconds=time.time() - start_time,
                        processor_name=self.name,
                    )
        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Could not read image: {e}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        # Check dependencies
        from .msi_utils.dependencies import check_sextractor

        if not check_sextractor():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="SExtractor not installed",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            from .msi_utils.sextractor import extract_sources

            config_dir = Path(__file__).parent / "msi_utils" / "config_files"
            sources_df = extract_sources(context.working_image_path, config_dir, context.working_dir)

            elapsed = time.time() - start_time

            return ProcessorResult(
                should_upload=True,
                extracted_data={
                    "num_sources": len(sources_df),
                    "sources_catalog": str(context.working_dir / f"{context.working_image_path.stem}.cat"),
                },
                confidence=1.0,
                reason=f"Extracted {len(sources_df)} sources in {elapsed:.1f}s",
                processing_time_seconds=elapsed,
                processor_name=self.name,
            )

        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Source extraction failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
