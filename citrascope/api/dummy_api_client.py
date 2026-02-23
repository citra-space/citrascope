"""Dummy API client for local testing without real server."""

import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from .abstract_api_client import AbstractCitraApiClient


class DummyApiClient(AbstractCitraApiClient):
    """
    Dummy API client that keeps all data in memory.

    Perfect for testing the task pipeline without needing the real API server.
    Automatically maintains ~10 upcoming tasks at all times.
    """

    # Simulated failure rate for testing retry logic (30% chance of upload failure)
    UPLOAD_FAILURE_RATE = 0.3

    def __init__(self, logger=None):
        """Initialize dummy API client with in-memory data."""
        self.logger = logger

        # Thread-safe data access
        self._data_lock = threading.Lock()

        # Initialize in-memory data structures
        self._initialize_data()

        if self.logger:
            self.logger.info("DummyApiClient initialized (in-memory mode)")

    def _initialize_data(self):
        """Initialize in-memory data structures."""
        now = datetime.now(timezone.utc)

        self.data = {
            "telescope": {
                "id": "dummy-telescope-001",
                "name": "Dummy Telescope",
                "groundStationId": "dummy-gs-001",
                "automatedScheduling": True,
                "maxSlewRate": 5.0,  # degrees per second
                # Sensor specs matching the DummyAdapter's synthetic camera constants
                # (1024×1024 px @ ~6 arcsec/px → pixel_size / focal_length * 206.265 ≈ 6.04
                #  → using pixel_size=5.86 μm and focal_length=200 mm)
                # Wide FOV (~1.7°) ensures enough V≤10 stars for Tetra3 plate solving.
                "pixelSize": 5.86,
                "focalLength": 200.0,
                "focalRatio": 3.4,
                "horizontalPixelCount": 1024,
                "verticalPixelCount": 1024,
                "imageCircleDiameter": None,
                "angularNoise": 2.0,
                "spectralMinWavelengthNm": None,
                "spectralMaxWavelengthNm": None,
            },
            "ground_station": {
                "id": "dummy-gs-001",
                "name": "Test Ground Station",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "altitude": 100,
            },
            "tasks": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "observation",
                    "status": "Pending",
                    "creationEpoch": now.isoformat(),
                    "updateEpoch": now.isoformat(),
                    "satelliteId": "sat-iss",
                    "satelliteName": "ISS",
                    "taskStart": (now + timedelta(seconds=10)).isoformat(),
                    "taskStop": (now + timedelta(seconds=15)).isoformat(),
                    "telescopeId": "dummy-telescope-001",
                    "telescopeName": "Dummy Telescope",
                    "groundStationId": "dummy-gs-001",
                    "groundStationName": "Test Ground Station",
                    "userId": "dummy-user",
                    "username": "Test User",
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "observation",
                    "status": "Pending",
                    "creationEpoch": now.isoformat(),
                    "updateEpoch": now.isoformat(),
                    "satelliteId": "sat-starlink",
                    "satelliteName": "STARLINK-1234",
                    "taskStart": (now + timedelta(seconds=20)).isoformat(),
                    "taskStop": (now + timedelta(seconds=25)).isoformat(),
                    "telescopeId": "dummy-telescope-001",
                    "telescopeName": "Dummy Telescope",
                    "groundStationId": "dummy-gs-001",
                    "groundStationName": "Test Ground Station",
                    "userId": "dummy-user",
                    "username": "Test User",
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "observation",
                    "status": "Pending",
                    "creationEpoch": now.isoformat(),
                    "updateEpoch": now.isoformat(),
                    "satelliteId": "sat-noaa18",
                    "satelliteName": "NOAA-18",
                    "taskStart": (now + timedelta(seconds=30)).isoformat(),
                    "taskStop": (now + timedelta(seconds=35)).isoformat(),
                    "telescopeId": "dummy-telescope-001",
                    "telescopeName": "Dummy Telescope",
                    "groundStationId": "dummy-gs-001",
                    "groundStationName": "Test Ground Station",
                    "userId": "dummy-user",
                    "username": "Test User",
                },
            ],
            "satellites": {
                "sat-iss": {
                    "id": "sat-iss",
                    "name": "ISS",
                    "elsets": [
                        {
                            "tle": [
                                "1 25544U 98067A   24043.12345678  .00002182  00000+0  41420-4 0  9990",
                                "2 25544  51.6461 208.9163 0001567  96.4656 263.6710 15.54225995123456",
                            ],
                            "tle_line1": "1 25544U 98067A   24043.12345678  .00002182  00000+0  41420-4 0  9990",
                            "tle_line2": "2 25544  51.6461 208.9163 0001567  96.4656 263.6710 15.54225995123456",
                            "creationEpoch": now.isoformat(),
                        }
                    ],
                },
                "sat-starlink": {
                    "id": "sat-starlink",
                    "name": "STARLINK-1234",
                    "elsets": [
                        {
                            "tle": [
                                "1 44713U 19074A   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                                "2 44713  53.0000 123.4567 0001234  90.0000 270.0000 15.06000000123456",
                            ],
                            "tle_line1": "1 44713U 19074A   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                            "tle_line2": "2 44713  53.0000 123.4567 0001234  90.0000 270.0000 15.06000000123456",
                            "creationEpoch": now.isoformat(),
                        }
                    ],
                },
                "sat-noaa18": {
                    "id": "sat-noaa18",
                    "name": "NOAA-18",
                    "elsets": [
                        {
                            "tle": [
                                "1 28654U 05018A   24043.12345678  .00000123  00000+0  12345-5 0  9999",
                                "2 28654  98.7000 234.5678 0012345  45.6789 314.5432 14.12345678987654",
                            ],
                            "tle_line1": "1 28654U 05018A   24043.12345678  .00000123  00000+0  12345-5 0  9999",
                            "tle_line2": "2 28654  98.7000 234.5678 0012345  45.6789 314.5432 14.12345678987654",
                            "creationEpoch": now.isoformat(),
                        }
                    ],
                },
            },
        }

    # Abstract methods implementation

    def does_api_server_accept_key(self):
        """Check if the API key is valid (always True for dummy)."""
        if self.logger:
            self.logger.debug("DummyApiClient: API key check (always valid)")
        return True

    def get_telescope(self, telescope_id):
        """Get telescope details."""
        with self._data_lock:
            telescope = self.data.get("telescope", {})

            # Ensure required fields exist
            if "maxSlewRate" not in telescope:
                telescope["maxSlewRate"] = 5.0
                if self.logger:
                    self.logger.info("DummyApiClient: Added missing maxSlewRate to telescope data")

            if self.logger:
                self.logger.debug(f"DummyApiClient: get_telescope({telescope_id})")
            return telescope

    def get_satellite(self, satellite_id):
        """Fetch satellite details including TLE.

        Auto-populates missing satellites with default TLE data.
        """
        with self._data_lock:
            satellites = self.data.get("satellites", {})

            # Auto-populate missing satellites
            if satellite_id not in satellites:
                # Default satellite data with realistic TLEs
                # Note: Must have "elsets" array for compatibility with task execution code
                now_iso = datetime.now(timezone.utc).isoformat()
                default_satellites = {
                    "sat-iss": {
                        "id": "sat-iss",
                        "name": "ISS",
                        "elsets": [
                            {
                                "tle": [
                                    "1 25544U 98067A   24043.12345678  .00002182  00000+0  41420-4 0  9990",
                                    "2 25544  51.6461 208.9163 0001567  96.4656 263.6710 15.54225995123456",
                                ],
                                "tle_line1": "1 25544U 98067A   24043.12345678  .00002182  00000+0  41420-4 0  9990",
                                "tle_line2": "2 25544  51.6461 208.9163 0001567  96.4656 263.6710 15.54225995123456",
                                "creationEpoch": now_iso,
                            }
                        ],
                    },
                    "sat-starlink": {
                        "id": "sat-starlink",
                        "name": "STARLINK-1234",
                        "elsets": [
                            {
                                "tle": [
                                    "1 44713U 19074A   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                                    "2 44713  53.0000 123.4567 0001234  90.0000 270.0000 15.06000000123456",
                                ],
                                "tle_line1": "1 44713U 19074A   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                                "tle_line2": "2 44713  53.0000 123.4567 0001234  90.0000 270.0000 15.06000000123456",
                                "creationEpoch": now_iso,
                            }
                        ],
                    },
                    "sat-noaa18": {
                        "id": "sat-noaa18",
                        "name": "NOAA-18",
                        "elsets": [
                            {
                                "tle": [
                                    "1 28654U 05018A   24043.12345678  .00000123  00000+0  12345-5 0  9999",
                                    "2 28654  98.7000 234.5678 0012345  45.6789 314.5432 14.12345678987654",
                                ],
                                "tle_line1": "1 28654U 05018A   24043.12345678  .00000123  00000+0  12345-5 0  9999",
                                "tle_line2": "2 28654  98.7000 234.5678 0012345  45.6789 314.5432 14.12345678987654",
                                "creationEpoch": now_iso,
                            }
                        ],
                    },
                    "sat-hubble": {
                        "id": "sat-hubble",
                        "name": "HST",
                        "elsets": [
                            {
                                "tle": [
                                    "1 20580U 90037B   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                                    "2 20580  28.4700 123.4567 0002345  45.6789 314.5432 15.09876543123456",
                                ],
                                "tle_line1": "1 20580U 90037B   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                                "tle_line2": "2 20580  28.4700 123.4567 0002345  45.6789 314.5432 15.09876543123456",
                                "creationEpoch": now_iso,
                            }
                        ],
                    },
                    "sat-sentinel": {
                        "id": "sat-sentinel",
                        "name": "SENTINEL-2A",
                        "elsets": [
                            {
                                "tle": [
                                    "1 40697U 15028A   24043.12345678  .00000123  00000+0  12345-5 0  9999",
                                    "2 40697  98.5700 234.5678 0001234  90.0000 270.0000 14.30987654123456",
                                ],
                                "tle_line1": "1 40697U 15028A   24043.12345678  .00000123  00000+0  12345-5 0  9999",
                                "tle_line2": "2 40697  98.5700 234.5678 0001234  90.0000 270.0000 14.30987654123456",
                                "creationEpoch": now_iso,
                            }
                        ],
                    },
                }

                if satellite_id in default_satellites:
                    satellite = default_satellites[satellite_id]
                    satellites[satellite_id] = satellite
                    if self.logger:
                        self.logger.info(f"DummyApiClient: Auto-populated satellite {satellite_id}")
                else:
                    if self.logger:
                        self.logger.warning(f"DummyApiClient: Unknown satellite {satellite_id}")
                    return None
            else:
                satellite = satellites[satellite_id]

            if self.logger:
                self.logger.debug(f"DummyApiClient: get_satellite({satellite_id})")
            return satellite

    def get_telescope_tasks(self, telescope_id):
        """Fetch tasks for telescope (returns only Pending/Scheduled).

        Automatically maintains ~10 upcoming tasks at all times for easy testing.
        """
        with self._data_lock:
            tasks = self.data.get("tasks", [])

            # Clean up old completed/failed tasks (keep last 20 for history)
            now = datetime.now(timezone.utc)
            active_tasks = []
            completed_tasks = []

            for task in tasks:
                status = task.get("status")
                if status in ["Pending", "Scheduled"]:
                    # Check if task is too old (expired)
                    try:
                        task_stop = datetime.fromisoformat(task.get("taskStop", "").replace("Z", "+00:00"))
                        if task_stop < now:
                            # Task expired, mark as failed
                            task["status"] = "Failed"
                            completed_tasks.append(task)
                        else:
                            active_tasks.append(task)
                    except Exception:
                        active_tasks.append(task)
                else:
                    completed_tasks.append(task)

            # Keep only last 20 completed tasks to prevent memory bloat
            completed_tasks = completed_tasks[-20:] if len(completed_tasks) > 20 else completed_tasks

            # Auto-generate new tasks if we have fewer than 10 pending
            target_task_count = 10
            if len(active_tasks) < target_task_count:
                num_to_generate = target_task_count - len(active_tasks)

                # Get telescope and ground station info
                telescope = self.data.get("telescope", {})
                ground_station = self.data.get("ground_station", {})

                # Satellite list to cycle through
                satellite_names = [
                    ("sat-iss", "ISS"),
                    ("sat-starlink", "STARLINK-1234"),
                    ("sat-noaa18", "NOAA-18"),
                    ("sat-hubble", "HST"),
                    ("sat-sentinel", "SENTINEL-2A"),
                ]

                # Find the latest task start time to continue from there
                latest_time = now
                # Also track which satellite was used last to continue the cycle
                last_satellite_index = 0
                if active_tasks:
                    for task in active_tasks:
                        try:
                            task_start = datetime.fromisoformat(task.get("taskStart", "").replace("Z", "+00:00"))
                            if task_start > latest_time:
                                latest_time = task_start
                            # Track which satellite this was
                            sat_id = task.get("satelliteId")
                            for idx, (sid, _) in enumerate(satellite_names):
                                if sid == sat_id:
                                    last_satellite_index = idx
                                    break
                        except Exception:
                            pass

                # Generate new tasks starting 30 seconds apart, continuing satellite cycle
                for i in range(num_to_generate):
                    sat_index = (last_satellite_index + i + 1) % len(satellite_names)
                    sat_id, sat_name = satellite_names[sat_index]
                    task_start = latest_time + timedelta(seconds=30 * (i + 1))
                    task_stop = task_start + timedelta(seconds=5)

                    new_task = {
                        "id": str(uuid.uuid4()),
                        "type": "observation",
                        "status": "Pending",
                        "creationEpoch": now.isoformat(),
                        "updateEpoch": now.isoformat(),
                        "satelliteId": sat_id,
                        "satelliteName": sat_name,
                        "taskStart": task_start.isoformat(),
                        "taskStop": task_stop.isoformat(),
                        "telescopeId": telescope.get("id", "dummy-telescope-001"),
                        "telescopeName": telescope.get("name", "Dummy Telescope"),
                        "groundStationId": ground_station.get("id", "dummy-gs-001"),
                        "groundStationName": ground_station.get("name", "Test Ground Station"),
                        "userId": "dummy-user",
                        "username": "Test User",
                    }
                    active_tasks.append(new_task)

                # Update in-memory task list
                self.data["tasks"] = active_tasks + completed_tasks

                if self.logger:
                    self.logger.info(f"DummyApiClient: Auto-generated {num_to_generate} new tasks")

            if self.logger:
                self.logger.debug(f"DummyApiClient: get_telescope_tasks({telescope_id}) -> {len(active_tasks)} tasks")
            return active_tasks

    def get_ground_station(self, ground_station_id):
        """Fetch ground station details."""
        with self._data_lock:
            ground_station = self.data.get("ground_station", {})
            if self.logger:
                self.logger.debug(f"DummyApiClient: get_ground_station({ground_station_id})")
            return ground_station

    def put_telescope_status(self, body):
        """Report telescope online status."""
        if self.logger:
            self.logger.debug(f"DummyApiClient: put_telescope_status({body})")
        return {"status": "ok"}

    def expand_filters(self, filter_names):
        """Expand filter names to spectral specs."""
        if self.logger:
            self.logger.debug(f"DummyApiClient: expand_filters({filter_names})")
        # Return fake filter specs
        filters = []
        for name in filter_names:
            filters.append(
                {
                    "name": name,
                    "centralWavelength": 550.0,  # Fake wavelength
                    "bandwidth": 100.0,
                }
            )
        return {"filters": filters}

    def update_telescope_spectral_config(self, telescope_id, spectral_config):
        """Update telescope spectral configuration."""
        if self.logger:
            self.logger.debug(f"DummyApiClient: update_telescope_spectral_config({telescope_id})")
        return {"status": "ok"}

    def update_ground_station_location(self, ground_station_id, latitude, longitude, altitude):
        """Update ground station GPS location."""
        with self._data_lock:
            if self.logger:
                self.logger.debug(
                    f"DummyApiClient: update_ground_station_location({ground_station_id}, "
                    f"lat={latitude}, lon={longitude}, alt={altitude})"
                )
            # Update in-memory data
            if "ground_station" in self.data:
                self.data["ground_station"]["latitude"] = latitude
                self.data["ground_station"]["longitude"] = longitude
                self.data["ground_station"]["altitude"] = altitude
            return {"status": "ok"}

    def get_elsets_latest(self, days: int = 14):
        """Return stub list of elsets (same shape as real API: satelliteId, satelliteName, tle)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        stub = [
            {
                "satelliteId": "sat-iss",
                "satelliteName": "ISS",
                "tle": [
                    "1 25544U 98067A   24043.12345678  .00002182  00000+0  41420-4 0  9990",
                    "2 25544  51.6461 208.9163 0001567  96.4656 263.6710 15.54225995123456",
                ],
                "creationEpoch": now_iso,
            },
            {
                "satelliteId": "sat-starlink",
                "satelliteName": "STARLINK-1234",
                "tle": [
                    "1 44713U 19074A   24043.12345678  .00001234  00000+0  12345-4 0  9998",
                    "2 44713  53.0000 123.4567 0001234  90.0000 270.0000 15.06000000123456",
                ],
                "creationEpoch": now_iso,
            },
        ]
        if self.logger:
            self.logger.debug(f"DummyApiClient: get_elsets_latest(days={days}) -> {len(stub)} items")
        return stub

    def upload_optical_observations(
        self,
        observations: list,
        telescope_record: dict,
        sensor_location: dict,
        task_id: str | None = None,
    ) -> bool:
        """Stub: log and return True (no real upload in dummy mode)."""
        if self.logger:
            self.logger.info(f"DummyApiClient: upload_optical_observations({len(observations)} obs, task={task_id})")
        return True

    # Additional methods used by the system

    def upload_image(self, task_id, telescope_id, filepath):
        """Fake image upload with simulated random failures for testing retry logic."""
        if self.logger:
            self.logger.info(f"DummyApiClient: Fake upload for task {task_id}: {filepath}")

        # Simulate upload delay (5 seconds)
        time.sleep(5)

        # Randomly fail to test retry logic
        if random.random() < self.UPLOAD_FAILURE_RATE:
            if self.logger:
                self.logger.warning(f"DummyApiClient: Simulated upload failure for task {task_id}")
            return None  # Indicate upload failure

        # Return a fake results URL on success
        return f"https://dummy-server/results/{task_id}"

    def mark_task_complete(self, task_id):
        """Mark a task as complete with simulated random failures for testing retry logic."""
        # Randomly fail to test retry logic
        if random.random() < self.UPLOAD_FAILURE_RATE:
            if self.logger:
                self.logger.warning(f"DummyApiClient: Simulated mark_complete failure for task {task_id}")
            return False  # Indicate failure to mark complete

        with self._data_lock:
            tasks = self.data.get("tasks", [])

            for task in tasks:
                if task.get("id") == task_id:
                    task["status"] = "Succeeded"
                    task["updateEpoch"] = datetime.now(timezone.utc).isoformat()
                    if self.logger:
                        self.logger.info(f"DummyApiClient: Marked task {task_id} as Succeeded")
                    break

        return True  # Success

    def mark_task_failed(self, task_id):
        """Mark a task as failed (updates in-memory)."""
        with self._data_lock:
            tasks = self.data.get("tasks", [])

            for task in tasks:
                if task.get("id") == task_id:
                    task["status"] = "Failed"
                    task["updateEpoch"] = datetime.now(timezone.utc).isoformat()
                    break

            if self.logger:
                self.logger.info(f"DummyApiClient: Marked task {task_id} as Failed")

            return {"status": "Failed"}
