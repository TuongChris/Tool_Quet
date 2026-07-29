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
    eng.canh_bao_gop = []
    eng.db_clips = lambda: []
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


def test_merge_manh_chong_nhau_tich_phan_mat_do_lon_nhat():
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=100, khop=30, t_clip=0, so_hash=40),
        _manh(bat_dau=110, khop=30, t_clip=10, so_hash=70),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 83
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


def test_merge_hon_hop_trung_lap_va_lien_ke_lay_dung_mat_do_tot_nhat():
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=100, khop=30, t_clip=0, so_hash=50),
        _manh(bat_dau=100, khop=30, t_clip=0, so_hash=80),
        _manh(bat_dau=130, khop=30, t_clip=30, so_hash=80),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 160
    assert ket_qua[0].matched_s == 60
    assert (ket_qua[0].start_s, ket_qua[0].end_s) == (100, 160)


def test_merge_clip_cat_doi_qua_overlap_phuc_hoi_du_bang_chung():
    ket_qua = _engine_thuan()._merge([
        _manh(bat_dau=1900, khop=1700, t_clip=0, so_hash=1700),
        _manh(bat_dau=3420, khop=1480, t_clip=1520, so_hash=1480),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 3000
    assert ket_qua[0].matched_s == 3000
    assert (ket_qua[0].vung_khop_s, ket_qua[0].end_s) == (1900, 4900)


def test_merge_manh_khop_bang_khong_khong_chia_cho_khong():
    eng = _engine_thuan()
    eng.config.min_match_s = 0

    ket_qua = eng._merge([
        _manh(bat_dau=100, khop=0, t_clip=0, so_hash=20),
        _manh(bat_dau=100, khop=20, t_clip=0, so_hash=40),
    ])

    assert len(ket_qua) == 1
    assert ket_qua[0].hashes == 40


def test_merge_cham_can_tren_hash_va_ty_le_khong_vuot_100():
    eng = _engine_thuan()
    eng.db_clips = lambda: [{"ten": "clip-goc.opus", "so_hash": 75}]

    ket_qua = eng._merge([
        _manh(bat_dau=100, khop=20, t_clip=0, so_hash=60),
        _manh(bat_dau=120, khop=20, t_clip=20, so_hash=60),
    ])
    eng._gan_chi_so(ket_qua, duration=1000)

    assert ket_qua[0].hashes == 75
    assert ket_qua[0].ty_le == 100.0
    assert any("cận trên" in dong for dong in eng.canh_bao_gop)


def test_merge_khong_tra_duoc_tong_hash_thi_khong_kep():
    eng = _engine_thuan()

    ket_qua = eng._merge([
        _manh(bat_dau=100, khop=20, t_clip=0, so_hash=60),
        _manh(bat_dau=120, khop=20, t_clip=20, so_hash=60),
    ])

    assert ket_qua[0].hashes == 120
    assert any(
        "không tra được tổng hash" in dong.lower()
        for dong in eng.canh_bao_gop
    )
