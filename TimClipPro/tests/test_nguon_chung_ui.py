# -*- coding: utf-8 -*-
"""Giao diện chế độ «một video gốc chung cho cả lô»: helper thuần + smoke Streamlit."""

from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

import common_original as co
from common_original_jobs import CommonOriginalJobController, VideoNguonChung, xuat_csv
from engine import Config, Match
from scan_ui import build_nguon_chung_status_dataframe, csv_nguon_chung, df_nguon_chung

APP_PY = Path(__file__).resolve().parents[1] / "app.py"
A, B = "A [aaaaaaaaaaa].opus", "B [bbbbbbbbbbb].opus"


def M(clip, start=0.0, hashes=6000, matched=300.0, ty_le=50.0):
    return Match(clip=clip, start_s=start, end_s=start + matched, matched_s=matched,
                 clip_offset_s=12.0, hashes=hashes, confidence="x", ty_le=ty_le,
                 clip_bat_dau_s=start, vung_khop_s=start)


def _kql(tim_thay=True):
    vids = []
    for i, clips in enumerate(([A, B], [A], [A] if tim_thay else [B]), 1):
        v = co.VideoTrongLo(thu_tu=i, nguon=f"https://youtu.be/vid0000000{i}",
                            ma=f"vid0000000{i}", tieu_de=f"=Video {i}", kenh="Kênh",
                            thoi_luong=3600.0)
        v.luot.append(co.LuotQuet(muc_tieu="collect", hop_le=True, tron=True,
                                  ung_vien=tuple(M(c, 100.0 * i) for c in clips),
                                  pham_vi="đã so khớp 01:00:00/01:00:00"))
        vids.append(v)
    tt = co.TrangThaiLo(kho_id="k", videos=vids, cfg=Config())
    kl = co.ket_luan(tt)
    return co.dung_ket_qua_lo(
        tt, kl, ma_lo="lo-thu", kho_ten="Kho SML",
        thong_tin_goc={"title": "Video gốc thử", "url": "https://youtu.be/aaaaaaaaaaa",
                       "upload_date": "20250102", "duration": 600.0},
        dem_ten={}, so_lieu={"so_luot": 3, "luot_tron": 3, "luot_mot_phan": 0,
                             "thoi_gian_s": 12.5})


# ---------------------------------------------------------------------------
#  Helper thuần
# ---------------------------------------------------------------------------

def test_bang_trang_thai_luc_chay_co_schema_chuoi_on_dinh():
    rong = build_nguon_chung_status_dataframe([])
    assert list(rong.columns) and all(str(t) == "string" for t in rong.dtypes)
    df = build_nguon_chung_status_dataframe([
        VideoNguonChung(thu_tu=1, nguon="u1", tieu_de="Video 1", so_luot=1,
                        trang_thai=co.CO_MAT, dang_quet=False, pham_vi="trọn"),
        VideoNguonChung(thu_tu=2, nguon="u2", so_luot=0, dang_quet=True)])
    assert df.iloc[0]["Video gốc đang xét"] == "Có mặt"
    assert df.iloc[1]["Video"].startswith("⏳")


def test_bang_ket_qua_cot_so_dung_kieu_va_hien_nguyen_van_tieu_de():
    df = df_nguon_chung(_kql())
    assert len(df) == 3
    assert str(df["Số hash khớp"].dtype) == "Int64"
    assert df.iloc[0]["Video vi phạm"] == "=Video 1", "bảng UI hiện nguyên văn"


def test_csv_chan_cong_thuc_bang_tinh_va_co_bom():
    b = csv_nguon_chung(_kql())
    assert b.startswith("﻿".encode("utf-8"))
    df = pd.read_csv(io.BytesIO(b), encoding="utf-8-sig")
    assert df.iloc[0]["Video vi phạm"].startswith("'=")


def test_xuat_csv_khong_ghi_de_file_cu(tmp_path):
    p1 = xuat_csv(_kql(), str(tmp_path))
    p2 = xuat_csv(_kql(), str(tmp_path))
    assert p1 != p2 and Path(p1).exists() and Path(p2).exists()


# ---------------------------------------------------------------------------
#  Smoke Streamlit
# ---------------------------------------------------------------------------

def _van_ban(at) -> str:
    phan = []
    for nhom in (at.markdown, at.info, at.caption, at.warning, at.error, at.success,
                 at.header, at.subheader):
        phan.extend(str(i.value) for i in nhom)
    phan.extend(str(i.label) for i in at.metric)
    phan.extend(str(i.value) for i in at.metric)
    return "\n".join(phan)


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception
    return at


def _radio(at):
    return next(r for r in at.radio if r.label == "Cách chọn kết quả")


def test_mac_dinh_van_la_moi_video_tu_chon(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    assert _radio(at).value == "Mỗi video tự chọn kết quả"


def test_che_do_nguon_chung_can_it_nhat_hai_link(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    _radio(at).set_value("Một video gốc chung cho cả lô")
    at.text_area[0].set_value("https://youtu.be/aaaaaaaaaaa")
    at.run()
    assert not at.exception
    assert "ít nhất 2 link" in _van_ban(at)
    nut = next(b for b in at.button if b.label == "🚀 Bắt đầu quét")
    assert nut.disabled


def test_ve_ket_qua_nguon_chung_khong_loi(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    at.session_state.job.update({"running": False, "kind": "nguon_chung",
                                 "results": [_kql()], "error": ""})
    at.run()
    assert not at.exception
    chu = _van_ban(at)
    assert "VIDEO GỐC CHUNG" in chu and "Video gốc thử" in chu and "3/3" in chu
    assert "không phải xác nhận quyền sở hữu" in chu
    assert len(at.dataframe) >= 1


def test_ve_ket_qua_khong_tim_thay_noi_ro_khong_phai_nguon_chung(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    at.session_state.job.update({"running": False, "kind": "nguon_chung",
                                 "results": [_kql(tim_thay=False)], "error": ""})
    at.run()
    assert not at.exception
    chu = _van_ban(at)
    assert "Không xác minh được một video gốc chung" in chu
    assert "KHÔNG phải nguồn chung" in chu


def test_ve_ket_qua_khong_tim_thay_hien_gioi_han_cua_ket_luan(tmp_path, monkeypatch):
    """Lượt quét trọn của `_kql` không thử bù tốc độ: giới hạn đó phải hiện ra."""
    kql = _kql(tim_thay=False)
    assert kql.gioi_han
    at = _app(tmp_path, monkeypatch)
    at.session_state.job.update({"running": False, "kind": "nguon_chung",
                                 "results": [kql], "error": ""})
    at.run()
    assert not at.exception
    chu = _van_ban(at)
    assert "chưa loại trừ tuyệt đối" in chu and "bù tốc độ" in chu


def test_luu_csv_nguon_chung_tu_giao_dien(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    at.session_state.job.update({"running": False, "kind": "nguon_chung",
                                 "results": [_kql()], "error": ""})
    at.run()
    next(b for b in at.button if b.key == "luu_csv_nguon_chung").click()
    at.run()
    assert not at.exception
    tep = list((tmp_path / "ketqua").glob("nguonchung_*.csv"))
    assert len(tep) == 1
    df = pd.read_csv(tep[0], encoding="utf-8-sig")
    assert list(df.columns) == co.HEADER_NGUON_CHUNG and len(df) == 3
    assert "Đã lưu" in _van_ban(at)


def test_dung_lo_nguon_chung_tu_giao_dien(tmp_path, monkeypatch):
    import streamlit

    from test_nguon_chung_jobs import EngineGia

    at = _app(tmp_path, monkeypatch)
    monkeypatch.setattr(streamlit, "rerun", lambda *a, **k: None)
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 4)}
    gia = EngineGia(tmp_path / "gia", tg)
    gia.chan = __import__("threading").Event()
    ctl = CommonOriginalJobController(gia)
    at.session_state.common_controller = ctl
    ctl.start([f"https://youtu.be/{v}" for v in tg])
    assert gia.dang_quet.wait(5)
    at.session_state.job.update({"running": True, "kind": "nguon_chung", "results": [],
                                 "error": ""})
    at.run()
    next(b for b in at.button if b.key == "dung_nguon_chung").click()
    at.run()
    assert not at.exception
    assert gia.cancel_event.is_set() and ctl.snapshot().cancelled
    gia.chan.set()
    han = time.monotonic() + 15
    while ctl.running and time.monotonic() < han:
        time.sleep(0.02)
    assert ctl.result is not None and ctl.result.trang_thai == co.DA_HUY
    at.run()
    assert not at.exception
    assert "Đã dừng theo yêu cầu" in _van_ban(at)


def test_man_hinh_dang_chay_nguon_chung(tmp_path, monkeypatch):
    import streamlit

    from test_nguon_chung_jobs import EngineGia

    at = _app(tmp_path, monkeypatch)
    monkeypatch.setattr(streamlit, "rerun", lambda *a, **k: None)
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 4)}
    gia = EngineGia(tmp_path / "gia", tg)
    gia.chan = __import__("threading").Event()
    ctl = CommonOriginalJobController(gia)
    at.session_state.common_controller = ctl
    ctl.start([f"https://youtu.be/{v}" for v in tg])
    assert gia.dang_quet.wait(5)
    at.session_state.job.update({"running": True, "kind": "nguon_chung", "results": [],
                                 "error": ""})
    at.run()
    assert not at.exception
    chu = _van_ban(at)
    assert "Đang tìm video gốc chung" in chu and "Quét trọn video mốc" in chu
    gia.chan.set()
    han = time.monotonic() + 15
    while ctl.running and time.monotonic() < han:
        time.sleep(0.02)
    at.run()
    assert not at.exception
    assert "VIDEO GỐC CHUNG" in _van_ban(at)
