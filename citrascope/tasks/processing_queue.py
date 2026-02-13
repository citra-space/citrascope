"""Background processing queue for image processing."""

from pathlib import Path
from typing import Callable

from citrascope.tasks.base_work_queue import BaseWorkQueue


class ProcessingQueue(BaseWorkQueue):
    """
    Background worker queue for image processing.
    Allows multiple processing tasks to run concurrently without blocking telescope.
    """

    def __init__(self, num_workers: int = 1, settings=None, logger=None):
        """
        Initialize processing queue.

        Args:
            num_workers: Number of concurrent processing threads (default: 1)
            settings: Settings instance with retry configuration
            logger: Logger instance
        """
        super().__init__(num_workers, settings, logger)

    def submit(self, task_id: str, image_path: Path, context: dict, on_complete: Callable):
        """
        Submit image for processing.

        Args:
            task_id: Task identifier
            image_path: Path to captured image
            context: Processing context (task, settings, daemon, etc.)
            on_complete: Callback(task_id, result) when processing finishes
        """
        self.logger.info(f"Queuing task {task_id} for processing")
        self.work_queue.put(
            {"task_id": task_id, "image_path": image_path, "context": context, "on_complete": on_complete}
        )

    def _execute_work(self, item):
        """Execute image processing work."""
        from citrascope.processors.processor_result import ProcessingContext

        task_id = item["task_id"]
        task_obj = item["context"].get("task")

        self.logger.info(f"[ProcessingWorker] Processing task {task_id}")

        try:
            # Build processing context
            context = ProcessingContext(
                image_path=item["image_path"],
                image_data=None,  # Loaded by processors
                task=task_obj,
                telescope_record=item["context"].get("telescope_record"),
                ground_station_record=item["context"].get("ground_station_record"),
                settings=item["context"].get("settings"),
                logger=self.logger,  # Pass logger to processors
            )

            # Get processor registry from daemon
            daemon = item["context"]["daemon"]
            result = daemon.processor_registry.process_all(context)

            # Success
            self.logger.info(f"[ProcessingWorker] Task {task_id} processed in {result.total_time:.2f}s")
            return (True, result)

        except Exception as e:
            self.logger.error(f"[ProcessingWorker] Processing failed for {task_id}: {e}", exc_info=True)
            return (False, None)

    def _on_success(self, item, result):
        """Handle successful processing completion."""
        task_id = item["task_id"]
        task_obj = item["context"].get("task")
        on_complete = item["on_complete"]

        if task_obj:
            task_obj.set_status_msg("Processing complete")

        on_complete(task_id, result)

    def _on_permanent_failure(self, item):
        """Handle permanent processing failure (fail-open: upload raw image)."""
        task_id = item["task_id"]
        task_obj = item["context"].get("task")
        on_complete = item["on_complete"]

        self.logger.error(f"[ProcessingWorker] Task {task_id} processing permanently failed, uploading raw image")

        if task_obj:
            task_obj.set_status_msg("Processing permanently failed (uploading raw image)")

        # Fail-open: notify with None result (will upload raw image)
        on_complete(task_id, None)

    def _update_retry_status(self, item, backoff, retry_count, max_retries):
        """Update task status message for retry."""
        task_obj = item["context"].get("task")
        if task_obj:
            task_obj.set_status_msg(
                f"Processing failed (attempt {retry_count}/{max_retries}), retrying in {backoff:.0f}s..."
            )

    def _set_retry_scheduled_time(self, item, scheduled_time=None):
        """Set the retry scheduled time on the task."""
        task_obj = item["context"].get("task")
        if task_obj:
            task_obj.set_retry_time(scheduled_time)
