# -*- coding: utf-8 -*-
"""Test logic thuần dựng hồ sơ vi phạm."""

from conftest import M

from dossier import dung_ho_so
from engine import ScanResult


def test_ho_so_rong_khi_khong_co_ket_qua():
    h = dung_ho_so(ScanResult(source_name="v", duration_s=3600))
    assert h.muc == []
    assert h.tong_giay_vi_pham == 0
    assert h.ty_le_video == 0.0


def test_khong_chia_cho_khong():
    h = dung_ho_so(ScanResult(source_name="v", duration_s=0))
    assert h.ty_le_video == 0.0


def test_dung_day_du_ho_so_va_meta():
    match = M("clip.mp4", start=65.2, hashes=321, matched=10.6)
    match.ty_le = 87.5
    kq = ScanResult(
        source_name="Video vi phạm",
        source_ref="https://www.youtube.com/watch?v=abc",
        source_id="abc",
        duration_s=100,
        matches=[match],
    )

    h = dung_ho_so(kq, {
        "clip.mp4": {"title": "Video gốc", "url": "https://youtu.be/goc"},
    })

    assert h.tieu_de_vi_pham == "Video vi phạm"
    assert h.link_vi_pham == kq.source_ref
    assert h.thoi_luong_hhmmss == "00:01:40"
    assert h.tong_giay_vi_pham == 11
    assert h.ty_le_video == 11.0
    assert len(h.muc) == 1
    assert h.muc[0].tieu_de_goc == "Video gốc"
    assert h.muc[0].link_goc == "https://youtu.be/goc"
    assert h.muc[0].tu_hhmmss == "00:01:05"
    assert h.muc[0].den_hhmmss == "00:01:16"
    assert h.muc[0].link_moc == "https://youtu.be/abc?t=65"
    assert h.muc[0].do_dai_giay == 11
    assert h.muc[0].ty_le == 87.5
    assert h.muc[0].hashes == 321


def test_status_loi_luon_tra_ho_so_rong():
    kq = ScanResult(
        source_name="v",
        duration_s=100,
        matches=[M(matched=25)],
        status="error",
        note="Nguồn hỏng",
    )

    h = dung_ho_so(kq)

    assert h.muc == []
    assert h.tong_giay_vi_pham == 0
    assert h.ty_le_video == 0.0


def test_meta_thieu_clip_dung_chuoi_rong():
    h = dung_ho_so(ScanResult(
        source_name="v",
        duration_s=100,
        matches=[M("khong-co-meta.mp4")],
    ))

    assert h.muc[0].tieu_de_goc == ""
    assert h.muc[0].link_goc == ""
