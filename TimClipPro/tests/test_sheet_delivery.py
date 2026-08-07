# -*- coding: utf-8 -*-
"""Giao Sheets không chặn quét, thử lại đúng loại lỗi, không ghi trùng."""

from __future__ import annotations

import threading
import time

import pytest

from sheet_delivery import (
    CHO_GUI,
    DA_GUI,
    THAT_BAI,
    SheetDelivery,
    SheetDeliveryWorker,
    khoa_giao_hang,
    phan_loai_loi,
)

HEADER = ["A", "B"]
ROWS = [["1", "2"]]


def _viec(key="k1", video="vid1"):
    return SheetDelivery(
        delivery_key=key, source_id=video, source_name="Video",
        header=HEADER, rows=ROWS, status=CHO_GUI,
    )


def _chay_xong(worker, timeout=15):
    han = time.monotonic() + timeout
    while worker.con_viec and time.monotonic() < han:
        time.sleep(0.01)
    worker.stop()


# ---------------------------------------------------------------------------
# Phân loại lỗi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("loi, thu_lai", [
    (RuntimeError("429 Too Many Requests"), True),
    (RuntimeError("503 Service Unavailable"), True),
    (TimeoutError("connection timed out"), True),
    (RuntimeError("Quota exceeded for quota metric"), True),
    (RuntimeError("PERMISSION_DENIED: caller lacks permission"), False),
    (RuntimeError("404 Not Found: spreadsheet"), False),
    (RuntimeError("invalid credential supplied"), False),
])
def test_phan_loai_loi(loi, thu_lai):
    assert phan_loai_loi(loi) is thu_lai


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_khoa_on_dinh_va_phan_biet_dung_ngu_nghia():
    goc = khoa_giao_hang("sheet", "ws", "ngang", 10, "vid", ROWS)

    assert goc == khoa_giao_hang("sheet", "ws", "ngang", 10, "vid", ROWS)
    # Quét lại cùng video -> job khác -> khoá khác -> ĐƯỢC ghi dòng mới.
    assert goc != khoa_giao_hang("sheet", "ws", "ngang", 11, "vid", ROWS)
    # Báo cáo khác định dạng -> khoá khác.
    assert goc != khoa_giao_hang("sheet", "ws", "doc", 10, "vid", ROWS)
    # Sheet/worksheet khác -> khoá khác.
    assert goc != khoa_giao_hang("sheet2", "ws", "ngang", 10, "vid", ROWS)
    assert goc != khoa_giao_hang("sheet", "ws2", "ngang", 10, "vid", ROWS)
    # Nội dung khác -> khoá khác.
    assert goc != khoa_giao_hang("sheet", "ws", "ngang", 10, "vid", [["9", "9"]])


def test_khong_gui_hai_lan_cung_mot_khoa():
    goi = []
    worker = SheetDeliveryWorker(lambda h, r: goi.append(r) or len(r))
    worker.start()

    assert worker.enqueue(_viec("same")) is True
    assert worker.enqueue(_viec("same")) is False, "Khoá trùng phải bị chặn"
    _chay_xong(worker)

    assert len(goi) == 1


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def test_thu_lai_loi_tam_thoi_roi_thanh_cong():
    lan = {"n": 0}

    def sender(header, rows):
        lan["n"] += 1
        if lan["n"] < 3:
            raise RuntimeError("503 Service Unavailable")
        return len(rows)

    worker = SheetDeliveryWorker(sender, max_attempts=5, sleep_fn=lambda s: None)
    worker.start()
    worker.enqueue(_viec())
    _chay_xong(worker)

    assert lan["n"] == 3
    assert worker.snapshot()["k1"].status == DA_GUI


def test_loi_vinh_vien_khong_thu_lai():
    lan = {"n": 0}

    def sender(header, rows):
        lan["n"] += 1
        raise RuntimeError("PERMISSION_DENIED")

    worker = SheetDeliveryWorker(sender, max_attempts=5, sleep_fn=lambda s: None)
    worker.start()
    worker.enqueue(_viec())
    _chay_xong(worker)

    assert lan["n"] == 1, "Lỗi vĩnh viễn mà vẫn thử lại là lãng phí quota"
    assert worker.snapshot()["k1"].status == THAT_BAI


def test_het_so_lan_thu_thi_dung_lai():
    lan = {"n": 0}

    def sender(header, rows):
        lan["n"] += 1
        raise RuntimeError("timeout")

    worker = SheetDeliveryWorker(sender, max_attempts=3, sleep_fn=lambda s: None)
    worker.start()
    worker.enqueue(_viec())
    _chay_xong(worker)

    assert lan["n"] == 3
    assert worker.snapshot()["k1"].status == THAT_BAI
    assert worker.tom_tat()["that_bai"] == 1


# ---------------------------------------------------------------------------
# Điều quan trọng nhất: Sheets không chặn quét
# ---------------------------------------------------------------------------

def test_sheets_cham_khong_lam_cham_luot_quet():
    """Sheets 0.3s/lần × 5 video = 1.5s nếu đồng bộ. enqueue phải ~tức thì."""
    def sender_cham(header, rows):
        time.sleep(0.3)
        return len(rows)

    worker = SheetDeliveryWorker(sender_cham)
    worker.start()

    bat_dau = time.monotonic()
    for i in range(5):
        worker.enqueue(_viec(f"k{i}", f"vid{i}"))
    thoi_gian_enqueue = time.monotonic() - bat_dau

    assert thoi_gian_enqueue < 0.2, (
        f"enqueue mất {thoi_gian_enqueue:.2f}s — scan worker đang bị Sheets chặn"
    )
    _chay_xong(worker, timeout=30)
    assert worker.tom_tat()["da_gui"] == 5


def test_sheets_sap_hoan_toan_van_khong_chan_va_khong_mat_trang_thai():
    worker = SheetDeliveryWorker(
        lambda h, r: (_ for _ in ()).throw(RuntimeError("connection reset")),
        max_attempts=2, sleep_fn=lambda s: None,
    )
    worker.start()
    for i in range(5):
        assert worker.enqueue(_viec(f"k{i}", f"vid{i}")) is True
    _chay_xong(worker, timeout=30)

    tom_tat = worker.tom_tat()
    assert tom_tat["tong"] == 5
    assert tom_tat["that_bai"] == 5
    assert tom_tat["da_gui"] == 0


def test_worker_khong_chet_vi_mot_viec_loi_la():
    """Sender ném BaseException lạ cũng không được làm chết thread."""
    lan = {"n": 0}

    def sender(header, rows):
        lan["n"] += 1
        if lan["n"] == 1:
            raise KeyError("lỗi lạ")
        return len(rows)

    worker = SheetDeliveryWorker(sender, max_attempts=2, sleep_fn=lambda s: None)
    worker.start()
    worker.enqueue(_viec("k1", "v1"))
    worker.enqueue(_viec("k2", "v2"))
    _chay_xong(worker, timeout=30)

    assert worker.snapshot()["k2"].status == DA_GUI, "Thread phải sống để làm việc sau"


def test_gui_dung_du_lieu_duoc_truyen():
    nhan = []
    worker = SheetDeliveryWorker(lambda h, r: nhan.append((h, r)) or len(r))
    worker.start()
    worker.enqueue(_viec())
    _chay_xong(worker)

    assert nhan == [(HEADER, ROWS)]


def test_stop_khong_treo_khi_khong_co_viec():
    worker = SheetDeliveryWorker(lambda h, r: len(r))
    worker.start()
    bat_dau = time.monotonic()
    worker.stop()
    assert time.monotonic() - bat_dau < 5


def test_enqueue_an_toan_tu_nhieu_thread():
    worker = SheetDeliveryWorker(lambda h, r: len(r))
    worker.start()

    def them(i):
        worker.enqueue(_viec(f"k{i}", f"v{i}"))

    ts = [threading.Thread(target=them, args=(i,)) for i in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=10)
    _chay_xong(worker, timeout=30)

    assert worker.tom_tat()["da_gui"] == 20
