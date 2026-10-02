# -*- coding: utf-8 -*-
"""Subprocess runner đọc output liên tục, heartbeat khi im lặng và hủy đúng cây PID.

SỞ HỮU CÂY PROCESS (audit TCP-14)

``Process.terminate()`` và cả việc dò ``psutil.children()`` của process gốc đều KHÔNG
đủ: khi process gốc đã thoát hoặc chết, Windows không gắn lại cha cho cháu, cây PID
đứt và cháu (worker audfprint, FFmpeg) sống tiếp, giữ file và CPU. Vì vậy mỗi lệnh
dài chạy trong một ``NhomTienTrinh``:

* Windows: một Job Object ``KILL_ON_JOB_CLOSE``. Mọi hậu duệ tự vào job. Kết thúc
  job giết trọn cây dù cha đã chết; nếu chính tool chết, Windows đóng handle và tự
  dọn cây.
* POSIX: process group riêng (``start_new_session``), dừng bằng ``killpg``.

Không bao giờ giết theo tên chương trình, không giết PID cũ chưa xác minh.
"""

from __future__ import annotations

import contextlib
import os
import queue
import signal
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


# =====================================================================
#  Job Object (Windows) — giữ quyền sở hữu cả cây process
# =====================================================================

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _JOB_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_BASIC_ACCOUNTING_INFORMATION = 1
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(ten, ctypes.c_ulonglong) for ten in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BASIC_LIMIT(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BASIC_LIMIT),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _BASIC_ACCOUNTING(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD)]
    _k32.QueryInformationJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.GetCurrentProcess.argtypes = []
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CloseHandle.restype = wintypes.BOOL


class NhomTienTrinh:
    """Quyền sở hữu MỘT cây process do tool khởi chạy.

    Dùng: ``nhom = NhomTienTrinh()`` → ``Popen(..., **nhom.tham_so_popen())`` →
    ``nhom.gan(popen)`` → cuối cùng ``nhom.ket_thuc()`` và ``nhom.dong()``.
    Không được job thì lùi về dừng cây theo psutil (vẫn chỉ cây của chính mình).
    """

    def __init__(self) -> None:
        self._job = None
        self._pid_goc: Optional[int] = None
        self.dung_job = False
        if os.name == "nt":
            job = _k32.CreateJobObjectW(None, None)
            if job:
                info = _EXTENDED_LIMIT()
                info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if _k32.SetInformationJobObject(
                    job, _JOB_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(info), ctypes.sizeof(info),
                ):
                    self._job = job
                else:
                    _k32.CloseHandle(job)

    def tham_so_popen(self) -> dict:
        if os.name == "nt":
            return {}
        return {"start_new_session": True}

    def gan(self, process: subprocess.Popen) -> bool:
        """Gắn process vừa tạo vào nhóm. Gọi NGAY sau ``Popen``."""
        self._pid_goc = process.pid
        if os.name != "nt" or self._job is None:
            return False
        handle = getattr(process, "_handle", None)
        tu_mo = False
        if handle is None:
            handle = _k32.OpenProcess(
                _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, process.pid)
            tu_mo = bool(handle)
        try:
            self.dung_job = bool(handle) and bool(
                _k32.AssignProcessToJobObject(self._job, int(handle)))
        finally:
            if tu_mo:
                _k32.CloseHandle(handle)
        return self.dung_job

    def gan_chinh_minh(self) -> bool:
        """Đưa CHÍNH process hiện tại vào job: mọi hậu duệ sinh ra sau đó chết theo
        nó khi nó thoát (handle job đóng → ``KILL_ON_JOB_CLOSE``). Dùng cho runner."""
        if os.name != "nt" or self._job is None:
            return False
        self._pid_goc = os.getpid()
        self.dung_job = bool(
            _k32.AssignProcessToJobObject(self._job, _k32.GetCurrentProcess()))
        # KHÔNG bao giờ tự đóng handle job khi chính mình đang ở trong job: đóng
        # handle cuối = giết mọi thành viên, kể cả process đang chạy dở lúc tắt
        # interpreter. Để hệ điều hành đóng lúc process đã thoát hẳn.
        self._khong_dong = self.dung_job
        return self.dung_job

    def so_process_con_song(self) -> Optional[int]:
        """Số process còn sống trong job; ``None`` nếu không dùng được job."""
        if not self.dung_job or self._job is None:
            return None
        acct = _BASIC_ACCOUNTING()
        if not _k32.QueryInformationJobObject(
            self._job, _JOB_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(acct), ctypes.sizeof(acct), None,
        ):
            return None
        return int(acct.ActiveProcesses)

    def ket_thuc(self, cho_s: float = 5.0) -> None:
        """Dừng MỌI process thuộc nhóm (kể cả cháu mồ côi) và chờ có hạn."""
        if self.dung_job and self._job is not None:
            _k32.TerminateJobObject(self._job, 1)
            het = time.monotonic() + max(0.0, cho_s)
            while time.monotonic() < het:
                con = self.so_process_con_song()
                if not con:
                    return
                time.sleep(0.02)
            return
        if os.name != "nt" and self._pid_goc:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(self._pid_goc, signal.SIGTERM)
            het = time.monotonic() + max(0.0, cho_s)
            while time.monotonic() < het:
                try:
                    os.killpg(self._pid_goc, 0)
                except (ProcessLookupError, PermissionError, OSError):
                    return
                time.sleep(0.05)
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(self._pid_goc, signal.SIGKILL)
            return
        if self._pid_goc:
            terminate_process_tree(self._pid_goc, wait_seconds=cho_s)

    def dong(self) -> None:
        if getattr(self, "_khong_dong", False):
            return
        job, self._job = self._job, None
        if job is not None and os.name == "nt":
            _k32.CloseHandle(job)

    def __del__(self) -> None:  # pragma: no cover - lưới an toàn cuối
        with contextlib.suppress(Exception):
            self.dong()


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

    nhom = NhomTienTrinh()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        **nhom.tham_so_popen(),
    )
    nhom.gan(process)
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
    goc_thoat_luc: Optional[float] = None
    da_don_mo_coi = False

    try:
        while True:
            now = time.monotonic()
            if cancel_event and cancel_event.is_set():
                cancelled = True
                nhom.ket_thuc()
                break
            if timeout_seconds is not None and now - started >= timeout_seconds:
                timed_out = True
                nhom.ket_thuc()
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

            # Gốc đã thoát mà ống stdout vẫn chưa đóng: một hậu duệ mồ côi đang giữ
            # đầu ghi. Không dọn thì vòng đọc treo tới khi nó tự chết (có thể hàng giờ).
            if process.poll() is not None and not eof and reader.is_alive():
                if goc_thoat_luc is None:
                    goc_thoat_luc = now
                elif not da_don_mo_coi and now - goc_thoat_luc >= 1.0:
                    da_don_mo_coi = True
                    if logger:
                        logger.warning(
                            "event=process_orphans_holding_output process=%s pid=%s",
                            process_name, process.pid,
                        )
                    nhom.ket_thuc()

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
        nhom.ket_thuc()
        raise
    finally:
        # Gốc đã thoát nhưng job còn process = cháu mồ côi (worker, FFmpeg). Chúng
        # thuộc về job này nên phải dừng ở đây, không được để sống tiếp giữ file.
        mo_coi = nhom.so_process_con_song()
        # POSIX không đếm được thành viên nhóm: luôn gửi tín hiệu cho cả process
        # group (nhóm đã trống thì killpg trả về ngay).
        if process.poll() is None or mo_coi or os.name != "nt":
            if mo_coi and process.poll() is not None and logger:
                logger.warning(
                    "event=process_orphans_terminated process=%s pid=%s count=%s",
                    process_name, process.pid, mo_coi,
                )
            nhom.ket_thuc()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        if process.stdout is not None:
            with contextlib.suppress(Exception):
                process.stdout.close()
        reader.join(timeout=1)
        nhom.dong()

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


# =====================================================================
#  Lệnh media ngắn: FFmpeg / FFprobe (audit TCP-15)
# =====================================================================

# Ngân sách mặc định. FFprobe chỉ đọc header nên có TRẦN TỔNG; FFmpeg cắt/nén thì đo
# tiến độ thật qua `-progress` và chỉ dừng khi IM LẶNG quá lâu — không đặt hạn chót
# tổng cho một tác vụ đang chạy khoẻ (bài học của watchdog 1800 giây).
TRAN_FFPROBE_S = 120.0
IM_LANG_FFMPEG_S = 300.0

GIOI_HAN_STDOUT_KY_TU = 256 * 1024
GIOI_HAN_STDERR_KY_TU = 8 * 1024
_KHOA_TIEN_DO = ("out_time_us", "out_time_ms", "out_time", "total_size", "progress")


@dataclass(frozen=True)
class KetQuaLenh:
    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False
    timed_out: bool = False
    ly_do: str = ""            # "huy" | "im_lang" | "tran_tong" | ""
    elapsed_seconds: float = 0.0


def chay_lenh_media(
    lenh: list[str],
    *,
    cancel_event: Optional[threading.Event] = None,
    tran_tong_s: Optional[float] = None,
    im_lang_toi_da_s: Optional[float] = None,
    theo_doi_tien_do: bool = False,
    them_co_tien_do: bool = True,
    env: Optional[dict[str, str]] = None,
) -> KetQuaLenh:
    """Chạy một lệnh media ngắn trong nhóm process riêng, có huỷ và timeout.

    ``theo_doi_tien_do``: đọc khối ``-progress`` của FFmpeg trên stdout; mỗi lần
    ``out_time``/``total_size`` đổi là một nhịp tiến triển. ``im_lang_toi_da_s`` chỉ
    tính khoảng KHÔNG có nhịp nào. ``them_co_tien_do`` tự chèn
    ``-progress pipe:1 -nostats`` ngay sau tên chương trình.

    Không ném lỗi vì returncode khác 0 — người gọi quyết định; huỷ/timeout đánh dấu
    trên kết quả để tầng trên ném ``Cancelled`` hay báo lỗi đúng loại.
    """
    lenh = list(lenh)
    if theo_doi_tien_do and them_co_tien_do:
        lenh = [lenh[0], "-progress", "pipe:1", "-nostats", *lenh[1:]]

    nhom = NhomTienTrinh()
    bat_dau = time.monotonic()
    process = subprocess.Popen(
        lenh,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        **nhom.tham_so_popen(),
    )
    nhom.gan(process)

    khoa = threading.Lock()
    phan_stdout: list[str] = []
    so_ky_tu_stdout = [0]
    duoi_stderr: deque[str] = deque(maxlen=200)
    tien_do = {"moc": time.monotonic(), "gia_tri": {}}

    def doc_stdout() -> None:
        assert process.stdout is not None
        for raw in iter(process.stdout.readline, b""):
            dong = raw.decode("utf-8", errors="replace")
            if theo_doi_tien_do and "=" in dong:
                khoa_tien_do, _, gia_tri = dong.strip().partition("=")
                if khoa_tien_do in _KHOA_TIEN_DO and gia_tri and gia_tri != "N/A":
                    with khoa:
                        if tien_do["gia_tri"].get(khoa_tien_do) != gia_tri:
                            tien_do["gia_tri"][khoa_tien_do] = gia_tri
                            tien_do["moc"] = time.monotonic()
            if so_ky_tu_stdout[0] < GIOI_HAN_STDOUT_KY_TU:
                phan_stdout.append(dong)
                so_ky_tu_stdout[0] += len(dong)

    def doc_stderr() -> None:
        assert process.stderr is not None
        for raw in iter(process.stderr.readline, b""):
            duoi_stderr.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))

    luong = [
        threading.Thread(target=doc_stdout, daemon=True, name=f"media-out-{process.pid}"),
        threading.Thread(target=doc_stderr, daemon=True, name=f"media-err-{process.pid}"),
    ]
    for t in luong:
        t.start()

    ly_do = ""
    try:
        while True:
            try:
                process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel_event is not None and cancel_event.is_set():
                ly_do = "huy"
                break
            bay_gio = time.monotonic()
            if tran_tong_s is not None and bay_gio - bat_dau >= tran_tong_s:
                ly_do = "tran_tong"
                break
            if theo_doi_tien_do and im_lang_toi_da_s is not None:
                with khoa:
                    moc = tien_do["moc"]
                if bay_gio - moc >= im_lang_toi_da_s:
                    ly_do = "im_lang"
                    break
    except BaseException:
        nhom.ket_thuc()
        raise
    finally:
        if ly_do or process.poll() is None or nhom.so_process_con_song() \
                or os.name != "nt":
            nhom.ket_thuc()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        for t in luong:
            t.join(timeout=2)
        for ong in (process.stdout, process.stderr):
            if ong is not None:
                with contextlib.suppress(Exception):
                    ong.close()
        nhom.dong()

    stderr = "\n".join(duoi_stderr)[-GIOI_HAN_STDERR_KY_TU:]
    return KetQuaLenh(
        returncode=process.returncode if process.returncode is not None else -1,
        stdout="".join(phan_stdout),
        stderr=stderr,
        cancelled=ly_do == "huy",
        timed_out=ly_do in {"im_lang", "tran_tong"},
        ly_do=ly_do,
        elapsed_seconds=time.monotonic() - bat_dau,
    )
