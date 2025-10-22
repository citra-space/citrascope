import heapq
import random
import threading
import time
from datetime import datetime

from dateutil import parser as dtparser
from skyfield.api import EarthSatellite, Topos, load

from citrascope.hardware.astro_hardware_adapter import AstroHardwareAdapter
from citrascope.tasks.task import Task


class TaskManager:
    def __init__(
        self, api_client, telescope_record, ground_station_record, logger, hardware_adapter: AstroHardwareAdapter
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
            tasks = self.api_client.get_telescope_tasks(self.telescope_record["id"])
            added = 0
            now = int(time.time())
            with self.heap_lock:
                for task_dict in tasks:
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
                            self.logger.info(f"Skipping past task {tid} that ended at {task_stop}")
                            continue  # Skip tasks whose end date has passed
                        heapq.heappush(self.task_heap, (start_epoch, stop_epoch, tid, task))
                        self.task_ids.add(tid)
                        added += 1
                if added > 0:
                    self.logger.info(self._heap_summary("Added tasks"))
                self.logger.info(self._heap_summary("Polled tasks"))
            self._stop_event.wait(15)

    def task_runner(self):
        while not self._stop_event.is_set():
            now = int(time.time())
            completed = 0
            with self.heap_lock:
                while self.task_heap and self.task_heap[0][0] <= now:
                    _, _, tid, task = self.task_heap[0]
                    self.logger.info(f"Starting task {tid} at {datetime.now().isoformat()}: {task}")

                    observation_succeeded = self._observe_satellite(task)

                    if observation_succeeded:
                        self.logger.info(f"Completed observation task {tid} successfully.")
                        heapq.heappop(self.task_heap)
                        self.task_ids.discard(tid)
                        completed += 1
                    else:
                        self.logger.error(f"Observation task {tid} failed.")

                if completed > 0:
                    self.logger.info(self._heap_summary("Completed tasks"))
            self._stop_event.wait(1)

    def _observe_satellite(self, task: Task):

        # Fetch satellite data for this task
        satellite_data = self.api_client.get_satellite(task.satelliteId)
        if not satellite_data:
            self.logger.error(f"Could not fetch satellite data for {task.satelliteId}")
            return False
        # self.logger.debug(f"Satellite data for {task.satelliteId}: {satellite_data}") #toooooo much spam to log atm

        # Get the most recent TLE (elset) for the satellite
        elsets = satellite_data.get("elsets", [])
        if not elsets:
            self.logger.error(f"No elsets found for satellite {task.satelliteId}")
            return False

        most_recent_elset = max(
            elsets,
            key=lambda e: (
                dtparser.isoparse(e["creationEpoch"])
                if e.get("creationEpoch")
                else dtparser.isoparse("1970-01-01T00:00:00Z")
            ),  # TODO: this is whack and should just bail
        )
        self.logger.debug(f"Most recent elset for {task.satelliteId}: {most_recent_elset}")

        # Derive the RA/DEC from the most recent elset
        ts = load.timescale()
        eph = load("de421.bsp")

        observer = eph["earth"] + Topos(
            latitude_degrees=self.ground_station_record["latitude"],
            longitude_degrees=self.ground_station_record["longitude"],
            elevation_m=self.ground_station_record["altitude"],
        )

        satellite = EarthSatellite(most_recent_elset["tle"][0], most_recent_elset["tle"][1], satellite_data["name"], ts)
        geocentric = satellite.at(ts.now())
        target_ra, target_dec, distance = geocentric.radec()

        # fake some RADEC numbers for now
        # ra = random.uniform(0, 24)
        # dec = random.uniform(0, 90)

        # Drive the telescope to point at the satellite as it passes overhead
        current_ra, current_dec = self.hardware_adapter.get_telescope_direction()

        self.logger.info(f"Telescope currently pointed to RA: {current_ra} hours, DEC: {current_dec} degrees")
        self.logger.info(
            f"Slewing telescope to point at sat '{satellite_data['name']}', RA: {target_ra} hours, DEC: {target_dec} degrees"
        )
        self.hardware_adapter.point_telescope(target_ra.hours, target_dec.degrees)  # type: ignore

        # wait for slew to complete
        while self.hardware_adapter.telescope_is_moving():
            current_ra, current_dec = self.hardware_adapter.get_telescope_direction()
            self.logger.info(f"Scope Moving towards {satellite_data['name']}, now at {current_ra}, {current_dec}")
            time.sleep(2)
        self.logger.info(
            f"Telescope now pointed to RA: {current_ra}/{target_ra.hours} hours, DEC: {current_dec}/{target_dec.degrees} degrees"
        )

        # perhaps start tracking object now? maybe do another fine-tune for the final shot?

        # take image...
        self.logger.info(f"Taking image of satellite '{satellite_data['name']}' for task {task.id}")
        self.hardware_adapter.take_image(task.id)

        filepath = f"images/citra_task_{task.id}_image.fits"

        upload_result = self.api_client.upload_image(task.id, self.telescope_record["id"], filepath)

        if upload_result:
            self.logger.info(f"Successfully uploaded image for task {task.id}")
        else:
            self.logger.error(f"Failed to upload image for task {task.id}")

        # Mark task done
        marked_complete = self.api_client.mark_task_complete(task.id)
        if not marked_complete:
            self.logger.error(f"Failed to mark task {task.id} as complete.")
            return False

        self.logger.info(f"Marked task {task.id} as complete.")
        return True

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
