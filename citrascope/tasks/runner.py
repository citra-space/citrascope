import heapq
import os
import threading
import time
from datetime import datetime

from dateutil import parser as dtparser

from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter
from citrascope.tasks.scope.static_telescope_task import StaticTelescopeTask
from citrascope.tasks.task import Task


class TaskManager:
    def __init__(
        self,
        api_client,
        telescope_record,
        ground_station_record,
        logger,
        hardware_adapter: AbstractAstroHardwareAdapter,
    ):
        self.api_client = api_client
        self.telescope_record = telescope_record
        self.ground_station_record = ground_station_record
        self.logger = logger
        self.task_heap = []  # min-heap by start time
        self.task_ids = set()
        self.hardware_adapter = hardware_adapter
        self.heap_lock = threading.RLock()
        self._stop_event = threading.Event()

    def poll_tasks(self):
        while not self._stop_event.is_set():
            try:
                tasks = self.api_client.get_telescope_tasks(self.telescope_record["id"])
                added = 0
                now = int(time.time())
                with self.heap_lock:
                    for task_dict in tasks:
                        try:
                            task = Task.from_dict(task_dict)
                            tid = task.id
                            task_start = task.taskStart
                            task_stop = task.taskStop
                            if tid and task_start and tid not in self.task_ids:
                                try:
                                    start_epoch = int(dtparser.isoparse(task_start).timestamp())
                                    stop_epoch = int(dtparser.isoparse(task_stop).timestamp()) if task_stop else 0
                                except Exception:
                                    self.logger.error(f"Could not parse taskStart/taskStop for task {tid}")
                                    continue
                                if stop_epoch and stop_epoch < now:
                                    self.logger.debug(f"Skipping past task {tid} that ended at {task_stop}")
                                    continue  # Skip tasks whose end date has passed
                                if task.status not in ["Pending", "Scheduled"]:
                                    self.logger.debug(f"Skipping task {tid} with status {task.status}")
                                    continue  # Only schedule pending/scheduled tasks
                                heapq.heappush(self.task_heap, (start_epoch, stop_epoch, tid, task))
                                self.task_ids.add(tid)
                                added += 1
                        except Exception as e:
                            self.logger.error(f"Error adding task {tid} to heap: {e}", exc_info=True)
                    if added > 0:
                        self.logger.info(self._heap_summary("Added tasks"))
                    self.logger.info(self._heap_summary("Polled tasks"))
            except Exception as e:
                self.logger.error(f"Exception in poll_tasks loop: {e}", exc_info=True)
                time.sleep(5)  # avoid tight error loop
            self._stop_event.wait(15)

    def task_runner(self):
        while not self._stop_event.is_set():
            try:
                now = int(time.time())
                completed = 0
                with self.heap_lock:
                    while self.task_heap and self.task_heap[0][0] <= now:
                        _, _, tid, task = self.task_heap[0]
                        self.logger.info(f"Starting task {tid} at {datetime.now().isoformat()}: {task}")

                        try:
                            observation_succeeded = self._observe_satellite(task)
                        except Exception as e:
                            self.logger.error(f"Exception during observation for task {tid}: {e}", exc_info=True)
                            observation_succeeded = False

                        if observation_succeeded:
                            self.logger.info(f"Completed observation task {tid} successfully.")
                            heapq.heappop(self.task_heap)
                            self.task_ids.discard(tid)
                            completed += 1
                        else:
                            self.logger.error(f"Observation task {tid} failed.")

                    if completed > 0:
                        self.logger.info(self._heap_summary("Completed tasks"))
            except Exception as e:
                self.logger.error(f"Exception in task_runner loop: {e}", exc_info=True)
                time.sleep(5)  # avoid tight error loop
            self._stop_event.wait(1)

    def _observe_satellite(self, task: Task):
        # For now, select StaticTelescopeTask; in the future, select based on task type/params
        # Example: if hasattr(task, 'tracking') and task.tracking:
        #     obs_task = TrackingTelescopeTask(...)
        # else:
        #     obs_task = StaticTelescopeTask(...)
        obs_task = StaticTelescopeTask(
            self.api_client, self.hardware_adapter, self.logger, self.telescope_record, self.ground_station_record, task
        )
        return obs_task.execute()

    def _heap_summary(self, event):
        with self.heap_lock:
            summary = f"{event}: {len(self.task_heap)} tasks in queue. "
            if self.task_heap:
                summary += "Next: " + ", ".join(
                    [
                        f"{tid} at {datetime.fromtimestamp(start).isoformat()}"
                        for start, stop, tid, _ in self.task_heap[:3]
                    ]
                )
                if len(self.task_heap) > 3:
                    summary += f", ... ({len(self.task_heap)-3} more)"
            else:
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
