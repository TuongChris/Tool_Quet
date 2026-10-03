# -*- coding: utf-8 -*-
"""`python cli.py youtube-doctor` — chẩn đoán chỉ đọc; mặc định KHÔNG gọi mạng, không in cookie."""

import json
import sys

import pytest
import yt_dlp

import cli
import youtube_doctor
from ytdlp_gia import BOT, YdlKichBan, info_mau

BI_MAT = "GIA_TRI_BI_MAT_GIA_d0c7"


def _data(tmp_path, cookie_noi_dung=None):
    data = tmp_path / "data"
    data.mkdir()
    cfg = {"network_timeout_s": 45, "ytdlp_sleep_requests_s": 1.0,
           "ytdlp_player_clients": ["", "android", "tv"]}
    if cookie_noi_dung is not None:
        p = tmp_path / "cookies.txt"
        p.write_text(cookie_noi_dung, encoding="utf-8")
        cfg["ytdlp_cookiefile"] = str(p)
    (data / "cau_hinh.json").write_text(json.dumps(cfg), encoding="utf-8")
    return str(data)


_COOKIE = ("# Netscape HTTP Cookie File\n"
           + "\t".join([".youtube.com", "TRUE", "/", "TRUE", "9999999999", "LOGIN_INFO",
                        BI_MAT]) + "\n"
           + "\t".join([".youtube.com", "TRUE", "/", "TRUE", "9999999999", "SAPISID",
                        BI_MAT]) + "\n")


def test_mac_dinh_khong_goi_mang_va_khong_lo_cookie(tmp_path, monkeypatch, capsys):
    ydl = YdlKichBan()
    monkeypatch.setattr(yt_dlp, "YoutubeDL", ydl)
    data = _data(tmp_path, _COOKIE)
    kq = youtube_doctor.chan_doan(data)
    assert ydl.goi == [] and ydl.opts == [], "mặc định không mở phiên yt-dlp nào"
    assert kq["mang"]["da_goi"] is False and kq["google"] == "không gọi"
    assert kq["yt_dlp"]["phien_ban"] and "js_runtime" in kq
    assert kq["cookie"]["cau_truc_hop_le"] and kq["cookie"]["co_cookie_dang_nhap"]
    assert kq["cau_hinh_mang"]["network_timeout_s"] == 45
    ma = youtube_doctor.chay(data)
    ra = capsys.readouterr().out
    assert ma == 0 and BI_MAT not in ra and BI_MAT not in json.dumps(kq, ensure_ascii=False)
    for ten in ("LOGIN_INFO", "SAPISID"):
        assert ten not in ra


def test_kiem_mang_chi_khi_nguoi_dung_yeu_cau_va_chi_mot_request(tmp_path, monkeypatch):
    ydl = YdlKichBan(info={"*": lambda _p, m: info_mau(m)})
    monkeypatch.setattr(yt_dlp, "YoutubeDL", ydl)
    kq = youtube_doctor.chan_doan(_data(tmp_path), url_mang="https://youtu.be/vid00000001")
    assert ydl.dem("info") == 1
    assert kq["mang"]["da_goi"] is True and kq["mang"]["ket_qua"] == "OK"


def test_kiem_mang_bi_bot_check_bao_dung_loai_va_ma_3(tmp_path, monkeypatch, capsys):
    ydl = YdlKichBan(info={"*": BOT})
    monkeypatch.setattr(yt_dlp, "YoutubeDL", ydl)
    data = _data(tmp_path)
    ma = youtube_doctor.chay(data, url_mang="https://youtu.be/vid00000001")
    assert ma == 3 and ydl.dem("info") == 1
    assert "BOT_CHALLENGE" in capsys.readouterr().out


def test_cli_goi_youtube_doctor_khong_dung_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMCLIP_DATA_DIR", _data(tmp_path))
    monkeypatch.setattr(cli, "Engine", lambda: pytest.fail("không được dựng Engine"))
    monkeypatch.setattr(yt_dlp, "YoutubeDL", YdlKichBan())
    monkeypatch.setattr(sys, "argv", ["cli.py", "youtube-doctor"])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 0
