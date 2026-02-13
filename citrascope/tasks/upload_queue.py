"""Background upload queue for uploading images and marking tasks complete."""

from pathlib import Path
from typing import Callable, Optional

from citrascope.tasks.base_work_queue import BaseWorkQueue


class UploadQueue(BaseWorkQueue):
    """
    Background worker for uploading images and marking tasks complete.
    Uploads can be slow (network), so run in background.
    """

    def __init__(self, num_workers: int = 1, settings=None, logger=None, daemon=None):
        """
        Initialize upload queue.

        Args:
            num_workers: Number of concurrent upload threads (default: 1, network is bottleneck)
            settings: Settings instance with retry configuration
            logger: Logger instance
            daemon: Daemon instance for stage tracking
        """
        super().__init__(num_workers, settings, logger)
        self.daemon = daemon

    def submit(
        self,
        task_id: str,
        task,
        image_path: str,
        processing_result: Optional[dict],
        api_client,
        telescope_id: str,
        settings,
        on_complete: Callable,
    ):
        """
        Submit image for upload.

        Args:
            task_id: Task identifier
            task: Task object (for status updates)
            image_path: Path to image file
            processing_result: Result from processors (or None if skipped)
            api_client: API client instance
            telescope_id: Telescope ID for upload
            settings: Settings instance (for keep_images flag)
            on_complete: Callback(task_id, success) when upload finishes
        """
        self.logger.info(f"Queuing task {task_id} for upload")
        self.work_queue.put(
            {
                "task_id": task_id,
                "task": task,
                "image_path": image_path,
                "processing_result": processing_result,
                "api_client": api_client,
                "telescope_id": telescope_id,
                "settings": settings,
                "on_complete": on_complete,
            }
        )

    def _execute_work(self, item):
        """Execute upload work."""
        task_id = item["task_id"]
        task_obj = item.get("task")

        self.logger.info(f"[UploadWorker] Uploading task {task_id}")

        # Upload image (can be slow due to network)
        if task_obj:
            task_obj.set_status_msg("Uploading image...")
        upload_result = item["api_client"].upload_image(task_id, item["telescope_id"], item["image_path"])

        if not upload_result:
            self.logger.error(f"[UploadWorker] Upload failed for {task_id}")
            return (False, None)

        # Mark task complete on server
        if task_obj:
            task_obj.set_status_msg("Marking complete...")
        marked_complete = item["api_client"].mark_task_complete(task_id)

        if not marked_complete:
            self.logger.error(f"[UploadWorker] Failed to mark {task_id} complete")
            return (False, None)

        # Success
        self.logger.info(f"[UploadWorker] Task {task_id} completed successfully")
        return (True, None)

    def _on_success(self, item, result):
        """Handle successful upload completion."""
        task_id = item["task_id"]
        task_obj = item.get("task")
        on_complete = item["on_complete"]

        if task_obj:
            task_obj.set_status_msg("Upload complete")

        # Cleanup local files if configured
        if not item["settings"].keep_images:
            if task_obj:
                task_obj.set_status_msg("Cleaning up...")
            self._cleanup_files(item["image_path"])

        on_complete(task_id, success=True)

    def _on_permanent_failure(self, item):
        """Handle permanent upload failure."""
        task_id = item["task_id"]
        task_obj = item.get("task")
        on_complete = item["on_complete"]

        self.logger.error(f"[UploadWorker] Task {task_id} upload permanently failed")

        if task_obj:
            task_obj.set_status_msg("Upload permanently failed")

        # Remove from stage tracking
        if self.daemon:
            self.daemon.remove_task_from_stages(task_id)

        on_complete(task_id, success=False)

    def _update_retry_status(self, item, backoff, retry_count, max_retries):
        """Update task status message for retry."""
        task_obj = item.get("task")
        if task_obj:
            task_obj.set_status_msg(
                f"Upload failed (attempt {retry_count}/{max_retries}), retrying in {backoff:.0f}s..."
            )

    def _set_retry_scheduled_time(self, item, scheduled_time=None):
        """Set the retry scheduled time on the task."""
        task_obj = item.get("task")
        if task_obj:
            task_obj.set_retry_time(scheduled_time)

    def _update_status_on_resubmit(self, item):
        """Update status when retry timer fires and task is resubmitted."""
        task_obj = item.get("task")
        if task_obj:
            task_obj.set_status_msg("Retrying upload...")

    def _cleanup_files(self, filepath: str):
        """Clean up image files after successful upload."""
        try:
            from pathlib import Path

            path = Path(filepath)

            # Delete main file
            if path.exists():
                path.unlink()
                self.logger.debug(f"Deleted {filepath}")

            # Delete related files (.new, .cat, .wcs, etc.)
            for related in path.parent.glob(f"{path.stem}.*"):
                if related != path and related.suffix in [
                    ".new",
                    ".cat",
                    ".wcs",
                    ".solved",
                    ".axy",
                    ".corr",
                    ".match",
                    ".rdls",
                ]:
                    related.unlink()
                    self.logger.debug(f"Deleted {related}")

        except Exception as e:
            self.logger.warning(f"Failed to cleanup files for {filepath}: {e}")
