# -*- coding: utf-8 -*-
"""Regression tests cho resolver metadata clip gốc thuần, không dùng dữ liệu thật."""

from __future__ import annotations

import json
import time
import unicodedata

import pytest

from clip_metadata import (
    ClipMetadataResolver,
    load_metadata_strict,
    source_from_mapping,
)


VIDEO_ID_A = "AbCdEf123_-"
VIDEO_ID_B = "ZYXwv9876-_"


def _metadata(
    video_id: str,
    title: str,
    *,
    upload_date: str = "20240131",
    duration: float = 123.5,
) -> dict:
    return {
        "id": video_id,
        "title": title,
        "url": f"https://youtu.be/{video_id}",
        "upload_date": upload_date,
        "duration": duration,
    }


def test_resolve_exact_key_returns_complete_official_metadata():
    name = f"20240131 - Tiêu đề [{VIDEO_ID_A}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {name: _metadata(VIDEO_ID_A, "Tiêu đề chính thức")}
    )

    result = resolver.resolve(name)

    assert result.resolution_method == "exact"
    assert result.status == "complete"
    assert result.complete is True
    assert result.video_id == VIDEO_ID_A
    assert result.title == "Tiêu đề chính thức"
    assert result.public_dict()["duration"] == pytest.approx(123.5)


@pytest.mark.parametrize(
    "stored_path",
    [
        rf"C:\Kho cũ\Thư mục\20240131 - Clip gốc [{VIDEO_ID_A}].opus",
        f"/mnt/kho cu/thu muc/20240131 - Clip gốc [{VIDEO_ID_A}].opus",
    ],
)
def test_resolve_basename_from_windows_and_posix_metadata_paths(stored_path):
    basename = f"20240131 - Clip gốc [{VIDEO_ID_A}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {stored_path: _metadata(VIDEO_ID_A, "Clip gốc")},
        windows_semantics=True,
    )

    result = resolver.resolve(basename)

    assert result.resolution_method == "exact_basename"
    assert result.metadata_key == stored_path
    assert result.video_id == VIDEO_ID_A


def test_resolve_canonical_filename_handles_windows_case_and_unicode_nfc():
    decomposed = unicodedata.normalize("NFD", "Café Việt")
    stored = f"20240131 - {decomposed} [{VIDEO_ID_A}].OPUS"
    requested = f"20240131 - CAFÉ VIỆT [{VIDEO_ID_A}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {stored: _metadata(VIDEO_ID_A, "Café Việt chính thức")},
        windows_semantics=True,
    )

    result = resolver.resolve(requested)

    assert result.resolution_method == "canonical_filename"
    assert result.status == "complete"
    assert result.title == "Café Việt chính thức"


def test_resolve_renamed_file_by_stable_youtube_id():
    old_name = f"20240131 - Tên trước đây [{VIDEO_ID_A}].opus"
    new_name = f"00000000 - Tên đã đổi hoàn toàn [{VIDEO_ID_A}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {old_name: _metadata(VIDEO_ID_A, "Tiêu đề từ metadata")}
    )

    result = resolver.resolve(new_name)

    assert result.resolution_method == "video_id"
    assert result.metadata_key == old_name
    assert result.title == "Tiêu đề từ metadata"
    assert result.url == f"https://youtu.be/{VIDEO_ID_A}"


def test_source_schema_validation_keeps_valid_entries_and_isolates_bad_data():
    valid_name = f"20240131 - Hợp lệ [{VIDEO_ID_A}].opus"
    invalid_name = f"00000000 - Trường lỗi [{VIDEO_ID_B}].opus"
    source = source_from_mapping(
        {
            valid_name: _metadata(VIDEO_ID_A, "Hợp lệ"),
            "not-an-object.opus": "invalid",
            invalid_name: {
                "id": "not-a-youtube-id",
                "title": 123,
                "url": ["not", "a", "url"],
                "upload_date": "20241399",
                "duration": -1,
            },
        },
        path="clips_meta.json",
        kind="live",
    )

    assert len(source.entries) == 2
    assert source.invalid_entries == 2
    assert "entry_not_object:not-an-object.opus" in source.warnings
    valid = next(entry for entry in source.entries if entry.key == valid_name)
    invalid = next(entry for entry in source.entries if entry.key == invalid_name)
    assert valid.video_id == VIDEO_ID_A
    assert set(invalid.warnings) == {
        "invalid_id",
        "invalid_title",
        "invalid_url",
        "invalid_upload_date",
        "invalid_duration",
    }
    # ID còn có thể phục hồi an toàn từ khóa filename, các trường sai bị để trống.
    assert invalid.video_id == VIDEO_ID_B
    assert invalid.title == ""
    assert invalid.url == ""
    assert invalid.upload_date == ""
    assert invalid.duration is None
    assert "invalid_field:invalid_duration" in source.warnings


def test_source_schema_rejects_non_mapping_root_without_raising():
    source = source_from_mapping([{"unexpected": "list"}], path="clips_meta.json")

    assert source.entries == ()
    assert source.invalid_entries == 0
    assert source.warnings == ("metadata_root_not_object",)


def test_snapshot_schema_and_warehouse_are_validated(tmp_path):
    name = f"20240131 - Snapshot [{VIDEO_ID_A}].opus"
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "warehouse": "Cory",
                "updated_at": "2026-08-06T21:30:00+07:00",
                "clips": {name: _metadata(VIDEO_ID_A, "Snapshot")},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    valid = load_metadata_strict(
        str(path), kind="snapshot", priority=0, expected_warehouse="Cory"
    )
    mismatch = load_metadata_strict(
        str(path), kind="snapshot", priority=0, expected_warehouse="Kho khác"
    )

    assert len(valid.entries) == 1
    assert valid.updated_at == "2026-08-06T21:30:00+07:00"
    assert valid.warnings == ()
    assert mismatch.entries == ()
    assert mismatch.warnings == ("snapshot_warehouse_mismatch",)


def test_partial_filename_fallback_unresolved_and_ambiguous_are_distinct():
    partial_name = f"00000000 - Metadata thiếu [{VIDEO_ID_A}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {
            partial_name: {"id": VIDEO_ID_A, "title": "Metadata thiếu"},
            f"20240101 - Bản cũ thứ nhất [{VIDEO_ID_B}].opus": _metadata(
                VIDEO_ID_B, "Bản thứ nhất"
            ),
            f"20240202 - Bản cũ thứ hai [{VIDEO_ID_B}].opus": _metadata(
                VIDEO_ID_B, "Bản thứ hai"
            ),
        }
    )

    partial = resolver.resolve(partial_name)
    fallback = resolver.resolve("20240801 - Chỉ có filename [QrStUv456_-].opus")
    unresolved = resolver.resolve("tệp không có định danh.opus")
    ambiguous = resolver.resolve(
        f"00000000 - Tên mới không xác định [{VIDEO_ID_B}].opus"
    )

    assert partial.status == "partial"
    assert partial.resolution_method == "filename_fallback"
    assert "fields_enriched_from_filename" in partial.warnings
    assert partial.url == f"https://youtu.be/{VIDEO_ID_A}"
    assert partial.missing_fields == ("upload_date", "duration")

    assert fallback.status == "partial"
    assert fallback.resolution_method == "filename_fallback"
    assert fallback.video_id == "QrStUv456_-"
    assert fallback.upload_date == "20240801"
    assert fallback.missing_fields == ("duration",)

    assert unresolved.status == "unresolved"
    assert unresolved.resolution_method == "basename_fallback"
    assert unresolved.title == "tệp không có định danh.opus"

    assert ambiguous.status == "ambiguous"
    assert ambiguous.resolution_method == "ambiguous"
    assert ambiguous.video_id == ""
    assert "metadata_candidates_ambiguous" in ambiguous.warnings


def test_source_priority_retains_primary_values_fills_gaps_and_reports_conflict():
    name = f"20240131 - Ưu tiên [{VIDEO_ID_A}].opus"
    primary = source_from_mapping(
        {
            name: {
                "id": VIDEO_ID_A,
                "title": "Tiêu đề snapshot",
                "url": "",
                "upload_date": "20240131",
                "duration": None,
            }
        },
        path="snapshot.json",
        kind="snapshot",
        priority=0,
    )
    secondary = source_from_mapping(
        {
            name: {
                "id": VIDEO_ID_A,
                "title": "Tiêu đề live khác",
                "url": f"https://youtu.be/{VIDEO_ID_A}",
                "upload_date": "20240131",
                "duration": 45.0,
            }
        },
        path="clips_meta.json",
        kind="live",
        priority=10,
    )
    resolver = ClipMetadataResolver([secondary, primary])

    result = resolver.resolve(name)

    assert result.status == "complete"
    assert result.title == "Tiêu đề snapshot"
    assert result.url == f"https://youtu.be/{VIDEO_ID_A}"
    assert result.duration == pytest.approx(45.0)
    assert result.source_kind == "snapshot"
    assert resolver.conflicts == [f"conflict:title:{name}"]


def test_coverage_and_audit_report_resolution_methods_orphans_and_samples(tmp_path):
    exact = f"20240101 - Exact [{VIDEO_ID_A}].opus"
    basename = "20240102 - Theo đường dẫn [BcDeFg234_-].opus"
    normalized_stored = "20240103 - CAFÉ [CdEfGh345_-].OPUS"
    normalized_requested = "20240103 - CAFÉ [CdEfGh345_-].opus"
    old_id_name = "20240104 - Tên cũ [DeFgHi456_-].opus"
    renamed = "00000000 - Tên mới [DeFgHi456_-].opus"
    fallback = "20240105 - Chỉ filename [EfGhIj567_-].opus"
    unresolved = "không có id.opus"
    orphan = "20240106 - Không nằm trong DB [FgHiJk678_-].opus"

    mapping = {
        exact: _metadata(VIDEO_ID_A, "Exact"),
        rf"C:\Kho cũ\{basename}": _metadata("BcDeFg234_-", "Theo đường dẫn"),
        normalized_stored: _metadata("CdEfGh345_-", "Café"),
        old_id_name: _metadata("DeFgHi456_-", "Tên chính thức"),
        orphan: _metadata("FgHiJk678_-", "Orphan"),
    }
    metadata_path = tmp_path / "clips_meta.json"
    source = source_from_mapping(
        mapping,
        path=str(metadata_path),
        kind="live",
        priority=0,
    )
    resolver = ClipMetadataResolver([source], windows_semantics=True)
    names = [exact, basename, normalized_requested, renamed, fallback, unresolved]

    coverage = resolver.coverage(names)
    assert coverage.to_dict() == {
        "selected_matches": 6,
        "resolved_complete": 4,
        "resolved_partial": 1,
        "filename_fallbacks": 1,
        "unresolved": 1,
        "ambiguous": 0,
    }

    database = tmp_path / "db.pklz"
    database.write_bytes(b"test-only")
    warehouse_folder = tmp_path / "Kho Cory"
    warehouse_folder.mkdir()
    audit = resolver.audit(
        [
            {"ten": name, "duong_dan": str(warehouse_folder / name)}
            for name in names
        ],
        warehouse="Cory",
        database_file=str(database),
        warehouse_folder=str(warehouse_folder),
        sample_limit=2,
    )

    assert audit.total_db_clips == 6
    assert audit.metadata_entries == 5
    assert audit.exact_matches == 1
    assert audit.exact_basename_matches == 1
    assert audit.normalized_matches == 1
    assert audit.id_matches == 1
    assert audit.filename_fallbacks == 1
    assert audit.missing == 1
    assert audit.ambiguous == 0
    assert audit.complete == 4
    assert audit.partial == 1
    assert audit.metadata_orphans == 1
    assert audit.database_exists is True
    assert audit.warehouse_folder_exists is True
    assert len(audit.samples) == 2
    assert [sample.status for sample in audit.samples] == ["partial", "unresolved"]


def test_resolve_many_preserves_input_order_and_duplicates():
    first = f"20240101 - Một [{VIDEO_ID_A}].opus"
    second = f"20240102 - Hai [{VIDEO_ID_B}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {
            first: _metadata(VIDEO_ID_A, "Một"),
            second: _metadata(VIDEO_ID_B, "Hai"),
        }
    )
    requested = [
        (second, None),
        (first, "C:\\Kho\\" + first),
        (second, None),
        ("không rõ.opus", None),
    ]

    resolved = resolver.resolve_many(iter(requested))

    assert [item.clip_name for item in resolved] == [
        second,
        first,
        second,
        "không rõ.opus",
    ]
    assert [item.video_id for item in resolved] == [
        VIDEO_ID_B,
        VIDEO_ID_A,
        VIDEO_ID_B,
        "",
    ]


def test_malformed_loader_is_read_only_and_does_not_create_recovery_files(tmp_path):
    path = tmp_path / "clips_meta.json"
    original = b'{"dang": "do dang"'
    path.write_bytes(original)
    before_names = sorted(item.name for item in tmp_path.iterdir())
    before_stat = path.stat()

    source = load_metadata_strict(str(path), kind="live", priority=0)

    after_stat = path.stat()
    assert source.entries == ()
    assert source.exists is True
    assert any(warning.startswith("metadata_read_error:") for warning in source.warnings)
    assert path.read_bytes() == original
    assert sorted(item.name for item in tmp_path.iterdir()) == before_names
    assert after_stat.st_size == before_stat.st_size
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns


def test_index_and_one_thousand_id_resolutions_performance_smoke():
    total = 2_000
    mapping = {}
    for index in range(total):
        video_id = f"id{index:09d}"
        name = f"20240101 - Clip {index:04d} [{video_id}].opus"
        mapping[name] = _metadata(video_id, f"Clip chính thức {index:04d}")

    index_started = time.perf_counter()
    resolver = ClipMetadataResolver.from_mapping(mapping)
    index_elapsed = time.perf_counter() - index_started

    lookup_started = time.perf_counter()
    resolved = [
        resolver.resolve(
            f"00000000 - Tên đã đổi {index:04d} [id{index:09d}].opus"
        )
        for index in range(1_000)
    ]
    lookup_elapsed = time.perf_counter() - lookup_started

    assert resolver.metadata_entries == total
    assert all(item.resolution_method == "video_id" for item in resolved)
    assert all(item.status == "complete" for item in resolved)
    # Ngưỡng rộng để chỉ bắt hồi quy lớn (ví dụ quét lại toàn bộ mapping mỗi lookup).
    assert index_elapsed < 5.0
    assert lookup_elapsed < 5.0


def test_conflicting_identity_never_exports_hybrid_metadata():
    name = f"20240101 - Conflict [{VIDEO_ID_A}].opus"
    source = source_from_mapping({
        name: {
            "id": VIDEO_ID_B,
            "title": "Không được tin cậy",
            "url": f"https://youtu.be/{VIDEO_ID_B}",
            "upload_date": "20240101",
            "duration": 10,
        }
    })
    resolver = ClipMetadataResolver([source])

    result = resolver.resolve(name)

    assert result.status == "ambiguous"
    assert result.video_id == ""
    assert result.url == ""
    assert result.complete is False


def test_same_key_conflicting_sources_are_ambiguous_not_field_merged():
    name = f"20240101 - Conflict [{VIDEO_ID_A}].opus"
    snapshot = source_from_mapping(
        {name: _metadata(VIDEO_ID_A, "A")},
        kind="snapshot",
        priority=0,
    )
    live_value = _metadata(VIDEO_ID_B, "B")
    # Key cũng mang ID A, vì vậy entry live tự mâu thuẫn và bị quarantine.
    live = source_from_mapping({name: live_value}, kind="live", priority=10)

    result = ClipMetadataResolver([snapshot, live]).resolve(name)

    assert result.status == "ambiguous"
    assert result.url == ""


def test_input_clip_name_and_path_with_different_ids_are_ambiguous():
    name = f"20240101 - A [{VIDEO_ID_A}].opus"
    path = rf"C:\Kho\20240101 - B [{VIDEO_ID_B}].opus"
    resolver = ClipMetadataResolver.from_mapping({name: _metadata(VIDEO_ID_A, "A")})

    result = resolver.resolve(name, path)

    assert result.status == "ambiguous"
    assert result.warnings == ("input_clip_identity_conflict",)


def test_windows_normalization_does_not_apply_unicode_casefold_expansion():
    stored = f"20240101 - Straße [{VIDEO_ID_A}].opus"
    requested = f"20240101 - Strasse [{VIDEO_ID_B}].opus"
    resolver = ClipMetadataResolver.from_mapping(
        {stored: _metadata(VIDEO_ID_A, "Straße")},
        windows_semantics=True,
    )

    result = resolver.resolve(requested)

    assert result.resolution_method == "filename_fallback"
    assert result.video_id == VIDEO_ID_B


def test_windows_canonicalization_never_casefolds_youtube_identity():
    stored = f"20240101 - Same title [{VIDEO_ID_A}].opus"
    different_case_id = "aBcDeF123_-"
    requested = f"20240101 - SAME TITLE [{different_case_id}].OPUS"
    resolver = ClipMetadataResolver.from_mapping(
        {stored: _metadata(VIDEO_ID_A, "Official A")},
        windows_semantics=True,
    )

    result = resolver.resolve(requested)

    assert result.status == "ambiguous"
    assert result.video_id == ""
    assert result.url == ""


def test_snapshot_filename_fallback_does_not_mask_official_entry_by_id():
    current = f"00000000 - Tên fallback [{VIDEO_ID_A}].opus"
    official_old = f"20240101 - Tên chính thức cũ [{VIDEO_ID_A}].opus"
    snapshot = source_from_mapping(
        {
            current: {
                **_metadata(VIDEO_ID_A, "Tên fallback", upload_date=""),
                "duration": None,
                "resolution_method": "filename_fallback",
            }
        },
        kind="snapshot",
        priority=0,
    )
    live = source_from_mapping(
        {official_old: _metadata(VIDEO_ID_A, "Tên chính thức")},
        kind="live",
        priority=10,
    )

    result = ClipMetadataResolver([snapshot, live]).resolve(current)

    assert result.resolution_method == "video_id"
    assert result.title == "Tên chính thức"
    assert result.complete is True


def test_strict_loader_rejects_duplicate_keys_and_nonfinite_duration(tmp_path):
    name = f"20240101 - A [{VIDEO_ID_A}].opus"
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"' + name + '": {"id": "' + VIDEO_ID_A + '"}, '
        '"' + name + '": {"id": "' + VIDEO_ID_B + '"}}',
        encoding="utf-8",
    )
    source = load_metadata_strict(str(duplicate), kind="live", priority=0)
    assert source.entries == ()
    assert source.warnings == ("metadata_duplicate_keys:1",)

    nonfinite = source_from_mapping({
        name: {**_metadata(VIDEO_ID_A, "A"), "duration": float("inf")}
    })
    assert nonfinite.entries[0].duration is None
    assert "invalid_duration" in nonfinite.entries[0].warnings


def test_supported_youtube_url_is_canonicalized_before_export_or_snapshot():
    name = f"20240101 - A [{VIDEO_ID_A}].opus"
    source = source_from_mapping({
        name: {
            **_metadata(VIDEO_ID_A, "A"),
            "url": (
                "https://user@example.invalid@www.youtube.com/watch"
                f"?v={VIDEO_ID_A}&private_parameter=redacted"
            ),
        }
    })

    result = ClipMetadataResolver([source]).resolve(name)

    assert result.url == f"https://youtu.be/{VIDEO_ID_A}"
    assert "private_parameter" not in result.url


def test_audit_counts_one_ambiguous_clip_once(tmp_path):
    requested = f"00000000 - New [{VIDEO_ID_A}].opus"
    resolver = ClipMetadataResolver.from_mapping({
        f"20240101 - A [{VIDEO_ID_A}].opus": _metadata(VIDEO_ID_A, "A"),
        f"20240102 - B [{VIDEO_ID_A}].opus": _metadata(VIDEO_ID_A, "B"),
    })
    audit = resolver.audit(
        [{"ten": requested, "duong_dan": requested}],
        database_file=str(tmp_path / "missing.pklz"),
    )

    assert audit.total_db_clips == 1
    assert audit.ambiguous == 1
    assert audit.complete == 0
    assert audit.partial == 0
