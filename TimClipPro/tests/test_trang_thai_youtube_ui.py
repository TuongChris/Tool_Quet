# -*- coding: utf-8 -*-
"""Giao diện «Trạng thái YouTube»: câu chữ thuần + AppTest (không lộ cookie, không gọi mạng)."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

import scan_ui
import truy_cap_youtube as t
from engine import ScanResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"
BI_MAT = "GIA_TRI_BI_MAT_GIA_ui42"
_DONG = "\t".join([".youtube.com", "TRUE", "/", "TRUE", "9999999999", "{ten}", BI_MAT]) + "\n"


def _cookie(tmp_path, dang_nhap=True, hong=False):
    noi_dung = "# Netscape HTTP Cookie File\n" + _DONG.format(ten="PREF")
    if dang_nhap:
        noi_dung += _DONG.format(ten="LOGIN_INFO") + _DONG.format(ten="SAPISID")
    if hong:
        noi_dung += f".youtube.com TRUE / TRUE 0 SID {BI_MAT}\n"
    p = tmp_path / "cookies.txt"
    p.write_text(noi_dung, encoding="utf-8")
    return str(p)


def _chu(dong):
    return " ".join(cau for _muc, cau in dong)


def test_chua_cau_hinh_cookie():
    dong = scan_ui.dong_trang_thai_youtube(t.chan_doan_cookie(""))
    assert ("info", "Cookie: chưa cấu hình.") in dong


def test_cookie_dung_cau_truc_noi_ro_chua_chac_con_duoc_chap_nhan(tmp_path):
    dong = scan_ui.dong_trang_thai_youtube(t.chan_doan_cookie(_cookie(tmp_path)))
    muc, cau = dong[-1]
    assert muc == "success" and "đúng cấu trúc" in cau and "chưa chắc" in cau
    assert BI_MAT not in _chu(dong) and "LOGIN_INFO" not in _chu(dong)


def test_cookie_sai_cau_truc_bao_loi(tmp_path):
    dong = scan_ui.dong_trang_thai_youtube(t.chan_doan_cookie(_cookie(tmp_path, hong=True)))
    assert dong[-1][0] == "error" and "dòng" in dong[-1][1]
    assert BI_MAT not in _chu(dong)


def test_cookie_tu_trinh_duyet_khong_mo_profile():
    dong = scan_ui.dong_trang_thai_youtube(t.chan_doan_cookie("", cookies_browser="edge"))
    assert dong[-1][0] == "info" and "trình duyệt" in dong[-1][1]


def test_lan_chay_cuoi_bi_chan_hien_dau_tien():
    p = t.PhienYouTube()
    p.ghi_loi(RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot"))
    dong = scan_ui.dong_trang_thai_youtube(t.chan_doan_cookie(""), p)
    assert dong[0][0] == "error" and "Đã dừng yêu cầu mới tới YouTube" in dong[0][1]


def test_lan_chay_cuoi_cookie_bi_tu_choi():
    p = t.PhienYouTube()
    p.ghi_lui_cookie()
    dong = scan_ui.dong_trang_thai_youtube(t.chan_doan_cookie(""), p)
    assert dong[0][0] == "warning" and "không được YouTube chấp nhận" in dong[0][1]


def test_thong_bao_lo_bi_chan_lay_tu_ket_qua():
    p = t.PhienYouTube()
    p.ghi_loi(RuntimeError("ERROR: [youtube] x: HTTP Error 429: Too Many Requests"))
    bo_qua = ScanResult(source_name="u2", status="error", loi_truy_cap=p.bo_qua("u2"))
    ok = ScanResult(source_name="u1")
    assert "Đã dừng yêu cầu mới tới YouTube" in scan_ui.thong_bao_youtube_chan([ok, bo_qua])
    assert scan_ui.thong_bao_youtube_chan([ok]) == ""


def test_app_hien_trang_thai_youtube_khong_lo_cookie(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    (data_dir / "cau_hinh.json").write_text(json.dumps(
        {"ytdlp_cookiefile": _cookie(tmp_path)}), encoding="utf-8")
    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception
    chu = " ".join(str(getattr(x, "value", "")) for x in
                   [*at.sidebar.markdown, *at.sidebar.caption, *at.sidebar.success,
                    *at.sidebar.info, *at.sidebar.warning, *at.sidebar.error])
    assert "Trạng thái YouTube" in chu and "đúng cấu trúc" in chu
    tat_ca = " ".join(str(getattr(x, "value", "")) for x in at.main) + chu
    assert BI_MAT not in tat_ca
