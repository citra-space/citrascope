"""Base class for background work queues with retry logic."""

import queue
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseWorkQueue(ABC):
    """Base class for background work queues with worker threads, retry logic, and exponential backoff."""

    def __init__(self, num_workers: int, settings, logger):
        """
        Initialize work queue.

        Args:
            num_workers: Number of concurrent worker threads
            settings: Settings instance with retry configuration
            logger: Logger instance
        """
        self.work_queue = queue.Queue()
        self.num_workers = num_workers
        self.settings = settings
        self.logger = logger
        self.workers = []
        self.running = False

        # Retry tracking (per-stage)
        self.retry_counts: Dict[str, int] = {}
        self.last_failure: Dict[str, float] = {}

    @abstractmethod
    def _execute_work(self, item: Dict[str, Any]) -> tuple[bool, Any]:
        """
        Execute stage-specific work. Must be implemented by subclasses.

        Args:
            item: Work item dictionary containing task_id and stage-specific data

        Returns:
            Tuple of (success: bool, result: Any)
        """
        pass

    @abstractmethod
    def _on_success(self, item: Dict[str, Any], result: Any):
        """
        Handle successful work completion.

        Args:
            item: Work item dictionary
            result: Result from _execute_work
        """
        pass

    @abstractmethod
    def _on_permanent_failure(self, item: Dict[str, Any]):
        """
        Handle permanent failure after max retries.

        Args:
            item: Work item dictionary
        """
        pass

    def _update_retry_status(self, item: Dict[str, Any], backoff: float, retry_count: int, max_retries: int):
        """Update task status message for retry."""
        task = self._get_task_from_item(item)
        if task:
            # Extract stage name from class name (e.g., "ImagingQueue" -> "Imaging")
            stage_name = self.__class__.__name__.replace("Queue", "")
            task.set_status_msg(
                f"{stage_name} failed (attempt {retry_count}/{max_retries}), retrying in {backoff:.0f}s..."
            )

    @abstractmethod
    def _get_task_from_item(self, item: Dict[str, Any]):
        """
        Get the Task object from the work item dictionary.
        Must be implemented by subclasses since item structure varies.

        Args:
            item: Work item dictionary

        Returns:
            Task object or None if not found
        """
        pass

    def _set_retry_scheduled_time(self, item: Dict[str, Any], scheduled_time: float = None):
        """Set the retry scheduled time on the task."""
        task = self._get_task_from_item(item)
        if task:
            task.set_retry_time(scheduled_time)

    def _update_status_on_resubmit(self, item: Dict[str, Any]):
        """Update status when retry timer fires and task is resubmitted."""
        task = self._get_task_from_item(item)
        if task:
            # Extract stage name from class name (e.g., "ImagingQueue" -> "imaging")
            stage_name = self.__class__.__name__.replace("Queue", "").lower()
            task.set_status_msg(f"Retrying {stage_name}...")

    def _set_executing(self, item: Dict[str, Any], executing: bool):
        """Set whether task is being actively executed."""
        task = self._get_task_from_item(item)
        if task:
            task.set_executing(executing)

    def _calculate_backoff(self, task_id: str) -> float:
        """Calculate exponential backoff delay."""
        retry_count = self.retry_counts.get(task_id, 0)
        initial = self.settings.initial_retry_delay_seconds
        max_delay = self.settings.max_retry_delay_seconds
        return min(initial * (2**retry_count), max_delay)

    def _should_retry(self, task_id: str) -> bool:
        """Check if task should be retried."""
        return self.retry_counts.get(task_id, 0) < self.settings.max_task_retries

    def _schedule_retry(self, item: Dict[str, Any]):
        """Schedule a retry with exponential backoff."""
        task_id = item["task_id"]
        self.retry_counts[task_id] = self.retry_counts.get(task_id, 0) + 1
        self.last_failure[task_id] = time.time()

        backoff = self._calculate_backoff(task_id)
        retry_count = self.retry_counts[task_id]
        max_retries = self.settings.max_task_retries

        self.logger.warning(
            f"Task {task_id} failed (attempt {retry_count}/{max_retries}), " f"retrying in {backoff:.0f}s"
        )

        # Let subclass update task status message
        self._update_retry_status(item, backoff, retry_count, max_retries)

        # Set retry scheduled time
        scheduled_time = time.time() + backoff
        self._set_retry_scheduled_time(item, scheduled_time)

        # Schedule resubmission (clear scheduled time and update status when resubmitted)
        def resubmit():
            self._set_retry_scheduled_time(item, None)
            # Update status to show we're no longer waiting, but about to retry
            self._update_status_on_resubmit(item)
            self.work_queue.put(item)

        timer = threading.Timer(backoff, resubmit)
        timer.daemon = True
        timer.start()

    def _worker_loop(self):
        """Worker thread main loop."""
        while self.running:
            try:
                item = self.work_queue.get(timeout=1)
                if item is None:  # Poison pill
                    break

                task_id = item["task_id"]

                try:
                    # Mark task as being actively executed
                    self._set_executing(item, True)

                    success, result = self._execute_work(item)

                    # Mark task as no longer executing
                    self._set_executing(item, False)

                    if success:
                        # Clean up retry tracking
                        self.retry_counts.pop(task_id, None)
                        self.last_failure.pop(task_id, None)
                        self._set_retry_scheduled_time(item, None)  # Clear retry scheduled time on success
                        self._on_success(item, result)
                    else:
                        # Work failed
                        if self._should_retry(task_id):
                            self._schedule_retry(item)
                        else:
                            # Permanent failure
                            self.logger.error(
                                f"Task {task_id} permanently failed after "
                                f"{self.retry_counts.get(task_id, 0)} retries"
                            )
                            self.retry_counts.pop(task_id, None)
                            self.last_failure.pop(task_id, None)
                            self._on_permanent_failure(item)

                except Exception as e:
                    # Mark task as no longer executing (even on exception)
                    self._set_executing(item, False)

                    self.logger.error(f"Worker error for {task_id}: {e}", exc_info=True)
                    if self._should_retry(task_id):
                        self._schedule_retry(item)
                    else:
                        self.retry_counts.pop(task_id, None)
                        self.last_failure.pop(task_id, None)
                        self._on_permanent_failure(item)

                finally:
                    self.work_queue.task_done()

            except queue.Empty:
                continue

    def start(self):
        """Start worker threads."""
        self.running = True
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop, name=f"{self.__class__.__name__}-Worker-{i}", daemon=True
            )
            worker.start()
            self.workers.append(worker)
            self.logger.info(f"Started {self.__class__.__name__} worker {i}")

    def stop(self):
        """Stop all workers gracefully."""
        self.logger.info(f"Stopping {self.__class__.__name__}...")
        self.running = False

        # Send poison pills
        for _ in range(self.num_workers):
            self.work_queue.put(None)

        # Wait for completion
        for worker in self.workers:
            worker.join(timeout=5)

        self.logger.info(f"{self.__class__.__name__} stopped")
