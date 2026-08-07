# -*- coding: utf-8 -*-
"""Smoke thật với audfprint/FFmpeg, chỉ dùng WAV và database tạm."""

from pathlib import Path

import pytest

from conftest import _giai_dieu, _ghi_wav
from engine import Config, Engine


@pytest.mark.slow
def test_nhanh_da_nhan_that_khong_treo_va_khong_mat_event(tmp_path):
    """Nhánh ncores=8 là nhánh production (`Config.ncores=0` → số nhân CPU).

    audfprint vendored đẩy nguyên một HashTable ~419 MB/worker qua
    ``multiprocessing.Pipe`` và giữ mọi đầu ghi ở tiến trình cha ⇒ treo cứng
    không tất định (đã tái hiện 3/6 lần trên chính audfprint gốc). Bản vá trong
    ``audfprint_progress_runner`` chuyển sang file tạm + đóng đầu ghi ở cha.

    Test này chạy lại nhiều lượt vì lỗi cũ không xảy ra mọi lần.
    """
    folder = tmp_path / "clips"
    folder.mkdir()
    ten_clip = [f"clip {i}.wav" for i in range(6)]
    for i, ten in enumerate(ten_clip):
        _ghi_wav(folder / ten, _giai_dieu(5, seed=950 + i))

    for luot in range(3):
        engine = Engine(
            root=str(Path(__file__).resolve().parents[1]),
            config=Config(ncores=8, shifts_kho=4),
            data_dir=str(tmp_path / f"data{luot}"),
            out_dir=str(tmp_path / f"out{luot}"),
        )
        events = []
        result = engine.build_database(str(folder), "new", progress_event=events.append)

        assert result["thanh_cong"] == len(ten_clip), f"lượt {luot}: {result}"
        assert result["that_bai"] == 0
        assert Path(engine.db_file).is_file()
        # Mỗi clip phải có đúng một event bắt đầu và một event kết thúc; mất dòng
        # do 8 tiến trình con ghi chồng lên nhau sẽ làm hụt con số này.
        da_xong = {
            event.file_name for event in events
            if event.status == "success" and event.file_name
        }
        assert da_xong == set(ten_clip), f"lượt {luot}: thiếu event cho {set(ten_clip) - da_xong}"
        assert events[-1].status == "completed"


@pytest.mark.slow
def test_audfprint_da_nhan_phat_event_truoc_khi_database_duoc_commit(tmp_path):
    folder = tmp_path / "clips"
    folder.mkdir()
    _ghi_wav(folder / "clip có khoảng trắng.wav", _giai_dieu(5, seed=901))
    _ghi_wav(folder / "tiếng Việt.wav", _giai_dieu(6, seed=902))
    (folder / "hỏng.wav").write_bytes(b"not audio")
    engine = Engine(
        root=str(Path(__file__).resolve().parents[1]),
        config=Config(ncores=2, shifts_kho=1),
        data_dir=str(tmp_path / "data"),
        out_dir=str(tmp_path / "out"),
    )
    events = []
    event_truoc_commit = []

    def progress(event):
        events.append(event)
        if event.file_name and event.status in {"running", "success", "failed"}:
            event_truoc_commit.append(not Path(engine.db_file).exists())

    result = engine.build_database(str(folder), "new", progress_event=progress)

    assert result["so_clip"] == 3
    assert result["thanh_cong"] == 2
    assert result["that_bai"] == 1
    assert all(event_truoc_commit)
    assert Path(engine.db_file).is_file()
    assert any(event.phase == "decoding" for event in events)
    assert any(event.file_name == "tiếng Việt.wav" for event in events)
    assert events[-1].status == "completed"
