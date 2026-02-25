"""Cable wrap safety check — monitors cumulative azimuth rotation in alt-az mode.

Tracks azimuth deltas via shortest-arc math, enforces two-tier limits,
and performs defensive directional unwinding when limits are reached.
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

SOFT_LIMIT_DEG = 180.0
HARD_LIMIT_DEG = 270.0
_SLEW_BLOCK_MARGIN_DEG = 10.0

_UNWIND_POLL_INTERVAL_S = 0.5
_STALL_THRESHOLD_DEG = 1.0
_STALL_READINGS = 3
_TRAVEL_BUDGET_DEG = 360.0
_CONVERGENCE_DEG = 5.0
_UNWIND_RATE = 7


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

        self._cumulative_deg: float = 0.0
        self._last_az: float | None = None
        self._unwinding: bool = False
        self._lock = threading.Lock()

        self._load_state()

    # ------------------------------------------------------------------
    # SafetyCheck interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "cable_wrap"

    def check(self) -> SafetyAction:
        with self._lock:
            if self._unwinding:
                return SafetyAction.QUEUE_STOP

            if self._mount.get_mount_mode() != "altaz":
                return SafetyAction.SAFE

            az = self._mount.get_azimuth()
            if az is None:
                return SafetyAction.SAFE

            if self._last_az is not None:
                delta = _shortest_arc(self._last_az, az)
                self._cumulative_deg += delta
            self._last_az = az

            self._save_state()

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
            if action_type == "slew":
                abs_cumulative = abs(self._cumulative_deg)
                if abs_cumulative >= SOFT_LIMIT_DEG:
                    return False
                # Block slews that could plausibly push cumulative past the
                # soft limit during transit.  We don't know the exact target
                # azimuth here, but any slew can add up to ~180° of wrap.
                # Block when remaining headroom is less than the margin.
                headroom = SOFT_LIMIT_DEG - abs_cumulative
                if headroom < _SLEW_BLOCK_MARGIN_DEG:
                    self._logger.warning(
                        "Slew blocked: only %.0f° headroom before soft limit " "(need %.0f° margin)",
                        headroom,
                        _SLEW_BLOCK_MARGIN_DEG,
                    )
                    return False
            return True

    def execute_action(self) -> None:
        """Perform a defensive directional unwind."""
        with self._lock:
            if self._unwinding:
                return
            self._unwinding = True
        try:
            self._do_unwind()
        finally:
            with self._lock:
                self._unwinding = False

    def reset(self) -> None:
        with self._lock:
            self._cumulative_deg = 0.0
            self._last_az = None
            self._save_state()

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

        try:
            while True:
                time.sleep(_UNWIND_POLL_INTERVAL_S)
                poll_count += 1

                az = self._mount.get_azimuth()
                if az is None:
                    self._logger.error("Lost azimuth reading during unwind — stopping")
                    break

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
                    break
        finally:
            self._mount.stop_move(direction)
            end_az = self._mount.get_azimuth()
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
