# -*- coding: utf-8 -*-
"""Resolver metadata clip gốc độc lập UI, I/O mạng và thuật toán fingerprint.

Module này chỉ chuẩn hóa/index/resolve dữ liệu đã có. Không gọi YouTube, không đọc
credential và không sửa ``clips_meta.json``.
"""

from __future__ import annotations

import json
import logging
import math
import ntpath
import os
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, Mapping, Optional
from urllib.parse import parse_qs, urlparse


YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
_BRACKET_ID_PATTERN = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
_FILENAME_PATTERN = re.compile(
    r"^(?P<date>\d{8})\s*-\s*(?P<title>.+?)\s+"
    r"\[(?P<video_id>[A-Za-z0-9_-]{11})\](?:\.[^./\\]+)?$"
)
_FIELDS = ("video_id", "title", "url", "upload_date", "duration")


def configure_metadata_logging(level: int = logging.INFO) -> logging.Logger:
    """Cấu hình một terminal handler idempotent cho app/CLI chính thức."""
    logger = logging.getLogger("clip_metadata")
    if not any(getattr(handler, "_timclip_metadata", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler._timclip_metadata = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def basename_compatible(value: str | os.PathLike | None) -> str:
    """Lấy basename của cả path Windows/POSIX, độc lập host đang chạy test."""
    if value is None:
        return ""
    text = str(value).replace("\\", "/")
    return text.rsplit("/", 1)[-1].strip()


def canonical_filename(
    value: str | os.PathLike | None,
    *,
    windows_semantics: bool | None = None,
) -> str:
    """Canonical filename có kiểm soát; không xóa extension/ký tự ở giữa."""
    windows = os.name == "nt" if windows_semantics is None else windows_semantics
    name = basename_compatible(value)
    if windows:
        name = name.rstrip(" .")
    name = unicodedata.normalize("NFC", name)
    return ntpath.normcase(name) if windows else name


def _youtube_ids_from_url(value: object) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    text = value.strip()
    ids: set[str] = set()
    try:
        parsed = urlparse(text)
    except ValueError:
        parsed = None
    if parsed and parsed.scheme in {"http", "https"}:
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/", 1)[0]
            if YOUTUBE_ID_PATTERN.fullmatch(candidate):
                ids.add(candidate)
        elif host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
            for candidate in parse_qs(parsed.query).get("v", []):
                if YOUTUBE_ID_PATTERN.fullmatch(candidate):
                    ids.add(candidate)
    return ids


def _ids_from_value(value: object) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    text = value.strip()
    ids: set[str] = set()
    if YOUTUBE_ID_PATTERN.fullmatch(text):
        ids.add(text)
    ids.update(_BRACKET_ID_PATTERN.findall(text))
    ids.update(_youtube_ids_from_url(text))
    return ids


def extract_youtube_id(value: object) -> str | None:
    """Trả ID chỉ khi input xác định đúng một ID YouTube 11 ký tự."""
    ids = _ids_from_value(value)
    return next(iter(ids)) if len(ids) == 1 else None


def valid_upload_date(value: object) -> str:
    """Chỉ trả về ngày ``YYYYMMDD`` có thật; rỗng/``00000000``/sai định dạng → "".

    API công khai để `channel.py` và resolver dùng chung đúng một định nghĩa
    "ngày đăng hợp lệ", tránh hai nơi hiểu khác nhau.
    """
    return _valid_upload_date(value)


def _valid_upload_date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{8}", value):
        return ""
    if value == "00000000":
        return ""
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return ""
    return value


def _valid_duration(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    duration = float(value)
    return duration if math.isfinite(duration) and duration > 0 else None


@dataclass(frozen=True)
class MetadataEntry:
    key: str
    video_id: str = ""
    title: str = ""
    url: str = ""
    upload_date: str = ""
    duration: float | None = None
    source_file: str = ""
    source_kind: str = "live"
    priority: int = 0
    warnings: tuple[str, ...] = ()
    origin_method: str = ""

    def public_dict(self) -> dict:
        return {
            "id": self.video_id,
            "title": self.title,
            "url": self.url,
            "upload_date": self.upload_date,
            "duration": self.duration,
        }


@dataclass(frozen=True)
class MetadataSource:
    path: str
    kind: str
    priority: int
    entries: tuple[MetadataEntry, ...] = ()
    exists: bool = True
    invalid_entries: int = 0
    warnings: tuple[str, ...] = ()
    updated_at: str = ""


@dataclass(frozen=True)
class ResolvedClipMetadata:
    clip_name: str
    video_id: str
    title: str
    url: str
    upload_date: str
    duration: float | None
    resolution_method: str
    status: str
    metadata_key: str
    source_file: str
    source_kind: str
    complete: bool
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]

    def public_dict(self) -> dict:
        return {
            "id": self.video_id,
            "title": self.title,
            "url": self.url,
            "upload_date": self.upload_date,
            "duration": self.duration,
        }


@dataclass(frozen=True)
class MetadataCoverage:
    selected_matches: int = 0
    resolved_complete: int = 0
    resolved_partial: int = 0
    filename_fallbacks: int = 0
    unresolved: int = 0
    ambiguous: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MetadataAuditSample:
    clip_name: str
    resolution_method: str
    status: str
    video_id: str
    missing_fields: tuple[str, ...]


@dataclass(frozen=True)
class MetadataAudit:
    warehouse: str
    database_file: str
    warehouse_folder: str
    database_exists: bool
    warehouse_folder_exists: bool
    total_db_clips: int
    metadata_entries: int
    exact_matches: int
    exact_basename_matches: int
    normalized_matches: int
    normcase_matches: int
    unicode_matches: int
    id_matches: int
    filename_fallbacks: int
    missing: int
    ambiguous: int
    complete: int
    partial: int
    invalid_entries: int
    conflicts: int
    metadata_orphans: int
    source_files: tuple[str, ...]
    updated_at: str
    warnings: tuple[str, ...]
    samples: tuple[MetadataAuditSample, ...] = ()

    def to_dict(self) -> dict:
        result = asdict(self)
        result["samples"] = [asdict(sample) for sample in self.samples]
        return result


@dataclass(frozen=True)
class MetadataRepairResult:
    dry_run: bool
    snapshot_path: str
    total_db_clips: int
    updated: int
    unchanged: int
    skipped_ambiguous: int
    unresolved: int
    errors: tuple[str, ...]
    audit: MetadataAudit

    def to_dict(self) -> dict:
        result = asdict(self)
        result["audit"] = self.audit.to_dict()
        return result


def source_from_mapping(
    mapping: object,
    *,
    path: str = "",
    kind: str = "live",
    priority: int = 0,
    exists: bool = True,
    inherited_warnings: Iterable[str] = (),
    updated_at: str = "",
) -> MetadataSource:
    """Validate mapping; entry/field sai bị cô lập và có warning giải thích."""
    warnings = list(inherited_warnings)
    if not isinstance(mapping, Mapping):
        warnings.append("metadata_root_not_object")
        return MetadataSource(
            path=path,
            kind=kind,
            priority=priority,
            exists=exists,
            warnings=tuple(warnings),
            updated_at=updated_at,
        )

    entries: list[MetadataEntry] = []
    invalid_entries = 0
    for raw_key, raw_value in mapping.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            invalid_entries += 1
            warnings.append("metadata_key_invalid")
            continue
        if not isinstance(raw_value, Mapping):
            invalid_entries += 1
            warnings.append(f"entry_not_object:{basename_compatible(raw_key)}")
            continue

        entry_warnings: list[str] = []
        raw_id = raw_value.get("id")
        video_id = extract_youtube_id(raw_id) or ""
        if raw_id not in (None, "") and not video_id:
            entry_warnings.append("invalid_id")

        title = raw_value.get("title")
        if title is None:
            title = ""
        elif not isinstance(title, str):
            title = ""
            entry_warnings.append("invalid_title")

        url = raw_value.get("url")
        if url is None:
            url = ""
        elif not isinstance(url, str):
            url = ""
            entry_warnings.append("invalid_url")
        else:
            url = url.strip()
            try:
                parsed_url = urlparse(url) if url else None
            except ValueError:
                parsed_url = None
            if url and (
                parsed_url is None
                or parsed_url.scheme not in {"http", "https"}
                or len(_youtube_ids_from_url(url)) != 1
            ):
                url = ""
                entry_warnings.append("invalid_url")

        # `publication_date` là trường chính tắc (ngày người dùng nhìn thấy trên
        # YouTube, đã quy đổi múi giờ). `upload_date` là schema cũ, chỉ dùng khi
        # entry chưa được nâng cấp — xem docs/PUBLICATION_DATE_ARCHITECTURE.md.
        raw_date = raw_value.get("publication_date")
        upload_date = _valid_upload_date(raw_date)
        if not upload_date:
            if raw_date not in (None, "", "00000000"):
                entry_warnings.append("invalid_publication_date")
            # Rơi về schema cũ là đường chạy BÌNH THƯỜNG với kho đã có từ trước,
            # không phải lỗi — tuyệt đối không phát cảnh báo ở đây.
            raw_date = raw_value.get("upload_date")
            upload_date = _valid_upload_date(raw_date)
            if raw_date not in (None, "", "00000000") and not upload_date:
                entry_warnings.append("invalid_upload_date")

        raw_duration = raw_value.get("duration")
        duration = _valid_duration(raw_duration)
        if raw_duration not in (None, "", 0, 0.0) and duration is None:
            entry_warnings.append("invalid_duration")

        ids = _ids_from_value(raw_key) | _ids_from_value(url)
        if video_id:
            ids.add(video_id)
        if len(ids) == 1:
            video_id = next(iter(ids))
            if url:
                # Chỉ giữ URL canonical, không persist userinfo/query/fragment có
                # thể chứa token dù hostname YouTube hợp lệ.
                url = f"https://youtu.be/{video_id}"
        elif len(ids) > 1:
            # Không index một entry tự mâu thuẫn theo bất kỳ ID nào. Exact lookup
            # vẫn có thể hiển thị các field không mâu thuẫn kèm cảnh báo.
            video_id = ""
            url = ""
            entry_warnings.append("conflicting_ids_in_entry")

        origin_method = ""
        if kind.startswith("snapshot"):
            raw_origin = raw_value.get("resolution_method")
            if raw_origin in {
                "exact",
                "exact_basename",
                "canonical_filename",
                "video_id",
                "filename_fallback",
                "basename_fallback",
            }:
                origin_method = str(raw_origin)

        entries.append(MetadataEntry(
            key=raw_key,
            video_id=video_id,
            title=title.strip(),
            url=url,
            upload_date=upload_date,
            duration=duration,
            source_file=path,
            source_kind=kind,
            priority=priority,
            warnings=tuple(entry_warnings),
            origin_method=origin_method,
        ))
        if entry_warnings:
            invalid_entries += 1
            for category in dict.fromkeys(entry_warnings):
                warnings.append(f"invalid_field:{category}")

    return MetadataSource(
        path=path,
        kind=kind,
        priority=priority,
        entries=tuple(entries),
        exists=exists,
        invalid_entries=invalid_entries,
        warnings=tuple(dict.fromkeys(warnings)),
        updated_at=updated_at,
    )


def load_metadata_strict(
    path: str,
    *,
    kind: str,
    priority: int,
    expected_warehouse: str = "",
) -> MetadataSource:
    """Đọc JSON tuyệt đối không phục hồi/rename/ghi file khi malformed."""
    absolute = os.path.abspath(path)
    if not os.path.isfile(absolute):
        return MetadataSource(
            path=absolute,
            kind=kind,
            priority=priority,
            exists=False,
        )
    duplicate_keys: list[str] = []

    def pairs_hook(pairs: list[tuple]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                duplicate_keys.append(str(key))
            result[key] = value
        return result

    def reject_constant(value: str):
        raise ValueError(f"JSON constant không hợp lệ: {value}")

    try:
        with open(absolute, encoding="utf-8") as handle:
            root = json.load(
                handle,
                object_pairs_hook=pairs_hook,
                parse_constant=reject_constant,
            )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return MetadataSource(
            path=absolute,
            kind=kind,
            priority=priority,
            warnings=(f"metadata_read_error:{type(exc).__name__}",),
        )
    if duplicate_keys:
        return MetadataSource(
            path=absolute,
            kind=kind,
            priority=priority,
            warnings=(f"metadata_duplicate_keys:{len(duplicate_keys)}",),
        )

    updated_at = ""
    mapping = root
    warnings: list[str] = []
    if kind.startswith("snapshot"):
        if not isinstance(root, Mapping):
            mapping = root
        else:
            warehouse = root.get("warehouse") or root.get("warehouse_name") or ""
            if expected_warehouse and warehouse != expected_warehouse:
                return MetadataSource(
                    path=absolute,
                    kind=kind,
                    priority=priority,
                    warnings=("snapshot_warehouse_mismatch",),
                )
            if root.get("schema_version") != 1:
                return MetadataSource(
                    path=absolute,
                    kind=kind,
                    priority=priority,
                    warnings=("snapshot_schema_unsupported",),
                )
            mapping = root.get("clips")
            updated_at = str(root.get("updated_at") or "")
    return source_from_mapping(
        mapping,
        path=absolute,
        kind=kind,
        priority=priority,
        inherited_warnings=warnings,
        updated_at=updated_at,
    )


def _entry_signature(entry: MetadataEntry) -> tuple:
    return (
        entry.video_id,
        entry.title,
        entry.url,
        entry.upload_date,
        entry.duration,
    )


def _entry_identity_conflict(entry: MetadataEntry) -> bool:
    return any(
        warning in {
            "conflicting_ids_in_entry",
            "conflicting_ids_across_sources",
        }
        for warning in entry.warnings
    )


def _entry_quality(entry: MetadataEntry) -> int:
    if entry.origin_method == "filename_fallback":
        return 1
    if entry.origin_method == "basename_fallback":
        return 2
    return 0


def _merge_entries(entries: Iterable[MetadataEntry]) -> tuple[MetadataEntry, tuple[str, ...]]:
    ordered = sorted(
        entries,
        key=lambda item: (
            _entry_quality(item),
            item.priority,
            item.source_file,
            item.key,
        ),
    )
    if not ordered:
        raise ValueError("Không có metadata entry để hợp nhất.")
    first = ordered[0]
    trusted_ids = {entry.video_id for entry in ordered if entry.video_id}
    if len(trusted_ids) > 1 or any(_entry_identity_conflict(entry) for entry in ordered):
        warnings = [warning for entry in ordered for warning in entry.warnings]
        warnings.append("conflicting_ids_across_sources")
        conflicts = (f"conflict:video_id:{basename_compatible(first.key)}",)
        # Không merge theo field khi identity không thống nhất: điều đó có thể tạo
        # record lai id=A nhưng URL/title của B. Resolver sẽ coi entry này ambiguous.
        return MetadataEntry(
            key=first.key,
            video_id=first.video_id,
            title=first.title,
            url=first.url,
            upload_date=first.upload_date,
            duration=first.duration,
            source_file=first.source_file,
            source_kind=first.source_kind,
            priority=first.priority,
            warnings=tuple(dict.fromkeys(warnings + list(conflicts))),
            origin_method=first.origin_method,
        ), conflicts
    values = {field: getattr(first, field) for field in _FIELDS}
    warnings = list(first.warnings)
    conflicts: list[str] = []
    origin_method = first.origin_method
    for entry in ordered[1:]:
        warnings.extend(entry.warnings)
        for field in _FIELDS:
            current = values[field]
            candidate = getattr(entry, field)
            if current in ("", None) and candidate not in ("", None):
                values[field] = candidate
                if _entry_quality(entry) > 0:
                    origin_method = "filename_fallback"
                    warnings.append("fields_enriched_from_snapshot_fallback")
            elif (
                current not in ("", None)
                and candidate not in ("", None)
                and current != candidate
            ):
                conflicts.append(f"conflict:{field}:{basename_compatible(first.key)}")
    return MetadataEntry(
        key=first.key,
        video_id=str(values["video_id"] or ""),
        title=str(values["title"] or ""),
        url=str(values["url"] or ""),
        upload_date=str(values["upload_date"] or ""),
        duration=values["duration"],
        source_file=first.source_file,
        source_kind=first.source_kind,
        priority=first.priority,
        warnings=tuple(dict.fromkeys(warnings + conflicts)),
        origin_method=origin_method,
    ), tuple(dict.fromkeys(conflicts))


def filename_fallback_parts(value: str) -> dict:
    """Suy metadata từ tên file ``<ngày> - <tiêu đề> [<VIDEO_ID>].<ext>``.

    API công khai cho các module khác (channel.py) dùng chung đúng một cách bóc
    tách tên file với resolver, tránh hai định nghĩa lệch nhau.
    """
    return _filename_fallback_parts(value)


def _filename_fallback_parts(value: str) -> dict:
    name = basename_compatible(value)
    match = _FILENAME_PATTERN.fullmatch(name)
    if not match:
        return {
            "video_id": "",
            "title": name,
            "url": "",
            "upload_date": "",
            "duration": None,
        }
    video_id = match.group("video_id")
    return {
        "video_id": video_id,
        "title": match.group("title").strip(),
        "url": f"https://youtu.be/{video_id}",
        "upload_date": _valid_upload_date(match.group("date")),
        "duration": None,
    }


class ClipMetadataResolver:
    """Index metadata một lần; mỗi resolve không quét tuyến tính toàn mapping."""

    def __init__(
        self,
        sources: Iterable[MetadataSource] = (),
        *,
        windows_semantics: bool | None = None,
    ):
        self.sources = tuple(sorted(sources, key=lambda item: item.priority))
        self.windows_semantics = (
            os.name == "nt" if windows_semantics is None else windows_semantics
        )
        raw_exact: dict[str, list[MetadataEntry]] = defaultdict(list)
        for source in self.sources:
            for entry in source.entries:
                raw_exact[entry.key].append(entry)

        self.conflicts: list[str] = []
        self._exact: dict[str, MetadataEntry] = {}
        for key, entries in raw_exact.items():
            merged, conflicts = _merge_entries(entries)
            self._exact[key] = merged
            self.conflicts.extend(conflicts)

        self._basename: dict[str, list[MetadataEntry]] = defaultdict(list)
        self._canonical: dict[str, list[MetadataEntry]] = defaultdict(list)
        self._video_id: dict[str, list[MetadataEntry]] = defaultdict(list)
        for entry in self._exact.values():
            basename = basename_compatible(entry.key)
            self._basename[basename].append(entry)
            self._canonical[canonical_filename(
                basename,
                windows_semantics=self.windows_semantics,
            )].append(entry)
            # source_from_mapping() chỉ đặt video_id khi toàn bộ bằng chứng trong
            # id/key/url cùng nhất quán. Không index lại từng field ở đây vì một
            # entry tự mâu thuẫn tuyệt đối không được chọn qua ID.
            if entry.video_id:
                self._video_id[entry.video_id].append(entry)

        for video_id, entries in self._video_id.items():
            if len({_entry_signature(entry) for entry in entries}) > 1:
                self.conflicts.append(f"ambiguous_video_id:{video_id}")

        self.invalid_entries = sum(source.invalid_entries for source in self.sources)
        self.warnings = tuple(dict.fromkeys(
            warning
            for source in self.sources
            for warning in source.warnings
        ))
        self.updated_at = next(
            (source.updated_at for source in self.sources if source.updated_at),
            "",
        )

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping | None,
        *,
        windows_semantics: bool | None = None,
    ) -> "ClipMetadataResolver":
        return cls(
            [source_from_mapping(mapping or {}, kind="compatibility")],
            windows_semantics=windows_semantics,
        )

    @property
    def metadata_entries(self) -> int:
        return len(self._exact)

    @property
    def source_files(self) -> tuple[str, ...]:
        return tuple(
            source.path for source in self.sources if source.exists and source.path
        )

    def compatibility_mapping(self) -> dict:
        return {key: entry.public_dict() for key, entry in self._exact.items()}

    @staticmethod
    def _choose(candidates: Iterable[MetadataEntry]) -> tuple[MetadataEntry | None, bool]:
        entries = list(dict.fromkeys(candidates))
        if not entries:
            return None, False
        if any(_entry_identity_conflict(entry) for entry in entries):
            return None, True
        best_quality = min(_entry_quality(entry) for entry in entries)
        entries = [entry for entry in entries if _entry_quality(entry) == best_quality]
        signatures = {_entry_signature(entry) for entry in entries}
        if len(signatures) > 1:
            return None, True
        merged, _ = _merge_entries(entries)
        return merged, False

    @staticmethod
    def _ambiguous_result(
        clip_name: str,
        warning: str = "metadata_candidates_ambiguous",
    ) -> ResolvedClipMetadata:
        name = basename_compatible(clip_name)
        return ResolvedClipMetadata(
            clip_name=name,
            video_id="",
            title=name,
            url="",
            upload_date="",
            duration=None,
            resolution_method="ambiguous",
            status="ambiguous",
            metadata_key="",
            source_file="",
            source_kind="none",
            complete=False,
            missing_fields=("video_id", "url", "upload_date", "duration"),
            warnings=(warning,),
        )

    def _resolved_from_entry(
        self,
        entry: MetadataEntry,
        clip_name: str,
        method: str,
    ) -> ResolvedClipMetadata:
        fallback = _filename_fallback_parts(clip_name)
        fallback_id = str(fallback["video_id"])
        identity_conflict = "conflicting_ids_in_entry" in entry.warnings or bool(
            entry.video_id and fallback_id and entry.video_id != fallback_id
        )
        if identity_conflict:
            return self._ambiguous_result(clip_name, "clip_identity_conflict")
        video_id = entry.video_id or str(fallback["video_id"])
        title = entry.title or str(fallback["title"])
        url = entry.url or str(fallback["url"])
        upload_date = entry.upload_date or str(fallback["upload_date"])
        duration = entry.duration
        values = {
            "video_id": video_id,
            "title": title,
            "url": url,
            "upload_date": upload_date,
            "duration": duration,
        }
        missing = tuple(field for field, value in values.items() if value in ("", None))
        warnings = list(entry.warnings)
        enriched_from_filename = any(
            getattr(entry, field) in ("", None)
            and fallback.get(field) not in ("", None)
            for field in ("video_id", "title", "url", "upload_date")
        )
        if enriched_from_filename:
            warnings.append("fields_enriched_from_filename")
        if missing:
            warnings.append("missing:" + ",".join(missing))
        complete = not missing
        effective_method = (
            entry.origin_method
            if entry.origin_method in {"filename_fallback", "basename_fallback"}
            else method
        )
        if enriched_from_filename:
            effective_method = "filename_fallback"
        status = "complete" if complete else "partial"
        if effective_method == "basename_fallback":
            complete = False
            status = "unresolved"
        return ResolvedClipMetadata(
            clip_name=basename_compatible(clip_name),
            video_id=video_id,
            title=title or basename_compatible(clip_name),
            url=url,
            upload_date=upload_date,
            duration=duration,
            resolution_method=effective_method,
            status=status,
            metadata_key=entry.key,
            source_file=entry.source_file,
            source_kind=entry.source_kind,
            complete=complete,
            missing_fields=missing,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def resolve(
        self,
        clip_name: str,
        clip_path: str | None = None,
    ) -> ResolvedClipMetadata:
        """Resolve theo exact → basename → canonical → unique ID → fallback."""
        names = [str(clip_name or "")]
        if clip_path and str(clip_path) not in names:
            names.append(str(clip_path))

        input_ids: set[str] = set()
        for name in names:
            input_ids.update(_ids_from_value(name))
        if len(input_ids) > 1:
            return self._ambiguous_result(
                clip_name or names[0],
                "input_clip_identity_conflict",
            )

        # Mức 1: exact clip name/path.
        ambiguous_seen = False
        for name in names:
            entry = self._exact.get(name)
            if entry and _entry_identity_conflict(entry):
                return self._ambiguous_result(
                    clip_name or name,
                    "metadata_identity_conflict",
                )
            if entry and _entry_quality(entry) == 0:
                return self._resolved_from_entry(entry, clip_name or name, "exact")

        # Mức 2: exact basename, kể cả metadata key là path cũ.
        for name in names:
            basename = basename_compatible(name)
            entry = self._exact.get(basename)
            if entry and _entry_identity_conflict(entry):
                return self._ambiguous_result(
                    clip_name or basename,
                    "metadata_identity_conflict",
                )
            if entry and _entry_quality(entry) == 0:
                return self._resolved_from_entry(entry, clip_name or basename, "exact_basename")
            selected, ambiguous = self._choose(self._basename.get(basename, ()))
            ambiguous_seen = ambiguous_seen or ambiguous
            if selected and _entry_quality(selected) == 0:
                return self._resolved_from_entry(
                    selected,
                    clip_name or basename,
                    "exact_basename",
                )

        # Mức 3: canonical filename.
        canonical_candidates: list[MetadataEntry] = []
        for name in names:
            canonical_candidates.extend(self._canonical.get(canonical_filename(
                name,
                windows_semantics=self.windows_semantics,
            ), ()))
        selected, ambiguous = self._choose(canonical_candidates)
        ambiguous_seen = ambiguous_seen or ambiguous
        if selected and _entry_quality(selected) == 0:
            return self._resolved_from_entry(
                selected,
                clip_name or names[0],
                "canonical_filename",
            )

        # Mức 4: ID ổn định từ filename/path.
        ids = input_ids
        if len(ids) == 1:
            video_id = next(iter(ids))
            selected, ambiguous = self._choose(self._video_id.get(video_id, ()))
            ambiguous_seen = ambiguous_seen or ambiguous
            if selected:
                return self._resolved_from_entry(
                    selected,
                    clip_name or names[0],
                    "video_id",
                )
        elif len(ids) > 1:
            ambiguous_seen = True

        if ambiguous_seen:
            return self._ambiguous_result(clip_name or names[0])

        # Mức 6/7: phục hồi offline từ filename hoặc tối thiểu basename.
        name = basename_compatible(clip_name or names[0])
        fallback = _filename_fallback_parts(name)
        if fallback["video_id"]:
            missing = tuple(
                field for field, value in fallback.items() if value in ("", None)
            )
            return ResolvedClipMetadata(
                clip_name=name,
                video_id=str(fallback["video_id"]),
                title=str(fallback["title"]),
                url=str(fallback["url"]),
                upload_date=str(fallback["upload_date"]),
                duration=None,
                resolution_method="filename_fallback",
                status="partial",
                metadata_key="",
                source_file="",
                source_kind="filename",
                complete=False,
                missing_fields=missing,
                warnings=(
                    "official_metadata_missing",
                    "title_may_be_sanitized_or_truncated",
                    "missing:" + ",".join(missing),
                ),
            )

        return ResolvedClipMetadata(
            clip_name=name,
            video_id="",
            title=name,
            url="",
            upload_date="",
            duration=None,
            resolution_method="basename_fallback",
            status="unresolved",
            metadata_key="",
            source_file="",
            source_kind="none",
            complete=False,
            missing_fields=("video_id", "url", "upload_date", "duration"),
            warnings=("official_metadata_unresolved",),
        )

    def resolve_many(
        self,
        clips: Iterable[tuple[str, Optional[str]]],
    ) -> tuple[ResolvedClipMetadata, ...]:
        """Giữ nguyên thứ tự và duplicate để không lệch đoạn ↔ video gốc."""
        return tuple(self.resolve(name, path) for name, path in clips)

    def coverage(self, clip_names: Iterable[str]) -> MetadataCoverage:
        resolved = [self.resolve(name) for name in clip_names]
        return MetadataCoverage(
            selected_matches=len(resolved),
            resolved_complete=sum(item.status == "complete" for item in resolved),
            resolved_partial=sum(item.status == "partial" for item in resolved),
            filename_fallbacks=sum(
                item.resolution_method == "filename_fallback" for item in resolved
            ),
            unresolved=sum(item.status == "unresolved" for item in resolved),
            ambiguous=sum(item.status == "ambiguous" for item in resolved),
        )

    def audit(
        self,
        db_clips: Iterable[Mapping],
        *,
        warehouse: str = "",
        database_file: str = "",
        warehouse_folder: str = "",
        sample_limit: int = 20,
    ) -> MetadataAudit:
        clips = list(db_clips)
        counts: dict[str, int] = defaultdict(int)
        matched_keys: set[str] = set()
        samples: list[MetadataAuditSample] = []
        for clip in clips:
            name = str(clip.get("ten") or basename_compatible(clip.get("duong_dan")))
            path = str(clip.get("duong_dan") or "")
            item = self.resolve(name, path)
            counts["method:" + item.resolution_method] += 1
            counts["status:" + item.status] += 1
            if item.resolution_method == "canonical_filename":
                requested = basename_compatible(name).strip()
                stored = basename_compatible(item.metadata_key).strip()
                requested_nfc = unicodedata.normalize("NFC", requested)
                stored_nfc = unicodedata.normalize("NFC", stored)
                if requested != requested_nfc or stored != stored_nfc:
                    counts["normalization:unicode"] += 1
                if (
                    requested_nfc != stored_nfc
                    and ntpath.normcase(requested_nfc) == ntpath.normcase(stored_nfc)
                ):
                    counts["normalization:normcase"] += 1
            if item.metadata_key:
                matched_keys.add(item.metadata_key)
            if item.status != "complete" and len(samples) < sample_limit:
                samples.append(MetadataAuditSample(
                    clip_name=basename_compatible(name),
                    resolution_method=item.resolution_method,
                    status=item.status,
                    video_id=item.video_id,
                    missing_fields=item.missing_fields,
                ))
        warnings = list(self.warnings)
        if clips and counts["status:complete"] == 0:
            warnings.append("metadata_coverage_complete_zero")
        return MetadataAudit(
            warehouse=warehouse,
            database_file=os.path.basename(database_file),
            warehouse_folder=os.path.basename(os.path.normpath(warehouse_folder))
            if warehouse_folder else "",
            database_exists=os.path.isfile(database_file),
            warehouse_folder_exists=os.path.isdir(warehouse_folder),
            total_db_clips=len(clips),
            metadata_entries=self.metadata_entries,
            exact_matches=counts["method:exact"],
            exact_basename_matches=counts["method:exact_basename"],
            normalized_matches=counts["method:canonical_filename"],
            normcase_matches=counts["normalization:normcase"],
            unicode_matches=counts["normalization:unicode"],
            id_matches=counts["method:video_id"],
            filename_fallbacks=counts["method:filename_fallback"],
            missing=counts["method:basename_fallback"],
            ambiguous=counts["status:ambiguous"],
            complete=counts["status:complete"],
            partial=counts["status:partial"],
            invalid_entries=self.invalid_entries,
            conflicts=len(set(self.conflicts)),
            metadata_orphans=len(set(self._exact) - matched_keys),
            source_files=tuple(
                "/".join(filter(None, (
                    os.path.basename(os.path.dirname(path)),
                    os.path.basename(path),
                )))
                for path in self.source_files
            ),
            updated_at=self.updated_at,
            warnings=tuple(dict.fromkeys(warnings)),
            samples=tuple(samples),
        )
