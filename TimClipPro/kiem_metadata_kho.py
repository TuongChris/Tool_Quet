# -*- coding: utf-8 -*-
"""Audit metadata kho clip theo chế độ chỉ đọc; chỉ ghi snapshot khi có --apply."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

from clip_metadata import (
    canonical_filename,
    extract_youtube_id,
    load_metadata_strict,
)
from engine import Engine


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def _doc_registry(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        root = json.load(handle)
    if not isinstance(root, dict) or not isinstance(root.get("danh_sach"), list):
        raise RuntimeError("data/khos.json không đúng schema object/danh_sach.")
    return root


def _engine_chi_doc(root: str, data_dir: str, kho_name: str | None) -> tuple[Engine, dict]:
    """Dựng Engine tối thiểu mà không chạy __init__ (không tạo SQLite/thư mục)."""
    root = os.path.abspath(root)
    data_dir = os.path.abspath(data_dir)
    registry_path = os.path.join(data_dir, "khos.json")
    registry = _doc_registry(registry_path)
    selected_name = kho_name or str(registry.get("dang_dung") or "")
    warehouse = next(
        (
            item
            for item in registry["danh_sach"]
            if isinstance(item, dict) and item.get("ten") == selected_name
        ),
        None,
    )
    if warehouse is None:
        available = ", ".join(
            str(item.get("ten"))
            for item in registry["danh_sach"]
            if isinstance(item, dict)
        )
        raise RuntimeError(
            f"Không có kho tên chính xác «{selected_name}». Kho hiện có: {available or '(rỗng)'}."
        )

    eng = object.__new__(Engine)
    eng.root = root
    eng.data_dir = data_dir
    eng.kho_file = registry_path
    eng.kho_dang_dung = str(warehouse["ten"])
    eng.kho_thu_muc = str(warehouse.get("thu_muc") or "")
    eng.db_file = Engine._duong_dan_db_kho(eng, str(warehouse.get("db") or ""))
    eng.audfprint = Engine._tim_audfprint(eng)
    eng.sqlite_file = os.path.join(data_dir, "lichsu.db")
    eng._cache_khoa = None
    eng._cache_clips = []
    eng._metadata_cache_key = None
    eng._metadata_resolver_cache = None
    eng.canh_bao_metadata = []
    return eng, registry


def _history_matches(sqlite_file: str, video_id: str) -> dict:
    if not os.path.isfile(sqlite_file):
        return {"job": None, "matches": [], "warning": "Không có lichsu.db."}
    uri = Path(sqlite_file).resolve().as_uri() + "?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            job = connection.execute(
                "SELECT id, created_at, source_name, source_ref, source_id, status, "
                "n_matches FROM jobs WHERE source_id=? ORDER BY id DESC LIMIT 1",
                (video_id,),
            ).fetchone()
            if job is None:
                return {"job": None, "matches": [], "warning": "Không thấy job phù hợp."}
            rows = connection.execute(
                "SELECT clip, start_s, end_s, matched_s, hashes, confidence "
                "FROM matches WHERE job_id=? ORDER BY start_s",
                (job["id"],),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {
            "job": None,
            "matches": [],
            "warning": f"Không đọc được SQLite: {type(exc).__name__}: {exc}",
        }
    return {
        "job": dict(job),
        "matches": [dict(row) for row in rows],
        "warning": "",
    }


def _source_summary(resolver) -> list[dict]:
    result = []
    for source in resolver.sources:
        parent = os.path.basename(os.path.dirname(source.path))
        fatal = any(
            warning.startswith((
                "metadata_read_error",
                "metadata_duplicate_keys",
                "snapshot_schema_unsupported",
                "snapshot_warehouse_mismatch",
            ))
            for warning in source.warnings
        )
        result.append({
            "file": "/".join(filter(None, (parent, os.path.basename(source.path)))),
            "kind": source.kind,
            "exists": source.exists,
            "readable": source.exists and not fatal,
            "root_is_object": (
                source.exists
                and not fatal
                and "metadata_root_not_object" not in source.warnings
            ),
            "entries": len(source.entries),
            "invalid_entries": source.invalid_entries,
            "warnings": list(source.warnings[:20]),
        })
    return result


def _related_artifact_summaries(eng: Engine, clips: list[dict], known: set[str]) -> list[dict]:
    result = []
    for path, kind, priority in eng._metadata_source_candidates(clips):
        for suffix, label in ((".bak", "backup"), (".tmp", "temporary")):
            artifact = path + suffix
            normalized = os.path.normcase(os.path.abspath(artifact))
            if normalized in known:
                continue
            artifact_kind = f"{kind}_{label}"
            expected = eng.kho_dang_dung if kind == "snapshot" else ""
            source = load_metadata_strict(
                artifact,
                kind=artifact_kind,
                priority=priority + 1,
                expected_warehouse=expected,
            )
            summary = _source_summary(type("Sources", (), {"sources": (source,)})())[0]
            result.append(summary)
    return result


def _report(eng: Engine, requested_name: str | None, video_id: str) -> dict:
    clips = eng.db_clips(bo_cache=True)
    resolver = eng.clip_metadata_resolver(bo_cache=True)
    audit = resolver.audit(
        clips,
        warehouse=eng.kho_dang_dung,
        database_file=eng.db_file,
        warehouse_folder=eng.kho_thu_muc,
        sample_limit=20,
    )
    history = _history_matches(eng.sqlite_file, video_id) if video_id else {
        "job": None,
        "matches": [],
        "warning": "",
    }
    path_by_name = {
        str(clip.get("ten") or ""): str(clip.get("duong_dan") or "")
        for clip in clips
    }
    selected = []
    for match in history["matches"]:
        clip_name = str(match.get("clip") or "")
        resolved = resolver.resolve(clip_name, path_by_name.get(clip_name))
        selected.append({
            "match_clip": clip_name,
            "exact_metadata_key": (
                resolved.metadata_key if resolved.resolution_method == "exact" else ""
            ),
            "normalized_metadata_key": canonical_filename(
                clip_name,
                windows_semantics=True,
            ),
            "extracted_youtube_id": extract_youtube_id(clip_name) or "",
            "resolution_method": resolved.resolution_method,
            "resolution_status": resolved.status,
            "metadata_key": resolved.metadata_key,
            "video_id": resolved.video_id,
            "title": resolved.title,
            "url": resolved.url,
            "upload_date": resolved.upload_date,
            "duration": resolved.duration,
            "missing_fields": list(resolved.missing_fields),
            "start_s": match.get("start_s"),
            "end_s": match.get("end_s"),
            "hashes": match.get("hashes"),
        })
    sources = _source_summary(resolver)
    known_sources = {
        os.path.normcase(os.path.abspath(source.path)) for source in resolver.sources
    }
    sources.extend(_related_artifact_summaries(eng, clips, known_sources))
    return {
        "requested_warehouse": requested_name or "(active)",
        "warehouse": eng.kho_dang_dung,
        "database_path": eng.db_file,
        "warehouse_folder": eng.kho_thu_muc,
        "database_exists": os.path.isfile(eng.db_file),
        "warehouse_folder_exists": os.path.isdir(eng.kho_thu_muc),
        "audit": audit.to_dict(),
        "sources": sources,
        "target_video_id": video_id,
        "history": history["job"],
        "history_warning": history["warning"],
        "selected_matches": selected,
        "warnings": list(dict.fromkeys([*eng.canh_bao_metadata, *audit.warnings])),
    }


def _print_text(report: dict) -> None:
    audit = report["audit"]
    print(f"Kho: {report['warehouse']}")
    if report["requested_warehouse"] not in {"(active)", report["warehouse"]}:
        print(f"Kho được yêu cầu: {report['requested_warehouse']} (không phải tên active)")
    print(f"Database fingerprint: {report['database_path']}")
    print(f"Thư mục clip: {report['warehouse_folder'] or '(chưa đặt)'}")
    print(f"Database tồn tại: {report['database_exists']}")
    print(f"Thư mục clip tồn tại: {report['warehouse_folder_exists']}")
    print(f"Số clip trong database: {audit['total_db_clips']}")
    print(f"Số metadata entry: {audit['metadata_entries']}")
    print(f"Khớp exact: {audit['exact_matches']}")
    print(f"Khớp exact basename: {audit['exact_basename_matches']}")
    print(f"Khớp canonical: {audit['normalized_matches']}")
    print(f"  Có dùng normcase: {audit['normcase_matches']}")
    print(f"  Có dùng Unicode NFC: {audit['unicode_matches']}")
    print(f"Khớp YouTube ID: {audit['id_matches']}")
    print(f"Fallback từ filename: {audit['filename_fallbacks']}")
    print(f"Không thể ánh xạ: {audit['missing']}")
    print(f"Ánh xạ mơ hồ: {audit['ambiguous']}")
    print(f"Metadata orphan: {audit['metadata_orphans']}")
    print("\nNguồn metadata:")
    for source in report["sources"]:
        print(
            f"- {source['file']} [{source['kind']}]: exists={source['exists']} "
            f"readable={source['readable']} entries={source['entries']} "
            f"invalid={source['invalid_entries']}"
        )
        for warning in source["warnings"]:
            print(f"    warning: {warning}")
    if report["target_video_id"]:
        print(f"\nKết quả lịch sử cho {report['target_video_id']}:")
        if report["history_warning"]:
            print("- " + report["history_warning"])
        for index, match in enumerate(report["selected_matches"], start=1):
            print(f"{index}. Match clip: {match['match_clip']}")
            print(
                "   Exact metadata key: "
                + (match["exact_metadata_key"] or "(không có)")
            )
            print(f"   Normalized metadata key: {match['normalized_metadata_key']}")
            print(f"   Extracted YouTube ID: {match['extracted_youtube_id'] or '(rỗng)'}")
            print(f"   Resolution: {match['resolution_method']} / {match['resolution_status']}")
            print(f"   Title: {match['title']}")
            print(f"   URL: {match['url'] or '(rỗng)'}")
            print(
                "   Missing fields: "
                + (", ".join(match["missing_fields"]) or "(không có)")
            )
    if report["warnings"]:
        print("\nCảnh báo:")
        for warning in report["warnings"][:20]:
            print("- " + str(warning))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kiểm tra ánh xạ metadata kho clip (mặc định tuyệt đối chỉ đọc)."
    )
    parser.add_argument("--kho", help="Tên kho chính xác; bỏ trống để dùng kho active.")
    parser.add_argument("--video-id", default="", help="YouTube ID để kiểm tra lịch sử.")
    parser.add_argument("--json", action="store_true", help="Xuất JSON thay vì text.")
    parser.add_argument(
        "--repair-offline",
        action="store_true",
        help="Lập kế hoạch snapshot offline; vẫn dry-run nếu thiếu --apply.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Thực sự ghi snapshot (không sửa clips_meta.json, không gọi mạng).",
    )
    args = parser.parse_args()
    if args.apply and not args.repair_offline:
        parser.error("--apply chỉ hợp lệ cùng --repair-offline.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    root = os.path.dirname(os.path.abspath(__file__))
    eng, _registry = _engine_chi_doc(root, os.path.join(root, "data"), args.kho)
    report = _report(eng, args.kho, args.video_id)
    if args.repair_offline:
        repair = eng.khoi_phuc_metadata_offline(dry_run=not args.apply)
        report["offline_repair"] = repair.to_dict()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
        if "offline_repair" in report:
            repair = report["offline_repair"]
            mode = "APPLY" if args.apply else "DRY-RUN"
            print(f"\nKhôi phục offline [{mode}]:")
            print(f"- Snapshot: {repair['snapshot_path']}")
            print(f"- Sẽ cập nhật/đã cập nhật: {repair['updated']}")
            print(f"- Không đổi: {repair['unchanged']}")
            print(f"- Mơ hồ bỏ qua: {repair['skipped_ambiguous']}")
            print(f"- Chưa resolve: {repair['unresolved']}")
            for error in repair["errors"]:
                print(f"- ERROR: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
