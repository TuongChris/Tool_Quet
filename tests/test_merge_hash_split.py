# -*- coding: utf-8 -*-
"""Test đỏ cho quy tắc hash khi một clip bị chia qua ranh giới khúc."""

from engine import Config, Engine


def _engine_thuan() -> Engine:
    """Dựng Engine tối thiểu không chạy __init__, không chạm dữ liệu thật."""
    eng = Engine.__new__(Engine)
    eng.config = Config()
    eng.config.min_hash = 1
    eng.config.min_match_s = 1.0
    eng.config.dedup_s = 20.0
    return eng


def _manh(
    bat_dau: float,
    khop: float,
    t_clip: float,
    so_hash: int,
) -> dict:
    return {
        "clip": r"C:\kho\clip-goc.opus",
        "bat_dau": bat_dau,
        "khop": khop,
        "t_clip": t_clip,
        "hash": so_hash,
        "align": bat_dau - t_clip,
    }


def test_merge_manh_chong_nhau_chi_lay_hash_lon_nhat():
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=100, khop=30, t_clip=0, so_hash=40),
        _manh(bat_dau=110, khop=30, t_clip=10, so_hash=70),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 70
    assert (ket_qua[0].start_s, ket_qua[0].end_s) == (100, 140)


def test_merge_hai_manh_lien_ke_cong_hash():
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=100, khop=20, t_clip=0, so_hash=40),
        _manh(bat_dau=120, khop=20, t_clip=20, so_hash=60),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 100
    assert (ket_qua[0].start_s, ket_qua[0].end_s) == (100, 140)


def test_merge_hai_manh_roi_nhau_trong_nguong_dedup_cong_hash():
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=100, khop=15, t_clip=0, so_hash=35),
        _manh(bat_dau=120, khop=15, t_clip=20, so_hash=55),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 90
    assert (ket_qua[0].start_s, ket_qua[0].end_s) == (100, 135)


def test_merge_khoang_cach_dung_bang_dedup_van_cong_hash():
    """Biên <= dedup_s dễ bị viết nhầm thành < dedup_s ở phase sửa."""
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=100, khop=20, t_clip=0, so_hash=45),
        _manh(bat_dau=140, khop=20, t_clip=40, so_hash=65),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 110
    assert (ket_qua[0].start_s, ket_qua[0].end_s) == (100, 160)
