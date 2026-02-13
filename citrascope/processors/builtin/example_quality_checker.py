"""Example quality checker processor.

This processor demonstrates the processor pattern by checking basic image quality metrics.
Real processors would implement more sophisticated checks like FWHM, SNR, star detection, etc.
"""

import time

import numpy as np

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessingContext, ProcessorResult


class QualityCheckProcessor(AbstractImageProcessor):
    """Example: Check basic image quality metrics.

    This processor checks for:
    - Saturation (clipped pixels)
    - Low signal (too dark)

    Real implementations would check:
    - FWHM (focus quality)
    - SNR (signal-to-noise ratio)
    - Star count and distribution
    - Tracking quality (elongated stars)
    - Cloud detection
    """

    name = "quality_checker"
    friendly_name = "Quality Checker"
    description = "Validates image quality by checking for saturation and low signal"

    def process(self, context: ProcessingContext) -> ProcessorResult:
        """Process image and check basic quality metrics.

        Args:
            context: ProcessingContext with image and task data

        Returns:
            ProcessorResult with upload decision
        """
        start = time.time()

        # Access image data (already loaded by registry)
        image_data = context.image_data
        if image_data is None:
            from astropy.io import fits

            image_data = fits.getdata(context.image_path)

        # Can access task info directly
        satellite_name = context.task.satelliteName if context.task else None
        task_id = context.task.id if context.task else None

        # Check for saturation
        max_value = np.max(image_data)
        saturated = max_value >= 65535 * 0.95  # 95% of 16-bit max

        # Check for meaningful signal
        mean_value = np.mean(image_data)
        too_dark = mean_value < 100

        # Extract basic stats
        extracted = {
            "max_pixel_value": float(max_value),
            "mean_pixel_value": float(mean_value),
            "std_pixel_value": float(np.std(image_data)),
            "satellite_name": satellite_name,  # Include task context
            "task_id": task_id,
        }

        # Decide
        if saturated:
            return ProcessorResult(
                should_upload=False,
                extracted_data=extracted,
                confidence=0.0,
                reason="Image saturated",
                processing_time_seconds=time.time() - start,
                processor_name=self.name,
            )
        elif too_dark:
            return ProcessorResult(
                should_upload=False,
                extracted_data=extracted,
                confidence=0.2,
                reason="Image too dark (no signal)",
                processing_time_seconds=time.time() - start,
                processor_name=self.name,
            )
        else:
            return ProcessorResult(
                should_upload=True,
                extracted_data=extracted,
                confidence=0.9,
                reason="Image quality acceptable",
                processing_time_seconds=time.time() - start,
                processor_name=self.name,
            )
