"""Observing session state machine for autonomous night operations.

Tracks sun altitude to determine when it is dark enough to observe, and
orchestrates startup actions (unpark, autofocus) and shutdown actions (drain
queues, park) based on configurable ``do_*`` switches.

The ``update()`` method is called from the ``TaskManager.poll_tasks`` loop
every 15 seconds.  It recomputes the session state and triggers actions
as needed — no additional threads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

from citrascope.location.twilight import ObservingWindow, compute_observing_window

if TYPE_CHECKING:
    from citrascope.settings.citrascope_settings import CitraScopeSettings


class SessionState(Enum):
    DAYTIME = "daytime"
    NIGHT_STARTUP = "night_startup"
    OBSERVING = "observing"
    NIGHT_SHUTDOWN = "night_shutdown"


class ObservingSessionManager:
    """State machine that drives autonomous night operations.

    State transitions::

        DAYTIME → NIGHT_STARTUP    when self_tasking_enabled and sun below threshold
        NIGHT_STARTUP → OBSERVING  when all enabled startup actions complete
        OBSERVING → NIGHT_SHUTDOWN when sun rises above threshold
        NIGHT_SHUTDOWN → DAYTIME   when queues drained and mount parked (if enabled)

    The manager does not own any threads — it is driven by external calls to
    ``update()`` on the poll loop's cadence.
    """

    def __init__(
        self,
        settings: CitraScopeSettings,
        logger: logging.Logger,
        get_location: Callable[[], tuple[float, float] | None],
        request_autofocus: Callable[[], Any],
        is_autofocus_running: Callable[[], bool],
        are_queues_idle: Callable[[], bool],
        park_mount: Callable[[], bool] | None,
        unpark_mount: Callable[[], bool] | None,
    ):
        self._settings = settings
        self._logger = logger
        self._get_location = get_location
        self._request_autofocus = request_autofocus
        self._is_autofocus_running = is_autofocus_running
        self._are_queues_idle = are_queues_idle
        self._park_mount = park_mount
        self._unpark_mount = unpark_mount

        self._state = SessionState.DAYTIME
        self._observing_window: ObservingWindow | None = None

        # Track which startup actions have been initiated/completed
        self._unpark_done = False
        self._autofocus_requested = False
        self._park_done = False

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def observing_window(self) -> ObservingWindow | None:
        return self._observing_window

    def update(self) -> SessionState:
        """Recompute session state and trigger actions.  Call from poll loop."""
        if not self._settings.self_tasking_enabled:
            if self._state != SessionState.DAYTIME:
                self._logger.info("Self-tasking disabled — resetting to DAYTIME")
                self._reset_to_daytime()
            return self._state

        self._refresh_observing_window()
        is_dark = self._observing_window.is_dark if self._observing_window else False

        if self._state == SessionState.DAYTIME:
            if is_dark:
                self._logger.info(
                    "Sun below threshold (%.1f°) — transitioning to NIGHT_STARTUP",
                    self._observing_window.current_sun_altitude if self._observing_window else 0,
                )
                self._state = SessionState.NIGHT_STARTUP
                self._unpark_done = False
                self._autofocus_requested = False

        elif self._state == SessionState.NIGHT_STARTUP:
            self._run_startup_actions()

        elif self._state == SessionState.OBSERVING:
            if not is_dark:
                self._logger.info("Sun rising above threshold — transitioning to NIGHT_SHUTDOWN")
                self._state = SessionState.NIGHT_SHUTDOWN
                self._park_done = False

        elif self._state == SessionState.NIGHT_SHUTDOWN:
            self._run_shutdown_actions()

        return self._state

    def _refresh_observing_window(self) -> None:
        location = self._get_location()
        if location is None:
            self._observing_window = None
            return
        lat, lon = location
        threshold = self._settings.self_tasking_sun_altitude_threshold
        try:
            self._observing_window = compute_observing_window(lat, lon, threshold)
        except Exception:
            self._logger.warning("Failed to compute observing window", exc_info=True)
            self._observing_window = None

    def _run_startup_actions(self) -> None:
        """Execute enabled startup actions in order: unpark → autofocus → done."""
        # Step 1: Unpark
        if self._settings.self_tasking_do_park and not self._unpark_done:
            if self._unpark_mount is not None:
                self._logger.info("NIGHT_STARTUP: Unparking mount")
                try:
                    self._unpark_mount()
                except Exception:
                    self._logger.warning("Unpark failed", exc_info=True)
            self._unpark_done = True
            return

        # Step 2: Autofocus
        if self._settings.self_tasking_do_autofocus and not self._autofocus_requested:
            self._logger.info("NIGHT_STARTUP: Requesting autofocus")
            try:
                self._request_autofocus()
            except Exception:
                self._logger.warning("Autofocus request failed", exc_info=True)
            self._autofocus_requested = True
            return

        if self._settings.self_tasking_do_autofocus and self._is_autofocus_running():
            return  # Still waiting for autofocus to finish

        # All startup actions complete
        self._logger.info("NIGHT_STARTUP complete — transitioning to OBSERVING")
        self._state = SessionState.OBSERVING

    def _run_shutdown_actions(self) -> None:
        """Drain queues then park (if enabled)."""
        if not self._are_queues_idle():
            return  # Wait for work to finish

        if self._settings.self_tasking_do_park and not self._park_done:
            if self._park_mount is not None:
                self._logger.info("NIGHT_SHUTDOWN: Parking mount")
                try:
                    self._park_mount()
                except Exception:
                    self._logger.warning("Park failed", exc_info=True)
            self._park_done = True

        self._logger.info("NIGHT_SHUTDOWN complete — transitioning to DAYTIME")
        self._reset_to_daytime()

    def _reset_to_daytime(self) -> None:
        self._state = SessionState.DAYTIME
        self._unpark_done = False
        self._autofocus_requested = False
        self._park_done = False

    def status_dict(self) -> dict[str, Any]:
        """Build a dict for the web status broadcast."""
        window = self._observing_window
        return {
            "observing_session_state": self._state.value,
            "sun_altitude": window.current_sun_altitude if window else None,
            "dark_window_start": window.dark_start if window else None,
            "dark_window_end": window.dark_end if window else None,
        }
