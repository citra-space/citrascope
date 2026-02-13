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
        from citrascope.processors.builtin.test_processor import TestProcessor

        self.processors: List[AbstractImageProcessor] = [
            QualityCheckProcessor(),
            TestProcessor(),
            # Add more processors here as you build them
        ]

    def get_all_processors(self) -> List[dict]:
        """Get metadata for all processors (enabled and disabled).

        Returns:
            List of dicts with processor metadata
        """
        return [
            {
                "name": p.name,
                "friendly_name": p.friendly_name,
                "description": p.description,
                "enabled": self.settings.enabled_processors.get(p.name, True),  # Default to enabled
            }
            for p in self.processors
        ]

    def process_all(self, context: ProcessingContext) -> AggregatedResult:
        """Run all enabled processors on an image.

        Args:
            context: ProcessingContext with image and task data

        Returns:
            AggregatedResult with upload decision and combined data
        """
        start_time = time.time()

        # Load image once for all processors if not already loaded
        if context.image_data is None:
            context.image_data = self._load_image(context.image_path)

        # Filter to only enabled processors
        enabled_processors = [
            p for p in self.processors if self.settings.enabled_processors.get(p.name, True)  # Default to enabled
        ]

        results = []
        for processor in enabled_processors:
            # Update status message to show which processor is running
            if context.task:
                context.task.set_status_msg(f"Running {processor.friendly_name}...")

            result = processor.process(context)
            results.append(result)
            # Don't catch exceptions - let them propagate to trigger retries
            # After max retries, ProcessingQueue will fail-open and upload raw image

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
