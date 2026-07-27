# -*- coding: utf-8 -*-
"""Test phân biệt thời điểm clip bắt đầu và vùng vân tay bắt đầu khớp."""

from bang_ngang import dinh_dang_doan
from conftest import M
from engine import Engine, ScanResult


def _ket_qua_tho(bat_dau: float, t_clip: float) -> dict:
    return {
        "clip": "C:/kho/clip.opus",
        "bat_dau": bat_dau,
        "khop": 30.0,
        "t_clip": t_clip,
        "hash": 100,
        "align": bat_dau - t_clip,
    }


def test_clip_bat_dau_bu_dung_offset(engine):
    match = engine._merge([_ket_qua_tho(bat_dau=908.5, t_clip=8.5)])[0]

    assert match.clip_bat_dau_s == 900.0
    assert match.start_s == 900.0
    assert match.vung_khop_s == 908.5
    assert match.end_s == 938.5
    assert match.clip_bat_dau_hhmmss == "00:15:00"


def test_khong_ra_so_am(engine):
    match = engine._merge([_ket_qua_tho(bat_dau=5.0, t_clip=30.0)])[0]

    assert match.clip_bat_dau_s == 0.0
    assert match.start_s == 0.0


def test_offset_bang_0_thi_khong_doi(engine):
    match = engine._merge([_ket_qua_tho(bat_dau=125.0, t_clip=0.0)])[0]

    assert match.clip_bat_dau_s == match.vung_khop_s == match.start_s == 125.0


def test_merge_sap_xep_theo_thoi_diem_clip_bat_dau(engine):
    muon_hon = _ket_qua_tho(bat_dau=100.0, t_clip=0.0)
    som_hon = _ket_qua_tho(bat_dau=110.0, t_clip=50.0)
    som_hon["clip"] = "C:/kho/clip-som.opus"

    matches = engine._merge([muon_hon, som_hon])

    assert [m.start_s for m in matches] == [60.0, 100.0]


def test_link_moc_lui_3_giay():
    noi_dung = dinh_dang_doan(M(start=850.0), "abc123", "")

    assert noi_dung.endswith("https://youtu.be/abc123?t=847")


def test_bao_cao_doc_tach_moc_clip_va_vung_khop(engine, monkeypatch):
    monkeypatch.setattr(engine, "clip_meta", lambda: {})
    match = engine._merge([_ket_qua_tho(bat_dau=908.5, t_clip=8.5)])[0]

    row = engine.to_rows([ScanResult(source_name="x", matches=[match])])[0]

    assert Engine.HEADER[7:9] == ["Clip bắt đầu từ", "Vùng khớp từ"]
    assert row[7:9] == ["00:15:00", "00:15:08"]
    assert len(row) == len(Engine.HEADER) == 16
