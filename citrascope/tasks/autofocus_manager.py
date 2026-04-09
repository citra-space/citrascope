"""Autofocus management: scheduling, target resolution, and execution.

Also tracks ongoing focus health (FWHM history from the imaging pipeline)
to support at-a-glance monitoring and future adaptive autofocus (#203).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from citrascope.constants import AUTOFOCUS_TARGET_PRESETS
from citrascope.hardware.abstract_astro_hardware_adapter import AbstractAstroHardwareAdapter

if TYPE_CHECKING:
    from citrascope.location.location_service import LocationService
    from citrascope.settings.citrascope_settings import CitraScopeSettings
    from citrascope.tasks.base_work_queue import BaseWorkQueue


class AutofocusManager:
    """Manages autofocus requests, scheduling, and execution.

    Owns the autofocus request flag and lock, determines when scheduled
    autofocus should run, resolves the target star from settings, and
    executes the routine via the hardware adapter.
    """

    def __init__(
        self,
        logger: logging.Logger,
        hardware_adapter: AbstractAstroHardwareAdapter,
        settings: CitraScopeSettings,
        imaging_queue: BaseWorkQueue | None = None,
        location_service: LocationService | None = None,
    ):
        self.logger = logger
        self.hardware_adapter = hardware_adapter
        self.settings = settings
        self.imaging_queue = imaging_queue
        self.location_service = location_service
        self._requested = False
        self._running = False
        self._progress = ""
        self._points: list[tuple[int, float]] = []
        self._fwhm_history: deque[tuple[float, int]] = deque(maxlen=50)
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()

    def request(self) -> bool:
        """Request autofocus to run at next safe point between tasks."""
        with self._lock:
            self._requested = True
            self.logger.info("Autofocus requested - will run between tasks")
            return True

    def cancel(self) -> bool:
        """Cancel autofocus whether it is queued or actively running.

        Returns:
            True if something was cancelled, False if nothing to cancel.
        """
        with self._lock:
            was_requested = self._requested
            is_running = self._running
            self._requested = False

        if is_running:
            self._cancel_event.set()
            self.logger.info("Autofocus cancellation requested (run in progress)")
            return True
        if was_requested:
            self.logger.info("Autofocus request cancelled")
            return True
        return False

    def is_requested(self) -> bool:
        """Check if autofocus is currently requested/queued."""
        with self._lock:
            return self._requested

    def is_running(self) -> bool:
        """Check if autofocus is currently executing."""
        with self._lock:
            return self._running

    @property
    def progress(self) -> str:
        """Current autofocus progress description (empty if not running)."""
        with self._lock:
            return self._progress

    def _set_progress(self, msg: str) -> None:
        with self._lock:
            self._progress = msg

    def _add_point(self, position: int, hfr: float) -> None:
        """Record a V-curve sample (thread-safe)."""
        with self._lock:
            self._points.append((position, hfr))

    @property
    def points(self) -> list[tuple[int, float]]:
        """Copy of the current autofocus V-curve points."""
        with self._lock:
            return list(self._points)

    def record_fwhm(self, value: float) -> None:
        """Record a FWHM measurement from the imaging pipeline (thread-safe)."""
        with self._lock:
            self._fwhm_history.append((value, int(time.time())))

    @property
    def fwhm_history(self) -> list[tuple[float, int]]:
        """Copy of the rolling FWHM history as (fwhm, unix_ts) tuples."""
        with self._lock:
            return list(self._fwhm_history)

    def check_and_execute(self) -> bool:
        """Check if autofocus should run (manual or scheduled) and execute if so.

        Call this between tasks in the runner loop. Returns True if autofocus ran.
        Waits for the imaging queue to drain before starting so we don't slew
        mid-exposure.
        """
        with self._lock:
            should_run = self._requested
            if should_run:
                self._requested = False
            elif self._should_run_scheduled():
                should_run = True
                self._requested = False

        if not should_run:
            return False

        if self.imaging_queue and not self.imaging_queue.is_idle():
            self.logger.info("Autofocus deferred - waiting for imaging queue to drain")
            with self._lock:
                self._requested = True
            return False

        self._execute()
        return True

    def _should_run_scheduled(self) -> bool:
        """Check if scheduled autofocus should run based on settings."""
        if not self.settings:
            return False

        if not self.settings.scheduled_autofocus_enabled:
            return False

        if not self.hardware_adapter.supports_autofocus():
            return False

        mode = self.settings.autofocus_schedule_mode
        if mode == "after_sunset":
            return self._should_run_after_sunset()
        return self._should_run_interval()

    def _should_run_interval(self) -> bool:
        """Interval mode: trigger when elapsed time exceeds the configured interval."""
        interval_minutes = self.settings.autofocus_interval_minutes
        last_timestamp = self.settings.last_autofocus_timestamp

        if last_timestamp is None:
            return True

        elapsed_minutes = (int(time.time()) - last_timestamp) / 60
        return elapsed_minutes >= interval_minutes

    def _should_run_after_sunset(self) -> bool:
        """After-sunset mode: trigger once per night at sunset + offset."""
        location = self._get_location()
        if location is None:
            return False

        lat, lon = location
        trigger_time = self._compute_sunset_trigger_time(lat, lon)
        if trigger_time is None:
            return False

        now_utc = datetime.now(timezone.utc)
        if now_utc < trigger_time:
            return False

        last_ts = self.settings.last_autofocus_timestamp
        if last_ts is None:
            return True

        last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        return last_dt < trigger_time

    def _get_location(self) -> tuple[float, float] | None:
        """Get observatory lat/lon from location service, or None if unavailable."""
        if self.location_service is None:
            return None
        loc = self.location_service.get_current_location()
        if loc and loc.get("latitude") is not None and loc.get("longitude") is not None:
            return loc["latitude"], loc["longitude"]
        return None

    def _compute_sunset_trigger_time(self, latitude: float, longitude: float) -> datetime | None:
        """Return sunset + offset as a UTC datetime, or None on failure."""
        try:
            from citrascope.location.twilight import compute_sunset_utc

            sunset = compute_sunset_utc(latitude, longitude)
            if sunset is None:
                self.logger.warning("Could not compute sunset for after-sunset autofocus (polar day?)")
                return None
            offset = self.settings.autofocus_after_sunset_offset_minutes
            return sunset + timedelta(minutes=offset)
        except Exception as e:
            self.logger.warning(f"Failed to compute sunset time: {e}")
            return None

    def get_next_autofocus_minutes(self) -> int | None:
        """Compute minutes until next scheduled autofocus, or None if not scheduled.

        Used by the web status endpoint to display countdown.
        """
        if not self.settings or not self.settings.scheduled_autofocus_enabled:
            return None
        if not self.hardware_adapter.supports_autofocus():
            return None

        mode = self.settings.autofocus_schedule_mode
        if mode == "after_sunset":
            return self._next_minutes_after_sunset()
        return self._next_minutes_interval()

    def _next_minutes_interval(self) -> int:
        last_ts = self.settings.last_autofocus_timestamp
        interval = self.settings.autofocus_interval_minutes
        if last_ts is None:
            return 0
        elapsed = (int(time.time()) - last_ts) / 60
        return max(0, int(interval - elapsed))

    def _next_minutes_after_sunset(self) -> int | None:
        location = self._get_location()
        if location is None:
            return None
        lat, lon = location
        trigger_time = self._compute_sunset_trigger_time(lat, lon)
        if trigger_time is None:
            return None
        now_utc = datetime.now(timezone.utc)
        if now_utc >= trigger_time:
            last_ts = self.settings.last_autofocus_timestamp
            if last_ts is not None:
                last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
                if last_dt >= trigger_time:
                    return None
            return 0
        remaining = (trigger_time - now_utc).total_seconds() / 60
        return max(0, int(remaining))

    def _resolve_target(self) -> tuple[float | None, float | None]:
        """Resolve autofocus target RA/Dec from settings (preset or custom)."""
        settings = self.settings
        if not settings:
            return None, None

        preset_key = settings.autofocus_target_preset or "mirach"

        if preset_key == "current":
            self.logger.info("Autofocus target: current position (no slew)")
            return None, None

        if preset_key == "custom":
            ra = settings.autofocus_target_custom_ra
            dec = settings.autofocus_target_custom_dec
            if ra is not None and dec is not None:
                self.logger.info(f"Autofocus target: custom (RA={ra:.4f}, Dec={dec:.4f})")
                return ra, dec
            self.logger.warning("Custom autofocus target missing RA/Dec, falling back to Mirach")
            preset_key = "mirach"

        preset = AUTOFOCUS_TARGET_PRESETS.get(preset_key)
        if not preset:
            self.logger.warning(f"Unknown autofocus preset '{preset_key}', falling back to Mirach")
            preset = AUTOFOCUS_TARGET_PRESETS["mirach"]

        self.logger.info(f"Autofocus target: {preset['name']} ({preset['designation']})")
        return preset["ra"], preset["dec"]

    def _execute(self) -> None:
        """Execute autofocus routine and update timestamp on both success and failure."""
        self._cancel_event.clear()
        with self._lock:
            self._running = True
            self._progress = "Starting..."
            self._points.clear()
        try:
            target_ra, target_dec = self._resolve_target()
            self.logger.info("Starting autofocus routine...")
            self.hardware_adapter.do_autofocus(
                target_ra=target_ra,
                target_dec=target_dec,
                on_progress=self._set_progress,
                cancel_event=self._cancel_event,
                on_point=self._add_point,
            )

            if self.hardware_adapter.supports_filter_management():
                try:
                    filter_config = self.hardware_adapter.get_filter_config()
                    if filter_config and self.settings:
                        self.settings.adapter_settings["filters"] = filter_config
                        self.logger.info(f"Saved filter configuration with {len(filter_config)} filters")
                except Exception as e:
                    self.logger.warning(f"Failed to save filter configuration after autofocus: {e}")

            self.logger.info("Autofocus routine completed successfully")
        except Exception as e:
            self.logger.error(f"Autofocus failed: {e!s}", exc_info=True)
        finally:
            with self._lock:
                self._running = False
                self._progress = ""
            if self.settings:
                self.settings.last_autofocus_timestamp = int(time.time())
                self.settings.save()
