"""Background upload queue for uploading images and marking tasks complete."""

import queue
import threading
from pathlib import Path
from typing import Callable, Optional


class UploadQueue:
    """
    Background worker for uploading images and marking tasks complete.
    Uploads can be slow (network), so run in background.
    """

    def __init__(self, num_workers: int = 1, logger=None):
        """
        Initialize upload queue.

        Args:
            num_workers: Number of concurrent upload threads (default: 1, network is bottleneck)
            logger: Logger instance
        """
        self.upload_queue = queue.Queue()
        self.num_workers = num_workers
        self.logger = logger
        self.workers = []
        self.running = False

    def start(self):
        """Start upload worker threads."""
        self.running = True
        for i in range(self.num_workers):
            worker = threading.Thread(target=self._upload_worker, name=f"UploadWorker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)
            self.logger.info(f"Started upload worker {i}")

    def stop(self):
        """Stop all workers gracefully."""
        self.logger.info("Stopping upload queue...")
        self.running = False

        # Send poison pills
        for _ in range(self.num_workers):
            self.upload_queue.put(None)

        # Wait for completion
        for worker in self.workers:
            worker.join(timeout=5)

        self.logger.info("Upload queue stopped")

    def submit(
        self,
        task_id: str,
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
            image_path: Path to image file
            processing_result: Result from processors (or None if skipped)
            api_client: API client instance
            telescope_id: Telescope ID for upload
            settings: Settings instance (for keep_images flag)
            on_complete: Callback(task_id, success) when upload finishes
        """
        self.logger.info(f"Queuing task {task_id} for upload")
        self.upload_queue.put(
            {
                "task_id": task_id,
                "image_path": image_path,
                "processing_result": processing_result,
                "api_client": api_client,
                "telescope_id": telescope_id,
                "settings": settings,
                "on_complete": on_complete,
            }
        )

    def _upload_worker(self):
        """Upload worker main loop."""
        while self.running:
            try:
                item = self.upload_queue.get(timeout=1)
                if item is None:  # Poison pill
                    break

                task_id = item["task_id"]
                self.logger.info(f"[UploadWorker] Uploading task {task_id}")

                try:
                    # Upload image (can be slow due to network)
                    upload_result = item["api_client"].upload_image(task_id, item["telescope_id"], item["image_path"])

                    if upload_result:
                        # Mark task complete on server
                        marked_complete = item["api_client"].mark_task_complete(task_id)

                        if marked_complete:
                            self.logger.info(f"[UploadWorker] Task {task_id} completed successfully")

                            # Cleanup local files if configured
                            if not item["settings"].keep_images:
                                self._cleanup_files(item["image_path"])

                            item["on_complete"](task_id, success=True)
                        else:
                            self.logger.error(f"[UploadWorker] Failed to mark {task_id} complete")
                            item["on_complete"](task_id, success=False)
                    else:
                        self.logger.error(f"[UploadWorker] Upload failed for {task_id}")
                        item["on_complete"](task_id, success=False)

                except Exception as e:
                    self.logger.error(f"[UploadWorker] Upload error for {task_id}: {e}", exc_info=True)
                    item["on_complete"](task_id, success=False)

                finally:
                    self.upload_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"[UploadWorker] Worker error: {e}", exc_info=True)

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
