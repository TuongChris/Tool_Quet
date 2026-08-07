# -*- coding: utf-8 -*-
"""Test lệnh CLI watch mà không gọi mạng hoặc quét thật."""

from types import SimpleNamespace

import pytest

import cli
from watch import BaoCao, MucTheoDoi, WatchList


class _EngineGia:
    def __init__(self):
        self.config = SimpleNamespace(ncores=1)
        self.data_dir = ""


class _ChannelSyncGia:
    ket_qua = {
        "tong": 2, "da_va": 1, "bo_qua": 1, "da_them_tu_dia": 1, "loi": [],
    }
    kho = ""

    def __init__(self, kho):
        type(self).kho = kho

    def va_metadata(self, progress=None):
        return self.ket_qua


class _YeuCauDungGia:
    def __init__(self, engine=None, file_dung=""):
        self.engine = engine
        self.file_dung = file_dung

    def bat_tin_hieu(self):
        pass

    def don_file_dung(self):
        pass


def test_cli_watch_khong_co_danh_sach_in_huong_dan(
    monkeypatch,
    capsys,
):
    duong_dan = []
    monkeypatch.setattr("sys.argv", ["cli.py", "watch"])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    monkeypatch.setattr(cli, "YeuCauDung", _YeuCauDungGia)
    monkeypatch.setattr(
        cli.watch,
        "doc_watchlist",
        lambda path: duong_dan.append(path) or WatchList(),
    )

    cli.main()

    noi_dung = capsys.readouterr().out
    assert duong_dan == ["watchlist.json"]
    assert "Hãy tạo file watchlist.json theo mẫu" in noi_dung
    assert '"gioi_han_moi_lan": 20' in noi_dung


def test_cli_watch_chuyen_tham_so_va_in_tom_tat(monkeypatch, capsys):
    wl = WatchList(
        muc=[MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ")],
        gioi_han_moi_lan=20,
    )
    loi_goi = []

    def chay_gia(
        engine,
        watchlist,
        progress,
        lister=None,
        sheet_link="",
        dang_ngang=True,
        dung_lai=None,
    ):
        loi_goi.append((
            watchlist.gioi_han_moi_lan,
            progress,
            sheet_link,
            dang_ngang,
            dung_lai,
        ))
        return BaoCao(quet_moi=1)

    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "watch",
            "--file",
            "khac.json",
            "--sheet",
            "sheet-id",
            "--gioi-han",
            "5",
        ],
    )
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    monkeypatch.setattr(cli, "YeuCauDung", _YeuCauDungGia)
    monkeypatch.setattr(cli.watch, "doc_watchlist", lambda path: wl)
    monkeypatch.setattr(cli.watch, "chay_giam_sat", chay_gia)

    cli.main()

    assert len(loi_goi) == 1
    assert loi_goi[0][:4] == (5, cli.in_tien_do, "sheet-id", True)
    assert isinstance(loi_goi[0][4], _YeuCauDungGia)
    assert "Quét mới: 1" in capsys.readouterr().out


def test_cli_watch_co_loi_thoat_ma_1_sau_khi_in_tom_tat(
    monkeypatch,
    capsys,
):
    wl = WatchList(muc=[MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ")])
    monkeypatch.setattr("sys.argv", ["cli.py", "watch"])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    monkeypatch.setattr(cli, "YeuCauDung", _YeuCauDungGia)
    monkeypatch.setattr(cli.watch, "doc_watchlist", lambda path: wl)
    monkeypatch.setattr(
        cli.watch,
        "chay_giam_sat",
        lambda *args, **kwargs: BaoCao(loi=["Không có mạng"]),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert "Không có mạng" in capsys.readouterr().out


def test_cli_watch_dang_doc_tat_bao_cao_ngang(monkeypatch):
    wl = WatchList(muc=[MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ")])
    dang_ngang = []
    monkeypatch.setattr("sys.argv", ["cli.py", "watch", "--dang-doc"])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    monkeypatch.setattr(cli, "YeuCauDung", _YeuCauDungGia)
    monkeypatch.setattr(cli.watch, "doc_watchlist", lambda path: wl)
    monkeypatch.setattr(
        cli.watch,
        "chay_giam_sat",
        lambda *args, **kwargs: (
            dang_ngang.append(kwargs["dang_ngang"]) or BaoCao()
        ),
    )

    cli.main()

    assert dang_ngang == [False]


def test_cli_vameta_goi_dung_thu_muc_va_in_tom_tat(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["cli.py", "vameta", "--kho", "D:/KhoClipGoc"],
    )
    monkeypatch.setattr(cli, "ChannelSync", _ChannelSyncGia)
    monkeypatch.setattr(
        cli,
        "Engine",
        lambda: pytest.fail("Lệnh vameta không cần tạo Engine"),
    )

    cli.main()

    assert _ChannelSyncGia.kho == "D:/KhoClipGoc"
    ra = capsys.readouterr().out
    assert "đã vá 1/2 mục metadata" in ra
    assert "bổ sung 1 mục lấy từ tên file trên đĩa" in ra
