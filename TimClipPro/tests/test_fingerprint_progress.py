# -*- coding: utf-8 -*-
"""Unit/integration tests cho progress contract và controller bounded queue."""

import logging
import threading
import time
from dataclasses import replace

import pytest

import fingerprint_progress as fp_module
from fingerprint_progress import (
    FingerprintJobController,
    FingerprintProgressTracker,
    progress_ban_dau,
)


def _logger_rong() -> logging.Logger:
    logger = logging.Logger("fingerprint-test")
    logger.addHandler(logging.NullHandler())
    return logger


def test_event_day_du_va_progress_khong_lui(monkeypatch, tmp_path):
    clock = [0.0]
    monkeypatch.setattr(fp_module.time, "monotonic", lambda: clock[0])
    events = []
    tracker = FingerprintProgressTracker(
        "job-test",
        callback=events.append,
        logger=_logger_rong(),
    )
    files = [
        str(tmp_path / "đã có.wav"),
        str(tmp_path / "clip có khoảng trắng.wav"),
        str(tmp_path / "lỗi.wav"),
        str(tmp_path / "bốn.wav"),
        str(tmp_path / "năm.wav"),
    ]

    tracker.discovering()
    tracker.set_files(files)
    tracker.skipped(files[0])
    for index, path in enumerate(files[1:4], 1):
        tracker.clip_started(path, 100 + index)
        tracker.phase("decoding", "Đang giải mã", path, 200 + index)
        clock[0] += 2.0
        tracker.clip_finished(
            path,
            success=path != files[2],
            elapsed=2.0,
            error_category="decode_error" if path == files[2] else "",
            message="file hỏng" if path == files[2] else "",
        )

    state = tracker.state
    assert events[0].phase == "discovering"
    assert any(event.phase == "validating" and event.total == 5 for event in events)
    assert any(event.status == "skipped_existing" for event in events)
    assert any(event.phase == "decoding" for event in events)
    assert any(event.status == "success" for event in events)
    assert any(event.status == "failed" for event in events)
    assert state.success_count == 2
    assert state.skipped_count == 1
    assert state.failed_count == 1
    assert state.processed_count == 4
    assert state.rate_per_minute == pytest.approx(30.0)
    assert state.eta_seconds == pytest.approx(2.0)
    assert all(a.percent <= b.percent for a, b in zip(events, events[1:]))
    assert all(event.processed_count <= event.total for event in events if event.total)
    assert all(
        event.success_count + event.skipped_count + event.failed_count <= event.total
        for event in events
        if event.total
    )
    assert state.file_name == "bốn.wav"


def test_total_bang_khong_khong_chia_cho_khong():
    events = []
    tracker = FingerprintProgressTracker(
        "empty",
        callback=events.append,
        logger=_logger_rong(),
    )
    tracker.set_files([])
    tracker.completed(db_written=False)

    assert tracker.state.percent == 1.0
    assert tracker.state.eta_seconds is None
    assert tracker.state.rate_per_minute is None


def test_finish_trung_khong_lam_count_vuot_total(tmp_path):
    path = str(tmp_path / "clip.wav")
    tracker = FingerprintProgressTracker("dedup", logger=_logger_rong())
    tracker.set_files([path])
    tracker.clip_started(path)
    tracker.clip_finished(path, success=True, elapsed=0.1)
    tracker.clip_finished(path, success=True, elapsed=0.1)

    assert tracker.state.success_count == 1
    assert tracker.state.processed_count == 1


class _EngineGia:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def build_database(self, folder, mode, progress_event, job_id):
        self.calls += 1
        tracker = FingerprintProgressTracker(
            job_id,
            callback=progress_event,
            logger=_logger_rong(),
        )
        files = [folder + "/một.wav", folder + "/hai.wav"]
        tracker.discovering()
        tracker.set_files(files)
        tracker.clip_started(files[0], 123)
        self.started.set()
        while not self.release.wait(0.02):
            if self.cancel_event.is_set():
                tracker.cancelled()
                return {"da_huy": True, "so_clip": 2, "da_xu_ly": 0}
        tracker.clip_finished(files[0], success=True, elapsed=0.1)
        tracker.skipped(files[1])
        tracker.completed()
        return {"da_huy": False, "so_clip": 2, "da_xu_ly": 2}

    def cancel(self):
        self.cancel_event.set()


def _doi_controller(controller, timeout=3.0):
    deadline = time.monotonic() + timeout
    while controller.running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not controller.running


def test_controller_nhan_event_khi_worker_chua_xong_va_chan_job_trung():
    engine = _EngineGia()
    controller = FingerprintJobController(engine, queue_maxsize=8)
    job_id = controller.start("D:/fixtures", "new")

    assert engine.started.wait(1)
    snapshot = controller.snapshot()
    assert snapshot.job_id == job_id
    assert snapshot.worker_alive is True
    assert snapshot.file_name == "một.wav"
    assert snapshot.status == "running"
    assert controller.drain()
    with pytest.raises(RuntimeError, match="job trùng"):
        controller.start("D:/fixtures", "new")

    engine.release.set()
    _doi_controller(controller)
    assert controller.snapshot().status == "completed"
    assert controller.result["da_xu_ly"] == 2
    assert engine.calls == 1


def test_controller_cancel_chi_bao_da_dung_sau_khi_worker_xac_nhan():
    engine = _EngineGia()
    controller = FingerprintJobController(engine)
    controller.start("D:/fixtures", "new")
    assert engine.started.wait(1)

    controller.cancel()
    assert controller.snapshot().status == "cancel_requested"
    _doi_controller(controller)
    assert controller.snapshot().status == "cancelled"
    assert controller.result["da_huy"] is True


def test_queue_va_recent_log_bi_gioi_han():
    controller = FingerprintJobController(_EngineGia(), queue_maxsize=3, recent_maxlen=4)
    event = progress_ban_dau("bounded")
    for index in range(20):
        controller.publish(replace(event, message=f"event-{index}", current=index))

    assert controller.events.qsize() == 3
    assert len(controller.recent()) == 4
    assert controller.snapshot().message == "event-19"
