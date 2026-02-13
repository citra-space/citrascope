"""Background processing queue for image processing."""

import queue
import threading
from pathlib import Path
from typing import Callable


class ProcessingQueue:
    """
    Background worker queue for image processing.
    Allows multiple processing tasks to run concurrently without blocking telescope.
    """

    def __init__(self, num_workers: int = 1, logger=None):
        """
        Initialize processing queue.

        Args:
            num_workers: Number of concurrent processing threads (default: 1)
            logger: Logger instance
        """
        self.task_queue = queue.Queue()
        self.num_workers = num_workers
        self.logger = logger
        self.workers = []
        self.running = False

    def start(self):
        """Start worker threads."""
        self.running = True
        for i in range(self.num_workers):
            worker = threading.Thread(target=self._worker_loop, name=f"ProcessingWorker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)
            self.logger.info(f"Started processing worker {i}")

    def stop(self):
        """Stop all workers gracefully."""
        self.logger.info("Stopping processing queue...")
        self.running = False

        # Send poison pills
        for _ in range(self.num_workers):
            self.task_queue.put(None)

        # Wait for completion
        for worker in self.workers:
            worker.join(timeout=5)

        self.logger.info("Processing queue stopped")

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
        self.task_queue.put(
            {"task_id": task_id, "image_path": image_path, "context": context, "on_complete": on_complete}
        )

    def _worker_loop(self):
        """Worker thread main loop."""
        while self.running:
            try:
                item = self.task_queue.get(timeout=1)
                if item is None:  # Poison pill
                    break

                task_id = item["task_id"]
                self.logger.info(f"[ProcessingWorker] Processing task {task_id}")

                try:
                    # Build processing context
                    from citrascope.processors.processor_result import ProcessingContext

                    task_obj = item["context"].get("task")
                    # Note: Status message will be updated by ProcessorRegistry for each processor

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

                    # Notify callback with result
                    self.logger.info(f"[ProcessingWorker] Task {task_id} processed in {result.total_time:.2f}s")
                    if task_obj:
                        task_obj.local_status_msg = "Processing complete"
                    item["on_complete"](task_id, result)

                except Exception as e:
                    self.logger.error(f"[ProcessingWorker] Processing failed for {task_id}: {e}", exc_info=True)
                    # Fail-open: notify with None result (will upload raw image)
                    item["on_complete"](task_id, None)

                finally:
                    self.task_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"[ProcessingWorker] Worker error: {e}", exc_info=True)
