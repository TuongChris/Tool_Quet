# -*- coding: utf-8 -*-
"""CLI khi YouTube chặn truy cập: mã thoát 3 (khác 1 = lỗi, 2 = bận), không traceback."""

import sys

import pytest

import cli
import truy_cap_youtube as t
import watch
from test_truy_cap_youtube_lo import _eng, _ma, _url
from ytdlp_gia import BOT, R429, YdlKichBan


def test_cli_youtube_bi_chan_thoat_ma_3_khong_traceback(tmp_path, monkeypatch, capsys):
    ydl = YdlKichBan(info={"*": BOT})
    e = _eng(tmp_path, monkeypatch, ydl)
    monkeypatch.setattr(cli, "Engine", lambda: e)
    monkeypatch.setattr(sys, "argv", ["cli.py", "youtube", _url(_ma(1)), _url(_ma(2))])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == cli.MA_THOAT_YOUTUBE_CHAN == 3
    ra = capsys.readouterr()
    assert "Traceback" not in ra.err + ra.out
    assert "Đã dừng yêu cầu mới tới YouTube" in ra.out + ra.err
    assert ydl.dem("info") == 1


def test_cli_watch_bi_chan_thoat_ma_3(tmp_path, monkeypatch):
    e = _eng(tmp_path, monkeypatch, YdlKichBan())
    monkeypatch.setattr(cli, "Engine", lambda: e)
    wl = tmp_path / "wl.json"
    wl.write_text('{"muc": [{"loai": "link", "url": "https://youtu.be/vid00000001"}]}',
                  encoding="utf-8")
    monkeypatch.setattr(watch, "chay_giam_sat", lambda *a, **k: watch.BaoCao(
        loi=["x"], chan_youtube="Đã dừng yêu cầu mới tới YouTube để tránh lặp lỗi xác minh."))
    monkeypatch.setattr(sys, "argv", ["cli.py", "watch", "--file", str(wl)])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 3


def test_cli_watch_ban_van_la_ma_2(tmp_path, monkeypatch):
    """Bận (tool.lock) giữ nguyên mã 2 — lịch chạy đang dựa vào nó."""
    e = _eng(tmp_path, monkeypatch, YdlKichBan())
    monkeypatch.setattr(cli, "Engine", lambda: e)
    wl = tmp_path / "wl.json"
    wl.write_text('{"muc": [{"loai": "link", "url": "https://youtu.be/vid00000001"}]}',
                  encoding="utf-8")
    monkeypatch.setattr(watch, "chay_giam_sat", lambda *a, **k: watch.BaoCao(
        loi=["bận"], ban=True))
    monkeypatch.setattr(sys, "argv", ["cli.py", "watch", "--file", str(wl)])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 2


def test_cli_kenh_liet_ke_bi_429_thoat_ma_3_khong_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(t.NGAN_SACH, "listing", t.NganSach(cho_tam_thoi=(0.01,),
                                                           cho_429=(0.01,)))

    def liet_ke(phien, url):
        phien.opts["logger"].error(R429.format(id="UCkenh"))
        return None

    e = _eng(tmp_path, monkeypatch, YdlKichBan(liet_ke=liet_ke))
    monkeypatch.setattr(cli, "Engine", lambda: e)
    kho = tmp_path / "kho_kenh"
    monkeypatch.setattr(sys, "argv", ["cli.py", "kenh", "https://www.youtube.com/@kenh",
                                      "--kho", str(kho)])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 3
    ra = capsys.readouterr()
    assert "Traceback" not in ra.err + ra.out and "giới hạn" in ra.err
