# -*- coding: utf-8 -*-
"""Streaming result + workspace riêng từng lượt quét. Không mạng, không audio thật."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from engine import ScanResult
from scan_jobs import (
    PHASE_SO_KHOP,
    PHASE_TAI,
    QUET_LOI,
    QUET_XONG,
    ScanJobController,
    doan_phase,
)


def _gia_lap_scan(engine, monkeypatch, ket_qua_theo_url: dict, cham: float = 0.0):
    """Thay scan_youtube bằng bản giả có phát tiến độ theo đúng thứ tự phase thật."""

    def scan_youtube(url, progress=None, luu_lich_su=True):
        for pct, msg in (
            (0.02, "Đang lấy thông tin video..."),
            (0.20, "Đang tải audio..."),
            (0.50, "Đang cắt khúc 1/2 (mốc 00:00:00)..."),
            (0.80, "Đang so khớp vân tay... khúc 1/2"),
        ):
            if progress:
                progress(pct, msg)
            if cham:
                time.sleep(cham)
        kq = ket_qua_theo_url[url]
        if progress:
            progress(1.0, "Xong — chọn kết quả tốt nhất.")
        return kq

    monkeypatch.setattr(engine, "scan_youtube", scan_youtube)


def _kq(name, source_id, matches=0, loi=False):
    r = ScanResult(source_name=name, source_ref=f"https://youtu.be/{source_id}")
    r.source_id = source_id
    r.matches = [object()] * matches
    r.so_dat_nguong = matches
    if loi:
        r.status, r.note = "error", "video riêng tư"
    return r


# ---------------------------------------------------------------------------
# scan_iter — nền tảng streaming
# ---------------------------------------------------------------------------

def test_scan_iter_tra_ket_qua_ngay_khong_cho_het_batch(engine, monkeypatch):
    urls = [f"u{i}" for i in range(1, 6)]
    _gia_lap_scan(engine, monkeypatch, {u: _kq(u, u) for u in urls})

    nhan_duoc = []
    for i, kq in enumerate(engine.scan_iter(urls, "youtube"), 1):
        nhan_duoc.append(kq.source_id)
        # Đang ở giữa batch mà đã có kết quả — đây chính là điều cần chứng minh.
        if i == 1:
            assert len(nhan_duoc) == 1

    assert nhan_duoc == urls


def test_scan_iter_goi_on_video_ngay_sau_moi_video(engine, monkeypatch):
    urls = ["a", "b", "c"]
    _gia_lap_scan(engine, monkeypatch, {u: _kq(u, u) for u in urls})
    goi = []

    list(engine.scan_iter(
        urls, "youtube",
        on_video=lambda i, tong, kq: goi.append((i, tong, kq.source_id)),
    ))

    assert goi == [(1, 3, "a"), (2, 3, "b"), (3, 3, "c")]


def test_loi_trong_on_video_khong_lam_hong_luot_quet(engine, monkeypatch):
    """Giao Sheets hỏng không được phép làm mất kết quả quét."""
    urls = ["a", "b"]
    _gia_lap_scan(engine, monkeypatch, {u: _kq(u, u) for u in urls})

    def no_tung(i, tong, kq):
        raise RuntimeError("Sheets sập")

    ket = list(engine.scan_iter(urls, "youtube", on_video=no_tung))

    assert [k.source_id for k in ket] == urls


def test_scan_many_van_giu_nguyen_hop_dong(engine, monkeypatch):
    urls = ["a", "b"]
    _gia_lap_scan(engine, monkeypatch, {u: _kq(u, u) for u in urls})

    ket = engine.scan_many(urls, "youtube")

    assert isinstance(ket, list)
    assert [k.source_id for k in ket] == urls


# ---------------------------------------------------------------------------
# Workspace riêng — lỗi đúng/sai nghiêm trọng nhất
# ---------------------------------------------------------------------------

def test_moi_luot_quet_co_workspace_rieng(engine):
    with engine.scan_workspace() as a, engine.scan_workspace() as b:
        assert a != b
        assert Path(a, "chunks").is_dir()
        assert Path(b, "chunks").is_dir()
        Path(a, "chunks", "x.wav").write_bytes(b"a")
        Path(b, "chunks", "x.wav").write_bytes(b"b")
        assert Path(a, "chunks", "x.wav").read_bytes() == b"a"
        assert Path(b, "chunks", "x.wav").read_bytes() == b"b"


def test_workspace_duoc_don_sach_ke_ca_khi_loi(engine):
    with pytest.raises(RuntimeError):
        with engine.scan_workspace() as ws:
            duong_dan = Path(ws)
            assert duong_dan.is_dir()
            raise RuntimeError("hỏng giữa chừng")
    assert not duong_dan.exists()


def test_hai_luot_quet_song_song_khong_xoa_chunk_cua_nhau(engine):
    """Trước bản vá, _cut_chunks rmtree thư mục CHUNG ngay đầu hàm."""
    ket = {}
    bat_dau = threading.Barrier(2)

    def chay(ten):
        with engine.scan_workspace() as ws:
            f = Path(ws, "chunks", "chunk_0000000.wav")
            f.write_bytes(ten.encode())
            bat_dau.wait(timeout=10)      # ép hai luồng chồng nhau
            time.sleep(0.05)
            ket[ten] = f.read_bytes() if f.exists() else None

    t = [threading.Thread(target=chay, args=(n,)) for n in ("A", "B")]
    for x in t:
        x.start()
    for x in t:
        x.join(timeout=20)

    assert ket == {"A": b"A", "B": b"B"}


# ---------------------------------------------------------------------------
# Suy phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg, phase", [
    ("Đang tải audio... 45%", PHASE_TAI),
    ("Đang so khớp vân tay... khúc 3/5", PHASE_SO_KHOP),
    ("Thông báo lạ không khớp gì", None),
])
def test_doan_phase(msg, phase):
    assert doan_phase(msg) == phase


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

def test_controller_ui_thay_tien_do_va_ket_qua_giua_chung(engine, monkeypatch):
    urls = ["a", "b", "c"]
    _gia_lap_scan(engine, monkeypatch, {u: _kq(u, u, matches=2) for u in urls}, cham=0.05)
    controller = ScanJobController(engine)
    controller.start(urls, "youtube")

    thay_dang_chay = thay_ket_qua_som = False
    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        anh = controller.snapshot()
        if anh.current_index >= 1 and anh.videos[anh.current_index - 1].phase != "queued":
            thay_dang_chay = True
        if controller.results() and anh.completed < anh.total:
            thay_ket_qua_som = True
        time.sleep(0.01)

    assert thay_dang_chay, "UI không bao giờ thấy video đang chạy"
    assert thay_ket_qua_som, "Kết quả chỉ xuất hiện khi cả batch xong"

    anh = controller.snapshot()
    assert anh.completed == 3 and anh.failed == 0
    assert anh.batch_progress == pytest.approx(1.0)
    assert [v.matches for v in anh.videos] == [2, 2, 2]


def test_mot_video_loi_khong_lam_mat_ca_batch(engine, monkeypatch):
    urls = ["a", "b", "c"]
    _gia_lap_scan(engine, monkeypatch, {
        "a": _kq("a", "a", matches=1),
        "b": _kq("b", "b", loi=True),
        "c": _kq("c", "c", matches=3),
    })
    controller = ScanJobController(engine)
    controller.start(urls, "youtube")
    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        time.sleep(0.01)

    anh = controller.snapshot()
    assert anh.completed == 2
    assert anh.failed == 1
    assert [v.scan_status for v in anh.videos] == [QUET_XONG, QUET_LOI, QUET_XONG]
    assert len(controller.results()) == 3


def test_khong_tao_hai_batch_trung_nhau(engine, monkeypatch):
    _gia_lap_scan(engine, monkeypatch, {"a": _kq("a", "a")}, cham=0.2)
    controller = ScanJobController(engine)
    controller.start(["a"], "youtube")
    try:
        with pytest.raises(RuntimeError, match="không tạo batch trùng"):
            controller.start(["a"], "youtube")
    finally:
        han = time.monotonic() + 30
        while controller.running and time.monotonic() < han:
            time.sleep(0.01)
