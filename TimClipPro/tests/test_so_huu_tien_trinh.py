# -*- coding: utf-8 -*-
"""Sở hữu cây process: dừng job thì MỌI hậu duệ thuộc job phải chết, process không
liên quan phải sống (audit TCP-14), và lệnh FFmpeg/FFprobe có timeout + huỷ đúng
nghĩa (audit TCP-15).

Mỗi process con mang một chuỗi đánh dấu duy nhất trên dòng lệnh: test chỉ coi một PID
là "còn sống" khi dòng lệnh của nó còn mang đúng chuỗi đó — không nhầm với process
khác tình cờ nhận lại PID cũ.
"""

import os
import subprocess
import sys
import threading
import time
import uuid

import psutil
import pytest

import process_runner

# Process gốc đẻ một process cháu (ngủ lâu), ghi PID cháu ra file, rồi tự ngủ/thoát.
MA_CAY = r"""
import pathlib, subprocess, sys, time
chau = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", sys.argv[3]])
pathlib.Path(sys.argv[1]).write_text(str(chau.pid))
time.sleep(float(sys.argv[2]))
"""


def _con_song(pid: int, dau: str) -> bool:
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE and dau in " ".join(
            p.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _cho_file(path, han_s=20.0) -> int:
    het = time.monotonic() + han_s
    while time.monotonic() < het:
        try:
            noi_dung = open(path, encoding="utf-8").read().strip()
            if noi_dung:
                return int(noi_dung)
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    raise AssertionError("process con không báo PID")


def _cho_chet(pid: int, dau: str, han_s=10.0) -> bool:
    het = time.monotonic() + han_s
    while time.monotonic() < het:
        if not _con_song(pid, dau):
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def doi_chung():
    """Một process KHÔNG thuộc job nào: không được bị giết nhầm."""
    dau = f"DOI-CHUNG-{uuid.uuid4().hex}"
    # Sống lâu hơn hẳn mọi test: nó chỉ được phép kết thúc khi chính fixture dọn nó.
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)", dau])
    yield p
    p.kill()
    p.wait(10)


def _don(pid, dau):
    if _con_song(pid, dau):
        psutil.Process(pid).kill()


def test_process_goc_thoat_binh_thuong_thi_chau_mo_coi_cung_bi_dung(tmp_path, doi_chung):
    dau = f"CHAU-{uuid.uuid4().hex}"
    pid_file = tmp_path / "chau.pid"
    chau = None
    try:
        bat_dau = time.monotonic()
        kq = process_runner.run_observed_process(
            [sys.executable, "-c", MA_CAY, str(pid_file), "0.3", dau],
            process_name="cay-thu",
        )
        # Cháu mồ côi còn giữ ống stdout: runner KHÔNG được treo chờ nó tự chết.
        assert time.monotonic() - bat_dau < 30
        chau = _cho_file(pid_file)
        assert kq.returncode == 0
        assert _cho_chet(chau, dau), "process cháu sống sót sau khi job kết thúc"
        assert doi_chung.poll() is None, "process không liên quan bị giết nhầm"
    finally:
        if chau:
            _don(chau, dau)


def test_huy_job_giet_ca_cay_trong_han(tmp_path, doi_chung):
    dau = f"CHAU-{uuid.uuid4().hex}"
    pid_file = tmp_path / "chau.pid"
    huy = threading.Event()
    chau = None

    def bam_dung():
        nonlocal chau
        chau = _cho_file(pid_file)
        huy.set()

    t = threading.Thread(target=bam_dung)
    t.start()
    try:
        bat_dau = time.monotonic()
        kq = process_runner.run_observed_process(
            [sys.executable, "-c", MA_CAY, str(pid_file), "120", dau],
            cancel_event=huy, process_name="cay-thu",
        )
        t.join(20)
        assert kq.cancelled
        assert time.monotonic() - bat_dau < 30
        assert _cho_chet(chau, dau), "process cháu sống sót sau khi huỷ"
        assert doi_chung.poll() is None
    finally:
        if chau:
            _don(chau, dau)


def test_process_goc_chet_dot_ngot_thi_chau_van_bi_dung(tmp_path, doi_chung):
    """Cha chết trước — cây PID đứt, nhưng job vẫn phải dọn được cháu."""
    dau = f"CHAU-{uuid.uuid4().hex}"
    pid_file = tmp_path / "chau.pid"
    chau = None

    def giet_goc_khi_san_sang(snapshot):
        nonlocal chau
        if chau is None and pid_file.exists() and pid_file.read_text().strip():
            chau = int(pid_file.read_text().strip())
            psutil.Process(snapshot.pid).kill()

    try:
        kq = process_runner.run_observed_process(
            [sys.executable, "-c", MA_CAY, str(pid_file), "120", dau],
            on_heartbeat=giet_goc_khi_san_sang, heartbeat_seconds=0.1,
            timeout_seconds=60, process_name="cay-thu",
        )
        assert not kq.timed_out
        assert chau is not None
        assert _cho_chet(chau, dau), "cháu mồ côi sống sót khi cha chết đột ngột"
        assert doi_chung.poll() is None
    finally:
        if chau:
            _don(chau, dau)


# ---------------------------------------------------------------------------
#  Lệnh media ngắn (FFmpeg/FFprobe): timeout theo IM LẶNG + huỷ
# ---------------------------------------------------------------------------

def test_lenh_treo_im_lang_bi_dung_theo_han_im_lang(doi_chung):
    bat_dau = time.monotonic()
    kq = process_runner.chay_lenh_media(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        im_lang_toi_da_s=1.0, theo_doi_tien_do=True, them_co_tien_do=False,
    )
    assert kq.timed_out and not kq.cancelled and kq.ly_do == "im_lang"
    assert time.monotonic() - bat_dau < 20
    assert doi_chung.poll() is None


def test_lenh_dang_tien_trien_khong_bi_giet_du_lau_hon_han_im_lang():
    """Hạn là cho sự IM LẶNG, không phải hạn chót tổng: còn báo tiến độ thì chạy tiếp."""
    ma = (
        "import sys, time\n"
        "for i in range(12):\n"
        "    print(f'out_time_us={i * 1000000}', flush=True)\n"
        "    print('progress=continue', flush=True)\n"
        "    time.sleep(0.25)\n"
        "print('progress=end', flush=True)\n"
    )
    kq = process_runner.chay_lenh_media(
        [sys.executable, "-c", ma], im_lang_toi_da_s=1.0, theo_doi_tien_do=True,
        them_co_tien_do=False,
    )
    assert kq.returncode == 0 and not kq.timed_out


def test_lenh_ngan_co_tran_tong(doi_chung):
    kq = process_runner.chay_lenh_media(
        [sys.executable, "-c", "import time; time.sleep(120)"], tran_tong_s=1.0,
    )
    assert kq.timed_out
    assert doi_chung.poll() is None


def test_lenh_media_huy_giua_chung():
    huy = threading.Event()
    threading.Timer(0.5, huy.set).start()
    bat_dau = time.monotonic()
    kq = process_runner.chay_lenh_media(
        [sys.executable, "-c", "import time; time.sleep(120)"], cancel_event=huy,
    )
    assert kq.cancelled
    assert time.monotonic() - bat_dau < 20


def test_lenh_media_tra_stdout_va_duoi_stderr_co_gioi_han():
    ma = ("import sys\n"
          "print('12.5')\n"
          "for i in range(5000): print('loi dong', i, file=sys.stderr)\n"
          "sys.exit(3)\n")
    kq = process_runner.chay_lenh_media([sys.executable, "-c", ma])
    assert kq.returncode == 3
    assert kq.stdout.strip().splitlines()[0] == "12.5"
    assert "loi dong 4999" in kq.stderr
    assert len(kq.stderr) < 20_000, "phần đuôi stderr phải có giới hạn"


# ---------------------------------------------------------------------------
#  Worker audfprint lỗi: không để lại process con
# ---------------------------------------------------------------------------

def _worker_hong_de_lai_con(analyzer, files, hashbits, depth, maxtime, pipe, path, nhip):
    import pathlib
    import subprocess as sp
    import sys as s
    import time as t

    con = sp.Popen([s.executable, "-c", "import time; time.sleep(120)", files[1]],
                   stdin=sp.DEVNULL, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    pathlib.Path(files[0]).write_text(str(con.pid))
    pipe.send({"ok": False, "loi": "lỗi giả lập sau khi đã đẻ process con"})
    t.sleep(60)


def test_worker_loi_thi_process_con_cua_worker_cung_bi_dung(tmp_path, monkeypatch, doi_chung):
    import audfprint_progress_runner as runner

    sys.path.insert(0, os.path.join(os.path.dirname(runner.__file__), "audfprint-master"))
    import hash_table

    dau = f"CON-WORKER-{uuid.uuid4().hex}"
    pid_file = tmp_path / "con.pid"
    monkeypatch.setattr(runner, "_worker_ghi_hash_table", _worker_hong_de_lai_con)
    ht = hash_table.HashTable(hashbits=4, depth=2, maxtime=16)
    con = None
    try:
        with pytest.raises(RuntimeError, match="lỗi giả lập"):
            runner.instrumented_multiproc_add(None, ht, [str(pid_file), dau],
                                              lambda _: None, 1)
        con = _cho_file(pid_file)
        assert _cho_chet(con, dau), "process con của worker còn sống sau khi runner lỗi"
        assert doi_chung.poll() is None
    finally:
        if con:
            _don(con, dau)
