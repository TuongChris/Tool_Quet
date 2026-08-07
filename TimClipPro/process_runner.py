# -*- coding: utf-8 -*-
"""Subprocess runner đọc output liên tục, heartbeat khi im lặng và hủy đúng cây PID."""

from __future__ import annotations

import contextlib
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

# Nhịp soi cây process. Bằng đúng chu kỳ vòng lặp cũ lúc subprocess im lặng, nên
# vẫn bắt được tiến trình FFmpeg tồn tại rất ngắn.
CHU_KY_SOI_CON_S = 0.2


@dataclass(frozen=True)
class ChildProcess:
    pid: int
    name: str


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    name: str
    elapsed_seconds: float
    children: tuple[ChildProcess, ...]
    silent_seconds: float


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    tail: tuple[str, ...]
    pid: int
    elapsed_seconds: float
    cancelled: bool = False
    timed_out: bool = False


def _children(pid: int) -> tuple[ChildProcess, ...]:
    try:
        root = psutil.Process(pid)
        result = []
        for child in root.children(recursive=True):
            try:
                result.append(ChildProcess(child.pid, child.name().lower()))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return tuple(sorted(result, key=lambda item: item.pid))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ()


def terminate_process_tree(pid: int, wait_seconds: float = 5.0) -> None:
    """Chỉ terminate root PID đã biết và descendants của chính nó."""
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    processes = root.children(recursive=True)
    processes.reverse()
    for process in processes:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            process.terminate()
    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
        root.terminate()
    _, alive = psutil.wait_procs([*processes, root], timeout=wait_seconds)
    for process in alive:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            process.kill()
    if alive:
        psutil.wait_procs(alive, timeout=wait_seconds)


def run_observed_process(
    command: list[str],
    *,
    on_line: Optional[Callable[[str], None]] = None,
    on_heartbeat: Optional[Callable[[ProcessSnapshot], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    logger=None,
    process_name: str = "subprocess",
    heartbeat_seconds: float = 10.0,
    slow_warning_seconds: float = 120.0,
    timeout_seconds: float | None = None,
    tail_lines: int = 30,
    include_in_tail: Optional[Callable[[str], bool]] = None,
    env: Optional[dict[str, str]] = None,
) -> ProcessResult:
    """Chạy process mà không block trên ``readline`` khi stdout im lặng."""
    started = time.monotonic()
    last_output = started
    output: queue.Queue[str | None] = queue.Queue(maxsize=256)
    tail: deque[str] = deque(maxlen=max(1, tail_lines))
    cancelled = False
    timed_out = False

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    if logger:
        logger.info("event=process_start process=%s pid=%s", process_name, process.pid)
        for handler in logger.handlers:
            handler.flush()

    def read_output() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                value = line.rstrip("\r\n")
                while True:
                    try:
                        output.put(value, timeout=0.2)
                        break
                    except queue.Full:
                        if process.poll() is not None:
                            return
        finally:
            with contextlib.suppress(queue.Full):
                output.put_nowait(None)

    reader = threading.Thread(
        target=read_output,
        name=f"stdout-{process.pid}",
        daemon=True,
    )
    reader.start()
    next_heartbeat = started
    next_children_poll = started
    last_children: tuple[ChildProcess, ...] = ()
    slow_warned = False
    eof = False

    try:
        while True:
            now = time.monotonic()
            if cancel_event and cancel_event.is_set():
                cancelled = True
                terminate_process_tree(process.pid)
                break
            if timeout_seconds is not None and now - started >= timeout_seconds:
                timed_out = True
                terminate_process_tree(process.pid)
                break

            # Rút theo lô. Trước đây mỗi vòng chỉ lấy MỘT dòng rồi mới làm phần
            # quan sát process phía dưới, nên thông lượng chỉ ~138 dòng/giây (đã đo).
            # Job 1717 clip phát hơn 3.400 dòng event; rút chậm làm đầy pipe của OS
            # và chặn chính subprocess ở print().
            try:
                line = output.get(timeout=0.2)
            except queue.Empty:
                line = ""
            for _ in range(512):
                if line is None:
                    eof = True
                elif line:
                    last_output = time.monotonic()
                    if include_in_tail is None or include_in_tail(line):
                        tail.append(line)
                    if on_line:
                        on_line(line)
                try:
                    line = output.get_nowait()
                except queue.Empty:
                    break

            now = time.monotonic()
            # psutil phải quét toàn bộ tiến trình của máy nên rất đắt. Soi cây process
            # theo NHỊP THỜI GIAN cố định thay vì sau mỗi dòng output: giữ nguyên tần
            # suất cũ lúc subprocess im lặng (~5 lần/giây, đủ để bắt tiến trình FFmpeg
            # ngắn) nhưng không còn tỉ lệ thuận với số dòng phát ra.
            if process.poll() is not None:
                children = ()
            elif now >= next_children_poll:
                children = _children(process.pid)
                next_children_poll = now + CHU_KY_SOI_CON_S
            else:
                children = last_children
            child_changed = children != last_children
            if child_changed and logger:
                old = {item.pid: item for item in last_children}
                new = {item.pid: item for item in children}
                for pid, child in new.items() - old.items():
                    logger.info(
                        "event=process_child_start process=%s pid=%s parent_pid=%s",
                        child.name,
                        pid,
                        process.pid,
                    )
                for pid, child in old.items() - new.items():
                    logger.info(
                        "event=process_child_end process=%s pid=%s parent_pid=%s",
                        child.name,
                        pid,
                        process.pid,
                    )
            if child_changed:
                last_children = children

            if (now >= next_heartbeat or child_changed) and on_heartbeat:
                on_heartbeat(ProcessSnapshot(
                    pid=process.pid,
                    name=process_name,
                    elapsed_seconds=now - started,
                    children=children,
                    silent_seconds=now - last_output,
                ))
                next_heartbeat = now + max(0.25, heartbeat_seconds)

            if not slow_warned and now - started >= slow_warning_seconds:
                slow_warned = True
                if logger:
                    logger.warning(
                        "event=process_slow process=%s pid=%s elapsed=%.1fs",
                        process_name,
                        process.pid,
                        now - started,
                    )

            if process.poll() is not None and (eof or not reader.is_alive()):
                while True:
                    try:
                        remaining = output.get_nowait()
                    except queue.Empty:
                        break
                    if remaining and (include_in_tail is None or include_in_tail(remaining)):
                        tail.append(remaining)
                    if remaining and on_line:
                        on_line(remaining)
                break
    except BaseException:
        terminate_process_tree(process.pid)
        raise
    finally:
        if process.poll() is None:
            terminate_process_tree(process.pid)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        if process.stdout is not None:
            with contextlib.suppress(Exception):
                process.stdout.close()
        reader.join(timeout=1)

    elapsed = time.monotonic() - started
    returncode = process.returncode if process.returncode is not None else -1
    if logger:
        logger.info(
            "event=process_end process=%s pid=%s exit_code=%s elapsed=%.3fs cancelled=%s timeout=%s",
            process_name,
            process.pid,
            returncode,
            elapsed,
            cancelled,
            timed_out,
        )
        for handler in logger.handlers:
            handler.flush()
    return ProcessResult(
        returncode=returncode,
        tail=tuple(tail),
        pid=process.pid,
        elapsed_seconds=elapsed,
        cancelled=cancelled,
        timed_out=timed_out,
    )
