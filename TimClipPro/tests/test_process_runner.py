# -*- coding: utf-8 -*-
"""Subprocess phải stream output/heartbeat và dọn đúng PID, không deadlock."""

import io
import logging
import sys
import threading
import time

import psutil

from process_runner import run_observed_process


def _logger_vao(stream):
    logger = logging.Logger("process-test")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def test_output_duoc_nhan_trong_luc_process_con_chay_va_logger_flush():
    lines = []
    observed_while_alive = []
    stream = io.StringIO()
    logger = _logger_vao(stream)
    command = [
        sys.executable,
        "-u",
        "-c",
        "import time; print('mot', flush=True); time.sleep(.35); "
        "print('hai', flush=True); time.sleep(.2)",
    ]
    holder = {"done": False}

    def on_line(line):
        lines.append((line, time.monotonic()))
        observed_while_alive.append(not holder["done"])
        assert "event=process_start" in stream.getvalue()

    result = run_observed_process(
        command,
        on_line=on_line,
        logger=logger,
        process_name="periodic-test",
        heartbeat_seconds=0.1,
    )
    holder["done"] = True

    assert result.returncode == 0
    assert [line for line, _ in lines] == ["mot", "hai"]
    assert all(observed_while_alive)
    assert lines[0][1] < lines[-1][1]
    assert "event=process_end" in stream.getvalue()


def test_rut_stdout_du_nhanh_de_khong_lam_day_pipe_cua_os():
    """Regression: vòng lặp chính từng chỉ rút MỘT dòng rồi mới quét cây process.

    psutil phải duyệt toàn bộ tiến trình của máy nên thông lượng tụt còn ~138
    dòng/giây (đã đo). Job 1717 clip phát hơn 3.400 dòng event; rút chậm làm đầy
    pipe của OS, chặn chính audfprint ở ``print()`` và khoá cứng cả job.
    """
    so_dong = 3000
    kich_ban = (
        "import sys\n"
        f"for i in range({so_dong}):\n"
        "    print('TIMCLIP_FINGERPRINT_EVENT ' + 'x' * 200 + ' #%d' % i, flush=True)\n"
    )
    nhan = []
    bat_dau = time.monotonic()
    result = run_observed_process(
        [sys.executable, "-u", "-c", kich_ban],
        on_line=nhan.append,
        on_heartbeat=lambda snapshot: None,
        heartbeat_seconds=10.0,
        timeout_seconds=60,
    )
    giay = time.monotonic() - bat_dau

    assert result.returncode == 0
    assert result.timed_out is False
    assert len(nhan) == so_dong, "Không được mất dòng output khi rút theo lô."
    # Bản lỗi cần ~22 giây cho 3000 dòng; bản đúng dưới 1 giây. Ngưỡng 8 giây đủ
    # rộng cho máy chậm nhưng vẫn bắt được hồi quy về kiểu rút từng dòng.
    assert giay < 8.0, f"Rút stdout quá chậm: {len(nhan) / giay:.0f} dòng/giây"


def test_process_im_lang_van_phat_heartbeat():
    snapshots = []
    result = run_observed_process(
        [sys.executable, "-c", "import time; time.sleep(.55)"],
        on_heartbeat=snapshots.append,
        heartbeat_seconds=0.1,
    )

    assert result.returncode == 0
    assert len(snapshots) >= 2
    assert snapshots[-1].elapsed_seconds >= 0.3


def test_exit_code_khac_khong_bi_nuot_va_tail_co_stderr():
    result = run_observed_process(
        [sys.executable, "-u", "-c", "import sys; print('loi', file=sys.stderr); sys.exit(7)"],
    )

    assert result.returncode == 7
    assert result.tail == ("loi",)


def test_timeout_don_root_va_child_cua_dung_job():
    child_pids = []
    command = [
        sys.executable,
        "-u",
        "-c",
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
        "print(p.pid,flush=True); time.sleep(30)",
    ]
    result = run_observed_process(
        command,
        on_line=lambda line: child_pids.append(int(line)),
        timeout_seconds=0.8,
        heartbeat_seconds=0.1,
    )

    assert result.timed_out is True
    assert child_pids
    deadline = time.monotonic() + 2
    while psutil.pid_exists(child_pids[0]) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pids[0])


def test_cancel_event_dung_process_im_lang():
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    try:
        result = run_observed_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cancel_event=cancel,
            heartbeat_seconds=0.1,
        )
    finally:
        timer.cancel()

    assert result.cancelled is True
    assert not psutil.pid_exists(result.pid)
