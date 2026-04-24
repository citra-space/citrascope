"""CitraSense settings as a Pydantic BaseModel.

Each persisted setting is a single field declaration (type + default).
Serialization via ``model_dump()`` and loading via ``model_validate()``
eliminate the need to maintain separate field lists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

# Current on-disk schema version. Incremented whenever the config file layout
# changes in an observer-visible way. Older files are migrated transparently
# in ``CitraSenseSettings.load``.
#
# v1: legacy scalar fields (``hardware_adapter`` / ``telescope_id``) plus a
#     top-level ``adapter_settings`` dict keyed by adapter name.
# v2: introduces ``sensors: list[SensorConfig]`` as the forward shape (phase 1
#     of citra-space/citrasense#306). Scalar fields kept as compatibility aliases.
# v3: ``sensors[]`` is the sole source of truth. Legacy scalars removed from
#     the model; ``load()`` migrates v1/v2 files automatically.
CONFIG_VERSION = 3
# Legacy scalar-only shape — synthesized ``sensors`` entries are marked with
# this id so they round-trip cleanly on resave.
DEFAULT_TELESCOPE_SENSOR_ID = "telescope-0"

# Application constants for platformdirs
# Defined before imports to avoid circular dependency
APP_NAME = "citrasense"
APP_AUTHOR = "citra-space"

from citrasense.constants import DEFAULT_API_PORT, DEFAULT_WEB_PORT, PROD_API_HOST
from citrasense.logging import CITRASENSE_LOGGER
from citrasense.settings.directory_manager import DirectoryManager
from citrasense.settings.settings_file_manager import SettingsFileManager

_VALID_SEXTRACTOR_FILTERS = frozenset({"default", "gauss_1.5_3x3", "gauss_2.5_5x5", "tophat_3.0_3x3", "tophat_5.0_5x5"})


class SensorConfig(BaseModel):
    """Per-sensor configuration block.

    Introduced in phase 1 of the multi-sensor migration (issue #306). In
    phase 1 the config list always has exactly one entry of type
    ``"telescope"`` wrapping today's hardware adapter; follow-ups will add
    radar and RF entries.

    Fields:
        id: Unique local sensor id (e.g. ``"telescope-0"``). Used by the
            daemon to look up the live sensor via the sensor manager.
        type: Registry key resolved through
            :mod:`citrasense.sensors.sensor_registry`.
        adapter: For telescope sensors, the short adapter key (``"nina"``,
            ``"kstars"``, ``"indi"``, ``"direct"``, ``"dummy"``) resolved
            through :mod:`citrasense.hardware.adapter_registry`. Empty for
            sensor types that don't use the adapter registry.
        adapter_settings: Adapter-specific settings blob. Merged (not
            replaced) by :meth:`CitraSenseSettings.update_and_save` so
            partial web-form saves don't wipe keys like ``"filters"``.
        citra_sensor_id: Backend-side id that identifies this sensor to the
            Citra API (what ``CitraSenseSettings.telescope_id`` holds today
            for the single-telescope case).
    """

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    adapter: str = ""
    adapter_settings: dict[str, Any] = Field(default_factory=dict)
    citra_sensor_id: str = ""


class CitraSenseSettings(BaseModel):
    """Settings for CitraSense loaded from JSON configuration file.

    Each field below is defined once — type, default, and optional validator.
    ``model_dump()`` auto-generates the serialization dict; ``model_validate()``
    handles loading from a config dict with defaults for missing keys.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    # ── Persisted settings ────────────────────────────────────────────
    # API
    host: str = PROD_API_HOST
    port: int = DEFAULT_API_PORT
    use_ssl: bool = True
    personal_access_token: str = ""
    use_dummy_api: bool = False

    # Sensors — single source of truth for all sensor configuration.
    # Each entry describes one physical sensor (telescope, radar, RF, …).
    sensors: list[SensorConfig] = Field(default_factory=list)

    # Persisted config schema version. Missing/older values trigger the
    # one-shot legacy migration in :meth:`CitraSenseSettings.load`.
    config_version: int = CONFIG_VERSION

    # Runtime / UI-configurable
    log_level: str = "INFO"
    keep_images: bool = False
    processing_output_retention_hours: int = 0

    # Processors
    processors_enabled: bool = True
    enabled_processors: dict[str, bool] = Field(default_factory=dict)
    skip_upload: bool = False
    use_local_apass_catalog: bool = False

    # Plate solving (astrometry.net)
    plate_solve_timeout: int = 60
    astrometry_index_path: str = ""

    # Source extraction (SExtractor)
    sextractor_detect_thresh: float = 5.0
    sextractor_detect_minarea: int = 3
    sextractor_filter_name: str = "default"

    # Task retry
    max_task_retries: int = 3
    initial_retry_delay_seconds: int = 30
    max_retry_delay_seconds: int = 300

    # Logging
    file_logging_enabled: bool = True
    log_retention_days: int = 30

    # Custom directory overrides (empty = use platformdirs defaults)
    custom_data_dir: str = ""
    custom_log_dir: str = ""

    # Autofocus
    scheduled_autofocus_enabled: bool = False
    autofocus_schedule_mode: str = "interval"
    autofocus_interval_minutes: int = 60
    autofocus_after_sunset_offset_minutes: int = 60
    last_autofocus_timestamp: int | None = None
    autofocus_target_preset: str = "mirach"
    autofocus_target_custom_ra: float | None = None
    autofocus_target_custom_dec: float | None = None

    # HFR-based auto-refocus (hfr_baseline is per-adapter, stored in adapter_settings)
    autofocus_on_hfr_increase_enabled: bool = False
    autofocus_hfr_increase_percent: int = 30
    autofocus_hfr_sample_window: int = 5

    # Alignment
    alignment_exposure_seconds: float = 2.0
    last_alignment_timestamp: int | None = None

    # Time synchronization
    time_check_interval_minutes: int = 5
    time_offset_pause_ms: float = 500.0

    # Hardware safety
    hardware_safety_check_enabled: bool = False

    # GPS
    gps_monitoring_enabled: bool = True
    gps_location_updates_enabled: bool = True
    gps_update_interval_minutes: int = 5

    # Task processing
    task_processing_paused: bool = False

    # Observation mode: "auto", "tracking", or "sidereal"
    observation_mode: str = "auto"

    # Exposure duration for take_image calls (seconds), used by both sidereal and tracking modes.
    exposure_seconds: float = 2.0

    # Number of images to capture per observation task (burst count).
    num_exposures: int = 3

    # Adaptive exposure (auto-compute exposure from satellite angular rate + plate scale)
    adaptive_exposure: bool = False
    adaptive_exposure_max_trail_pixels: float = 3.0
    adaptive_exposure_min_seconds: float = 0.1
    adaptive_exposure_max_seconds: float = 30.0

    # MSI / elset cache
    elset_refresh_interval_hours: float = 6

    # Calibration
    calibration_frame_count: int = 30
    flat_frame_count: int = 15

    # Observing session (darkness-driven night lifecycle)
    observing_session_enabled: bool = False
    observing_session_sun_altitude_threshold: float = -12.0  # Civil=-6, Nautical=-12, Astronomical=-18
    observing_session_do_pointing_calibration: bool = False
    observing_session_do_autofocus: bool = True
    observing_session_do_park: bool = True

    # Self-tasking (autonomous work requests)
    self_tasking_enabled: bool = False
    self_tasking_satellite_group_ids: list[str] = Field(default_factory=list)
    self_tasking_include_orbit_regimes: list[str] = Field(default_factory=list)
    self_tasking_exclude_object_types: list[str] = Field(default_factory=list)
    self_tasking_collection_type: str = "Track"

    # ── Non-persisted public attrs (excluded from model_dump) ─────────
    web_port: int = Field(default=DEFAULT_WEB_PORT, exclude=True)

    # ── Private infrastructure ────────────────────────────────────────
    _config_manager: SettingsFileManager = PrivateAttr()
    _dir_manager: DirectoryManager = PrivateAttr()

    # ── Validators (warn-and-fallback, never raise) ───────────────────

    @field_validator("autofocus_target_custom_ra", mode="before")
    @classmethod
    def _validate_custom_ra(cls, v: Any) -> float | None:
        if v is not None:
            try:
                v = float(v)
            except (ValueError, TypeError):
                CITRASENSE_LOGGER.warning("Invalid autofocus_target_custom_ra (%s). Clearing.", v)
                return None
            if not (0 <= v <= 360):
                CITRASENSE_LOGGER.warning("Invalid autofocus_target_custom_ra (%s). Clearing.", v)
                return None
        return v

    @field_validator("autofocus_target_custom_dec", mode="before")
    @classmethod
    def _validate_custom_dec(cls, v: Any) -> float | None:
        if v is not None:
            try:
                v = float(v)
            except (ValueError, TypeError):
                CITRASENSE_LOGGER.warning("Invalid autofocus_target_custom_dec (%s). Clearing.", v)
                return None
            if not (-90 <= v <= 90):
                CITRASENSE_LOGGER.warning("Invalid autofocus_target_custom_dec (%s). Clearing.", v)
                return None
        return v

    @field_validator("autofocus_schedule_mode", mode="before")
    @classmethod
    def _validate_autofocus_schedule_mode(cls, v: Any) -> str:
        if v not in ("interval", "after_sunset"):
            CITRASENSE_LOGGER.warning("Invalid autofocus_schedule_mode (%r). Falling back to 'interval'.", v)
            return "interval"
        return v

    @field_validator("autofocus_after_sunset_offset_minutes", mode="before")
    @classmethod
    def _validate_autofocus_sunset_offset(cls, v: Any) -> int:
        try:
            v = int(v)
        except (ValueError, TypeError):
            CITRASENSE_LOGGER.warning(
                "Invalid autofocus_after_sunset_offset_minutes (%s). Setting to default 60 minutes.", v
            )
            return 60
        if v < 0 or v > 720:
            CITRASENSE_LOGGER.warning(
                "autofocus_after_sunset_offset_minutes (%s) out of range [0, 720]. Setting to default 60.", v
            )
            return 60
        return v

    @field_validator("autofocus_interval_minutes", mode="before")
    @classmethod
    def _validate_autofocus_interval(cls, v: Any) -> int:
        try:
            v = int(v)
        except (ValueError, TypeError):
            CITRASENSE_LOGGER.warning("Invalid autofocus_interval_minutes (%s). Setting to default 60 minutes.", v)
            return 60
        if v < 1 or v > 1440:
            CITRASENSE_LOGGER.warning("Invalid autofocus_interval_minutes (%s). Setting to default 60 minutes.", v)
            return 60
        return v

    @field_validator("autofocus_hfr_increase_percent", mode="before")
    @classmethod
    def _validate_hfr_increase_percent(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid autofocus_hfr_increase_percent (%r). Falling back to 30.", v)
            return 30
        if v < 10 or v > 200:
            clamped = max(10, min(200, v))
            CITRASENSE_LOGGER.warning(
                "autofocus_hfr_increase_percent %d out of range [10, 200]. Clamped to %d.", v, clamped
            )
            return clamped
        return v

    @field_validator("autofocus_hfr_sample_window", mode="before")
    @classmethod
    def _validate_hfr_sample_window(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid autofocus_hfr_sample_window (%r). Falling back to 5.", v)
            return 5
        if v < 3 or v > 20:
            clamped = max(3, min(20, v))
            CITRASENSE_LOGGER.warning("autofocus_hfr_sample_window %d out of range [3, 20]. Clamped to %d.", v, clamped)
            return clamped
        return v

    @field_validator("observation_mode", mode="before")
    @classmethod
    def _validate_observation_mode(cls, v: Any) -> str:
        if v == "static":
            return "sidereal"
        if v not in ("auto", "tracking", "sidereal"):
            CITRASENSE_LOGGER.warning("Invalid observation_mode (%r). Falling back to 'auto'.", v)
            return "auto"
        return v

    @field_validator("num_exposures", mode="before")
    @classmethod
    def _validate_num_exposures(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid num_exposures (%r). Falling back to 3.", v)
            return 3
        if v < 1 or v > 50:
            clamped = max(1, min(50, v))
            CITRASENSE_LOGGER.warning("num_exposures %d out of range [1, 50]. Clamped to %d.", v, clamped)
            return clamped
        return v

    @field_validator("exposure_seconds", mode="before")
    @classmethod
    def _validate_exposure_seconds(cls, v: Any) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid exposure_seconds (%r). Falling back to 2.0.", v)
            return 2.0
        if v < 0.01 or v > 300:
            clamped = max(0.01, min(300.0, v))
            CITRASENSE_LOGGER.warning("exposure_seconds %.3f out of range [0.01, 300]. Clamped to %.3f.", v, clamped)
            return clamped
        return v

    @field_validator("adaptive_exposure_max_trail_pixels", mode="before")
    @classmethod
    def _validate_adaptive_max_trail(cls, v: Any) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid adaptive_exposure_max_trail_pixels (%r). Falling back to 3.0.", v)
            return 3.0
        if v < 0.5 or v > 50.0:
            clamped = max(0.5, min(50.0, v))
            CITRASENSE_LOGGER.warning(
                "adaptive_exposure_max_trail_pixels %.1f out of range [0.5, 50]. Clamped to %.1f.", v, clamped
            )
            return clamped
        return v

    @field_validator("adaptive_exposure_min_seconds", mode="before")
    @classmethod
    def _validate_adaptive_min(cls, v: Any) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid adaptive_exposure_min_seconds (%r). Falling back to 0.1.", v)
            return 0.1
        if v < 0.01 or v > 10.0:
            clamped = max(0.01, min(10.0, v))
            CITRASENSE_LOGGER.warning(
                "adaptive_exposure_min_seconds %.3f out of range [0.01, 10]. Clamped to %.3f.", v, clamped
            )
            return clamped
        return v

    @field_validator("adaptive_exposure_max_seconds", mode="before")
    @classmethod
    def _validate_adaptive_max(cls, v: Any) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid adaptive_exposure_max_seconds (%r). Falling back to 30.0.", v)
            return 30.0
        if v < 1.0 or v > 300.0:
            clamped = max(1.0, min(300.0, v))
            CITRASENSE_LOGGER.warning(
                "adaptive_exposure_max_seconds %.1f out of range [1, 300]. Clamped to %.1f.", v, clamped
            )
            return clamped
        return v

    @field_validator("processing_output_retention_hours", mode="before")
    @classmethod
    def _validate_processing_output_retention(cls, v: Any) -> int:
        # Migrate legacy bool: True → -1 (keep forever), False → 0 (delete immediately)
        if v is True:
            return -1
        if v is False:
            return 0
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid processing_output_retention_hours (%r). Falling back to 0.", v)
            return 0
        if v < -1:
            CITRASENSE_LOGGER.warning("processing_output_retention_hours (%d) below -1. Clamped to -1.", v)
            return -1
        return v

    @field_validator("calibration_frame_count", mode="before")
    @classmethod
    def _validate_calibration_frame_count(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid calibration_frame_count (%r). Falling back to 30.", v)
            return 30
        if v < 5 or v > 100:
            clamped = max(5, min(100, v))
            CITRASENSE_LOGGER.warning("calibration_frame_count %d out of range [5, 100]. Clamped to %d.", v, clamped)
            return clamped
        return v

    @field_validator("flat_frame_count", mode="before")
    @classmethod
    def _validate_flat_frame_count(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid flat_frame_count (%r). Falling back to 15.", v)
            return 15
        if v < 5 or v > 50:
            clamped = max(5, min(50, v))
            CITRASENSE_LOGGER.warning("flat_frame_count %d out of range [5, 50]. Clamped to %d.", v, clamped)
            return clamped
        return v

    @field_validator("plate_solve_timeout", mode="before")
    @classmethod
    def _validate_plate_solve_timeout(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            default_timeout = cls.model_fields["plate_solve_timeout"].default
            CITRASENSE_LOGGER.warning("Invalid plate_solve_timeout (%r). Falling back to %s.", v, default_timeout)
            return default_timeout
        if v < 10 or v > 300:
            clamped = max(10, min(300, v))
            CITRASENSE_LOGGER.warning("plate_solve_timeout %d out of range [10, 300]. Clamped to %d.", v, clamped)
            return clamped
        return v

    @field_validator("sextractor_detect_thresh", mode="before")
    @classmethod
    def _validate_sextractor_detect_thresh(cls, v: Any) -> float:
        try:
            v = float(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid sextractor_detect_thresh (%r). Falling back to 5.0.", v)
            return 5.0
        if v < 1.0 or v > 20.0:
            clamped = max(1.0, min(20.0, v))
            CITRASENSE_LOGGER.warning(
                "sextractor_detect_thresh %.1f out of range [1.0, 20.0]. Clamped to %.1f.", v, clamped
            )
            return clamped
        return v

    @field_validator("sextractor_detect_minarea", mode="before")
    @classmethod
    def _validate_sextractor_detect_minarea(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning("Invalid sextractor_detect_minarea (%r). Falling back to 3.", v)
            return 3
        if v < 1 or v > 50:
            clamped = max(1, min(50, v))
            CITRASENSE_LOGGER.warning("sextractor_detect_minarea %d out of range [1, 50]. Clamped to %d.", v, clamped)
            return clamped
        return v

    @field_validator("sextractor_filter_name", mode="before")
    @classmethod
    def _validate_sextractor_filter_name(cls, v: Any) -> str:
        v = str(v) if v else "default"
        if v not in _VALID_SEXTRACTOR_FILTERS:
            CITRASENSE_LOGGER.warning("Unknown sextractor_filter_name (%r). Falling back to 'default'.", v)
            return "default"
        return v

    @field_validator("observing_session_sun_altitude_threshold", mode="before")
    @classmethod
    def _validate_sun_altitude_threshold(cls, v: Any) -> float:
        valid = (-6.0, -12.0, -18.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            CITRASENSE_LOGGER.warning(
                "Invalid observing_session_sun_altitude_threshold (%r). Falling back to -12.0.", v
            )
            return -12.0
        if v not in valid:
            CITRASENSE_LOGGER.warning(
                "observing_session_sun_altitude_threshold (%s) not in %s. Falling back to -12.0.", v, valid
            )
            return -12.0
        return v

    @field_validator("custom_data_dir", "custom_log_dir", mode="before")
    @classmethod
    def _validate_custom_dir(cls, v: Any) -> str:
        if not v:
            return ""
        v = str(v)
        p = Path(v).expanduser().resolve()
        if not p.is_absolute():
            CITRASENSE_LOGGER.warning("custom dir path %r is not absolute. Ignoring.", v)
            return ""
        return str(p)

    # ── Cross-field validators ────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_adaptive_exposure_range(self) -> CitraSenseSettings:
        if self.adaptive_exposure_min_seconds > self.adaptive_exposure_max_seconds:
            CITRASENSE_LOGGER.warning(
                "adaptive_exposure_min_seconds (%.3f) > adaptive_exposure_max_seconds (%.3f). Clamping min to max.",
                self.adaptive_exposure_min_seconds,
                self.adaptive_exposure_max_seconds,
            )
            self.adaptive_exposure_min_seconds = self.adaptive_exposure_max_seconds
        return self

    # ── Deprecated scalar access (delegates to sensors[0]) ───────────

    @property
    def hardware_adapter(self) -> str:
        """Legacy compat: adapter key of the first sensor."""
        return self.sensors[0].adapter if self.sensors else ""

    @property
    def telescope_id(self) -> str:
        """Legacy compat: Citra sensor ID of the first sensor."""
        return self.sensors[0].citra_sensor_id if self.sensors else ""

    @property
    def adapter_settings(self) -> dict[str, Any]:
        """Legacy compat: adapter settings of the first sensor."""
        return self.sensors[0].adapter_settings if self.sensors else {}

    @adapter_settings.setter
    def adapter_settings(self, value: dict[str, Any]) -> None:
        if self.sensors:
            self.sensors[0].adapter_settings = value

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def load(cls, web_port: int = DEFAULT_WEB_PORT) -> CitraSenseSettings:
        """Load settings from the JSON config file on disk.

        Handles transparent migration from v1/v2 config files:

        * **v1** (scalars only): ``hardware_adapter``, ``telescope_id``, and a
          top-level ``adapter_settings`` dict keyed by adapter name are
          converted into a single ``sensors[0]`` entry.
        * **v2** (dual-write): ``sensors[]`` exists alongside scalars. The
          scalars are stripped; any ``adapter_settings`` archive entries are
          injected into the matching sensor if its own blob is empty.

        Args:
            web_port: Port for web interface (CLI bootstrap option only).
        """
        mgr = SettingsFileManager()
        config = mgr.load_config()

        # Pop the legacy nested adapter_settings archive (keyed by adapter name).
        all_adapter_settings: dict[str, dict[str, Any]] = config.pop("adapter_settings", {})
        config["web_port"] = web_port

        # Migrate legacy keep_processing_output bool → processing_output_retention_hours
        if "keep_processing_output" in config and "processing_output_retention_hours" not in config:
            old_val = config.pop("keep_processing_output")
            config["processing_output_retention_hours"] = -1 if old_val else 0
        else:
            config.pop("keep_processing_output", None)

        # ── v1/v2 → v3 migration ──────────────────────────────────────
        hw_adapter = config.pop("hardware_adapter", "")
        telescope_id = config.pop("telescope_id", "")

        sensors_raw: list[dict[str, Any]] | None = config.get("sensors")

        if not sensors_raw and hw_adapter:
            # v1: no sensors list — synthesize from legacy scalars.
            config["sensors"] = [
                {
                    "id": DEFAULT_TELESCOPE_SENSOR_ID,
                    "type": "telescope",
                    "adapter": hw_adapter,
                    "adapter_settings": all_adapter_settings.get(hw_adapter, {}),
                    "citra_sensor_id": telescope_id,
                }
            ]
        elif sensors_raw:
            # v2: sensors exist.  Inject adapter_settings from the archive
            # if the sensor's own blob is empty.
            for sd in sensors_raw:
                adapter = sd.get("adapter", "")
                if not sd.get("adapter_settings") and adapter and adapter in all_adapter_settings:
                    sd["adapter_settings"] = all_adapter_settings[adapter]

        instance = cls.model_validate(config)
        instance._config_manager = mgr
        instance._dir_manager = DirectoryManager(instance.custom_data_dir, instance.custom_log_dir)
        return instance

    # ── Public helpers ────────────────────────────────────────────────

    @property
    def config_manager(self) -> SettingsFileManager:
        """Access the underlying file manager (for path queries, etc.)."""
        return self._config_manager

    @property
    def directories(self) -> DirectoryManager:
        """Centralized directory paths (data, images, processing, logs)."""
        return self._dir_manager

    def is_configured(self) -> bool:
        """Check if minimum required configuration is present."""
        if not self.personal_access_token or not self.sensors:
            return False
        head = self.sensors[0]
        return bool(head.citra_sensor_id and head.adapter)

    def get_sensor_config(self, sensor_id: str) -> SensorConfig | None:
        """Look up a sensor config by its local id."""
        for s in self.sensors:
            if s.id == sensor_id:
                return s
        return None

    # ── Serialization & persistence ───────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary for serialization.

        Returns:
            Dictionary of all persisted settings (excludes runtime-only
            ``web_port``).  ``sensors[]`` is the canonical sensor config.
        """
        d = self.model_dump()
        d["config_version"] = CONFIG_VERSION
        return d

    def save(self) -> None:
        """Save current settings to JSON config file."""
        self._config_manager.save_config(self.to_dict())
        CITRASENSE_LOGGER.info("Configuration saved to %s", self._config_manager.get_config_path())

    def update_and_save(self, config: dict[str, Any]) -> None:
        """Update settings from dict and save.

        Merges the incoming *config* on top of the current ``to_dict()`` so
        that fields not present in the incoming payload are preserved (e.g.
        backend-only settings that the web UI never sends).

        Per-sensor ``adapter_settings`` are shallow-merged so partial saves
        from the web form don't wipe keys like ``"filters"`` that the form
        never sends.

        Args:
            config: Configuration dict.  May contain ``sensors[]`` with
                per-sensor config including ``adapter_settings``.
        """
        config.pop("web_port", None)
        # Strip legacy scalars that old clients may still send.
        config.pop("hardware_adapter", None)
        config.pop("telescope_id", None)

        # Smart-merge per-sensor adapter_settings.
        incoming_sensors: list[dict[str, Any]] | None = config.get("sensors")
        if incoming_sensors and self.sensors:
            existing_by_id = {s.id: s for s in self.sensors}
            for sd in incoming_sensors:
                existing = existing_by_id.get(sd.get("id", ""))
                if existing:
                    merged_as = {**existing.adapter_settings, **sd.get("adapter_settings", {})}
                    sd["adapter_settings"] = merged_as

        # Handle legacy top-level adapter_settings from old web clients.
        old_as: dict | None = config.pop("adapter_settings", None)
        if old_as and isinstance(old_as, dict) and self.sensors:
            head = self.sensors[0]
            head.adapter_settings = {**head.adapter_settings, **old_as}
            if incoming_sensors:
                for sd in incoming_sensors:
                    if sd.get("id") == head.id:
                        sd["adapter_settings"] = head.adapter_settings
                        break

        merged = self.to_dict()
        merged.update(config)

        allowed_keys = {k for k, v in type(self).model_fields.items() if not v.exclude}
        merged = {k: v for k, v in merged.items() if k in allowed_keys}
        merged["config_version"] = CONFIG_VERSION

        self._config_manager.save_config(merged)
