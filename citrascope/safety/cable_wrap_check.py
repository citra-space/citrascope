"""Cable wrap safety check — monitors cumulative azimuth rotation in alt-az mode.

Tracks azimuth deltas via shortest-arc math, enforces two-tier limits,
and performs defensive directional unwinding when limits are reached.

Observation runs on a dedicated thread so that ``check()`` is a pure
read with no side effects — safe to call from any number of callers
without double-counting azimuth deltas.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from citrascope.safety.safety_monitor import SafetyAction, SafetyCheck

if TYPE_CHECKING:
    from citrascope.hardware.devices.mount.abstract_mount import AbstractMount

SOFT_LIMIT_DEG = 240.0
HARD_LIMIT_DEG = 270.0

_OBSERVE_INTERVAL_S = 0.5
_UNWIND_POLL_INTERVAL_S = 0.5
_STALL_THRESHOLD_DEG = 1.0
_STALL_READINGS = 3
_TRAVEL_BUDGET_DEG = 360.0
_CONVERGENCE_DEG = 5.0
_UNWIND_RATE = 7
_UNWIND_TIMEOUT_S = 300.0
_SAVE_INTERVAL_S = 10.0


def _shortest_arc(from_deg: float, to_deg: float) -> float:
    """Signed shortest-arc delta on a 360-degree circle.

    Positive = clockwise (increasing azimuth), negative = counter-clockwise.
    Result is always in (-180, 180].
    """
    diff = (to_deg - from_deg) % 360.0
    if diff > 180.0:
        diff -= 360.0
    return diff


class CableWrapCheck(SafetyCheck):
    """Monitors cumulative azimuth rotation and unwinds when limits are hit.

    Observation (reading azimuth, accumulating deltas, persisting state) runs
    on its own thread at ~2 Hz via ``start()`` / ``stop()``.  ``check()`` is a
    pure read that compares the accumulated value against limits — no I/O, no
    side effects.

    Designed to work with any mount that implements the optional
    ``get_azimuth()``, ``start_move()``, and ``stop_move()`` methods.
    Mounts that don't support these are silently excluded (always SAFE).
    """

    def __init__(
        self,
        logger: logging.Logger,
        mount: AbstractMount,
        state_file: Path | None = None,
    ) -> None:
        self._logger = logger
        self._mount = mount
        self._state_file = state_file
        self._is_altaz: bool = mount.get_mount_mode() == "altaz"

        self._cumulative_deg: float = 0.0
        self._last_az: float | None = None
        self._unwinding: bool = False
        self._unwind_thread: threading.Thread | None = None
        self._az_healthy: bool = True
        self._lock = threading.Lock()
        self._last_save_time: float = 0.0

        self._observe_thread: threading.Thread | None = None
        self._observe_stop = threading.Event()

        self._load_state()

    # ------------------------------------------------------------------
    # Observation thread
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background observation thread."""
        if self._observe_thread is not None and self._observe_thread.is_alive():
            return
        self._observe_stop.clear()
        self._observe_thread = threading.Thread(target=self._observe_loop, daemon=True, name="cable-wrap-observer")
        self._observe_thread.start()
        self._logger.info("Cable wrap observer started (interval=%.1fs)", _OBSERVE_INTERVAL_S)

    def stop(self) -> None:
        """Stop the background observation thread."""
        if self._observe_thread is None:
            return
        self._observe_stop.set()
        self._observe_thread.join(timeout=_OBSERVE_INTERVAL_S + 2)
        self._observe_thread = None
        self._logger.info("Cable wrap observer stopped")

    def _observe_loop(self) -> None:
        while not self._observe_stop.is_set():
            try:
                self._observe_once()
            except Exception:
                self._logger.error("Cable wrap observation failed", exc_info=True)
            self._observe_stop.wait(_OBSERVE_INTERVAL_S)

    def _observe_once(self) -> None:
        """Single observation cycle: read azimuth, accumulate delta, persist.

        Called by the observation thread, or directly by tests.  During an
        active unwind the observation thread yields — the unwind loop takes
        over accumulation at its own cadence.

        When the mount has a state cache the azimuth is read from its
        cached snapshot (zero serial I/O).  If no cache is attached,
        the reading is treated as lost (az = None).
        """
        if not self._is_altaz:
            return

        try:
            cached = self._mount.cached_state
            az = cached.az_deg if cached is not None else None
        except Exception:
            self._logger.debug("Failed to read azimuth", exc_info=True)
            az = None

        with self._lock:
            if self._unwinding:
                return

            if az is None:
                self._az_healthy = False
                return

            self._az_healthy = True

            if self._last_az is not None:
                delta = _shortest_arc(self._last_az, az)
                self._cumulative_deg += delta
            self._last_az = az

            abs_cumulative = abs(self._cumulative_deg)
            now = time.monotonic()
            if now - self._last_save_time >= _SAVE_INTERVAL_S or abs_cumulative >= SOFT_LIMIT_DEG:
                self._save_state()
                self._last_save_time = now

    # ------------------------------------------------------------------
    # SafetyCheck interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "cable_wrap"

    def check(self) -> SafetyAction:
        """Pure evaluation — no I/O, no side effects."""
        with self._lock:
            if self._unwinding:
                return SafetyAction.QUEUE_STOP

            if not self._is_altaz:
                return SafetyAction.SAFE

            if not self._az_healthy:
                return SafetyAction.WARN

            abs_cumulative = abs(self._cumulative_deg)
            if abs_cumulative >= HARD_LIMIT_DEG:
                self._logger.critical(
                    "Cable wrap HARD LIMIT: %.1f° cumulative (limit %.1f°)",
                    self._cumulative_deg,
                    HARD_LIMIT_DEG,
                )
                return SafetyAction.EMERGENCY
            if abs_cumulative >= SOFT_LIMIT_DEG:
                self._logger.warning(
                    "Cable wrap soft limit: %.1f° cumulative (limit %.1f°)",
                    self._cumulative_deg,
                    SOFT_LIMIT_DEG,
                )
                return SafetyAction.QUEUE_STOP
            return SafetyAction.SAFE

    def check_proposed_action(self, action_type: str, **kwargs) -> bool:
        with self._lock:
            if self._unwinding:
                return False
            if action_type in ("slew", "home"):
                if abs(self._cumulative_deg) >= SOFT_LIMIT_DEG:
                    return False
            return True

    def execute_action(self) -> None:
        """Perform a defensive directional unwind."""
        with self._lock:
            if self._unwinding:
                return
            self._unwinding = True
            self._unwind_thread = threading.current_thread()
        try:
            self._do_unwind()
        finally:
            with self._lock:
                self._unwinding = False
                self._unwind_thread = None

    def join_unwind(self, timeout: float = 10.0) -> None:
        """Block until any in-progress unwind completes (for clean shutdown)."""
        with self._lock:
            thread = self._unwind_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def reset(self) -> None:
        with self._lock:
            self._cumulative_deg = 0.0
            self._last_az = None
            self._save_state()

    @property
    def is_unwinding(self) -> bool:
        with self._lock:
            return self._unwinding

    def get_status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "cumulative_deg": round(self._cumulative_deg, 1),
                "soft_limit": SOFT_LIMIT_DEG,
                "hard_limit": HARD_LIMIT_DEG,
                "unwinding": self._unwinding,
            }

    # ------------------------------------------------------------------
    # Directional unwind
    # ------------------------------------------------------------------

    def _get_mount_radec(self) -> str:
        """Best-effort RA/Dec string for logging — never raises."""
        try:
            ra, dec = self._mount.get_radec()
            return f"{ra:.2f}/{dec:.2f}"
        except Exception:
            return "n/a"

    def _do_unwind(self) -> None:
        start_az = self._mount.get_azimuth()
        ra_dec = self._get_mount_radec()
        self._logger.warning(
            "Starting cable unwind from %.1f° cumulative | az=%.1f° | ra/dec=%s | direction=%s",
            self._cumulative_deg,
            start_az or 0.0,
            ra_dec,
            "west" if self._cumulative_deg > 0 else "east",
        )

        self._mount.stop_tracking()

        direction = "west" if self._cumulative_deg > 0 else "east"
        if not self._mount.start_move(direction, rate=_UNWIND_RATE):
            self._logger.error("Mount does not support directional motion — cannot unwind")
            return

        recent_readings: list[float] = []
        travel = 0.0
        poll_count = 0
        converged = False
        deadline = time.monotonic() + _UNWIND_TIMEOUT_S

        try:
            while True:
                time.sleep(_UNWIND_POLL_INTERVAL_S)
                poll_count += 1

                if time.monotonic() > deadline:
                    self._logger.error(
                        "Unwind wall-clock timeout (%.0fs) — stopping",
                        _UNWIND_TIMEOUT_S,
                    )
                    break

                az = self._mount.get_azimuth()
                if az is None:
                    self._logger.error("Lost azimuth reading during unwind — stopping")
                    break

                with self._lock:
                    if self._last_az is not None:
                        delta = _shortest_arc(self._last_az, az)
                        self._cumulative_deg += delta
                        travel += abs(delta)
                    self._last_az = az

                self._logger.info(
                    "Unwind poll #%d: az=%.1f° cumulative=%.1f° travel=%.1f° | ra/dec=%s",
                    poll_count,
                    az,
                    self._cumulative_deg,
                    travel,
                    self._get_mount_radec(),
                )

                # Stall detection — use wrapped pairwise deltas so readings
                # near the 0/360 boundary (e.g. [359.5, 0.0, 0.5]) don't
                # produce a false 359° span.
                recent_readings.append(az)
                if len(recent_readings) > _STALL_READINGS:
                    recent_readings.pop(0)
                if len(recent_readings) == _STALL_READINGS:
                    max_step = max(
                        abs(_shortest_arc(recent_readings[i], recent_readings[i + 1]))
                        for i in range(len(recent_readings) - 1)
                    )
                    if max_step < _STALL_THRESHOLD_DEG:
                        self._logger.error(
                            "Unwind stall detected (max step %.1f° over %d readings) "
                            "— possible cable binding or obstruction",
                            max_step,
                            _STALL_READINGS,
                        )
                        break

                # Travel budget
                if travel > _TRAVEL_BUDGET_DEG:
                    self._logger.error(
                        "Unwind travel budget exceeded (%.1f° > %.1f°) — stopping",
                        travel,
                        _TRAVEL_BUDGET_DEG,
                    )
                    break

                # Convergence
                if abs(self._cumulative_deg) < _CONVERGENCE_DEG:
                    self._logger.info("Cable unwind converged at %.1f° cumulative", self._cumulative_deg)
                    converged = True
                    break
        finally:
            self._mount.stop_move(direction)
            end_az = self._mount.get_azimuth()
            if converged:
                self._logger.info(
                    "Cable unwind complete: %d polls, %.1f° traveled, "
                    "az %.1f° → %.1f° | final ra/dec=%s | resetting cumulative to 0",
                    poll_count,
                    travel,
                    start_az or 0.0,
                    end_az or 0.0,
                    self._get_mount_radec(),
                )
                self.reset()
            else:
                self._logger.error(
                    "Unwind did NOT converge: %d polls, %.1f° traveled, "
                    "az %.1f° → %.1f° | %.1f° cumulative remaining | "
                    "operator must verify cable state before resuming",
                    poll_count,
                    travel,
                    start_az or 0.0,
                    end_az or 0.0,
                    self._cumulative_deg,
                )
                self._save_state()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        if self._state_file is None:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"cumulative_deg": self._cumulative_deg}),
                encoding="utf-8",
            )
        except Exception:
            self._logger.debug("Failed to persist cable wrap state", exc_info=True)

    def _load_state(self) -> None:
        if self._state_file is None:
            return
        if not self._state_file.exists():
            self._logger.warning(
                "Cable wrap state file not found (%s) — " "operator should verify cables are unwound",
                self._state_file,
            )
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._cumulative_deg = float(data.get("cumulative_deg", 0.0))
            self._logger.info("Loaded cable wrap state: %.1f° cumulative", self._cumulative_deg)
        except Exception:
            self._logger.warning("Failed to load cable wrap state", exc_info=True)
