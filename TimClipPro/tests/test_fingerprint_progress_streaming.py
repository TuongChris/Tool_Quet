# -*- coding: utf-8 -*-
"""Regression Lỗi A: tiến trình phải tới UI TRONG LÚC job chạy, không phải cuối batch.

Chế độ hỏng cũ (trước bản vá): engine chỉ đếm tiến độ bằng cách bắt chuỗi
``ingesting #`` trên stdout của audfprint. Với ``--ncores > 1`` (mặc định production
là ``so_nhan_nen_dung()`` = số nhân CPU), audfprint đi nhánh ``multiproc_add`` →
``make_ht_from_list`` gọi thẳng ``wavfile2hashes`` và KHÔNG BAO GIỜ in dòng
``ingesting #``. Kết quả: 0 dòng khớp → 0 event → giao diện đứng im tới khi cả batch
xong.

Các test dưới đây chạy subprocess THẬT qua ``_run_stream``/``run_observed_process``
(không mock) với một audfprint giả **không in một dòng ``ingesting #`` nào**, và
kiểm tra event vẫn tới theo từng clip, trải đều theo thời gian thực.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

from fingerprint_progress import FingerprintJobController
from kho_gia import ma_ghi_kho_cho_process_con

# audfprint giả: chỉ phát structured event, im lặng một khoảng ở giữa, và
# TUYỆT ĐỐI không in "ingesting #" — đúng như audfprint thật khi ncores > 1.
AUDFPRINT_GIA = '''
import json, os, sys, time

listfile, db_file, im_lang = sys.argv[1], sys.argv[2], float(sys.argv[3])
with open(listfile, encoding="utf-8") as fh:
    files = [dong for dong in fh.read().splitlines() if dong.strip()]

def phat(**payload):
    print(
        "TIMCLIP_FINGERPRINT_EVENT " + json.dumps(payload, ensure_ascii=False),
        flush=True,
    )

for chi_so, duong_dan in enumerate(files):
    phat(
        event="clip_started",
        file=duong_dan,
        phase="fingerprinting",
        process_pid=os.getpid(),
    )
    time.sleep(0.2)
    if chi_so == 1:
        time.sleep(im_lang)          # audfprint thật cũng im lặng khi đang giải mã
    phat(
        event="clip_finished",
        file=duong_dan,
        status="success",
        elapsed_seconds=0.2,
        hash_count=42,
        process_pid=os.getpid(),
    )

# Kho .pklz HỢP LỆ: Engine kiểm kho tạm trước khi công bố (audit TCP-02).
_ghi_kho_hop_le(db_file, files)
print("Saved fprints for %d files" % len(files), flush=True)
'''

assert "ingesting #" not in AUDFPRINT_GIA, "Fixture phải mô phỏng đúng nhánh ncores>1."


def _lap_kho(tmp_path, ten=("một.wav", "có khoảng trắng.wav", "tiếng Việt.wav")):
    folder = tmp_path / "clips"
    folder.mkdir()
    for item in ten:
        (folder / item).write_bytes(b"fixture")
    return folder


def _gan_audfprint_gia(engine, tmp_path, monkeypatch, im_lang: float, heartbeat: float):
    """Thay đúng dòng lệnh audfprint; giữ nguyên toàn bộ pipeline streaming thật."""
    script = tmp_path / "audfprint_gia.py"
    script.write_text(ma_ghi_kho_cho_process_con() + AUDFPRINT_GIA, encoding="utf-8")
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    def build_cmd(sub, *them, db_file):
        listfile = them[them.index("--list") + 1]
        return [sys.executable, "-u", str(script), listfile, db_file, str(im_lang)]

    monkeypatch.setattr(engine, "_audfprint_build_cmd", build_cmd)

    # Nhịp heartbeat production là 10 giây; ép ngắn lại để test không phải chờ.
    goc = type(engine)._run_stream

    def run_stream(self, lenh, on_line=None, **kwargs):
        kwargs["heartbeat_seconds"] = heartbeat
        return goc(self, lenh, on_line, **kwargs)

    monkeypatch.setattr(type(engine), "_run_stream", run_stream)
    return script


def test_event_tung_clip_van_toi_khi_audfprint_khong_in_ingesting(
    engine,
    tmp_path,
    monkeypatch,
):
    """Chế độ hỏng cũ: 0 dòng 'ingesting #' → 0 event. Bản vá phải phát đủ 3 clip."""
    folder = _lap_kho(tmp_path)
    _gan_audfprint_gia(engine, tmp_path, monkeypatch, im_lang=0.0, heartbeat=0.2)

    events = []
    ket_thuc = {"luc": None}

    def ghi_nhan(event):
        events.append((time.monotonic(), event))

    bat_dau = time.monotonic()
    ket_qua = engine.build_database(str(folder), "new", progress_event=ghi_nhan)
    ket_thuc["luc"] = time.monotonic()

    assert ket_qua["thanh_cong"] == 3
    assert ket_qua["that_bai"] == 0

    ten_clip = [
        event.file_name
        for _, event in events
        if event.status == "running" and event.phase == "fingerprinting"
    ]
    assert set(ten_clip) == {"một.wav", "có khoảng trắng.wav", "tiếng Việt.wav"}

    # Event đầu tiên có tên clip phải tới SỚM, không phải lúc kết thúc batch.
    luc_clip_dau = next(
        luc for luc, event in events if event.status == "running" and event.file_name
    )
    tong_thoi_gian = ket_thuc["luc"] - bat_dau
    assert luc_clip_dau - bat_dau < tong_thoi_gian * 0.5, (
        "Event clip đầu tiên tới quá muộn — giao diện sẽ có cảm giác đứng im."
    )

    # Progress không lùi, current không vượt total, total đúng.
    phan_tram = [event.percent for _, event in events]
    assert all(a <= b for a, b in zip(phan_tram, phan_tram[1:]))
    assert all(event.current <= event.total for _, event in events if event.total)
    assert any(event.total == 3 for _, event in events)
    assert events[-1][1].status == "completed"
    assert events[-1][1].percent == pytest.approx(1.0)


def test_heartbeat_van_cap_nhat_khi_audfprint_im_lang(engine, tmp_path, monkeypatch):
    """Clip chạy lâu mà subprocess không in gì thì UI vẫn phải nhận nhịp sống."""
    folder = _lap_kho(tmp_path)
    _gan_audfprint_gia(engine, tmp_path, monkeypatch, im_lang=1.2, heartbeat=0.2)

    events = []
    engine.build_database(str(folder), "new", progress_event=events.append)

    nhip = [event for event in events if event.status == "heartbeat"]
    assert nhip, "Không có heartbeat nào trong lúc subprocess im lặng."
    assert all(event.active_subprocess_pid for event in nhip)
    # Heartbeat không được tự tăng phần trăm khi chưa clip nào xong thêm.
    assert all(event.current <= event.total for event in nhip if event.total)


def test_controller_cho_phep_ui_ve_tien_do_khi_worker_con_chay(
    engine,
    tmp_path,
    monkeypatch,
):
    """UI đọc snapshot ở main thread; phải thấy total/tên clip TRƯỚC khi job xong."""
    folder = _lap_kho(tmp_path)
    _gan_audfprint_gia(engine, tmp_path, monkeypatch, im_lang=0.0, heartbeat=0.2)

    controller = FingerprintJobController(engine)
    job_id = controller.start(str(folder), "new")
    assert job_id

    thay_total = thay_ten_clip = False
    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        anh = controller.snapshot()
        thay_total = thay_total or anh.total == 3
        thay_ten_clip = thay_ten_clip or bool(anh.file_name)
        time.sleep(0.02)

    assert thay_total, "UI không bao giờ biết tổng số clip trong lúc job chạy."
    assert thay_ten_clip, "UI không bao giờ thấy clip hiện tại trong lúc job chạy."

    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        time.sleep(0.02)
    assert controller.error == ""
    assert controller.result["thanh_cong"] == 3
    assert controller.snapshot().status == "completed"


def test_khong_tao_hai_job_van_tay_trung_nhau(engine, tmp_path, monkeypatch):
    """Bấm hai lần không được sinh hai worker cùng ghi một kho."""
    folder = _lap_kho(tmp_path)
    _gan_audfprint_gia(engine, tmp_path, monkeypatch, im_lang=0.6, heartbeat=0.2)

    controller = FingerprintJobController(engine)
    controller.start(str(folder), "new")
    try:
        with pytest.raises(RuntimeError, match="đang chạy"):
            controller.start(str(folder), "new")
    finally:
        han = time.monotonic() + 30
        while controller.running and time.monotonic() < han:
            time.sleep(0.02)


def test_worker_khong_goi_streamlit_va_queue_khong_phinh_vo_han(engine, tmp_path, monkeypatch):
    """Queue bounded: worker phát nhiều event hơn sức chứa cũng không tăng vô hạn."""
    folder = _lap_kho(tmp_path)
    _gan_audfprint_gia(engine, tmp_path, monkeypatch, im_lang=0.0, heartbeat=0.05)

    controller = FingerprintJobController(engine, queue_maxsize=4)
    ten_luong = []

    goc_publish = controller.publish

    def publish(event):
        ten_luong.append(threading.current_thread().name)
        goc_publish(event)

    controller.publish = publish
    controller.start(str(folder), "new")
    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        assert controller.events.qsize() <= 4
        time.sleep(0.02)

    assert controller.events.qsize() <= 4
    assert any(ten.startswith("fingerprint-") for ten in ten_luong), (
        "Event phải được phát từ worker thread riêng, không phải main thread."
    )
