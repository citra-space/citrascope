"""Unit tests for UploadQueue upload-path branching logic.

Tests that:
- When satellite observations are present in processing_result, upload_optical_observations
  is called and upload_image is NOT called.
- When no satellite observations are present, upload_image is called and
  upload_optical_observations is NOT called.
- When observations are present but telescope_record or sensor_location is missing,
  the queue falls back to upload_image.
- FITS cleanup runs on both paths when keep_images is False.
"""

from dataclasses import dataclass, field
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal stubs so we can instantiate UploadQueue without a full daemon
# ---------------------------------------------------------------------------


@dataclass
class _FakeAggregatedResult:
    should_upload: bool = True
    extracted_data: dict = field(default_factory=dict)
    all_results: list = field(default_factory=list)
    total_time: float = 0.0
    skip_reason: str | None = None


_TELESCOPE_RECORD = {
    "id": "tel-uuid-001",
    "name": "Test Scope",
    "angularNoise": 2.5,
    "spectralMinWavelengthNm": 400.0,
    "spectralMaxWavelengthNm": 700.0,
}

_SENSOR_LOCATION = {"latitude": 40.0, "longitude": -111.0, "altitude": 1400.0}

_SAT_OBS = [
    {
        "norad_id": "sat-uuid-abc",
        "name": "TEST-SAT",
        "ra": 123.4,
        "dec": 45.6,
        "mag": 8.2,
        "filter": "Clear",
        "timestamp": "2024-02-12T01:23:45.000000",
        "phase_angle": 30.1,
        "fwhm": 1.2,
    }
]


def _make_upload_queue():
    """Return an UploadQueue with a no-op background worker (doesn't start threads)."""
    from citrascope.tasks.upload_queue import UploadQueue

    q = UploadQueue.__new__(UploadQueue)
    q.logger = MagicMock()
    q.task_manager = None
    return q


def _build_item(
    sat_obs=None,
    telescope_record=_TELESCOPE_RECORD,
    sensor_location=_SENSOR_LOCATION,
    api_client=None,
    keep_images=False,
):
    """Build a minimal work-item dict for _execute_work / _on_success."""
    if api_client is None:
        api_client = MagicMock()
        api_client.upload_image.return_value = "https://example.com/results/task-1"
        api_client.upload_optical_observations.return_value = True
        api_client.mark_task_complete.return_value = True

    extracted_data = {}
    if sat_obs is not None:
        extracted_data["satellite_matcher.satellite_observations"] = sat_obs

    pr = _FakeAggregatedResult(extracted_data=extracted_data)

    settings = MagicMock()
    settings.keep_images = keep_images

    task_obj = MagicMock()

    return {
        "task_id": "task-uuid-001",
        "task": task_obj,
        "image_path": "/tmp/fake_image.fits",
        "processing_result": pr,
        "api_client": api_client,
        "telescope_record": telescope_record,
        "sensor_location": sensor_location,
        "settings": settings,
        "on_complete": MagicMock(),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUploadQueueBranching:
    def test_obs_path_calls_upload_optical_observations(self):
        """When sat obs present, upload_optical_observations is called; upload_image is not."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_optical_observations.return_value = True
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=_SAT_OBS, api_client=api)
        success, meta = q._execute_work(item)

        assert success is True
        assert meta["obs_path"] is True
        api.upload_optical_observations.assert_called_once_with(
            _SAT_OBS, _TELESCOPE_RECORD, _SENSOR_LOCATION, task_id="task-uuid-001"
        )
        api.upload_image.assert_not_called()

    def test_no_obs_path_calls_upload_image(self):
        """When no sat obs, upload_image is called; upload_optical_observations is not."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_image.return_value = "https://example.com/results/task-1"
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=[], api_client=api)
        success, meta = q._execute_work(item)

        assert success is True
        assert meta["obs_path"] is False
        api.upload_image.assert_called_once_with(
            "task-uuid-001", _TELESCOPE_RECORD["id"], "/tmp/fake_image.fits"
        )  # telescope id derived from telescope_record["id"] inside _execute_work
        api.upload_optical_observations.assert_not_called()

    def test_no_processing_result_falls_back_to_image_upload(self):
        """When processing_result is None, fall back to upload_image."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_image.return_value = "https://example.com/results/task-1"
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=None, api_client=api)
        item["processing_result"] = None
        success, meta = q._execute_work(item)

        assert success is True
        assert meta["obs_path"] is False
        api.upload_image.assert_called_once()
        api.upload_optical_observations.assert_not_called()

    def test_missing_telescope_record_falls_back_to_image_upload(self):
        """When sat obs present but telescope_record is None, fall back to upload_image."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_image.return_value = "https://example.com/results/task-1"
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=_SAT_OBS, telescope_record=None, api_client=api)
        success, meta = q._execute_work(item)

        assert success is True
        assert meta["obs_path"] is False
        api.upload_image.assert_called_once()
        api.upload_optical_observations.assert_not_called()

    def test_missing_sensor_location_falls_back_to_image_upload(self):
        """When sat obs present but sensor_location is None, fall back to upload_image."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_image.return_value = "https://example.com/results/task-1"
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=_SAT_OBS, sensor_location=None, api_client=api)
        success, meta = q._execute_work(item)

        assert success is True
        assert meta["obs_path"] is False
        api.upload_image.assert_called_once()
        api.upload_optical_observations.assert_not_called()

    def test_obs_upload_failure_returns_false(self):
        """When upload_optical_observations returns False, _execute_work returns (False, None)."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_optical_observations.return_value = False

        item = _build_item(sat_obs=_SAT_OBS, api_client=api)
        success, meta = q._execute_work(item)

        assert success is False
        assert meta is None
        api.mark_task_complete.assert_not_called()

    def test_image_upload_failure_returns_false(self):
        """When upload_image returns falsy, _execute_work returns (False, None)."""
        q = _make_upload_queue()
        api = MagicMock()
        api.upload_image.return_value = None

        item = _build_item(sat_obs=[], api_client=api)
        success, meta = q._execute_work(item)

        assert success is False
        assert meta is None
        api.mark_task_complete.assert_not_called()

    def test_cleanup_runs_on_obs_path_when_keep_images_false(self, tmp_path):
        """FITS cleanup runs after obs-only upload when keep_images is False."""
        fits = tmp_path / "image.fits"
        fits.write_bytes(b"FITS")

        q = _make_upload_queue()
        api = MagicMock()
        api.upload_optical_observations.return_value = True
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=_SAT_OBS, api_client=api, keep_images=False)
        item["image_path"] = str(fits)

        success, meta = q._execute_work(item)
        assert success is True
        assert meta["obs_path"] is True

        q._on_success(item, meta)
        assert not fits.exists(), "FITS file should be deleted after obs-path upload"

    def test_cleanup_runs_on_fits_path_when_keep_images_false(self, tmp_path):
        """FITS cleanup runs after standard FITS upload when keep_images is False."""
        fits = tmp_path / "image.fits"
        fits.write_bytes(b"FITS")

        q = _make_upload_queue()
        api = MagicMock()
        api.upload_image.return_value = "https://example.com/results/task-1"
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=[], api_client=api, keep_images=False)
        item["image_path"] = str(fits)

        success, meta = q._execute_work(item)
        assert success is True

        q._on_success(item, meta)
        assert not fits.exists(), "FITS file should be deleted after standard upload"

    def test_cleanup_skipped_when_keep_images_true(self, tmp_path):
        """FITS file is NOT deleted when keep_images is True."""
        fits = tmp_path / "image.fits"
        fits.write_bytes(b"FITS")

        q = _make_upload_queue()
        api = MagicMock()
        api.upload_optical_observations.return_value = True
        api.mark_task_complete.return_value = True

        item = _build_item(sat_obs=_SAT_OBS, api_client=api, keep_images=True)
        item["image_path"] = str(fits)

        success, meta = q._execute_work(item)
        assert success is True

        q._on_success(item, meta)
        assert fits.exists(), "FITS file should be kept when keep_images=True"
