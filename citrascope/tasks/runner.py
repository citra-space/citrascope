import heapq
import os
import threading
import time
from datetime import datetime, timezone

from dateutil import parser as dtparser

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.tasks.scope.static_telescope_task import StaticTelescopeTask
from citrascope.tasks.scope.tracking_telescope_task import TrackingTelescopeTask
from citrascope.tasks.task import Task

# Task polling interval in seconds
TASK_POLL_INTERVAL_SECONDS = 15


class TaskManager:
    def __init__(
        self,
        api_client,
        logger,
        hardware_adapter: AbstractAstroHardwareAdapter,
        daemon,
    ):
        self.api_client = api_client
        self.logger = logger
        self.hardware_adapter = hardware_adapter
        self.daemon = daemon
        self.task_heap = []  # min-heap by start time (scheduled future work only)
        self.task_ids = set()
        self.task_dict = {}  # task_id -> Task object for quick lookup
        self.active_tasks = {}  # task_id -> {task, stage, start_time, stop_time} for in-flight work
        self.heap_lock = threading.RLock()
        self._stop_event = threading.Event()
        self.current_task_id = None  # Track currently executing task
        self.task_retry_counts = {}  # Track retry attempts per task ID
        self.task_last_failure = {}  # Track last failure timestamp per task ID
        # Task processing control (always starts active)
        self._processing_active = True
        self._processing_lock = threading.Lock()
        # Autofocus request flag (set by manual or scheduled triggers)
        self._autofocus_requested = False
        self._autofocus_lock = threading.Lock()
        # Automated scheduling state (initialized from server on startup)
        self._automated_scheduling = (
            daemon.telescope_record.get("automatedScheduling", False) if daemon.telescope_record else False
        )

    def poll_tasks(self):
        while not self._stop_event.is_set():
            try:
                self._report_online()
                tasks = self.api_client.get_telescope_tasks(self.daemon.telescope_record["id"])

                # If API call failed (timeout, network error, etc.), wait before retrying
                if tasks is None:
                    self._stop_event.wait(TASK_POLL_INTERVAL_SECONDS)
                    continue

                added = 0
                removed = 0
                now = int(time.time())
                with self.heap_lock:
                    # Build a map of current valid tasks from the API
                    api_task_map = {}
                    for task_dict in tasks:
                        try:
                            task = Task.from_dict(task_dict)
                            tid = task.id
                            if tid and task.status in ["Pending", "Scheduled"]:
                                api_task_map[tid] = task
                        except Exception as e:
                            self.logger.error(f"Error parsing task from API: {e}", exc_info=True)

                    # Remove tasks from heap that are no longer valid (cancelled, completed, or not in API response)
                    new_heap = []
                    for start_epoch, stop_epoch, tid, task in self.task_heap:
                        # Keep task if it's still in the API response with a valid status
                        # Don't remove currently executing task
                        if tid == self.current_task_id or tid in api_task_map:
                            new_heap.append((start_epoch, stop_epoch, tid, task))
                        else:
                            self.logger.info(f"Removing task {tid} from queue (cancelled or status changed)")
                            self.task_ids.discard(tid)
                            self.task_dict.pop(tid, None)
                            # Clean up retry tracking
                            self.task_retry_counts.pop(tid, None)
                            self.task_last_failure.pop(tid, None)
                            removed += 1

                    # Rebuild heap if we removed anything
                    if removed > 0:
                        self.task_heap = new_heap
                        heapq.heapify(self.task_heap)

                    # Add new tasks that aren't already in the heap
                    for tid, task in api_task_map.items():
                        # Skip if task is in heap or is currently being executed
                        if tid not in self.task_ids and tid != self.current_task_id:
                            task_start = task.taskStart
                            task_stop = task.taskStop
                            try:
                                start_epoch = int(dtparser.isoparse(task_start).timestamp())
                                stop_epoch = int(dtparser.isoparse(task_stop).timestamp()) if task_stop else 0
                            except Exception:
                                self.logger.error(f"Could not parse taskStart/taskStop for task {tid}")
                                continue
                            if stop_epoch and stop_epoch < now:
                                self.logger.debug(f"Skipping past task {tid} that ended at {task_stop}")
                                continue  # Skip tasks whose end date has passed
                            heapq.heappush(self.task_heap, (start_epoch, stop_epoch, tid, task))
                            self.task_ids.add(tid)
                            self.task_dict[tid] = task  # Store for quick lookup
                            added += 1

                    if added > 0 or removed > 0:
                        action = []
                        if added > 0:
                            action.append(f"Added {added}")
                        if removed > 0:
                            action.append(f"Removed {removed}")
                        self.logger.info(self._heap_summary(f"{', '.join(action)} tasks"))
                    # self.logger.info(self._heap_summary("Polled tasks"))
            except Exception as e:
                self.logger.error(f"Exception in poll_tasks loop: {e}", exc_info=True)
                time.sleep(5)  # avoid tight error loop
            self._stop_event.wait(TASK_POLL_INTERVAL_SECONDS)

    def _report_online(self):
        """
        PUT to /telescopes to report this telescope as online.
        """
        telescope_id = self.daemon.telescope_record["id"]
        iso_timestamp = datetime.now(timezone.utc).isoformat()
        self.api_client.put_telescope_status([{"id": telescope_id, "last_connection_epoch": iso_timestamp}])
        self.logger.debug(f"Reported online status for telescope {telescope_id} at {iso_timestamp}")

    def task_runner(self):
        while not self._stop_event.is_set():
            # Check if task processing is paused
            with self._processing_lock:
                is_paused = not self._processing_active

            if is_paused:
                self._stop_event.wait(1)
                continue

            try:
                now = int(time.time())
                completed = 0
                while True:
                    # Check pause status before starting each task
                    with self._processing_lock:
                        if not self._processing_active:
                            break

                    with self.heap_lock:
                        if not (self.task_heap and self.task_heap[0][0] <= now):
                            break
                        # Pop task from heap BEFORE starting execution
                        start_time, stop_time, tid, task = heapq.heappop(self.task_heap)
                        self.task_ids.discard(tid)

                        # Move to active tracking
                        self.active_tasks[tid] = {
                            "task": task,
                            "stage": "shooting",
                            "start_time": time.time(),
                            "stop_time": stop_time,
                        }

                        self.logger.info(f"Starting task {tid} at {datetime.now().isoformat()}: {task}")
                        self.current_task_id = tid  # Mark as in-flight

                    # Mark task as entering shooting stage
                    self.daemon.update_task_stage(tid, "shooting")

                    # Observation is now outside the lock!
                    try:
                        observation_succeeded = self._observe_satellite(task)
                    except Exception as e:
                        self.logger.error(f"Exception during observation for task {tid}: {e}", exc_info=True)
                        observation_succeeded = False

                    with self.heap_lock:
                        self.current_task_id = None  # Clear after done (success or fail)
                        if observation_succeeded:
                            self.logger.info(f"Completed observation task {tid} successfully.")
                            # Task already popped from heap at start - stays in active_tasks
                            # Keep task in task_dict for processing/upload stages
                            # It will be removed when remove_task_from_stages is called
                            # Clean up retry tracking for successful task
                            self.task_retry_counts.pop(tid, None)
                            self.task_last_failure.pop(tid, None)
                            completed += 1
                        else:
                            # Task failed - implement retry logic with exponential backoff
                            retry_count = self.task_retry_counts.get(tid, 0)
                            max_retries = self.daemon.settings.max_task_retries if self.daemon.settings else 3

                            if retry_count >= max_retries:
                                # Max retries exceeded - permanently fail the task
                                self.logger.error(
                                    f"Observation task {tid} failed after {retry_count} retries. Permanently failing."
                                )
                                # Remove from active tracking
                                self.active_tasks.pop(tid, None)
                                # Remove from task_dict since task won't enter pipeline
                                self.task_dict.pop(tid, None)
                                # Clean up retry tracking
                                self.task_retry_counts.pop(tid, None)
                                self.task_last_failure.pop(tid, None)
                                # Remove from stage tracking
                                self.daemon.remove_task_from_stages(tid)
                                # Mark task as failed in API
                                try:
                                    self.api_client.mark_task_failed(tid)
                                except Exception as e:
                                    self.logger.error(f"Failed to mark task {tid} as failed in API: {e}")
                            else:
                                # Retry with exponential backoff
                                self.task_retry_counts[tid] = retry_count + 1
                                self.task_last_failure[tid] = now

                                # Calculate backoff delay: initial_delay * 2^retry_count, capped at max_delay
                                initial_delay = (
                                    self.daemon.settings.initial_retry_delay_seconds if self.daemon.settings else 30
                                )
                                max_delay = (
                                    self.daemon.settings.max_retry_delay_seconds if self.daemon.settings else 300
                                )
                                backoff_delay = min(initial_delay * (2**retry_count), max_delay)

                                # Move from active back to heap with new scheduled time
                                active_info = self.active_tasks.pop(tid, None)
                                if active_info:
                                    new_start_time = now + backoff_delay
                                    heapq.heappush(
                                        self.task_heap,
                                        (new_start_time, active_info["stop_time"], tid, active_info["task"]),
                                    )
                                    self.task_ids.add(tid)  # Re-add to set

                                    self.logger.warning(
                                        f"Observation task {tid} failed (attempt {retry_count + 1}/{max_retries}). "
                                        f"Retrying in {backoff_delay} seconds at {datetime.fromtimestamp(new_start_time).isoformat()}"
                                    )

                                # Remove from stage tracking while waiting for retry
                                self.daemon.remove_task_from_stages(tid)

                if completed > 0:
                    self.logger.info(self._heap_summary("Completed tasks"))
            except Exception as e:
                self.logger.error(f"Exception in task_runner loop: {e}", exc_info=True)
                time.sleep(5)  # avoid tight error loop

            # Check for autofocus requests between tasks
            with self._autofocus_lock:
                should_autofocus = self._autofocus_requested
                if should_autofocus:
                    self._autofocus_requested = False  # Clear flag before execution
                # Also check if scheduled autofocus should run (inside lock to prevent race condition)
                elif self._should_run_scheduled_autofocus():
                    should_autofocus = True
                    self._autofocus_requested = False  # Ensure flag is clear

            if should_autofocus:
                self._execute_autofocus()

            self._stop_event.wait(1)

    def _observe_satellite(self, task: Task):

        # stake a still
        static_task = StaticTelescopeTask(
            self.api_client,
            self.hardware_adapter,
            self.logger,
            task,
            self.daemon,
        )
        return static_task.execute()

        # track the sat for a while with longer exposure
        # tracking_task = TrackingTelescopeTask(
        #     self.api_client, self.hardware_adapter, self.logger, task, self.daemon
        # )
        # return tracking_task.execute()

    def get_task_by_id(self, task_id: str):
        """Get a task by ID. Thread-safe."""
        with self.heap_lock:
            return self.task_dict.get(task_id)

    def _heap_summary(self, event):
        with self.heap_lock:
            summary = f"{event}: {len(self.task_heap)} tasks in queue. "
            next_tasks = []
            if self.task_heap:
                next_tasks = [
                    f"{tid} at {datetime.fromtimestamp(start).isoformat()}"
                    for start, stop, tid, _ in self.task_heap[:3]
                ]
                if len(self.task_heap) > 3:
                    next_tasks.append(f"... ({len(self.task_heap)-3} more)")
            if self.current_task_id is not None:
                # Show the current in-flight task at the front
                summary += f"Current: {self.current_task_id}. "
            if not next_tasks:
                summary += "No tasks scheduled."
            return summary

    def pause(self) -> bool:
        """Pause task processing. Returns new state (False)."""
        with self._processing_lock:
            self._processing_active = False
            self.logger.info("Task processing paused")
            return self._processing_active

    def resume(self) -> bool:
        """Resume task processing. Returns new state (True)."""
        with self._processing_lock:
            self._processing_active = True
            self.logger.info("Task processing resumed")
            return self._processing_active

    def is_processing_active(self) -> bool:
        """Check if task processing is currently active."""
        with self._processing_lock:
            return self._processing_active

    def request_autofocus(self) -> bool:
        """Request autofocus to run at next safe point between tasks.

        Returns:
            bool: True indicating request was queued.
        """
        with self._autofocus_lock:
            self._autofocus_requested = True
            self.logger.info("Autofocus requested - will run between tasks")
            return True

    def cancel_autofocus(self) -> bool:
        """Cancel pending autofocus request if still queued.

        Returns:
            bool: True if autofocus was cancelled, False if nothing to cancel.
        """
        with self._autofocus_lock:
            was_requested = self._autofocus_requested
            self._autofocus_requested = False
            if was_requested:
                self.logger.info("Autofocus request cancelled")
            return was_requested

    def is_autofocus_requested(self) -> bool:
        """Check if autofocus is currently requested/queued.

        Returns:
            bool: True if autofocus is queued, False otherwise.
        """
        with self._autofocus_lock:
            return self._autofocus_requested

    def _should_run_scheduled_autofocus(self) -> bool:
        """Check if scheduled autofocus should run based on settings.

        Returns:
            bool: True if autofocus is enabled and interval has elapsed.
        """
        if not self.daemon.settings:
            return False

        # Check if scheduled autofocus is enabled (top-level setting)
        if not self.daemon.settings.scheduled_autofocus_enabled:
            return False

        # Check if adapter supports autofocus
        if not self.hardware_adapter.supports_autofocus():
            return False

        interval_minutes = self.daemon.settings.autofocus_interval_minutes
        last_timestamp = self.daemon.settings.last_autofocus_timestamp

        # If never run (None), treat as overdue and run immediately
        if last_timestamp is None:
            return True

        # Check if interval has elapsed
        elapsed_minutes = (int(time.time()) - last_timestamp) / 60
        return elapsed_minutes >= interval_minutes

    def _execute_autofocus(self) -> None:
        """Execute autofocus routine and update timestamp on both success and failure."""
        try:
            self.logger.info("Starting autofocus routine...")
            self.hardware_adapter.do_autofocus()

            # Save updated filter configuration after autofocus
            if self.hardware_adapter.supports_filter_management():
                try:
                    filter_config = self.hardware_adapter.get_filter_config()
                    if filter_config and self.daemon.settings:
                        self.daemon.settings.adapter_settings["filters"] = filter_config
                        self.logger.info(f"Saved filter configuration with {len(filter_config)} filters")
                except Exception as e:
                    self.logger.warning(f"Failed to save filter configuration after autofocus: {e}")

            self.logger.info("Autofocus routine completed successfully")
        except Exception as e:
            self.logger.error(f"Autofocus failed: {str(e)}", exc_info=True)
        finally:
            # Always update timestamp to prevent retry spam
            if self.daemon.settings:
                self.daemon.settings.last_autofocus_timestamp = int(time.time())
                self.daemon.settings.save()

    def start(self):
        self._stop_event.clear()
        self.poll_thread = threading.Thread(target=self.poll_tasks, daemon=True)
        self.runner_thread = threading.Thread(target=self.task_runner, daemon=True)
        self.poll_thread.start()
        self.runner_thread.start()

    def stop(self):
        self._stop_event.set()
        self.poll_thread.join()
        self.runner_thread.join()
