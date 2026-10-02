# -*- coding: utf-8 -*-
"""Watch phải quét bằng ĐÚNG kho được yêu cầu (audit TCP-08) và lọc lịch sử theo kho
đó (TCP-07).

Không mở được kho yêu cầu thì dừng cả lượt TRƯỚC khi liệt kê/tải/quét/xuất/đẩy Sheets
— không lẳng lặng dùng kho đang chọn trước đó. Engine, sổ đăng ký kho và SQLite là
thật; chỉ thay liệt kê kênh, quét một video và Google Sheets bằng bản đếm lượt gọi.
"""

import hashlib
import sys
from types import SimpleNamespace

import pytest

import cli
import watch
from engine import Engine, ScanResult
from kho_gia import ghi_kho
from watch import MucTheoDoi, WatchList, chay_giam_sat


def _sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _eng(tmp_path) -> Engine:
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    for ten in ("A", "B"):
        thu_muc = tmp_path / f"nguon_{ten}"
        thu_muc.mkdir(exist_ok=True)
        e.add_kho(ten, str(thu_muc))
        ghi_kho(e.db_file, [(str(thu_muc / "goc.opus"), 9)])
    e.use_kho("A")
    return e


class _Dem:
    def __init__(self):
        self.liet_ke = 0
        self.quet = []
        self.xuat = 0
        self.sheets = 0


def _gan_dem(e, monkeypatch, dem: _Dem, video_id="vid00000001"):
    def lister(url, limit=None):
        dem.liet_ke += 1
        return [SimpleNamespace(id=video_id, title="Video", url=f"https://youtu.be/{video_id}")]

    def quet(url, progress=None):
        dem.quet.append((url, e.kho_dang_dung))
        return ScanResult(source_name=url, source_ref=url, source_id=video_id,
                          duration_s=300.0, vung_da_khop=[(0.0, 300.0)])

    def xuat(ket):
        dem.xuat += 1
        return "ket_qua.csv"

    class SheetsDem:
        def __init__(self, sheet=""):
            pass

        def san_sang(self):
            return True

        def append(self, header, rows):
            dem.sheets += 1
            return len(rows)

    monkeypatch.setattr(e, "scan_youtube", quet)
    monkeypatch.setattr(e, "export_csv_ngang", xuat)
    monkeypatch.setattr(e, "export_csv", xuat)
    monkeypatch.setattr(watch, "SheetsExporter", SheetsDem)
    return lister


@pytest.mark.parametrize("ten_kho", ["Kho không tồn tại", "a"])
def test_khong_mo_duoc_kho_yeu_cau_thi_dung_truoc_moi_thao_tac(tmp_path, monkeypatch,
                                                                ten_kho):
    e = _eng(tmp_path)
    dem = _Dem()
    lister = _gan_dem(e, monkeypatch, dem)
    so_dang_ky = _sha(e.kho_file)
    lich_su = _sha(e.sqlite_file)
    wl = WatchList(muc=[MucTheoDoi("kenh", "kenh-1")], kho=ten_kho)

    bc = chay_giam_sat(e, wl, lister=lister, sheet_link="sheet-gia")

    assert dem.liet_ke == 0 and dem.quet == [] and dem.xuat == 0 and dem.sheets == 0
    assert bc.quet_moi == 0 and not bc.csv_path and bc.sheets_so_dong == 0
    assert any(ten_kho in dong and "dừng" in dong.lower() for dong in bc.loi), bc.loi
    assert e.kho_dang_dung == "A"
    assert _sha(e.kho_file) == so_dang_ky
    assert _sha(e.sqlite_file) == lich_su


def test_watch_quet_bang_dung_kho_yeu_cau(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    dem = _Dem()
    lister = _gan_dem(e, monkeypatch, dem)

    chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "kenh-1")], kho="B"),
                  lister=lister)

    assert [kho for _, kho in dem.quet] == ["B"]


def test_watch_loc_lich_su_theo_kho_A_roi_B(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.save_job(ScanResult(source_name="Đã quét ở A", source_id="vid00000001",
                          duration_s=300.0, vung_da_khop=[(0.0, 300.0)]), "youtube")
    dem = _Dem()
    lister = _gan_dem(e, monkeypatch, dem)

    bc_a = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")], kho="A"),
                         lister=lister)
    assert dem.quet == [] and bc_a.da_quet_truoc == 1, "cùng kho A: được bỏ qua"

    bc_b = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")], kho="B"),
                         lister=lister)
    assert [kho for _, kho in dem.quet] == ["B"], "kho B chưa từng kiểm video này"
    assert bc_b.da_quet_truoc == 0


def test_quet_lai_chu_dong_khong_xoa_lich_su(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.save_job(ScanResult(source_name="Đã quét ở A", source_id="vid00000001",
                          duration_s=300.0, vung_da_khop=[(0.0, 300.0)]), "youtube")
    so_job = len(e.list_jobs())
    dem = _Dem()
    lister = _gan_dem(e, monkeypatch, dem)

    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")], kho="A"),
                       lister=lister, quet_lai=True)

    assert [kho for _, kho in dem.quet] == ["A"]
    assert bc.da_quet_truoc == 0
    assert len(e.list_jobs()) == so_job, "quét lại chủ động không được xoá lịch sử"


class _EngineCli:
    def __init__(self):
        self.config = SimpleNamespace(ncores=1)
        self.data_dir = ""


class _YeuCauDungGia:
    def __init__(self, engine=None, file_dung=""):
        pass

    def bat_tin_hieu(self):
        pass

    def don_file_dung(self):
        pass


def test_cli_watch_co_co_quet_lai(monkeypatch):
    wl = WatchList(muc=[MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ")])
    goi = []
    monkeypatch.setattr(sys, "argv", ["cli.py", "watch", "--quet-lai"])
    monkeypatch.setattr(cli, "Engine", _EngineCli)
    monkeypatch.setattr(cli, "YeuCauDung", _YeuCauDungGia)
    monkeypatch.setattr(cli.watch, "doc_watchlist", lambda path: wl)
    monkeypatch.setattr(cli.watch, "chay_giam_sat",
                        lambda *a, **k: goi.append(k.get("quet_lai")) or watch.BaoCao())

    cli.main()

    assert goi == [True]
