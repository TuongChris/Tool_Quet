# -*- coding: utf-8 -*-
"""Regression tests Engine: per-file event, skip, lỗi, atomic DB và cancel."""

import json
import os
from pathlib import Path

import pytest

from engine import Cancelled


PREFIX = "TIMCLIP_FINGERPRINT_EVENT "


def _clips(tmp_path, names=("ngắn.wav", "có khoảng trắng.wav", "hỏng.wav")):
    folder = tmp_path / "clips"
    folder.mkdir()
    result = []
    for name in names:
        path = folder / name
        path.write_bytes(b"fixture")
        result.append(str(path))
    return folder, sorted(result)


def _line(event, path, **extra):
    return PREFIX + json.dumps(
        {"event": event, "file": path, "process_pid": 1234, **extra},
        ensure_ascii=False,
    )


def test_engine_phat_event_that_theo_tung_file_va_tong_ket(engine, tmp_path, monkeypatch):
    folder, files = _clips(tmp_path)
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    events = []

    def run_stream(command, on_line=None, **kwargs):
        for path in files:
            on_line(_line("clip_started", path, phase="fingerprinting"))
            failed = path.endswith("hỏng.wav")
            on_line(_line(
                "clip_finished",
                path,
                status="failed" if failed else "success",
                category="decode_error" if failed else "",
                message="file lỗi" if failed else "",
                elapsed_seconds=0.2,
            ))
        Path(command[command.index("--dbase") + 1]).write_bytes(b"database moi")
        return 0, ["Saved fprints"]

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    result = engine.build_database(str(folder), "new", progress_event=events.append)

    assert result["thanh_cong"] == 2
    assert result["that_bai"] == 1
    assert result["da_xu_ly"] == 3
    assert Path(engine.db_file).read_bytes() == b"database moi"
    assert events[0].phase == "discovering"
    assert any(event.phase == "validating" and event.total == 3 for event in events)
    assert [event.file_name for event in events if event.status == "running" and event.file_name]
    assert any(event.status == "failed" and event.file_name == "hỏng.wav" for event in events)
    assert events[-1].status == "completed"
    assert all(a.percent <= b.percent for a, b in zip(events, events[1:]))


def test_phase_decoding_den_tu_event_that_chu_khong_phai_doan_theo_tien_trinh(
    engine,
    tmp_path,
    monkeypatch,
):
    """Wrapper phát `clip_phase` từ đúng nơi gọi FFmpeg nên phase là tất định.

    Trước đây phase `decoding` chỉ được suy ra khi *bắt gặp* tiến trình ffmpeg lúc
    lấy mẫu cây process — clip ngắn thì ffmpeg sống vài chục mili giây nên lúc có
    lúc không.
    """
    folder, files = _clips(tmp_path, ("clip.wav",))
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    def run_stream(command, on_line=None, **kwargs):
        on_line(_line("clip_started", files[0], phase="fingerprinting"))
        on_line(_line("clip_phase", files[0], phase="decoding"))
        on_line(_line("clip_phase", files[0], phase="fingerprinting"))
        on_line(_line("clip_finished", files[0], status="success", elapsed_seconds=0.1))
        Path(command[command.index("--dbase") + 1]).write_bytes(b"db")
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    events = []
    engine.build_database(str(folder), "new", progress_event=events.append)

    thu_tu = [event.phase for event in events]
    assert "decoding" in thu_tu, "Không nhận được phase decoding từ event thật."
    assert thu_tu.index("decoding") < len(thu_tu) - 1
    decoding = next(event for event in events if event.phase == "decoding")
    assert decoding.file_name == "clip.wav"
    assert decoding.active_subprocess_pid == 1234
    assert events[-1].status == "completed"


def test_clip_phase_la_pha_ket_thuc_thi_bi_bo_qua(engine, tmp_path, monkeypatch):
    """Một dòng stdout hỏng không được đẩy job sang trạng thái kết thúc giả."""
    folder, files = _clips(tmp_path, ("clip.wav",))
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    def run_stream(command, on_line=None, **kwargs):
        on_line(_line("clip_started", files[0]))
        on_line(_line("clip_phase", files[0], phase="completed"))
        on_line(_line("clip_phase", files[0], phase="khong_ton_tai"))
        on_line(_line("clip_finished", files[0], status="success", elapsed_seconds=0.1))
        Path(command[command.index("--dbase") + 1]).write_bytes(b"db")
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    events = []
    ket_qua = engine.build_database(str(folder), "new", progress_event=events.append)

    assert ket_qua["thanh_cong"] == 1
    # Chỉ event cuối cùng của job mới được mang trạng thái kết thúc.
    assert [e for e in events if e.status == "completed"] == [events[-1]]
    assert all(event.phase != "khong_ton_tai" for event in events)


def test_add_bo_qua_fingerprint_da_co_nhung_thu_lai_record_zero_hash(
    engine,
    tmp_path,
    monkeypatch,
):
    folder, files = _clips(tmp_path, ("đã có.wav", "zero hash.wav", "mới.wav"))
    Path(engine.db_file).write_bytes(b"database cu")
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    monkeypatch.setattr(
        engine,
        "db_clips",
        lambda bo_cache=False: [
            {"duong_dan": files[0], "so_hash": 100},
            {"duong_dan": files[2], "so_hash": 0},
        ],
    )
    seen = []

    def run_stream(command, on_line=None, **kwargs):
        listfile = command[command.index("--list") + 1]
        pending = Path(listfile).read_text(encoding="utf-8").splitlines()
        seen.extend(pending)
        for path in pending:
            on_line(_line("clip_started", path))
            on_line(_line(
                "clip_finished",
                path,
                status="success",
                elapsed_seconds=0.1,
            ))
        Path(command[command.index("--dbase") + 1]).write_bytes(b"database them")
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    result = engine.build_database(str(folder), "add")

    assert result["bo_qua"] == 1
    assert result["thanh_cong"] == 2
    assert files[0] not in seen
    assert files[2] in seen
    assert Path(engine.db_file).read_bytes() == b"database them"


def test_cancel_giu_nguyen_database_cu_va_khong_bao_staged_la_da_commit(
    engine,
    tmp_path,
    monkeypatch,
):
    folder, files = _clips(tmp_path, ("một.wav", "hai.wav"))
    Path(engine.db_file).write_bytes(b"database production")
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    def run_stream(command, on_line=None, **kwargs):
        on_line(_line("clip_started", files[0]))
        on_line(_line(
            "clip_finished",
            files[0],
            status="success",
            elapsed_seconds=0.1,
        ))
        raise Cancelled()

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    result = engine.build_database(str(folder), "new")

    assert result["da_huy"] is True
    assert result["thanh_cong"] == 0
    assert result["da_tinh_xong_chua_ghi"] == 1
    assert Path(engine.db_file).read_bytes() == b"database production"
    assert not any((Path(engine.data_dir) / "fingerprint_jobs").glob("*/database.pklz"))


def test_process_bao_thanh_cong_nhung_khong_co_db_tam_thi_job_failed_va_db_cu_con_nguyen(
    engine,
    tmp_path,
    monkeypatch,
):
    folder, _ = _clips(tmp_path, ("clip.wav",))
    Path(engine.db_file).write_bytes(b"database production")
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    monkeypatch.setattr(engine, "_run_stream", lambda *args, **kwargs: (0, []))

    with pytest.raises(RuntimeError, match="không tạo database tạm"):
        engine.build_database(str(folder), "new")

    assert Path(engine.db_file).read_bytes() == b"database production"
    assert not any((Path(engine.data_dir) / "fingerprint_jobs").glob("*/database.pklz"))


def test_log_ky_thuat_duoc_dong_sau_job_de_windows_xoa_duoc(engine, tmp_path, monkeypatch):
    folder, files = _clips(tmp_path, ("clip.wav",))
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    def run_stream(command, on_line=None, **kwargs):
        on_line(_line("clip_started", files[0]))
        on_line(_line(
            "clip_finished",
            files[0],
            status="success",
            elapsed_seconds=0.1,
        ))
        Path(command[command.index("--dbase") + 1]).write_bytes(b"db")
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)
    engine.build_database(str(folder), "new")
    log_path = Path(engine.out_dir) / "fingerprint.log"
    assert "event=clip" in log_path.read_text(encoding="utf-8")
    os.remove(log_path)
    assert not log_path.exists()
