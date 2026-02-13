"""Slow test processor for pipeline visualization testing."""

import time

from citrascope.processors.abstract_processor import AbstractImageProcessor
from citrascope.processors.processor_result import ProcessorResult


class SlowTestProcessor(AbstractImageProcessor):
    """
    A slow processor that takes 20 seconds to run.

    Perfect for testing the pipeline visualization - lets you see tasks
    sitting in the processing stage for a while.
    """

    name = "slow_test"
    friendly_name = "Slow Test Processor"
    description = "Test processor with 20-second delay for pipeline visualization testing"

    def process(self, context) -> ProcessorResult:
        """Run a slow test process (20 second delay)."""
        start = time.time()

        if context.logger:
            context.logger.info(f"SlowTestProcessor: Starting 20-second processing for {context.task.satelliteName}")

        # Simulate long-running processing (e.g., plate solving, photometry)
        time.sleep(20)

        if context.logger:
            context.logger.info(f"SlowTestProcessor: Completed processing for {context.task.satelliteName}")

        return ProcessorResult(
            should_upload=True,
            extracted_data={
                "slow_test.processing_time": 20.0,
                "slow_test.satellite": context.task.satelliteName,
            },
            confidence=1.0,
            reason="Slow test processing complete",
            processing_time_seconds=time.time() - start,
            processor_name=self.name,
        )
