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

    @abstractmethod
    def _update_retry_status(self, item: Dict[str, Any], backoff: float, retry_count: int, max_retries: int):
        """
        Update task status message for retry. Must be implemented by subclasses.

        Args:
            item: Work item dictionary
            backoff: Backoff delay in seconds
            retry_count: Current retry attempt number
            max_retries: Maximum number of retries allowed
        """
        pass

    @abstractmethod
    def _set_retry_scheduled_time(self, item: Dict[str, Any], scheduled_time: float = None):
        """
        Set the retry scheduled time on the task. Must be implemented by subclasses.

        Args:
            item: Work item dictionary
            scheduled_time: Unix timestamp when retry will execute (None if not waiting for retry)
        """
        pass

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

        # Schedule resubmission (clear scheduled time when resubmitted)
        def resubmit():
            self._set_retry_scheduled_time(item, None)
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
                    success, result = self._execute_work(item)

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
