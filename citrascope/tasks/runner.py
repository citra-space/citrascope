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
        settings,
        processor_registry,
    ):
        self.api_client = api_client
        self.logger = logger
        self.hardware_adapter = hardware_adapter
        self.daemon = daemon
        self.settings = settings
        self.processor_registry = processor_registry

        # Initialize work queues (TaskManager now owns these)
        from citrascope.tasks.imaging_queue import ImagingQueue
        from citrascope.tasks.processing_queue import ProcessingQueue
        from citrascope.tasks.upload_queue import UploadQueue

        self.imaging_queue = ImagingQueue(
            num_workers=1,
            settings=settings,
            logger=logger,
            api_client=api_client,
            task_manager=self,
        )
        self.processing_queue = ProcessingQueue(
            num_workers=1,
            settings=settings,
            logger=logger,
        )
        self.upload_queue = UploadQueue(
            num_workers=1,
            settings=settings,
            logger=logger,
            task_manager=self,
        )

        # Stage tracking (TaskManager now owns this)
        self._stage_lock = threading.Lock()
        self.imaging_tasks = {}  # task_id -> start_time (float)
        self.processing_tasks = {}  # task_id -> start_time (float)
        self.uploading_tasks = {}  # task_id -> start_time (float)

        self.task_heap = []  # min-heap by start time (scheduled future work only)
        self.task_ids = set()
        self.task_dict = {}  # task_id -> Task object for quick lookup
        self.heap_lock = threading.RLock()
        self._stop_event = threading.Event()
        self.current_task_id = None  # Track currently executing task
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

    def update_task_stage(self, task_id: str, stage: str):
        """Move task to specified stage. Stage is 'imaging', 'processing', or 'uploading'."""
        with self._stage_lock:
            # Remove from all stages first
            self.imaging_tasks.pop(task_id, None)
            self.processing_tasks.pop(task_id, None)
            self.uploading_tasks.pop(task_id, None)

            # Add to new stage
            if stage == "imaging":
                self.imaging_tasks[task_id] = time.time()
            elif stage == "processing":
                self.processing_tasks[task_id] = time.time()
            elif stage == "uploading":
                self.uploading_tasks[task_id] = time.time()

    def remove_task_from_all_stages(self, task_id: str):
        """Remove task from all stages and active tracking (when complete)."""
        with self._stage_lock:
            self.imaging_tasks.pop(task_id, None)
            self.processing_tasks.pop(task_id, None)
            self.uploading_tasks.pop(task_id, None)

        # Also remove from task_dict
        with self.heap_lock:
            self.task_dict.pop(task_id, None)

    def get_tasks_by_stage(self) -> dict:
        """Get current tasks in each stage, enriched with task details."""
        with self._stage_lock:
            now = time.time()

            def enrich_task(task_id: str, start_time: float) -> dict:
                """Look up task details and create enriched dict."""
                result = {"task_id": task_id, "elapsed": now - start_time}
                # Look up task from task manager
                task = self.get_task_by_id(task_id)
                if task:
                    result["target_name"] = task.satelliteName
                    # Use thread-safe getters for status fields
                    status_msg, retry_time, is_executing = task.get_status_info()
                    result["status_msg"] = status_msg
                    result["retry_scheduled_time"] = retry_time
                    result["is_being_executed"] = is_executing
                return result

            def sort_tasks(tasks):
                """Sort tasks: active work first, queued next, retry-waiting last."""

                def sort_key(task):
                    retry_time = task.get("retry_scheduled_time")
                    is_executing = task.get("is_being_executed", False)

                    # Three-tier priority:
                    # Priority 0: Currently executing (highest priority)
                    # Priority 1: Queued and ready to execute
                    # Priority 2: Waiting for retry (lowest priority)
                    if retry_time is not None:
                        priority = 2
                        sort_value = retry_time  # Soonest retry first
                    elif is_executing:
                        priority = 0
                        sort_value = -task.get("elapsed", 0)  # Longest running first
                    else:
                        priority = 1
                        sort_value = -task.get("elapsed", 0)  # Longest waiting first

                    return (priority, sort_value)

                return sorted(tasks, key=sort_key)

            return {
                "imaging": sort_tasks([enrich_task(tid, start) for tid, start in self.imaging_tasks.items()]),
                "processing": sort_tasks([enrich_task(tid, start) for tid, start in self.processing_tasks.items()]),
                "uploading": sort_tasks([enrich_task(tid, start) for tid, start in self.uploading_tasks.items()]),
            }

    def poll_tasks(self):
        while not self._stop_event.is_set():
            try:
                # Refresh elset hot list when stale (for satellite matcher)
                if getattr(self.daemon, "elset_cache", None) and self.daemon.telescope_record:
                    interval_hours = getattr(self.daemon.settings, "elset_refresh_interval_hours", 6)
                    self.daemon.elset_cache.refresh_if_stale(
                        self.api_client, self.logger, interval_hours=interval_hours
                    )
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

                        self.logger.info(f"Starting task {tid} at {datetime.now().isoformat()}: {task}")
                        self.current_task_id = tid  # Mark as in-flight

                    # Mark task as entering imaging stage (uses stage tracking)
                    self.update_task_stage(tid, "imaging")

                    # Set initial status message
                    task.set_status_msg("Queued for imaging...")

                    # Create telescope task instance
                    telescope_task = self._create_telescope_task(task)

                    # Submit to imaging queue (handles retries)
                    def on_imaging_complete(task_id, success):
                        """Callback when imaging completes or permanently fails."""
                        if success:
                            with self.heap_lock:
                                self.current_task_id = None  # Clear after done
                            self.logger.info(f"Completed imaging task {task_id} successfully.")
                            # Task stays in stage tracking and task_dict for processing/upload stages
                        else:
                            # Permanent failure - remove from tracking
                            self.logger.error(f"Imaging task {task_id} permanently failed.")
                            with self.heap_lock:
                                self.current_task_id = None  # Clear after done
                            self.remove_task_from_all_stages(task_id)

                    self.imaging_queue.submit(tid, task, telescope_task, on_imaging_complete)
                    completed += 1

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

    def _create_telescope_task(self, task: Task):
        """Create appropriate telescope task instance for the given task."""
        # For now, use StaticTelescopeTask
        # Future: could choose between Static and Tracking based on task type
        return StaticTelescopeTask(
            self.api_client,
            self.hardware_adapter,
            self.logger,
            task,
            self.daemon,
        )

    def _observe_satellite(self, task: Task):
        """Legacy method - now handled by ImagingQueue. Kept for reference."""
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

        # Start work queues
        self.logger.info("Starting work queues...")
        self.imaging_queue.start()
        self.processing_queue.start()
        self.upload_queue.start()

        # Start task management threads
        self.poll_thread = threading.Thread(target=self.poll_tasks, daemon=True)
        self.runner_thread = threading.Thread(target=self.task_runner, daemon=True)
        self.poll_thread.start()
        self.runner_thread.start()

    def stop(self):
        self._stop_event.set()

        # Stop work queues
        self.logger.info("Stopping work queues...")
        self.imaging_queue.stop()
        self.processing_queue.stop()
        self.upload_queue.stop()

        # Stop task management threads
        self.poll_thread.join()
        self.runner_thread.join()
