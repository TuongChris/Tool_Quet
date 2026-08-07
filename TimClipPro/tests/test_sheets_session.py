# -*- coding: utf-8 -*-
"""Dùng lại kết nối Google Sheets. Không gọi mạng — gspread giả đếm số lượt gọi."""

from __future__ import annotations

import threading

import pytest

import sheets
from sheets import SheetsExporter, xoa_cache_ket_noi

HEADER = ["A", "B"]
ROWS = [["1", "2"]]


class _Worksheet:
    def __init__(self, dem, noi_dung=None):
        self.dem = dem
        self.noi_dung = noi_dung if noi_dung is not None else []
        self.title = "KetQuaQuet"
        self.spreadsheet = type("S", (), {"title": "Bang"})()

    def get_values(self, o=None):
        self.dem["get_values"] += 1
        return [self.noi_dung[0]] if self.noi_dung else []

    def get_all_values(self):
        self.dem["get_all_values"] += 1
        return list(self.noi_dung)

    def append_row(self, row, value_input_option=None):
        self.dem["append_row"] += 1
        self.noi_dung.append(row)

    def append_rows(self, rows, value_input_option=None):
        self.dem["append_rows"] += 1
        self.noi_dung.extend(rows)


class _Spreadsheet:
    def __init__(self, dem, ws):
        self.dem = dem
        self._ws = ws

    def worksheet(self, ten):
        self.dem["worksheet"] += 1
        return self._ws

    def add_worksheet(self, title, rows, cols):
        return self._ws


class _Client:
    def __init__(self, dem, sh):
        self.dem = dem
        self._sh = sh

    def open_by_key(self, key):
        self.dem["open_by_key"] += 1
        return self._sh


@pytest.fixture()
def moi_truong(tmp_path, monkeypatch):
    import gspread

    xoa_cache_ket_noi()
    key = tmp_path / "google_key.json"
    key.write_text('{"client_email": "x@y.iam.gserviceaccount.com"}', encoding="utf-8")

    dem = {k: 0 for k in ("service_account", "open_by_key", "worksheet",
                          "get_values", "get_all_values", "append_row", "append_rows")}
    ws = _Worksheet(dem)
    sh = _Spreadsheet(dem, ws)

    def service_account(filename=None):
        dem["service_account"] += 1
        return _Client(dem, sh)

    monkeypatch.setattr(gspread, "service_account", service_account)
    yield {"key": str(key), "dem": dem, "ws": ws}
    xoa_cache_ket_noi()


def _exporter(moi_truong, sheet="abc123"):
    return SheetsExporter(key_path=moi_truong["key"], sheet=sheet)


# ---------------------------------------------------------------------------
# Điểm chính: dùng lại kết nối
# ---------------------------------------------------------------------------

def test_muoi_lan_append_chi_xac_thuc_va_mo_bang_mot_lan(moi_truong):
    dem = moi_truong["dem"]
    for _ in range(10):
        _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["service_account"] == 1, "Xác thực lại mỗi lần append là lãng phí"
    assert dem["open_by_key"] == 1
    assert dem["worksheet"] == 1
    assert dem["append_rows"] == 10, "Vẫn phải ghi đủ 10 lượt"


def test_khong_tai_toan_bo_bang_de_kiem_tra_header(moi_truong):
    dem = moi_truong["dem"]
    for _ in range(10):
        _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["get_all_values"] == 0, (
        "get_all_values() kéo về cả bảng — chi phí tăng theo số dòng đã tích luỹ"
    )
    assert dem["get_values"] == 1, "Chỉ cần đọc ô A1 đúng một lần cho cả phiên"


def test_header_chi_duoc_ghi_dung_mot_lan(moi_truong):
    dem = moi_truong["dem"]
    for _ in range(5):
        _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["append_row"] == 1
    assert moi_truong["ws"].noi_dung[0] == ["A", "B"]
    assert len(moi_truong["ws"].noi_dung) == 6      # 1 header + 5 dòng


def test_bang_da_co_header_thi_khong_ghi_them(moi_truong):
    moi_truong["ws"].noi_dung.append(["A", "B"])
    dem = moi_truong["dem"]

    _exporter(moi_truong).append(HEADER, ROWS)
    _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["append_row"] == 0
    assert dem["get_values"] == 1


# ---------------------------------------------------------------------------
# Cache phải mất hiệu lực đúng lúc
# ---------------------------------------------------------------------------

def test_doi_sheet_thi_mo_ket_noi_moi(moi_truong):
    dem = moi_truong["dem"]
    _exporter(moi_truong, "sheet_mot").append(HEADER, ROWS)
    _exporter(moi_truong, "sheet_hai").append(HEADER, ROWS)

    assert dem["open_by_key"] == 2


def test_doi_file_key_thi_xac_thuc_lai(moi_truong, tmp_path):
    import os
    import time

    dem = moi_truong["dem"]
    _exporter(moi_truong).append(HEADER, ROWS)
    time.sleep(0.01)
    os.utime(moi_truong["key"], None)          # giả lập thay khoá
    _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["service_account"] == 2, "Thay google_key.json phải xác thực lại"


def test_loi_khi_ghi_thi_bo_cache_de_lan_sau_ket_noi_lai(moi_truong, monkeypatch):
    dem = moi_truong["dem"]
    ws = moi_truong["ws"]
    goc = ws.append_rows
    lan = {"n": 0}

    def hong(rows, value_input_option=None):
        lan["n"] += 1
        if lan["n"] == 1:
            raise RuntimeError("connection reset")
        return goc(rows, value_input_option=value_input_option)

    monkeypatch.setattr(ws, "append_rows", hong)

    with pytest.raises(RuntimeError, match="connection reset"):
        _exporter(moi_truong).append(HEADER, ROWS)
    _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["service_account"] == 2, "Sau lỗi phải mở kết nối mới"


def test_khong_tu_thu_lai_append_de_tranh_ghi_trung(moi_truong, monkeypatch):
    """Ghi có thể đã tới Google rồi; thử lại ngay tại đây sẽ tạo dòng trùng."""
    ws = moi_truong["ws"]
    lan = {"n": 0}

    def hong(rows, value_input_option=None):
        lan["n"] += 1
        raise RuntimeError("503 Service Unavailable")

    monkeypatch.setattr(ws, "append_rows", hong)

    with pytest.raises(RuntimeError):
        _exporter(moi_truong).append(HEADER, ROWS)

    assert lan["n"] == 1, "sheets.append() không được tự thử lại"


# ---------------------------------------------------------------------------
# Tương thích và an toàn luồng
# ---------------------------------------------------------------------------

def test_lui_ve_get_all_values_khi_gspread_cu(moi_truong, monkeypatch):
    ws = moi_truong["ws"]
    monkeypatch.delattr(type(ws), "get_values", raising=False)
    monkeypatch.setattr(ws, "get_values", None, raising=False)

    _exporter(moi_truong).append(HEADER, ROWS)

    assert moi_truong["dem"]["get_all_values"] == 1


def test_rows_rong_khong_cham_toi_mang(moi_truong):
    assert _exporter(moi_truong).append(HEADER, []) == 0
    assert moi_truong["dem"]["service_account"] == 0


def test_chua_cau_hinh_thi_bao_loi_ro_rang(tmp_path):
    xoa_cache_ket_noi()
    ex = SheetsExporter(key_path=str(tmp_path / "khong_co.json"), sheet="abc")
    with pytest.raises(RuntimeError):
        ex.append(HEADER, ROWS)


def test_nhieu_thread_append_dong_thoi_van_dung_mot_ket_noi(moi_truong):
    dem = moi_truong["dem"]
    loi = []

    def chay():
        try:
            _exporter(moi_truong).append(HEADER, ROWS)
        except Exception as e:  # noqa: BLE001
            loi.append(e)

    ts = [threading.Thread(target=chay) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=15)

    assert not loi
    assert dem["service_account"] == 1
    assert dem["append_rows"] == 12


def test_kiem_tra_ket_noi_van_mo_moi_khong_dung_cache(moi_truong):
    """«Kiểm tra kết nối» phải thật sự chạm tới Google, không trả lời từ cache."""
    dem = moi_truong["dem"]
    _exporter(moi_truong).append(HEADER, ROWS)
    ok, _ = _exporter(moi_truong).kiem_tra()

    assert ok is True
    assert dem["service_account"] == 2


def test_cache_o_cap_module_nen_instance_moi_van_dung_lai(moi_truong):
    """app.py tạo SheetsExporter mới mỗi lần đẩy — cache theo instance sẽ vô dụng."""
    dem = moi_truong["dem"]
    a = _exporter(moi_truong)
    b = _exporter(moi_truong)
    assert a is not b

    a.append(HEADER, ROWS)
    b.append(HEADER, ROWS)

    assert dem["service_account"] == 1


def test_xoa_cache_buoc_ket_noi_lai(moi_truong):
    dem = moi_truong["dem"]
    _exporter(moi_truong).append(HEADER, ROWS)
    sheets.xoa_cache_ket_noi()
    _exporter(moi_truong).append(HEADER, ROWS)

    assert dem["service_account"] == 2
