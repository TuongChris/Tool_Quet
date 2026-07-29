# -*- coding: utf-8 -*-
"""Test đỏ mô tả chính sách overlap có trần và không bị đảo chiều."""

from engine import Config, Engine


CLIP_DAI_PHUT = [10, 20, 30, 45, 50, 60, 90]


def _engine_thuan_voi_clip(clip_dai_giay: float) -> Engine:
    """Dựng Engine tối thiểu không chạy __init__, không đọc hoặc ghi đĩa."""
    eng = Engine.__new__(Engine)
    eng.config = Config()
    eng.config.chunk_s = 3600
    eng.config.overlap_tu_dong = True
    eng.clip_meta = lambda: {
        "clip.opus": {"duration": clip_dai_giay},
    }
    return eng


def test_config_co_tran_overlap_mac_dinh_180_giay():
    """Trần phải là cấu hình công khai để phase sau có thể hiệu chỉnh."""
    assert Config().overlap_max_s == 180


def test_overlap_khong_bao_gio_vuot_tran_cau_hinh():
    overlaps = []
    for so_phut in CLIP_DAI_PHUT:
        eng = _engine_thuan_voi_clip(so_phut * 60)
        eng.config.overlap_max_s = 180
        overlaps.append(eng._overlap_thuc_te())

    assert all(
        overlap <= 180 for overlap in overlaps
    ), f"Overlap vượt trần 180 giây: {overlaps}"


def test_overlap_don_dieu_khong_giam_theo_do_dai_clip():
    overlaps = [
        _engine_thuan_voi_clip(so_phut * 60)._overlap_thuc_te()
        for so_phut in CLIP_DAI_PHUT
    ]
    cac_buoc = [3600 - overlap for overlap in overlaps]

    assert all(
        truoc <= sau for truoc, sau in zip(overlaps, overlaps[1:])
    ), f"Overlap bị giảm khi clip dài hơn: {overlaps}"
    assert all(
        truoc >= sau for truoc, sau in zip(cac_buoc, cac_buoc[1:])
    ), f"Bước nhảy bị tăng ngược khi clip dài hơn: {cac_buoc}"
