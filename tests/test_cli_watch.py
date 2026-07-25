# -*- coding: utf-8 -*-
"""Test lệnh CLI watch mà không gọi mạng hoặc quét thật."""

from types import SimpleNamespace

import pytest

import cli
from watch import BaoCao, MucTheoDoi, WatchList


class _EngineGia:
    def __init__(self):
        self.config = SimpleNamespace(ncores=1)


class _ChannelSyncGia:
    ket_qua = {"tong": 2, "da_va": 1, "bo_qua": 1, "loi": []}
    kho = ""

    def __init__(self, kho):
        type(self).kho = kho

    def va_metadata(self, progress=None):
        return self.ket_qua


def test_cli_watch_khong_co_danh_sach_in_huong_dan(
    monkeypatch,
    capsys,
):
    duong_dan = []
    monkeypatch.setattr("sys.argv", ["cli.py", "watch"])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
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
    ):
        loi_goi.append((
            watchlist.gioi_han_moi_lan,
            progress,
            sheet_link,
            dang_ngang,
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
    monkeypatch.setattr(cli.watch, "doc_watchlist", lambda path: wl)
    monkeypatch.setattr(cli.watch, "chay_giam_sat", chay_gia)

    cli.main()

    assert loi_goi == [(5, cli.in_tien_do, "sheet-id", True)]
    assert "Quét mới: 1" in capsys.readouterr().out


def test_cli_watch_co_loi_thoat_ma_1_sau_khi_in_tom_tat(
    monkeypatch,
    capsys,
):
    wl = WatchList(muc=[MucTheoDoi("link", "https://youtu.be/dQw4w9WgXcQ")])
    monkeypatch.setattr("sys.argv", ["cli.py", "watch"])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
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
    assert "đã vá 1/2 mục metadata" in capsys.readouterr().out
