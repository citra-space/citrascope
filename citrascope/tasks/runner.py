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
        telescope_record,
        ground_station_record,
        logger,
        hardware_adapter: AbstractAstroHardwareAdapter,
        keep_images: bool = False,
        settings=None,
    ):
        self.api_client = api_client
        self.telescope_record = telescope_record
        self.ground_station_record = ground_station_record
        self.logger = logger
        self.settings = settings
        self.task_heap = []  # min-heap by start time
        self.task_ids = set()
        self.hardware_adapter = hardware_adapter
        self.heap_lock = threading.RLock()
        self._stop_event = threading.Event()
        self.current_task_id = None  # Track currently executing task
        self.keep_images = keep_images
        self.task_retry_counts = {}  # Track retry attempts per task ID
        self.task_last_failure = {}  # Track last failure timestamp per task ID

    def poll_tasks(self):
        while not self._stop_event.is_set():
            try:
                self._report_online()
                tasks = self.api_client.get_telescope_tasks(self.telescope_record["id"])

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
        telescope_id = self.telescope_record["id"]
        iso_timestamp = datetime.now(timezone.utc).isoformat()
        self.api_client.put_telescope_status([{"id": telescope_id, "last_connection_epoch": iso_timestamp}])
        self.logger.debug(f"Reported online status for telescope {telescope_id} at {iso_timestamp}")

    def task_runner(self):
        while not self._stop_event.is_set():
            try:
                now = int(time.time())
                completed = 0
                while True:
                    with self.heap_lock:
                        if not (self.task_heap and self.task_heap[0][0] <= now):
                            break
                        _, _, tid, task = self.task_heap[0]
                        self.logger.info(f"Starting task {tid} at {datetime.now().isoformat()}: {task}")
                        self.current_task_id = tid  # Mark as in-flight

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
                            heapq.heappop(self.task_heap)
                            self.task_ids.discard(tid)
                            # Clean up retry tracking for successful task
                            self.task_retry_counts.pop(tid, None)
                            self.task_last_failure.pop(tid, None)
                            completed += 1
                        else:
                            # Task failed - implement retry logic with exponential backoff
                            retry_count = self.task_retry_counts.get(tid, 0)
                            max_retries = self.settings.max_task_retries if self.settings else 3

                            if retry_count >= max_retries:
                                # Max retries exceeded - permanently fail the task
                                self.logger.error(
                                    f"Observation task {tid} failed after {retry_count} retries. Permanently failing."
                                )
                                heapq.heappop(self.task_heap)
                                self.task_ids.discard(tid)
                                # Clean up retry tracking
                                self.task_retry_counts.pop(tid, None)
                                self.task_last_failure.pop(tid, None)
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
                                initial_delay = self.settings.initial_retry_delay_seconds if self.settings else 30
                                max_delay = self.settings.max_retry_delay_seconds if self.settings else 300
                                backoff_delay = min(initial_delay * (2**retry_count), max_delay)

                                # Update task start time in heap to retry after backoff delay
                                _, stop_epoch, _, task = heapq.heappop(self.task_heap)
                                new_start_time = now + backoff_delay
                                heapq.heappush(self.task_heap, (new_start_time, stop_epoch, tid, task))

                                self.logger.warning(
                                    f"Observation task {tid} failed (attempt {retry_count + 1}/{max_retries}). "
                                    f"Retrying in {backoff_delay} seconds at {datetime.fromtimestamp(new_start_time).isoformat()}"
                                )

                if completed > 0:
                    self.logger.info(self._heap_summary("Completed tasks"))
            except Exception as e:
                self.logger.error(f"Exception in task_runner loop: {e}", exc_info=True)
                time.sleep(5)  # avoid tight error loop
            self._stop_event.wait(1)

    def _observe_satellite(self, task: Task):

        # stake a still
        static_task = StaticTelescopeTask(
            self.api_client,
            self.hardware_adapter,
            self.logger,
            self.telescope_record,
            self.ground_station_record,
            task,
            self.keep_images,
        )
        return static_task.execute()

        # track the sat for a while with longer exposure
        # tracking_task = TrackingTelescopeTask(
        #     self.api_client, self.hardware_adapter, self.logger, self.telescope_record, self.ground_station_record, task
        # )
        # return tracking_task.execute()

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
