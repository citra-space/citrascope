"""Background imaging queue for telescope operations."""

from typing import Callable

from citrascope.tasks.base_work_queue import BaseWorkQueue


class ImagingQueue(BaseWorkQueue):
    """
    Background worker queue for telescope imaging operations.
    Allows telescope operations to be queued and retried with exponential backoff.
    """

    def __init__(self, num_workers: int, settings, logger, api_client, daemon):
        """
        Initialize imaging queue.

        Args:
            num_workers: Number of concurrent imaging threads (default: 1)
            settings: Settings instance
            logger: Logger instance
            api_client: API client for marking tasks failed
            daemon: Daemon instance for stage tracking
        """
        super().__init__(num_workers, settings, logger)
        self.api_client = api_client
        self.daemon = daemon

    def submit(self, task_id: str, task, telescope_task_instance, on_complete: Callable):
        """
        Submit telescope task for imaging.

        Args:
            task_id: Task identifier
            task: Task object
            telescope_task_instance: Instance of StaticTelescopeTask or TrackingTelescopeTask
            on_complete: Callback(task_id, success) when imaging finishes
        """
        self.logger.info(f"Queuing task {task_id} for imaging")
        self.work_queue.put(
            {
                "task_id": task_id,
                "task": task,
                "telescope_task_instance": telescope_task_instance,
                "on_complete": on_complete,
            }
        )

    def _execute_work(self, item):
        """Execute telescope imaging operation."""
        task_id = item["task_id"]
        task = item["task"]
        telescope_task = item["telescope_task_instance"]

        self.logger.info(f"[ImagingWorker] Imaging task {task_id}")

        # Ensure task is in imaging stage (important for retries)
        self.daemon.update_task_stage(task_id, "imaging")

        # Clear any stale status messages from previous attempts
        if task:
            task.set_status_msg("Starting imaging...")

        # Execute the telescope observation
        observation_succeeded = telescope_task.execute()

        return (observation_succeeded, None)

    def _on_success(self, item, result):
        """Handle successful imaging completion."""
        task_id = item["task_id"]
        on_complete = item["on_complete"]

        self.logger.info(f"[ImagingWorker] Task {task_id} imaging completed successfully")

        # Don't update status message here - telescope task already set it to "Queued for processing..."
        # during upload_image_and_mark_complete()

        on_complete(task_id, success=True)

    def _on_permanent_failure(self, item):
        """Handle permanent imaging failure after max retries."""
        task_id = item["task_id"]
        task = item["task"]
        on_complete = item["on_complete"]

        self.logger.error(f"[ImagingWorker] Task {task_id} imaging permanently failed")

        # Update status message
        if task:
            task.set_status_msg("Imaging permanently failed")

        # Mark task as failed in API
        try:
            self.api_client.mark_task_failed(task_id)
        except Exception as e:
            self.logger.error(f"Failed to mark task {task_id} as failed in API: {e}")

        # Remove from stage tracking
        self.daemon.remove_task_from_stages(task_id)

        # Notify callback
        on_complete(task_id, success=False)

    def _update_retry_status(self, item, backoff, retry_count, max_retries):
        """Update task status message for retry."""
        task = item.get("task")
        if task:
            task.set_status_msg(f"Imaging failed (attempt {retry_count}/{max_retries}), retrying in {backoff:.0f}s...")

    def _set_retry_scheduled_time(self, item, scheduled_time=None):
        """Set the retry scheduled time on the task."""
        task = item.get("task")
        if task:
            task.set_retry_time(scheduled_time)

    def _update_status_on_resubmit(self, item):
        """Update status when retry timer fires and task is resubmitted."""
        task = item.get("task")
        if task:
            task.set_status_msg("Retrying imaging...")
