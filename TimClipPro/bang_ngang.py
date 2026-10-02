# -*- coding: utf-8 -*-
"""Dựng một dòng báo cáo ngang cho mỗi video vi phạm."""

from datetime import datetime
from typing import Any

from clip_metadata import ClipMetadataResolver
from engine import Engine, hhmmss, nhan_pham_vi
from publication_date import format_publication_date


SO_DOAN = 5

HEADER_NGANG: list = [
    "Thời gian quét",
    "Link kênh vi phạm",
    "Tên kênh vi phạm",
    "Id kênh vi phạm",
    "Link video vi phạm",
    "Tên video vi phạm",
    "Thời lượng video vi phạm",
    "Ngày đăng video vi phạm",
    "Đoạn vi phạm 1 trong video vi phạm",
    "Đoạn vi phạm 2 trong video vi phạm",
    "Đoạn vi phạm 3 trong video vi phạm",
    "Đoạn vi phạm 4 trong video vi phạm",
    "Đoạn vi phạm 5 trong video vi phạm",
    "Link video gốc 1",
    "Tên video gốc 1",
    "Ngày đăng video gốc 1",
    "Thời lượng video gốc 1",
    "Link video gốc 2",
    "Tên video gốc 2",
    "Ngày đăng video gốc 2",
    "Thời lượng video gốc 2",
    "Link video gốc 3",
    "Tên video gốc 3",
    "Ngày đăng video gốc 3",
    "Thời lượng video gốc 3",
    "Link video gốc 4",
    "Tên video gốc 4",
    "Ngày đăng video gốc 4",
    "Thời lượng video gốc 4",
    "Link video gốc 5",
    "Tên video gốc 5",
    "Ngày đăng video gốc 5",
    "Thời lượng video gốc 5",
    "Tổng số đoạn phát hiện",
]


def dinh_dang_ngay(s) -> str:
    """Đổi "20250115" -> "15/01/2025". Rỗng hoặc sai định dạng -> "".

    Uỷ quyền cho ``publication_date.format_publication_date`` để mọi exporter
    (CSV ngang, CSV dọc, Markdown, Sheets, UI) dùng đúng một hàm định dạng.
    """
    return format_publication_date(s)


def dinh_dang_doan(m: Any, source_id: str, source_ref: str) -> str:
    """Trả về khoảng thời gian và link nhảy tới mốc nếu có."""
    noi_dung = f"{m.start_hhmmss} – {m.end_hhmmss}"
    giay_link = max(0, int(m.start_s) - 3)
    link = Engine.link_moc(source_id, source_ref, giay_link)
    return f"{noi_dung} · {link}" if link else noi_dung


def dung_dong_ngang(
    kq: Any,
    clips_meta: dict | None = None,
    *,
    resolver: ClipMetadataResolver | None = None,
) -> list:
    """Dựng ĐÚNG MỘT dòng 34 phần tử từ một ScanResult. Hàm thuần, không I/O."""
    resolver = resolver or ClipMetadataResolver.from_mapping(clips_meta or {})

    loi = kq.status != "ok"
    matches = [] if loi else list(kq.matches[:SO_DOAN])
    dong = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        kq.channel_url or "",
        kq.channel_name or "",
        kq.channel_id or "",
        kq.source_ref or "",
        # Quét chưa trọn (dừng sớm, chỉ tải phần đầu, khúc lỗi) phải hiện ngay trên
        # dòng báo cáo — cột này vốn đã mang trạng thái "(LỖI: …)", không thêm cột mới.
        f"(LỖI: {kq.note})" if loi else (kq.source_name or "") + nhan_pham_vi(kq),
        hhmmss(kq.duration_s),
        dinh_dang_ngay(kq.upload_date),
    ]

    for i in range(SO_DOAN):
        dong.append(
            dinh_dang_doan(matches[i], kq.source_id, kq.source_ref)
            if i < len(matches)
            else ""
        )

    for i in range(SO_DOAN):
        if i >= len(matches):
            dong.extend(["", "", "", ""])
            continue
        meta = resolver.resolve(matches[i].clip)
        duration = meta.duration
        dong.extend([
            meta.url,
            meta.title,
            dinh_dang_ngay(meta.upload_date),
            (
                hhmmss(duration)
                if isinstance(duration, (int, float)) and duration > 0
                else ""
            ),
        ])

    so_dat_nguong = kq.so_dat_nguong
    dong.append(
        so_dat_nguong
        if isinstance(so_dat_nguong, int) and not isinstance(so_dat_nguong, bool)
        else 0
    )
    return dong
