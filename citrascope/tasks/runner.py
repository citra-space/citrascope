import threading
import time
import heapq
from datetime import datetime
from dateutil import parser as dtparser

class TaskManager:
    def __init__(self, client, telescope_id, logger):
        self.client = client
        self.telescope_id = telescope_id
        self.logger = logger
        self.task_heap = []  # min-heap by start time
        self.task_ids = set()
        self.heap_lock = threading.RLock()
        self._stop_event = threading.Event()

    def poll_tasks(self):
        while not self._stop_event.is_set():
            tasks = self.client.get_telescope_tasks(self.telescope_id)
            added = 0
            now = int(time.time())
            with self.heap_lock:
                for task in tasks:
                    tid = task.get("id")
                    task_start = task.get("taskStart")
                    task_stop = task.get("taskStop")
                    if tid and task_start and tid not in self.task_ids:
                        try:
                            start_epoch = int(dtparser.isoparse(task_start).timestamp())
                            stop_epoch = int(dtparser.isoparse(task_stop).timestamp()) if task_stop else None
                        except Exception:
                            self.logger.error(f"Could not parse taskStart/taskStop for task {tid}")
                            continue
                        if stop_epoch is not None and stop_epoch < now:
                            self.logger.debug(f"Skipping past task {tid} that ended at {task_stop}")
                            continue  # Skip tasks whose end date has passed
                        heapq.heappush(self.task_heap, (start_epoch, tid, task))
                        self.task_ids.add(tid)
                        added += 1
                if added > 0:
                    self.logger.info(self._heap_summary("Added tasks"))
                self.logger.info(self._heap_summary("Polled tasks"))
                self._stop_event.wait(30)

    def task_runner(self):
        while not self._stop_event.is_set():
            now = int(time.time())
            completed = 0
            with self.heap_lock:
                while self.task_heap and self.task_heap[0][0] <= now:
                    _, tid, task = heapq.heappop(self.task_heap)
                    self.logger.info(f"Starting task {tid} at {datetime.now().isoformat()}: {task}")
                    # TODO: Implement actual task execution logic here
                    self.task_ids.discard(tid)
                    completed += 1
                if completed > 0:
                    self.logger.info(self._heap_summary("Completed tasks"))
                self._stop_event.wait(1)
    def _heap_summary(self, event):
        with self.heap_lock:
            summary = f"{event}: {len(self.task_heap)} tasks in queue. "
            if self.task_heap:
                summary += "Next: " + ", ".join([
                    f"{tid} at {datetime.fromtimestamp(start).isoformat()}"
                    for start, tid, _ in self.task_heap[:3]
                ])
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
