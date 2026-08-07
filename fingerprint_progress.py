# -*- coding: utf-8 -*-
"""Progress contract, aggregation, logging and UI-safe job controller.

Module này không phụ thuộc Streamlit. Worker chỉ phát ``FingerprintProgress``;
main thread của UI đọc snapshot/queue và tự quyết định cách hiển thị.
"""

from __future__ import annotations

import logging
import contextlib
import os
import queue
import re
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, replace
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional


PHASES = {
    "discovering",
    "validating",
    "probing",
    "decoding",
    "fingerprinting",
    "saving",
    "completed",
    "cancelled",
    "failed",
}
TERMINAL_STATUSES = {"completed", "cancelled", "failed"}
_KY_TU_DIEU_KHIEN = re.compile(r"[\x00-\x1f\x7f]+")
_KHONG_DOI = object()


def ten_file_an_toan(path: str | None) -> str | None:
    """Chỉ giữ basename sạch để UI/log không làm lộ cả đường dẫn vận hành."""
    if not path:
        return None
    return _KY_TU_DIEU_KHIEN.sub("?", os.path.basename(str(path)))[:240]


def tao_fingerprint_logger(log_dir: str) -> logging.Logger:
    """Logger terminal + rotating file, mỗi output directory có một logger riêng."""
    os.makedirs(log_dir, exist_ok=True)
    khoa = str(abs(hash(os.path.normcase(os.path.abspath(log_dir)))))
    logger = logging.getLogger(f"fingerprint.job.{khoa}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    terminal = logging.StreamHandler(sys.stdout)
    terminal.setFormatter(formatter)
    terminal.setLevel(logging.INFO)
    logger.addHandler(terminal)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "fingerprint.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    return logger


def dong_fingerprint_logger(logger: logging.Logger) -> None:
    """Flush/đóng handler để Windows không giữ khóa file log sau khi job kết thúc."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.flush()
        with contextlib.suppress(Exception):
            handler.close()


@dataclass(frozen=True)
class FingerprintProgress:
    job_id: str
    phase: str
    current: int
    total: int
    file_name: str | None
    status: str
    message: str
    success_count: int
    skipped_count: int
    failed_count: int
    processed_count: int
    elapsed_seconds: float
    eta_seconds: float | None
    rate_per_minute: float | None
    updated_at: float
    last_progress_at: float
    current_clip_started_at: float | None
    active_subprocess_pid: int | None
    last_db_write_at: float | None
    worker_alive: bool = True
    queue_size: int = 0
    error_category: str = ""

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 1.0 if self.status == "completed" else 0.0
        return max(0.0, min(1.0, self.processed_count / self.total))


def progress_ban_dau(job_id: str | None = None) -> FingerprintProgress:
    now = time.time()
    return FingerprintProgress(
        job_id=job_id or uuid.uuid4().hex,
        phase="discovering",
        current=0,
        total=0,
        file_name=None,
        status="running",
        message="Đang chuẩn bị danh sách clip...",
        success_count=0,
        skipped_count=0,
        failed_count=0,
        processed_count=0,
        elapsed_seconds=0.0,
        eta_seconds=None,
        rate_per_minute=None,
        updated_at=now,
        last_progress_at=now,
        current_clip_started_at=None,
        active_subprocess_pid=None,
        last_db_write_at=None,
    )


class FingerprintProgressTracker:
    """Giữ invariant progress và phát cùng một event cho UI, CLI và logger."""

    def __init__(
        self,
        job_id: str,
        callback: Optional[Callable[[FingerprintProgress], None]] = None,
        legacy_callback: Optional[Callable[[float, str], None]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.job_id = job_id
        self.callback = callback
        self.legacy_callback = legacy_callback
        self.logger = logger or logging.getLogger("fingerprint.job")
        self._started_mono = time.monotonic()
        self._state = progress_ban_dau(job_id)
        self._files: list[str] = []
        self._indices: dict[str, int] = {}
        self._active: dict[str, tuple[float, int]] = {}
        self._finished: set[str] = set()
        self._work_finished_at: deque[float] = deque(maxlen=20)
        self._last_heartbeat_mono = 0.0
        self._lock = threading.RLock()
        self.errors: list[dict] = []

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    @property
    def state(self) -> FingerprintProgress:
        with self._lock:
            return self._state

    def _rate_eta(self, processed: int, total: int) -> tuple[float | None, float | None]:
        if len(self._work_finished_at) < 3 or processed <= 0 or total <= processed:
            return None, None
        span = self._work_finished_at[-1] - self._work_finished_at[0]
        if span <= 0:
            return None, None
        rate_s = (len(self._work_finished_at) - 1) / span
        if rate_s <= 0:
            return None, None
        return rate_s * 60.0, (total - processed) / rate_s

    def _emit(
        self,
        *,
        phase: str | None = None,
        status: str | None = None,
        message: str | None = None,
        file_name: str | None = None,
        current: int | None = None,
        active_pid: int | None | object = _KHONG_DOI,
        db_write: bool = False,
        error_category: str = "",
    ) -> FingerprintProgress:
        with self._lock:
            old = self._state
            new_phase = phase or old.phase
            if new_phase not in PHASES:
                raise ValueError(f"Phase fingerprint không hợp lệ: {new_phase}")
            now_wall = time.time()
            processed = old.success_count + old.skipped_count + old.failed_count
            rate, eta = self._rate_eta(processed, old.total)
            clip_started = old.current_clip_started_at
            if file_name:
                active = self._active.get(self._key(file_name))
                if active:
                    clip_started = active[0]
            if not self._active:
                clip_started = None
            snapshot = replace(
                old,
                phase=new_phase,
                status=status or old.status,
                message=message if message is not None else old.message,
                file_name=ten_file_an_toan(file_name) if file_name else old.file_name,
                current=max(old.current, current or 0),
                processed_count=processed,
                elapsed_seconds=max(0.0, time.monotonic() - self._started_mono),
                eta_seconds=eta,
                rate_per_minute=rate,
                updated_at=now_wall,
                last_progress_at=now_wall,
                current_clip_started_at=clip_started,
                active_subprocess_pid=(
                    old.active_subprocess_pid
                    if active_pid is _KHONG_DOI
                    else active_pid
                ),
                last_db_write_at=now_wall if db_write else old.last_db_write_at,
                error_category=error_category,
            )
            self._state = snapshot

        if self.callback:
            self.callback(snapshot)
        if self.legacy_callback:
            self.legacy_callback(snapshot.percent, snapshot.message)
        return snapshot

    def discovering(self, message: str = "Đang chuẩn bị danh sách clip...") -> None:
        self._log("INFO", "job", f"phase=discovering message={message!r}")
        self._emit(phase="discovering", status="running", message=message)

    def set_files(self, files: list[str]) -> None:
        with self._lock:
            self._files = list(files)
            self._indices = {self._key(path): i for i, path in enumerate(files, 1)}
            self._state = replace(self._state, total=len(files))
        self._log("INFO", "job", f"total={len(files)} phase=validating")
        self._emit(
            phase="validating",
            status="running",
            message=f"Đã tìm thấy {len(files)} clip; đang kiểm tra kho hiện có...",
        )

    def _index(self, path: str) -> int:
        return self._indices.get(self._key(path), 0)

    def skipped(self, path: str) -> None:
        key = self._key(path)
        with self._lock:
            if key in self._finished:
                return
            self._finished.add(key)
            self._state = replace(
                self._state,
                skipped_count=self._state.skipped_count + 1,
            )
        index = self._index(path)
        name = ten_file_an_toan(path)
        self._log("INFO", "clip", f"skip index={index} total={self.state.total} file={name!r}")
        self._emit(
            phase="validating",
            status="skipped_existing",
            message=f"Đã có vân tay, bỏ qua: {name}",
            file_name=path,
            current=index,
        )

    def clip_started(self, path: str, process_pid: int | None = None) -> None:
        key = self._key(path)
        index = self._index(path)
        with self._lock:
            self._active[key] = (time.time(), index)
        name = ten_file_an_toan(path)
        self._log(
            "INFO",
            "clip",
            f"start index={index} total={self.state.total} file={name!r} pid={process_pid or '-'}",
        )
        self._emit(
            phase="fingerprinting",
            status="running",
            message=f"Đang giải mã và tạo vân tay: {name}",
            file_name=path,
            current=index,
            active_pid=process_pid,
        )

    def phase(
        self,
        phase: str,
        message: str,
        path: str | None = None,
        process_pid: int | None = None,
    ) -> None:
        self._log(
            "INFO",
            "phase",
            f"phase={phase} file={ten_file_an_toan(path)!r} pid={process_pid or '-'}",
        )
        self._emit(
            phase=phase,
            status="running",
            message=message,
            file_name=path,
            current=self._index(path) if path else None,
            active_pid=process_pid,
        )

    def clip_finished(
        self,
        path: str,
        *,
        success: bool,
        elapsed: float,
        error_category: str = "",
        message: str = "",
    ) -> None:
        key = self._key(path)
        with self._lock:
            if key in self._finished:
                return
            self._finished.add(key)
            self._active.pop(key, None)
            if success:
                self._state = replace(
                    self._state,
                    success_count=self._state.success_count + 1,
                )
            else:
                self._state = replace(
                    self._state,
                    failed_count=self._state.failed_count + 1,
                )
                self.errors.append({
                    "file": ten_file_an_toan(path) or "",
                    "category": error_category or "fingerprint_error",
                    "message": message or "Không tạo được vân tay.",
                })
            self._work_finished_at.append(time.monotonic())
        index = self._index(path)
        name = ten_file_an_toan(path)
        outcome = "success" if success else "failed"
        self._log(
            "INFO" if success else "ERROR",
            "clip",
            f"{outcome} index={index} total={self.state.total} file={name!r} elapsed={elapsed:.3f}s",
        )
        self._emit(
            phase="fingerprinting",
            status=outcome,
            message=(
                f"Đã tạo vân tay: {name}"
                if success
                else f"Lỗi clip {name}: {message or 'không có dữ liệu vân tay'}"
            ),
            file_name=path,
            current=index,
            error_category=error_category,
        )

    def heartbeat(
        self,
        process_pid: int,
        message: str,
        phase: str | None = None,
    ) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat_mono < 0.25 and phase == self.state.phase:
            return
        self._last_heartbeat_mono = now
        self._log("INFO", "heartbeat", f"phase={phase or self.state.phase} pid={process_pid}")
        self._emit(
            phase=phase or self.state.phase,
            status="heartbeat",
            message=message,
            active_pid=process_pid,
        )

    def saving(self, process_pid: int | None = None) -> None:
        self._log("INFO", "phase", f"phase=saving pid={process_pid or '-'}")
        self._emit(
            phase="saving",
            status="running",
            message="Đang hợp nhất và ghi database vân tay...",
            active_pid=process_pid,
        )

    def completed(
        self,
        message: str = "Hoàn tất tạo vân tay.",
        *,
        db_written: bool = True,
    ) -> None:
        self._log(
            "INFO",
            "job",
            f"completed processed={self.state.processed_count} total={self.state.total}",
        )
        self._emit(
            phase="completed",
            status="completed",
            message=message,
            active_pid=None,
            db_write=db_written,
        )

    def cancelled(self, message: str = "Đã dừng sau khi hoàn tất phần có thể giữ lại.") -> None:
        self._log("WARNING", "job", "cancelled")
        self._emit(
            phase="cancelled",
            status="cancelled",
            message=message,
            active_pid=None,
        )

    def failed(self, message: str, category: str = "job_error") -> None:
        self._log("ERROR", "job", f"failed category={category} message={message!r}")
        self._emit(
            phase="failed",
            status="failed",
            message=message,
            active_pid=None,
            error_category=category,
        )

    def _log(self, level: str, event: str, detail: str) -> None:
        log = getattr(self.logger, level.lower(), self.logger.info)
        log(f"job_id={self.job_id} event={event} {detail}")
        for handler in self.logger.handlers:
            handler.flush()


class FingerprintJobController:
    """Một worker + queue bounded; không gọi API Streamlit từ worker thread."""

    def __init__(self, engine, queue_maxsize: int = 256, recent_maxlen: int = 50):
        self.engine = engine
        self.events: queue.Queue[FingerprintProgress] = queue.Queue(maxsize=queue_maxsize)
        self._recent: deque[FingerprintProgress] = deque(maxlen=recent_maxlen)
        self._state: FingerprintProgress | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._result: dict | None = None
        self._error = ""
        self._lock = threading.RLock()
        self._started_mono: float | None = None

    def publish(self, event: FingerprintProgress) -> None:
        with self._lock:
            event = replace(event, queue_size=self.events.qsize())
            self._state = event
            self._recent.append(event)
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            self.events.put_nowait(event)

    def start(self, folder: str, mode: str) -> str:
        with self._lock:
            if self._running or (self._thread and self._thread.is_alive()):
                raise RuntimeError("Job tạo vân tay đang chạy; không thể tạo job trùng.")
            job_id = uuid.uuid4().hex
            self._state = progress_ban_dau(job_id)
            self._result = None
            self._error = ""
            self._running = True
            self._started_mono = time.monotonic()
            self._recent.clear()
            while not self.events.empty():
                try:
                    self.events.get_nowait()
                except queue.Empty:
                    break
            self.publish(self._state)

            def target() -> None:
                try:
                    result = self.engine.build_database(
                        folder,
                        mode,
                        progress_event=self.publish,
                        job_id=job_id,
                    )
                    with self._lock:
                        self._result = result
                    if self.snapshot().status not in TERMINAL_STATUSES:
                        self.publish(replace(
                            self.snapshot(),
                            phase="completed",
                            status="completed",
                            message="Hoàn tất tạo vân tay.",
                            updated_at=time.time(),
                        ))
                except Exception as exc:  # noqa: BLE001
                    with self._lock:
                        self._error = str(exc)
                    if self.snapshot().status not in TERMINAL_STATUSES:
                        self.publish(replace(
                            self.snapshot(),
                            phase="failed",
                            status="failed",
                            message=f"Job tạo vân tay thất bại: {exc}",
                            error_category=type(exc).__name__,
                            updated_at=time.time(),
                        ))
                finally:
                    with self._lock:
                        self._running = False

            self._thread = threading.Thread(
                target=target,
                name=f"fingerprint-{job_id[:8]}",
                daemon=True,
            )
            self._thread.start()
            return job_id

    def cancel(self) -> None:
        self.engine.cancel()
        with self._lock:
            if self._state and self._state.status not in TERMINAL_STATUSES:
                self.publish(replace(
                    self._state,
                    status="cancel_requested",
                    message="Đang yêu cầu dừng; chờ subprocess xác nhận...",
                    updated_at=time.time(),
                ))

    def snapshot(self) -> FingerprintProgress:
        with self._lock:
            state = self._state or progress_ban_dau()
            alive = bool(self._thread and self._thread.is_alive())
            elapsed = state.elapsed_seconds
            if self._started_mono is not None and state.status not in TERMINAL_STATUSES:
                elapsed = max(elapsed, time.monotonic() - self._started_mono)
            return replace(
                state,
                worker_alive=alive if self._thread else self._running,
                queue_size=self.events.qsize(),
                elapsed_seconds=max(elapsed, 0.0),
            )

    def drain(self, limit: int = 256) -> list[FingerprintProgress]:
        drained = []
        for _ in range(max(0, limit)):
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                break
        return drained

    def recent(self) -> list[FingerprintProgress]:
        with self._lock:
            return list(self._recent)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running or bool(self._thread and self._thread.is_alive())

    @property
    def result(self) -> dict | None:
        with self._lock:
            return self._result

    @property
    def error(self) -> str:
        with self._lock:
            return self._error
