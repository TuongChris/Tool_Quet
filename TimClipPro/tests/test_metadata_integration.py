# -*- coding: utf-8 -*-
"""Integration tests metadata/report bằng dữ liệu tạm, không dùng DB fingerprint thật."""

from __future__ import annotations

import csv
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from bang_ngang import HEADER_NGANG
from engine import Engine, Match, ScanResult
import engine as engine_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _metadata(
    video_id: str,
    title: str,
    *,
    upload_date: str = "20240131",
    duration: float = 125.0,
) -> dict:
    return {
        "id": video_id,
        "title": title,
        "url": f"https://youtu.be/{video_id}",
        "upload_date": upload_date,
        "duration": duration,
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _make_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    warehouses: dict[str, Path],
    clips_by_warehouse: dict[str, list[dict]],
    *,
    active: str,
) -> Engine:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "dang_dung": active,
        "danh_sach": [
            {
                "ten": name,
                "thu_muc": str(folder),
                "db": f"kho_{index}.pklz",
            }
            for index, (name, folder) in enumerate(warehouses.items(), start=1)
        ],
    }
    _write_json(data_dir / "khos.json", registry)
    engine = Engine(
        root=str(PROJECT_ROOT),
        data_dir=str(data_dir),
        out_dir=str(tmp_path / "output"),
    )

    def fake_db_clips(bo_cache: bool = False) -> list[dict]:
        del bo_cache
        return [dict(clip) for clip in clips_by_warehouse[engine.kho_dang_dung]]

    monkeypatch.setattr(engine, "db_clips", fake_db_clips)
    return engine


@pytest.fixture
def network_forbidden(monkeypatch):
    """Làm test thất bại ngay nếu một đường xuất báo cáo âm thầm gọi mạng."""

    def blocked(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Exporter metadata không được gọi mạng")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)

    import requests
    import yt_dlp

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", blocked)
    return blocked


def test_direct_warehouse_metadata_wins_when_database_paths_are_stale(
    tmp_path,
    monkeypatch,
):
    current_folder = tmp_path / "Kho Cory hiện tại"
    stale_folder = tmp_path / "Kho Cory đường dẫn cũ"
    current_folder.mkdir()
    stale_folder.mkdir()
    clip = "20240131 - Clip Unicode tiếng Việt [AbCdEf123_-].opus"
    _write_json(
        current_folder / "clips_meta.json",
        {clip: _metadata("AbCdEf123_-", "Metadata từ kho đang chọn")},
    )
    _write_json(
        stale_folder / "clips_meta.json",
        {clip: _metadata("AbCdEf123_-", "Metadata từ đường dẫn DB cũ")},
    )
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Cory": current_folder},
        {
            "Cory": [
                {"ten": clip, "duong_dan": str(stale_folder / clip)},
            ]
        },
        active="Cory",
    )

    resolver = engine.clip_metadata_resolver()
    result = resolver.resolve(clip)

    assert result.status == "complete"
    assert result.title == "Metadata từ kho đang chọn"
    assert result.source_kind == "live"
    assert Path(result.source_file) == current_folder / "clips_meta.json"
    assert resolver.source_files[0] == str(current_folder / "clips_meta.json")


def test_malformed_snapshot_falls_back_to_live_with_warning_and_no_mutation(
    tmp_path,
    monkeypatch,
):
    folder = tmp_path / "Kho Cory"
    folder.mkdir()
    clip = "20240201 - Clip hợp lệ [BcDeFg234_-].opus"
    _write_json(
        folder / "clips_meta.json",
        {clip: _metadata("BcDeFg234_-", "Metadata live hợp lệ")},
    )
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Cory": folder},
        {"Cory": [{"ten": clip, "duong_dan": str(folder / clip)}]},
        active="Cory",
    )
    snapshot = Path(engine._metadata_snapshot_path())
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    malformed = b'{"schema_version": 1, "clips": '
    snapshot.write_bytes(malformed)
    names_before = sorted(path.name for path in snapshot.parent.iterdir())
    stat_before = snapshot.stat()

    result = engine.clip_metadata_resolver(bo_cache=True).resolve(clip)

    stat_after = snapshot.stat()
    assert result.title == "Metadata live hợp lệ"
    assert result.source_kind == "live"
    assert any("metadata_read_error:" in warning for warning in engine.canh_bao_metadata)
    assert snapshot.read_bytes() == malformed
    assert snapshot.stat().st_mtime_ns == stat_before.st_mtime_ns == stat_after.st_mtime_ns
    assert sorted(path.name for path in snapshot.parent.iterdir()) == names_before
    assert not Path(str(snapshot) + ".bak").exists()
    assert not Path(str(snapshot) + ".tmp").exists()


def test_offline_apply_refuses_to_overwrite_malformed_snapshot_or_valid_backup(
    tmp_path,
    monkeypatch,
):
    folder = tmp_path / "Kho Cory"
    folder.mkdir()
    clip = "20240201 - Clip hợp lệ [BcDeFg234_-].opus"
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Cory": folder},
        {"Cory": [{"ten": clip, "duong_dan": str(folder / clip)}]},
        active="Cory",
    )
    Path(engine.db_file).write_bytes(b"test-only-not-a-fingerprint-database")
    snapshot = Path(engine._metadata_snapshot_path())
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    primary_bytes = b'{"schema_version": 1, "clips": '
    snapshot.write_bytes(primary_bytes)
    backup_payload = {
        "schema_version": 1,
        "warehouse": "Cory",
        "updated_at": "2026-08-06T00:00:00+07:00",
        "clips": {clip: _metadata("BcDeFg234_-", "Backup hợp lệ")},
    }
    backup = Path(str(snapshot) + ".bak")
    backup_bytes = json.dumps(backup_payload, ensure_ascii=False).encode("utf-8")
    backup.write_bytes(backup_bytes)

    result = engine.khoi_phuc_metadata_offline(dry_run=False)

    assert result.errors
    assert "không hợp lệ" in result.errors[0]
    assert snapshot.read_bytes() == primary_bytes
    assert backup.read_bytes() == backup_bytes
    assert not Path(str(snapshot) + ".tmp").exists()


def test_switching_warehouse_invalidates_cache_without_cross_contamination(
    tmp_path,
    monkeypatch,
):
    folder_a = tmp_path / "Kho A"
    folder_b = tmp_path / "Kho B"
    folder_a.mkdir()
    folder_b.mkdir()
    clip = "clip-chung.opus"
    _write_json(
        folder_a / "clips_meta.json",
        {clip: _metadata("CdEfGh345_-", "Chỉ thuộc kho A")},
    )
    _write_json(
        folder_b / "clips_meta.json",
        {clip: _metadata("DeFgHi456_-", "Chỉ thuộc kho B")},
    )
    clips = {
        "Kho A": [{"ten": clip, "duong_dan": str(folder_a / clip)}],
        "Kho B": [{"ten": clip, "duong_dan": str(folder_b / clip)}],
    }
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Kho A": folder_a, "Kho B": folder_b},
        clips,
        active="Kho A",
    )

    resolver_a = engine.clip_metadata_resolver()
    assert resolver_a.resolve(clip).title == "Chỉ thuộc kho A"
    assert engine._metadata_resolver_cache is resolver_a

    engine.use_kho("Kho B")
    assert engine._metadata_resolver_cache is None
    resolver_b = engine.clip_metadata_resolver()
    result_b = resolver_b.resolve(clip)
    assert resolver_b is not resolver_a
    assert result_b.title == "Chỉ thuộc kho B"
    assert result_b.video_id == "DeFgHi456_-"
    assert all(Path(path).parent == folder_b for path in resolver_b.source_files)

    engine.use_kho("Kho A")
    assert engine.clip_metadata_resolver().resolve(clip).title == "Chỉ thuộc kho A"


def test_offline_repair_dry_run_then_atomic_snapshot_never_touches_clips_meta(
    tmp_path,
    monkeypatch,
):
    folder = tmp_path / "Kho Cory"
    folder.mkdir()
    official = "20240131 - Có metadata [EfGhIj567_-].opus"
    fallback = "00000000 - Tên Unicode có khoảng trắng [FgHiJk678_-].opus"
    live_path = folder / "clips_meta.json"
    _write_json(
        live_path,
        {official: _metadata("EfGhIj567_-", "Tiêu đề chính thức")},
    )
    live_before = live_path.read_bytes()
    live_stat_before = live_path.stat()
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Cory": folder},
        {
            "Cory": [
                {"ten": official, "duong_dan": str(folder / official)},
                {"ten": fallback, "duong_dan": str(folder / fallback)},
            ]
        },
        active="Cory",
    )
    snapshot = Path(engine._metadata_snapshot_path())
    # Marker tạm chỉ thỏa guard tồn tại; db_clips đã được thay bằng API giả ở trên.
    Path(engine.db_file).write_bytes(b"test-only-not-a-fingerprint-database")

    dry_run = engine.khoi_phuc_metadata_offline(dry_run=True)

    assert dry_run.dry_run is True
    assert dry_run.errors == ()
    assert dry_run.total_db_clips == 2
    assert dry_run.updated == 2
    assert not snapshot.exists()
    assert not Path(str(snapshot) + ".tmp").exists()
    assert live_path.read_bytes() == live_before
    assert live_path.stat().st_mtime_ns == live_stat_before.st_mtime_ns

    applied = engine.khoi_phuc_metadata_offline(dry_run=False)

    assert applied.dry_run is False
    assert applied.errors == ()
    assert applied.total_db_clips == 2
    assert applied.updated == 2
    assert snapshot.exists()
    assert not Path(str(snapshot) + ".tmp").exists()
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["warehouse"] == "Cory"
    assert list(payload["clips"]) == [official, fallback]
    assert payload["clips"][official]["title"] == "Tiêu đề chính thức"
    assert payload["clips"][fallback]["id"] == "FgHiJk678_-"
    assert payload["clips"][fallback]["resolution_method"] == "filename_fallback"
    assert live_path.read_bytes() == live_before
    assert live_path.stat().st_mtime_ns == live_stat_before.st_mtime_ns


def test_target_three_matches_resolve_in_all_reports_without_network(
    tmp_path,
    monkeypatch,
    network_forbidden,
):
    del network_forbidden
    folder = tmp_path / "Kho Cory"
    folder.mkdir()
    current_names = [
        "00000000 - Pedro Pascal Wants You. [SSS #070] [iiPCTnSoj9w].opus",
        "00000000 - DO NOT CLICK THIS VIDEO. [SSS #003] [Nkr7YLIlAdU].opus",
        (
            "00000000 - what would you do if she asked for a ride home_ "
            "[SSS #031] [pqzrFR3anuo].opus"
        ),
    ]
    old_keys = [
        "20230101 - Tên metadata cũ số 1 [iiPCTnSoj9w].opus",
        "20230202 - Tên metadata cũ số 2 [Nkr7YLIlAdU].opus",
        "20230303 - Tên metadata cũ số 3 [pqzrFR3anuo].opus",
    ]
    ids = ["iiPCTnSoj9w", "Nkr7YLIlAdU", "pqzrFR3anuo"]
    titles = [
        "Video gốc chính thức 1",
        "Video gốc chính thức 2",
        "Video gốc chính thức 3",
    ]
    dates = ["20230101", "20230202", "20230303"]
    durations = [1_300.0, 5_500.0, 9_900.0]
    metadata = {
        old_key: _metadata(
            video_id,
            title,
            upload_date=upload_date,
            duration=duration,
        )
        for old_key, video_id, title, upload_date, duration in zip(
            old_keys,
            ids,
            titles,
            dates,
            durations,
            strict=True,
        )
    }
    _write_json(folder / "clips_meta.json", metadata)
    clips = [
        {"ten": name, "duong_dan": str(folder / name)}
        for name in current_names
    ]
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Cory": folder},
        {"Cory": clips},
        active="Cory",
    )
    matches = [
        Match(
            clip=current_names[0],
            start_s=404.0,
            end_s=1125.2,
            matched_s=721.2,
            clip_offset_s=0.0,
            hashes=8_775,
            confidence="Rất chắc chắn",
            ty_le=87.7,
        ),
        Match(
            clip=current_names[1],
            start_s=4108.5,
            end_s=5409.9,
            matched_s=1301.4,
            clip_offset_s=0.0,
            hashes=8_485,
            confidence="Rất chắc chắn",
            ty_le=84.8,
        ),
        Match(
            clip=current_names[2],
            start_s=8583.8,
            end_s=9552.9,
            matched_s=969.1,
            clip_offset_s=0.0,
            hashes=10_605,
            confidence="Rất chắc chắn",
            ty_le=90.1,
        ),
    ]
    result = ScanResult(
        source_name="Video mục tiêu Zlfty7Enrkg",
        source_ref="https://www.youtube.com/watch?v=Zlfty7Enrkg",
        source_id="Zlfty7Enrkg",
        duration_s=10_000,
        matches=matches,
        so_dat_nguong=12,
        channel_name="Kênh kiểm thử",
        channel_id="UC_TEST",
        channel_url="https://www.youtube.com/channel/UC_TEST",
        upload_date="20260806",
    )

    resolved = engine.resolve_metadata_for_matches(matches)
    assert [item.resolution_method for item in resolved] == ["video_id"] * 3
    assert [item.title for item in resolved] == titles
    coverage = engine.metadata_coverage(matches)
    assert coverage.resolved_complete == 3
    assert coverage.filename_fallbacks == 0

    vertical = engine.to_rows([result])
    assert len(vertical) == 3
    assert all(len(row) == len(Engine.HEADER) == 16 for row in vertical)
    assert [row[3] for row in vertical] == current_names
    assert [row[4] for row in vertical] == titles
    assert [row[5] for row in vertical] == [
        f"https://youtu.be/{video_id}" for video_id in ids
    ]

    horizontal = engine.to_rows_ngang([result])
    assert len(horizontal) == 1
    row = horizontal[0]
    assert len(row) == len(HEADER_NGANG) == 34
    # Mốc media cắt phần lẻ chứ không làm tròn (start_s = 404,0 / 4108,5 / 8583,8).
    assert row[8].startswith("00:06:44")
    assert row[9].startswith("01:08:28")
    assert row[10].startswith("02:23:03")
    assert [row[index] for index in (14, 18, 22)] == titles
    assert [row[index] for index in (13, 17, 21)] == [
        f"https://youtu.be/{video_id}" for video_id in ids
    ]
    assert row[25:33] == [""] * 8
    assert row[33] == 12

    vertical_path = Path(
        engine.export_csv([result], str(tmp_path / "vertical.csv"))
    )
    horizontal_path = Path(
        engine.export_csv_ngang([result], str(tmp_path / "horizontal.csv"))
    )
    dossier_paths = engine.export_ho_so(
        [result],
        str(tmp_path / "dossier.md"),
    )
    assert len(dossier_paths) == 1

    with vertical_path.open(encoding="utf-8-sig", newline="") as handle:
        vertical_csv = list(csv.reader(handle))
    with horizontal_path.open(encoding="utf-8-sig", newline="") as handle:
        horizontal_csv = list(csv.reader(handle))
    assert len(vertical_csv) == 4
    assert all(len(csv_row) == 16 for csv_row in vertical_csv)
    assert len(horizontal_csv) == 2
    assert all(len(csv_row) == 34 for csv_row in horizontal_csv)
    assert horizontal_csv[1][33] == "12"

    dossier_text = Path(dossier_paths[0]).read_text(encoding="utf-8")
    positions = [dossier_text.index(title) for title in titles]
    assert positions == sorted(positions)
    assert all(f"https://youtu.be/{video_id}" in dossier_text for video_id in ids)
    assert "Tổng số đoạn vi phạm:** 3" in dossier_text


def test_explicit_network_patch_uses_bounded_retry_and_updates_only_snapshot(
    tmp_path,
    monkeypatch,
):
    folder = tmp_path / "Kho Cory"
    folder.mkdir()
    clip = "00000000 - Tên từ filename [GhIjKl789_-].opus"
    engine = _make_engine(
        tmp_path,
        monkeypatch,
        {"Cory": folder},
        {"Cory": [{"ten": clip, "duong_dan": str(folder / clip)}]},
        active="Cory",
    )
    Path(engine.db_file).write_bytes(b"test-only-not-a-fingerprint-database")
    live_path = folder / "clips_meta.json"
    attempts = 0
    progress_events = []

    def fetcher(video_id: str) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("timeout test")
        return {
            "id": video_id,
            "title": "Tiêu đề chính thức từ mạng giả",
            "url": f"https://www.youtube.com/watch?v={video_id}&tracking=redacted",
            "upload_date": "20240506",
            "duration": 321,
        }

    monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)
    result = engine.va_metadata_thieu(
        lambda pct, message: progress_events.append((pct, message)),
        fetcher=fetcher,
        max_retries=2,
    )

    assert attempts == 2
    assert result["tong"] == result["da_va"] == 1
    assert result["loi"] == []
    assert progress_events[-1][0] == 1.0
    assert not live_path.exists()
    snapshot = Path(result["snapshot_path"])
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    saved = payload["clips"][clip]
    assert saved["title"] == "Tiêu đề chính thức từ mạng giả"
    assert saved["url"] == "https://youtu.be/GhIjKl789_-"
    assert saved["upload_date"] == "20240506"
    assert saved["duration"] == 321.0
    assert saved["resolution_method"] == "video_id"
