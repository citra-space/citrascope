"""Tests for TaskDispatcher: routing, facade, runtime registration, queue
management, and safety evaluation."""

from __future__ import annotations

import heapq
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from dateutil import parser as dtparser

from citrasense.safety.safety_monitor import SafetyAction
from citrasense.tasks.task import Task
from citrasense.tasks.task_dispatcher import TaskDispatcher

# ── helpers ────────────────────────────────────────────────────────────────


def _mock_settings():
    s = MagicMock()
    s.task_processing_paused = False
    return s


def _make_dispatcher(**overrides) -> TaskDispatcher:
    defaults = {
        "api_client": MagicMock(),
        "logger": MagicMock(),
        "settings": _mock_settings(),
    }
    defaults.update(overrides)
    return TaskDispatcher(**defaults)


def _mock_runtime(sensor_id: str = "scope-0", sensor_type: str = "telescope"):
    rt = MagicMock()
    rt.sensor_id = sensor_id
    rt.sensor_type = sensor_type
    rt.acquisition_queue = MagicMock()
    rt.acquisition_queue.is_idle.return_value = True
    rt.processing_queue = MagicMock()
    rt.upload_queue = MagicMock()
    rt.autofocus_manager = MagicMock()
    rt.alignment_manager = MagicMock()
    rt.homing_manager = MagicMock()
    rt.calibration_manager = None
    rt.are_queues_idle.return_value = True
    return rt


def _mock_task(sensor_type="telescope", sensor_id=None):
    task = MagicMock()
    task.sensor_type = sensor_type
    task.sensor_id = sensor_id
    task.id = "task-001"
    return task


# ── Runtime registration ──────────────────────────────────────────────────


class TestRuntimeRegistration:
    def test_register_runtime_sets_dispatcher(self):
        td = _make_dispatcher()
        rt = _mock_runtime()
        td.register_runtime(rt)

        rt.set_dispatcher.assert_called_once_with(td)
        assert td._runtimes["scope-0"] is rt

    def test_default_runtime_returns_first(self):
        td = _make_dispatcher()
        rt = _mock_runtime()
        td.register_runtime(rt)

        assert td._default_runtime is rt

    def test_multiple_runtimes(self):
        td = _make_dispatcher()
        rt1 = _mock_runtime("scope-0", "telescope")
        rt2 = _mock_runtime("radar-0", "passive_radar")
        td.register_runtime(rt1)
        td.register_runtime(rt2)

        assert len(td._runtimes) == 2


# ── Task routing ──────────────────────────────────────────────────────────


class TestTaskRouting:
    def test_routes_by_sensor_id(self):
        td = _make_dispatcher()
        rt1 = _mock_runtime("scope-0", "telescope")
        rt2 = _mock_runtime("radar-0", "passive_radar")
        td.register_runtime(rt1)
        td.register_runtime(rt2)

        task = _mock_task(sensor_type="passive_radar", sensor_id="radar-0")
        assert td._runtime_for_task(task) is rt2

    def test_routes_by_sensor_type_fallback(self):
        td = _make_dispatcher()
        rt1 = _mock_runtime("scope-0", "telescope")
        rt2 = _mock_runtime("radar-0", "passive_radar")
        td.register_runtime(rt1)
        td.register_runtime(rt2)

        task = _mock_task(sensor_type="passive_radar", sensor_id=None)
        assert td._runtime_for_task(task) is rt2

    def test_falls_back_to_default(self):
        td = _make_dispatcher()
        rt = _mock_runtime("scope-0", "telescope")
        td.register_runtime(rt)

        task = _mock_task(sensor_type="unknown", sensor_id=None)
        assert td._runtime_for_task(task) is rt

    def test_rejects_task_with_no_runtimes(self):
        td = _make_dispatcher()
        task = _mock_task()
        assert td._runtime_for_task(task) is None


# ── Stage tracking ────────────────────────────────────────────────────────


class TestStageTracking:
    def test_update_task_stage_imaging(self):
        td = _make_dispatcher()
        td.update_task_stage("t1", "imaging")
        assert "t1" in td.imaging_tasks

    def test_update_task_stage_moves_between_stages(self):
        td = _make_dispatcher()
        td.update_task_stage("t1", "imaging")
        td.update_task_stage("t1", "processing")
        assert "t1" not in td.imaging_tasks
        assert "t1" in td.processing_tasks

    def test_remove_task_from_all_stages(self):
        td = _make_dispatcher()
        td.update_task_stage("t1", "uploading")
        td.task_dict["t1"] = MagicMock()
        td.remove_task_from_all_stages("t1")
        assert "t1" not in td.uploading_tasks
        assert "t1" not in td.task_dict


# ── Stats ─────────────────────────────────────────────────────────────────


class TestStats:
    def test_lifetime_counters(self):
        td = _make_dispatcher()
        td.record_task_started()
        td.record_task_started()
        td.record_task_succeeded()
        td.record_task_failed()
        stats = td.get_task_stats()
        assert stats == {"started": 2, "succeeded": 1, "failed": 1}


# ── Drop scheduled task ──────────────────────────────────────────────────


class TestDropScheduledTask:
    def test_drop_removes_from_heap(self):
        td = _make_dispatcher()
        task = MagicMock()
        heapq.heappush(td.task_heap, (1000, 2000, "t1", task))
        td.task_ids.add("t1")
        td.task_dict["t1"] = task

        assert td.drop_scheduled_task("t1") is True
        assert "t1" not in td.task_ids
        assert "t1" not in td.task_dict
        assert all(entry[2] != "t1" for entry in td.task_heap)

    def test_drop_unknown_returns_false(self):
        td = _make_dispatcher()
        assert td.drop_scheduled_task("nope") is False


# ── Lifecycle ─────────────────────────────────────────────────────────────


class TestLifecycle:
    def test_start_starts_runtimes(self):
        td = _make_dispatcher()
        rt = _mock_runtime()
        td.register_runtime(rt)

        td.start()

        rt.start.assert_called_once()

        td.stop()

        rt.stop.assert_called_once()


# ── Queue management (migrated from test_task_manager.py) ────────────────


def _create_test_task(task_id, status="Pending", start_offset_seconds=60):
    now = datetime.now(timezone.utc)
    start_time = now + timedelta(seconds=start_offset_seconds)
    stop_time = start_time + timedelta(seconds=300)
    return Task(
        id=task_id,
        type="observation",
        status=status,
        creationEpoch=now.isoformat(),
        updateEpoch=now.isoformat(),
        taskStart=start_time.isoformat(),
        taskStop=stop_time.isoformat(),
        userId="user-123",
        username="testuser",
        satelliteId="sat-456",
        satelliteName="Test Satellite",
        telescopeId="test-telescope-123",
        telescopeName="Test Telescope",
        groundStationId="test-gs-456",
        groundStationName="Test Ground Station",
    )


@pytest.fixture
def wired_dispatcher():
    """Create a TaskDispatcher with a registered runtime, for queue management tests."""
    api_client = MagicMock()
    api_client.get_telescope_tasks.return_value = []
    api_client.put_telescope_status.return_value = None
    settings = MagicMock()
    settings.keep_images = False
    settings.max_task_retries = 3
    settings.initial_retry_delay_seconds = 30
    settings.max_retry_delay_seconds = 300
    settings.task_processing_paused = False

    td = TaskDispatcher(
        api_client=api_client,
        logger=MagicMock(),
        settings=settings,
        telescope_record={"id": "test-telescope-123", "maxSlewRate": 5.0, "automatedScheduling": False},
    )

    runtime = MagicMock()
    runtime.sensor_id = "test-telescope-123"
    runtime.sensor_type = "telescope"
    runtime.acquisition_queue = MagicMock()
    runtime.acquisition_queue.is_idle.return_value = True
    runtime.processing_queue = MagicMock()
    runtime.upload_queue = MagicMock()
    runtime.are_queues_idle.return_value = True
    td._runtimes["test-telescope-123"] = runtime
    return td, api_client


def test_poll_tasks_adds_new_tasks(wired_dispatcher):
    td, api_client = wired_dispatcher
    task1 = _create_test_task("task-001", "Pending")
    task2 = _create_test_task("task-002", "Scheduled", start_offset_seconds=120)

    api_client.get_telescope_tasks.return_value = [task1.__dict__, task2.__dict__]

    with td.heap_lock:
        td._report_online()
        tasks = api_client.get_telescope_tasks(td.telescope_record["id"])
        api_task_map = {}
        for task_dict in tasks:
            task = Task.from_dict(task_dict)
            tid = task.id
            if tid and task.status in ["Pending", "Scheduled"]:
                api_task_map[tid] = task

        now = int(time.time())
        for tid, task in api_task_map.items():
            if tid not in td.task_ids and tid != td.current_task_id:
                start_epoch = int(dtparser.isoparse(task.taskStart).timestamp())
                stop_epoch = int(dtparser.isoparse(task.taskStop).timestamp()) if task.taskStop else 0
                if not (stop_epoch and stop_epoch < now):
                    heapq.heappush(td.task_heap, (start_epoch, stop_epoch, tid, task))
                    td.task_ids.add(tid)
                    td.task_dict[tid] = task

    assert len(td.task_heap) == 2
    assert "task-001" in td.task_ids
    assert "task-002" in td.task_ids


def test_poll_tasks_removes_cancelled_tasks(wired_dispatcher):
    td, api_client = wired_dispatcher
    task1 = _create_test_task("task-001", "Pending")
    task2 = _create_test_task("task-002", "Pending", start_offset_seconds=120)

    start1 = int(dtparser.isoparse(task1.taskStart).timestamp())
    stop1 = int(dtparser.isoparse(task1.taskStop).timestamp())
    start2 = int(dtparser.isoparse(task2.taskStart).timestamp())
    stop2 = int(dtparser.isoparse(task2.taskStop).timestamp())

    with td.heap_lock:
        heapq.heappush(td.task_heap, (start1, stop1, "task-001", task1))
        heapq.heappush(td.task_heap, (start2, stop2, "task-002", task2))
        td.task_ids.update({"task-001", "task-002"})
        td.task_dict.update({"task-001": task1, "task-002": task2})

    assert len(td.task_heap) == 2

    api_client.get_telescope_tasks.return_value = [task1.__dict__]

    with td.heap_lock:
        tasks = api_client.get_telescope_tasks(td.telescope_record["id"])
        api_task_map = {}
        for task_dict in tasks:
            task = Task.from_dict(task_dict)
            tid = task.id
            if tid and task.status in ["Pending", "Scheduled"]:
                api_task_map[tid] = task

        new_heap = []
        removed = 0
        for se, so, tid, task in td.task_heap:
            if tid == td.current_task_id or tid in api_task_map:
                new_heap.append((se, so, tid, task))
            else:
                td.task_ids.discard(tid)
                td.task_dict.pop(tid, None)
                removed += 1
        if removed > 0:
            td.task_heap = new_heap
            heapq.heapify(td.task_heap)

    assert len(td.task_heap) == 1
    assert "task-001" in td.task_ids
    assert "task-002" not in td.task_ids


def test_poll_tasks_removes_tasks_with_changed_status(wired_dispatcher):
    td, api_client = wired_dispatcher
    task1 = _create_test_task("task-001", "Pending")
    se = int(dtparser.isoparse(task1.taskStart).timestamp())
    so = int(dtparser.isoparse(task1.taskStop).timestamp())

    with td.heap_lock:
        heapq.heappush(td.task_heap, (se, so, "task-001", task1))
        td.task_ids.add("task-001")
        td.task_dict["task-001"] = task1

    cancelled = _create_test_task("task-001", "Cancelled")
    api_client.get_telescope_tasks.return_value = [cancelled.__dict__]

    with td.heap_lock:
        tasks = api_client.get_telescope_tasks(td.telescope_record["id"])
        api_task_map = {}
        for td2 in tasks:
            t = Task.from_dict(td2)
            if t.id and t.status in ["Pending", "Scheduled"]:
                api_task_map[t.id] = t

        new_heap = []
        for se2, so2, tid, task in td.task_heap:
            if tid == td.current_task_id or tid in api_task_map:
                new_heap.append((se2, so2, tid, task))
            else:
                td.task_ids.discard(tid)
                td.task_dict.pop(tid, None)
        td.task_heap = new_heap
        heapq.heapify(td.task_heap)

    assert len(td.task_heap) == 0
    assert "task-001" not in td.task_ids


def test_poll_tasks_does_not_remove_current_task(wired_dispatcher):
    td, api_client = wired_dispatcher
    task1 = _create_test_task("task-001", "Pending")
    se = int(dtparser.isoparse(task1.taskStart).timestamp())
    so = int(dtparser.isoparse(task1.taskStop).timestamp())

    with td.heap_lock:
        heapq.heappush(td.task_heap, (se, so, "task-001", task1))
        td.task_ids.add("task-001")
        td.task_dict["task-001"] = task1
        td.current_task_id = "task-001"

    api_client.get_telescope_tasks.return_value = []

    with td.heap_lock:
        tasks = api_client.get_telescope_tasks(td.telescope_record["id"])
        api_task_map = {}
        for td2 in tasks:
            t = Task.from_dict(td2)
            if t.id and t.status in ["Pending", "Scheduled"]:
                api_task_map[t.id] = t

        new_heap = []
        for se2, so2, tid, task in td.task_heap:
            if tid == td.current_task_id or tid in api_task_map:
                new_heap.append((se2, so2, tid, task))
            else:
                td.task_ids.discard(tid)
        td.task_heap = new_heap
        heapq.heapify(td.task_heap)

    assert len(td.task_heap) == 1
    assert "task-001" in td.task_ids


# ── _evaluate_safety — cable wrap soft-lock regression (#239) ────────────


class TestEvaluateSafetyQueueStop:
    """Verify QUEUE_STOP always attempts corrective action when the imaging
    queue is idle, even if the state transition already happened on a
    previous tick (regression for issue #239 soft-lock)."""

    def _call(self, td, *, queue_idle: bool, action: SafetyAction, triggered_check=None):
        mock_monitor = MagicMock()
        mock_monitor.evaluate.return_value = (action, triggered_check)
        td.safety_monitor = mock_monitor
        td._default_runtime.acquisition_queue.is_idle.return_value = queue_idle
        return td._evaluate_safety()

    def test_unwind_fires_after_queue_drains(self, wired_dispatcher):
        td, _ = wired_dispatcher
        check = MagicMock()
        check.name = "cable_wrap"

        result = self._call(td, queue_idle=False, action=SafetyAction.QUEUE_STOP, triggered_check=check)
        assert result is True
        check.execute_action.assert_not_called()

        result = self._call(td, queue_idle=True, action=SafetyAction.QUEUE_STOP, triggered_check=check)
        assert result is True
        check.execute_action.assert_called_once()

    def test_unwind_retried_after_failure(self, wired_dispatcher):
        td, _ = wired_dispatcher
        check = MagicMock()
        check.name = "cable_wrap"
        check.execute_action.side_effect = [RuntimeError("stall"), None]

        self._call(td, queue_idle=True, action=SafetyAction.QUEUE_STOP, triggered_check=check)
        assert check.execute_action.call_count == 1
        td.logger.error.assert_called()

        self._call(td, queue_idle=True, action=SafetyAction.QUEUE_STOP, triggered_check=check)
        assert check.execute_action.call_count == 2

    def test_no_action_when_queue_busy(self, wired_dispatcher):
        td, _ = wired_dispatcher
        check = MagicMock()
        check.name = "cable_wrap"
        self._call(td, queue_idle=False, action=SafetyAction.QUEUE_STOP, triggered_check=check)
        check.execute_action.assert_not_called()

    def test_queue_stop_yields_task_loop(self, wired_dispatcher):
        td, _ = wired_dispatcher
        result = self._call(td, queue_idle=False, action=SafetyAction.QUEUE_STOP)
        assert result is True

    def test_safe_does_not_yield(self, wired_dispatcher):
        td, _ = wired_dispatcher
        result = self._call(td, queue_idle=True, action=SafetyAction.SAFE)
        assert result is False
