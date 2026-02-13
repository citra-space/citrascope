"""Test processor for pipeline visualization and retry testing."""

import random
import time

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessorResult


class TestProcessor(AbstractImageProcessor):
    """
    A test processor that takes 20 seconds to run and randomly fails.

    Perfect for testing:
    - Pipeline visualization (see tasks in processing stage)
    - Retry logic (random failures trigger retries)
    """

    delay_seconds = 20
    failure_rate = 0.3  # 30% chance of failure

    name = "test"
    friendly_name = "Test Processor"
    description = "Test processor with 20-second delay and random failures for testing retry logic"

    def process(self, context) -> ProcessorResult:
        """Run a slow test process with random failures."""
        start = time.time()

        if context.logger:
            context.logger.info(f"TestProcessor: Starting 20-second processing for {context.task.satelliteName}")

        # Simulate long-running processing (e.g., plate solving, photometry)
        time.sleep(self.delay_seconds)

        # Randomly fail to test retry logic
        if random.random() < self.failure_rate:
            if context.logger:
                context.logger.warning(f"TestProcessor: Random failure for {context.task.satelliteName}")
            raise RuntimeError("Simulated random processing failure for testing")

        if context.logger:
            context.logger.info(f"TestProcessor: Completed processing for {context.task.satelliteName}")

        return ProcessorResult(
            should_upload=True,
            extracted_data={
                "test.processing_time": float(self.delay_seconds),
                "test.satellite": context.task.satelliteName,
            },
            confidence=1.0,
            reason="Test processing complete",
            processing_time_seconds=time.time() - start,
            processor_name=self.name,
        )
