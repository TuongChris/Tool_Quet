# -*- coding: utf-8 -*-
"""Test tích hợp: chạy audio THẬT qua toàn bộ pipeline. Chậm -> đánh dấu 'slow'."""
import pytest


@pytest.mark.slow
def test_toan_bo_luong_tim_dung_vi_tri(engine, bo_clip):
    engine.config.chunk_s = 300
    engine.config.overlap_s = 60
    engine.config.min_hash_floor = 50
    engine.config.min_hash_strong = 200
    engine.config.top_n = 5

    engine.add_kho("Test", bo_clip["kho"])
    r = engine.build_database(bo_clip["kho"], "new")
    assert r["da_xu_ly"] == 4

    kq = engine.scan_media(bo_clip["vi_pham"])
    assert kq.status == "ok"
    assert kq.matches, "Phải tìm ra clip đã giấu trong video dài"

    # Mỗi clip phải được định vị đúng mốc đã giấu (sai số 5 giây)
    tim_thay = {m.clip: m.start_s for m in kq.matches}
    for idx, giay in bo_clip["vi_tri"].items():
        ten = f"clip_{idx}.wav"
        if ten in tim_thay:
            assert abs(tim_thay[ten] - giay) < 5, f"{ten} lệch mốc quá xa"


@pytest.mark.slow
def test_khong_bao_nham_khi_video_khong_chua_clip(engine, bo_clip, tmp_path):
    import shutil
    engine.config.chunk_s = 300
    engine.config.overlap_s = 60
    engine.config.min_hash_floor = 50
    engine.add_kho("Test", bo_clip["kho"])
    engine.build_database(bo_clip["kho"], "new")

    # Dùng chính 1 clip gốc làm "video dài" -> chỉ được khớp với chính nó,
    # nhưng bộ chặn tự khớp phải loại nó đi
    nguon = tmp_path / "clip_0.wav"
    shutil.copy(f"{bo_clip['kho']}/clip_0.wav", nguon)
    kq = engine.scan_media(str(nguon))
    assert all("clip_0" not in m.clip for m in kq.matches), "Chặn tự khớp bị hỏng"


@pytest.mark.slow
def test_nap_lai_kho_lan_hai_khong_bi_khoa_file(engine, bo_clip):
    """Tái hiện WinError 32: nạp kho -> đọc danh sách -> nạp lại."""
    engine.config.chunk_s = 300
    engine.add_kho("Test", bo_clip["kho"])
    engine.build_database(bo_clip["kho"], "new")
    engine.db_clips()
    engine.build_database(bo_clip["kho"], "new")   # không được ném PermissionError
    assert len(engine.db_clips()) == 4
