"""Satellite association processor using TLE propagation."""

import time

import pandas as pd

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult


class SatelliteMatcherProcessor(AbstractImageProcessor):
    """
    Satellite association processor using TLE propagation.

    Propagates TLEs for target satellite, predicts position at image timestamp,
    and matches detected sources with predicted positions. Requires all previous
    processors to have run successfully.

    Typical processing time: 1-2 seconds.
    """

    name = "satellite_matcher"
    friendly_name = "Satellite Matcher"
    description = "Match detected sources with TLE predictions (requires full pipeline)"

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image with satellite matching.

        Args:
            context: Processing context with image and settings

        Returns:
            ProcessorResult with satellite matching outcome
        """
        start_time = time.time()

        # Check prerequisites
        catalog_path = context.working_dir / "output.cat"
        if not catalog_path.exists():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="Source catalog not found",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        # Check for ephemeris
        from .msi_utils.dependencies import check_ephemeris

        if not check_ephemeris():
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason="Ephemeris file missing (de421.bsp)",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )

        try:
            from .msi_utils.tle_matching import match_satellites

            # Load sources
            sources_df = pd.read_csv(catalog_path, delim_whitespace=True, comment="#")

            # Match satellites
            satellite_observations = match_satellites(
                sources_df, context, tracking_mode="rate"  # Could make this configurable
            )

            elapsed = time.time() - start_time

            return ProcessorResult(
                should_upload=True,
                extracted_data={
                    "num_satellites_detected": len(satellite_observations),
                    "satellite_observations": satellite_observations,
                },
                confidence=1.0 if satellite_observations else 0.5,
                reason=f"Matched {len(satellite_observations)} satellite(s) in {elapsed:.1f}s",
                processing_time_seconds=elapsed,
                processor_name=self.name,
            )

        except Exception as e:
            return ProcessorResult(
                should_upload=True,
                extracted_data={},
                confidence=0.0,
                reason=f"Satellite matching failed: {str(e)}",
                processing_time_seconds=time.time() - start_time,
                processor_name=self.name,
            )
