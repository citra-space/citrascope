"""Registry for managing and executing image processors."""

import time
from pathlib import Path
from typing import List

import numpy as np

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import AggregatedResult, ProcessingContext, ProcessorResult


class ProcessorRegistry:
    """Manages and executes image processors."""

    def __init__(self, settings, logger):
        """Initialize the processor registry.

        Args:
            settings: CitraScopeSettings instance
            logger: Logger instance for diagnostics
        """
        self.settings = settings
        self.logger = logger

        # Hardcode processor list (simple, explicit)
        from citrascope.processors.builtin.example_quality_checker import QualityCheckProcessor

        self.processors: List[AbstractImageProcessor] = [
            QualityCheckProcessor(),
            # Add more processors here as you build them
        ]

    def process_all(self, context: ProcessingContext) -> AggregatedResult:
        """Run all processors on an image.

        Args:
            context: ProcessingContext with image and task data

        Returns:
            AggregatedResult with upload decision and combined data
        """
        start_time = time.time()

        # Load image once for all processors if not already loaded
        if context.image_data is None:
            context.image_data = self._load_image(context.image_path)

        results = []
        for processor in self.processors:
            try:
                result = processor.process(context)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Processor {processor.name} failed: {e}", exc_info=True)
                # Fail-open: errors don't block upload

        total_time = time.time() - start_time
        return self._aggregate_results(results, total_time)

    def _aggregate_results(self, results: List[ProcessorResult], total_time: float) -> AggregatedResult:
        """Combine processor results into upload decision.

        Logic:
        - If ANY processor says don't upload → don't upload
        - Combine extracted_data with processor name prefixes

        Args:
            results: List of individual processor results
            total_time: Total processing time in seconds

        Returns:
            AggregatedResult with combined decision and data
        """
        should_upload = all(r.should_upload for r in results) if results else True

        # Combine extracted data with processor name prefixes to avoid collisions
        combined_data = {}
        for result in results:
            for key, value in result.extracted_data.items():
                prefixed_key = f"{result.processor_name}.{key}"
                combined_data[prefixed_key] = value

        # Find first rejection reason if any
        skip_reason = None
        for result in results:
            if not result.should_upload:
                skip_reason = f"{result.processor_name}: {result.reason}"
                break

        return AggregatedResult(
            should_upload=should_upload,
            extracted_data=combined_data,
            all_results=results,
            total_time=total_time,
            skip_reason=skip_reason,
        )

    def _load_image(self, image_path: Path) -> np.ndarray:
        """Load image from FITS file.

        Args:
            image_path: Path to FITS file

        Returns:
            Numpy array with image data
        """
        from astropy.io import fits

        return fits.getdata(image_path)
