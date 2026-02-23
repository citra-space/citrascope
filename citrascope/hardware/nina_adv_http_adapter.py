import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

from citrascope.constants import AUTOFOCUS_TARGET_PRESETS
from citrascope.hardware.abstract_astro_hardware_adapter import (
    AbstractAstroHardwareAdapter,
    FilterConfig,
    ObservationStrategy,
    SettingSchemaEntry,
)


class NinaAdvancedHttpAdapter(AbstractAstroHardwareAdapter):
    """HTTP adapter for controlling astronomical equipment through N.I.N.A. (Nighttime Imaging 'N' Astronomy) Advanced API.
    https://bump.sh/christian-photo/doc/advanced-api/"""

    DEFAULT_FOCUS_POSITION = 9000
    CAM_URL = "/equipment/camera/"
    FILTERWHEEL_URL = "/equipment/filterwheel/"
    FOCUSER_URL = "/equipment/focuser/"
    MOUNT_URL = "/equipment/mount/"
    SAFETYMON_URL = "/equipment/safetymonitor/"
    SEQUENCE_URL = "/sequence/"

    def __init__(self, logger: logging.Logger, images_dir: Path, **kwargs):
        super().__init__(images_dir=images_dir, **kwargs)
        self.logger: logging.Logger = logger
        self.nina_api_path = kwargs.get("nina_api_path", "http://nina:1888/v2/api")

        self.binning_x = kwargs.get("binning_x", 1)
        self.binning_y = kwargs.get("binning_y", 1)

    @classmethod
    def get_settings_schema(cls, **kwargs) -> list[SettingSchemaEntry]:
        """
        Return a schema describing configurable settings for the NINA Advanced HTTP adapter.
        """
        return [
            {
                "name": "nina_api_path",
                "friendly_name": "N.I.N.A. API URL",
                "type": "str",
                "default": "http://nina:1888/v2/api",
                "description": "Base URL for the NINA Advanced HTTP API",
                "required": True,
                "placeholder": "http://localhost:1888/v2/api",
                "pattern": r"^https?://.*",
                "group": "Connection",
            },
            {
                "name": "binning_x",
                "friendly_name": "Binning X",
                "type": "int",
                "default": 1,
                "description": "Horizontal pixel binning for observations (1=no binning, 2=2x2, etc.)",
                "required": False,
                "placeholder": "1",
                "min": 1,
                "max": 4,
                "group": "Imaging",
            },
            {
                "name": "binning_y",
                "friendly_name": "Binning Y",
                "type": "int",
                "default": 1,
                "description": "Vertical pixel binning for observations (1=no binning, 2=2x2, etc.)",
                "required": False,
                "placeholder": "1",
                "min": 1,
                "max": 4,
                "group": "Imaging",
            },
        ]

    def do_autofocus(self, target_ra: float | None = None, target_dec: float | None = None):
        """Perform autofocus routine for all enabled filters.

        Slews telescope to a bright reference star and runs autofocus
        for each enabled filter in the filter map, updating focus positions.

        Args:
            target_ra: RA of the slew target in degrees (J2000), or None for Mirach
            target_dec: Dec of the slew target in degrees (J2000), or None for Mirach

        Raises:
            RuntimeError: If no filters discovered or no enabled filters
        """
        if not self.filter_map:
            raise RuntimeError("No filters discovered. Cannot perform autofocus.")

        # Filter to only enabled filters
        enabled_filters = {fid: fdata for fid, fdata in self.filter_map.items() if fdata.get("enabled", True)}
        if not enabled_filters:
            raise RuntimeError("No enabled filters. Cannot perform autofocus.")

        self.logger.info(f"Performing autofocus routine on {len(enabled_filters)} enabled filter(s) ...")

        if target_ra is not None and target_dec is not None:
            ra = target_ra
            dec = target_dec
        else:
            mirach = AUTOFOCUS_TARGET_PRESETS["mirach"]
            ra = mirach["ra"]
            dec = mirach["dec"]

        self.logger.info(f"Slewing to autofocus target (RA={ra:.4f}, Dec={dec:.4f}) ...")
        try:
            response = requests.get(f"{self.nina_api_path}{self.MOUNT_URL}slew?ra={ra}&dec={dec}", timeout=30)
            response.raise_for_status()
            mount_status = response.json()
            self.logger.info(f"Mount {mount_status['Response']}")
        except requests.Timeout:
            raise RuntimeError("Mount slew request timed out")
        except requests.RequestException as e:
            raise RuntimeError(f"Mount slew failed: {e}")

        # wait for slew to complete
        while self.telescope_is_moving():
            self.logger.info("Waiting for mount to finish slewing...")
            time.sleep(5)

        for id, filter in enabled_filters.items():
            self.logger.info(f"Focusing Filter ID: {id}, Name: {filter['name']}")
            # Pass existing focus position to preserve it if autofocus fails
            existing_focus = filter.get("focus_position", self.DEFAULT_FOCUS_POSITION)
            focus_value = self._auto_focus_one_filter(id, filter["name"], existing_focus)
            self.filter_map[id]["focus_position"] = focus_value

    # autofocus routine
    def _auto_focus_one_filter(self, filter_id: int, filter_name: str, existing_focus_position: int) -> int:

        # change to the requested filter
        correct_filter_in_place = False
        while not correct_filter_in_place:
            requests.get(self.nina_api_path + self.FILTERWHEEL_URL + "change-filter?filterId=" + str(filter_id))
            filterwheel_status = requests.get(self.nina_api_path + self.FILTERWHEEL_URL + "info").json()
            current_filter_id = filterwheel_status["Response"]["SelectedFilter"]["Id"]
            if current_filter_id == filter_id:
                correct_filter_in_place = True
            else:
                self.logger.info(f"Waiting for filterwheel to change to filter ID {filter_id} ...")
                time.sleep(5)

        # move to starting focus position
        self.logger.info("Moving focus to autofocus starting position ...")
        starting_focus_position = self.DEFAULT_FOCUS_POSITION
        is_in_starting_position = False
        while not is_in_starting_position:
            focuser_status = requests.get(
                self.nina_api_path + self.FOCUSER_URL + "move?position=" + str(starting_focus_position)
            ).json()
            focuser_status = requests.get(self.nina_api_path + self.FOCUSER_URL + "info").json()
            if int(focuser_status["Response"]["Position"]) == starting_focus_position:
                is_in_starting_position = True
            else:
                self.logger.info("Waiting for focuser to reach starting position ...")
                time.sleep(5)

        # start autofocus
        self.logger.info("Starting autofocus ...")
        focuser_status = requests.get(self.nina_api_path + self.FOCUSER_URL + "auto-focus").json()
        self.logger.info(f"Focuser {focuser_status['Response']}")

        last_completed_autofocus = requests.get(self.nina_api_path + self.FOCUSER_URL + "last-af").json()

        if not last_completed_autofocus.get("Success"):
            self.logger.error(f"Failed to start autofocus: {last_completed_autofocus.get('Error')}")
            # Preserve existing focus position if it's not the default, otherwise use default
            if existing_focus_position != self.DEFAULT_FOCUS_POSITION:
                self.logger.warning(f"Preserving existing focus position: {existing_focus_position}")
                return existing_focus_position
            else:
                self.logger.warning(f"Using default focus position: {self.DEFAULT_FOCUS_POSITION}")
                return self.DEFAULT_FOCUS_POSITION

        while (
            last_completed_autofocus["Response"]["Filter"] != filter_name
            or last_completed_autofocus["Response"]["InitialFocusPoint"]["Position"] != starting_focus_position
        ):
            self.logger.info("Waiting autofocus")
            last_completed_autofocus = requests.get(self.nina_api_path + self.FOCUSER_URL + "last-af").json()
            time.sleep(15)

        autofocused_position = last_completed_autofocus["Response"]["CalculatedFocusPoint"]["Position"]
        autofocused_value = last_completed_autofocus["Response"]["CalculatedFocusPoint"]["Value"]

        self.logger.info(
            f"Autofocus complete for filter {filter_name}: Position {autofocused_position}, HFR {autofocused_value}"
        )
        return autofocused_position

    def _do_point_telescope(self, ra: float, dec: float):
        self.logger.info(f"Slewing to RA: {ra}, Dec: {dec}")
        try:
            response = requests.get(f"{self.nina_api_path}{self.MOUNT_URL}slew?ra={ra}&dec={dec}", timeout=30)
            response.raise_for_status()
            slew_response = response.json()

            if slew_response.get("Success"):
                self.logger.info(f"Mount slew initiated: {slew_response['Response']}")
                return True
            else:
                self.logger.error(f"Failed to slew mount: {slew_response.get('Error')}")
                return False
        except requests.Timeout:
            self.logger.error("Mount slew request timed out")
            return False
        except requests.RequestException as e:
            self.logger.error(f"Mount slew request failed: {e}")
            return False

    def connect(self) -> bool:
        try:
            # start connection to all equipments
            self.logger.info("Connecting camera ...")
            cam_status = requests.get(self.nina_api_path + self.CAM_URL + "connect", timeout=5).json()
            if not cam_status["Success"]:
                self.logger.error(f"Failed to connect camera: {cam_status.get('Error')}")
                return False
            self.logger.info(f"Camera Connected!")

            self.logger.info("Starting camera cooling ...")
            cool_status = requests.get(self.nina_api_path + self.CAM_URL + "cool", timeout=5).json()
            if not cool_status["Success"]:
                self.logger.warning(f"Failed to start camera cooling: {cool_status.get('Error')}")
            else:
                self.logger.info("Cooler started!")

            self.logger.info("Connecting filterwheel ...")
            filterwheel_status = requests.get(self.nina_api_path + self.FILTERWHEEL_URL + "connect", timeout=5).json()
            if not filterwheel_status["Success"]:
                self.logger.warning(f"Failed to connect filterwheel: {filterwheel_status.get('Error')}")
            else:
                self.logger.info(f"Filterwheel Connected!")

            self.logger.info("Connecting focuser ...")
            focuser_status = requests.get(self.nina_api_path + self.FOCUSER_URL + "connect", timeout=5).json()
            if not focuser_status["Success"]:
                self.logger.warning(f"Failed to connect focuser: {focuser_status.get('Error')}")
            else:
                self.logger.info(f"Focuser Connected!")

            self.logger.info("Connecting mount ...")
            mount_status = requests.get(self.nina_api_path + self.MOUNT_URL + "connect", timeout=5).json()
            if not mount_status["Success"]:
                self.logger.error(f"Failed to connect mount: {mount_status.get('Error')}")
                return False
            self.logger.info(f"Mount Connected!")

            self.logger.info("Unparking mount ...")
            mount_status = requests.get(self.nina_api_path + self.MOUNT_URL + "unpark", timeout=5).json()
            if not mount_status["Success"]:
                self.logger.error(f"Failed to unpark mount: {mount_status.get('Error')}")
                return False
            self.logger.info(f"Mount Unparked!")

            # Discover available filters (focus positions loaded from saved settings)
            self.discover_filters()

            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to NINA Advanced API: {e}")
            return False

    def discover_filters(self):
        self.logger.info("Discovering filters ...")
        filterwheel_info = requests.get(self.nina_api_path + self.FILTERWHEEL_URL + "info", timeout=5).json()
        if not filterwheel_info.get("Success"):
            self.logger.error(f"Failed to get filterwheel info: {filterwheel_info.get('Error')}")
            raise RuntimeError("Failed to get filterwheel info")

        filters = filterwheel_info["Response"]["AvailableFilters"]
        for filter in filters:
            filter_id = filter["Id"]
            filter_name = filter["Name"]
            # Use existing focus position and enabled state if filter already in map
            if filter_id in self.filter_map:
                focus_position = self.filter_map[filter_id].get("focus_position", self.DEFAULT_FOCUS_POSITION)
                enabled = self.filter_map[filter_id].get("enabled", True)
                self.logger.info(
                    f"Discovered filter: {filter_name} with ID: {filter_id}, using saved focus position: {focus_position}, enabled: {enabled}"
                )
            else:
                focus_position = self.DEFAULT_FOCUS_POSITION
                enabled = True  # Default new filters to enabled
                self.logger.info(
                    f"Discovered new filter: {filter_name} with ID: {filter_id}, using default focus position: {focus_position}"
                )

            self.filter_map[filter_id] = {"name": filter_name, "focus_position": focus_position, "enabled": enabled}

    def disconnect(self):
        pass

    def supports_autofocus(self) -> bool:
        """Indicates that NINA adapter supports autofocus."""
        return True

    def supports_filter_management(self) -> bool:
        """Indicates that NINA adapter supports filter/focus management."""
        return True

    def is_telescope_connected(self) -> bool:
        """Check if telescope is connected and responsive."""
        try:
            mount_info = requests.get(f"{self.nina_api_path}{self.MOUNT_URL}info", timeout=2).json()
            return mount_info.get("Success", False) and mount_info.get("Response", {}).get("Connected", False)
        except Exception:
            return False

    def is_camera_connected(self) -> bool:
        """Check if camera is connected and responsive."""
        try:
            cam_info = requests.get(f"{self.nina_api_path}{self.CAM_URL}info", timeout=2).json()
            return cam_info.get("Success", False) and cam_info.get("Response", {}).get("Connected", False)
        except Exception:
            return False

    def list_devices(self) -> list[str]:
        return []

    def select_telescope(self, device_name: str) -> bool:
        return True

    def get_telescope_direction(self) -> tuple[float, float]:
        mount_info = requests.get(self.nina_api_path + self.MOUNT_URL + "info").json()
        if mount_info.get("Success"):
            ra_degrees = mount_info["Response"]["Coordinates"]["RADegrees"]
            dec_degrees = mount_info["Response"]["Coordinates"]["Dec"]
            return (ra_degrees, dec_degrees)
        else:
            self.logger.error(f"Failed to get telescope direction: {mount_info.get('Error')}")
            raise RuntimeError(f"Failed to get mount info: {mount_info.get('Error')}")

    def telescope_is_moving(self) -> bool:
        mount_info = requests.get(self.nina_api_path + self.MOUNT_URL + "info").json()
        if mount_info.get("Success"):
            return mount_info["Response"]["Slewing"]
        else:
            self.logger.error(f"Failed to get telescope status: {mount_info.get('Error')}")
            return False

    def select_camera(self, device_name: str) -> bool:
        return True

    def take_image(self, task_id: str, exposure_duration_seconds=1) -> str:
        raise NotImplementedError

    def set_custom_tracking_rate(self, ra_rate: float, dec_rate: float):
        pass  # TODO: make real

    def get_tracking_rate(self) -> tuple[float, float]:
        return (0, 0)  # TODO: make real

    def perform_alignment(self, target_ra: float, target_dec: float) -> bool:
        return True  # TODO: make real

    def _get_sequence_template(self) -> str:
        """Load the sequence template as a string for placeholder replacement."""
        template_path = os.path.join(os.path.dirname(__file__), "nina_adv_http_survey_template.json")
        with open(template_path, "r") as f:
            return f.read()

    def get_observation_strategy(self) -> ObservationStrategy:
        return ObservationStrategy.SEQUENCE_TO_CONTROLLER

    def _find_by_id(self, data, target_id):
        """Recursively search for an item with a specific $id in the JSON structure.

        Args:
            data: The JSON data structure to search (dict, list, or primitive)
            target_id: The $id value to search for (as string)

        Returns:
            The item with the matching $id, or None if not found
        """
        if isinstance(data, dict):
            if data.get("$id") == target_id:
                return data
            for value in data.values():
                result = self._find_by_id(value, target_id)
                if result is not None:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_by_id(item, target_id)
                if result is not None:
                    return result
        return None

    def _get_max_id(self, data):
        """Recursively find the maximum $id value in the JSON structure.

        Args:
            data: The JSON data structure to search (dict, list, or primitive)

        Returns:
            The maximum numeric $id value found, or 0 if none found
        """
        max_id = 0
        if isinstance(data, dict):
            if "$id" in data:
                try:
                    max_id = max(max_id, int(data["$id"]))
                except (ValueError, TypeError):
                    pass
            for value in data.values():
                max_id = max(max_id, self._get_max_id(value))
        elif isinstance(data, list):
            for item in data:
                max_id = max(max_id, self._get_max_id(item))
        return max_id

    def _update_all_ids(self, data, id_counter):
        """Recursively update all $id values in a data structure.

        Args:
            data: The JSON data structure to update (dict, list, or primitive)
            id_counter: A list with a single integer element [current_id] that gets incremented

        Returns:
            None (modifies data in place)
        """
        if isinstance(data, dict):
            if "$id" in data:
                data["$id"] = str(id_counter[0])
                id_counter[0] += 1
            for value in data.values():
                self._update_all_ids(value, id_counter)
        elif isinstance(data, list):
            for item in data:
                self._update_all_ids(item, id_counter)

    def perform_observation_sequence(self, task, satellite_data) -> str | list[str]:
        """Create and execute a NINA sequence for the given satellite.

        Args:
            task: Task object containing id and filter assignment
            satellite_data: Satellite data including TLE information

        Returns:
            str: Path to the captured image
        """
        elset = satellite_data["most_recent_elset"]

        # Load template as JSON and replace binning placeholders
        template_str = self._get_sequence_template()
        template_str = template_str.replace("{binning_x}", str(self.binning_x))
        template_str = template_str.replace("{binning_y}", str(self.binning_y))
        sequence_json = json.loads(template_str)

        nina_sequence_name = f"Citra Target: {satellite_data['name']}, Task: {task.id}"

        # Replace basic placeholders (use \r\n for Windows NINA compatibility)
        tle_data = f"{elset['tle'][0]}\r\n{elset['tle'][1]}"
        sequence_json["Name"] = nina_sequence_name

        # Navigate to the TLE container (ID 20 in the template)
        target_container = self._find_by_id(sequence_json, "20")
        if not target_container:
            raise RuntimeError("Could not find TLE container (ID 20) in sequence template")

        target_container["TLEData"] = tle_data
        target_container["Name"] = satellite_data["name"]
        target_container["Target"]["TargetName"] = satellite_data["name"]

        # Find the TLE control item and update it
        tle_items = target_container["Items"]["$values"]
        for item in tle_items:
            if item.get("$type") == "DaleGhent.NINA.PlaneWaveTools.TLE.TLEControl, PlaneWave Tools":
                item["Line1"] = elset["tle"][0]
                item["Line2"] = elset["tle"][1]
                break

        # Find the template triplet (filter/focus/expose) - should be items 1, 2, 3
        # (item 0 is TLE control)
        template_triplet = tle_items[1:4]  # SwitchFilter, MoveFocuserAbsolute, TakeExposure

        # Clear the items list and rebuild with TLE control + triplets for each filter
        new_items = [tle_items[0]]  # Keep TLE control as first item

        # Generate triplet for each discovered filter
        # Find the maximum ID in use and start after it to avoid collisions
        base_id = self._get_max_id(sequence_json) + 1
        self.logger.debug(f"Starting dynamic ID generation at {base_id}")

        id_counter = [base_id]  # Use list so it can be modified in nested function

        # Select filters to use for this task
        filters_to_use = self.select_filters_for_task(task, allow_no_filter=False)

        for filter_id, filter_info in filters_to_use.items():
            filter_name = filter_info["name"]
            focus_position = filter_info["focus_position"]

            # Create a deep copy of the triplet and update ALL nested IDs
            filter_triplet = json.loads(json.dumps(template_triplet))
            self._update_all_ids(filter_triplet, id_counter)

            # Update filter switch (first item in triplet)
            filter_triplet[0]["Filter"]["_name"] = filter_name
            filter_triplet[0]["Filter"]["_position"] = filter_id

            # Update focus position (second item in triplet)
            filter_triplet[1]["Position"] = focus_position

            # Exposure settings (third item) are already set from template

            # Add this triplet to the sequence
            new_items.extend(filter_triplet)

            self.logger.debug(f"Added filter {filter_name} (ID: {filter_id}) with focus position {focus_position}")

        # Update the items list
        tle_items.clear()
        tle_items.extend(new_items)

        # Convert back to JSON string
        template_str = json.dumps(sequence_json, indent=2)

        # POST the sequence

        self.logger.info(f"Posting NINA sequence")
        post_response = requests.post(f"{self.nina_api_path}{self.SEQUENCE_URL}load", json=sequence_json).json()
        if not post_response.get("Success"):
            self.logger.error(f"Failed to post sequence: {post_response.get('Error')}")
            raise RuntimeError("Failed to post NINA sequence")

        self.logger.info(f"Loaded sequence to NINA, starting sequence...")

        start_response = requests.get(
            f"{self.nina_api_path}{self.SEQUENCE_URL}start?skipValidation=true"
        ).json()  # TODO: try and fix validation issues
        if not start_response.get("Success"):
            self.logger.error(f"Failed to start sequence: {start_response.get('Error')}")
            raise RuntimeError("Failed to start NINA sequence")

        timeout_minutes = 60
        poll_interval_seconds = 10
        elapsed_time = 0
        status_response = None
        while elapsed_time < timeout_minutes * 60:
            status_response = requests.get(f"{self.nina_api_path}{self.SEQUENCE_URL}json").json()

            start_status = status_response["Response"][1][
                "Status"
            ]  # these are also based on the hardcoded template sections for now...
            targets_status = status_response["Response"][2]["Status"]
            end_status = status_response["Response"][3]["Status"]
            self.logger.debug(f"Sequence status - Start: {start_status}, Targets: {targets_status}, End: {end_status}")

            if start_status == "FINISHED" and targets_status == "FINISHED" and end_status == "FINISHED":
                self.logger.info(f"NINA sequence completed")
                break

            self.logger.info(f"NINA sequence still running, waiting {poll_interval_seconds} seconds...")
            time.sleep(poll_interval_seconds)
            elapsed_time += poll_interval_seconds
        else:
            self.logger.error(f"NINA sequence did not complete within timeout of {timeout_minutes} minutes")
            raise RuntimeError("NINA sequence timeout")

        # get a list of images taken in the sequence
        self.logger.info(f"Retrieving list of images taken in sequence...")
        images_response = requests.get(f"{self.nina_api_path}/image-history?all=true").json()
        if not images_response.get("Success"):
            self.logger.error(f"Failed to get images list: {images_response.get('Error')}")
            raise RuntimeError("Failed to get images list from NINA")

        images_to_download = []
        expected_image_count = len(filters_to_use)  # One image per filter in sequence
        images_found = len(images_response["Response"])
        self.logger.info(
            f"Found {images_found} images in NINA image history, considering the last {expected_image_count}"
        )
        start_index = max(0, images_found - expected_image_count)
        end_index = images_found
        if images_found < expected_image_count:
            self.logger.warning(f"Fewer images found ({images_found}) than expected ({expected_image_count})")
        for i in range(start_index, end_index):
            possible_image = images_response["Response"][i]
            if "Filename" not in possible_image:
                self.logger.warning(f"Image {i} has no filename in response, skipping")
                continue

            if task.id in possible_image["Filename"]:
                self.logger.info(f"Image {i} {possible_image['Filename']} matches task id")
                images_to_download.append(i)
            else:
                self.logger.warning(
                    f"Image {i} {possible_image['Filename']} does not match task id, skipping. Please make sure NINA is configured to include Sequence Title in image filenames under Options > Imaging > Image File Pattern."
                )

        # Get the most recent image from NINA (index 0) in raw FITS format
        filepaths = []
        for image_index in images_to_download:
            self.logger.debug(f"Retrieving image from NINA...")
            image_response = requests.get(
                f"{self.nina_api_path}/image/{image_index}",
                params={"raw_fits": "true"},
            )

            if image_response.status_code != 200:
                self.logger.error(f"Failed to retrieve image: HTTP {image_response.status_code}")
                raise RuntimeError("Failed to retrieve image from NINA")

            image_data = image_response.json()
            if not image_data.get("Success"):
                self.logger.error(f"Failed to get image: {image_data.get('Error')}")
                raise RuntimeError(f"Failed to get image from NINA: {image_data.get('Error')}")

            # Decode base64 FITS data and save to file
            fits_base64 = image_data["Response"]
            fits_bytes = base64.b64decode(fits_base64)

            # Save the FITS file
            filepath = str(self.images_dir / f"citra_task_{task.id}_image_{image_index}.fits")
            filepaths.append(filepath)

            with open(filepath, "wb") as f:
                f.write(fits_bytes)

            self.logger.info(f"Saved FITS image to {filepath}")

        return filepaths
