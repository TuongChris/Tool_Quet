# -*- coding: utf-8 -*-
"""Nguồn chân lý duy nhất cho “Ngày đăng video”.

Vì sao cần module này
=====================
yt-dlp trả ``upload_date`` là **ngày theo lịch UTC** của thời điểm phát hành.
YouTube hiển thị cho người xem theo **múi giờ của họ**. Với người dùng ở
``Asia/Ho_Chi_Minh`` (UTC+7), video phát hành từ **17:00 UTC trở đi** đã sang
ngày hôm sau ở Việt Nam, nên ``upload_date`` lệch đúng một ngày.

Đo được trên hai video thật::

    Asv1kjFuX-4  timestamp=1785528034  UTC 2026-07-31 20:00:34
                 -> ICT 2026-08-01 03:00:34  => 01/08/2026 (đúng)
                 upload_date='20260731'      => 31/07/2026 (lệch 1 ngày)

    T_mKh8IUpWw  timestamp=1750445139  UTC 2025-06-20 18:45:39
                 -> ICT 2025-06-21 01:45:39  => 21/06/2025 (đúng)
                 upload_date='20250620'      => 20/06/2025 (lệch 1 ngày)

Video phát hành trong khoảng 00:00–16:59:59 UTC có cùng ngày ở cả hai múi giờ,
nên đúng sẵn — đó là lý do chỉ *một số* video bị sai chứ không phải tất cả.
Offset +7 giờ **không bao giờ** làm lệch quá một ngày; nếu quan sát thấy lệch
2 ngày thì đó là lỗi khác, phải điều tra riêng chứ không được cộng trừ bù.

Quy tắc
=======
1. Ưu tiên trường có **thời điểm chính xác** (epoch giây) vì chỉ nó mới đổi
   được múi giờ: ``release_timestamp`` rồi tới ``timestamp``.
2. Nếu không có epoch, dùng chuỗi ``YYYYMMDD`` (``release_date`` rồi
   ``upload_date``). Chuỗi này **không có giờ** nên không thể quy đổi múi giờ;
   lấy nguyên và đánh dấu độ tin cậy thấp hơn kèm cảnh báo.
3. Cuối cùng mới tới ngày suy từ tên file.

Không bao giờ:
  * cộng/trừ ``timedelta`` để “sửa” ngày,
  * dùng ``datetime.fromtimestamp(ts)`` không kèm tzinfo (phụ thuộc múi giờ máy),
  * dùng ``.replace(tzinfo=...)`` để quy đổi múi giờ,
  * lấy ngày từ mtime của file hay ngày tải.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOGGER = logging.getLogger("publication_date")

# Múi giờ dùng để quyết định “ngày đăng” người dùng nhìn thấy. Đổi được bằng
# biến môi trường để triển khai ở nơi khác không phải sửa code.
MUI_GIO_MAC_DINH = os.environ.get("TIMCLIP_MUI_GIO", "Asia/Ho_Chi_Minh")

# Epoch giây hợp lệ: từ 2005-01-01 (trước khi YouTube tồn tại) tới 2100-01-01.
EPOCH_NHO_NHAT = 1104537600
EPOCH_LON_NHAT = 4102444800

_YYYYMMDD = re.compile(r"\d{8}")

# Thứ tự đã kiểm chứng trên metadata thật; xem docstring module.
TRUONG_EPOCH = ("release_timestamp", "timestamp")
TRUONG_NGAY = ("release_date", "upload_date")

DO_TIN_CAY = {
    "release_timestamp": "high",
    "timestamp": "high",
    "release_date": "medium",
    "upload_date": "medium",
    "filename": "low",
}


@dataclass(frozen=True)
class PublicationDateResult:
    """Ngày đăng kèm nguồn gốc, để lúc nào cũng trả lời được “lấy từ đâu?”."""

    date: Optional[date]
    source_field: Optional[str]
    raw_value: Any
    confidence: str
    warnings: tuple[str, ...] = ()

    @property
    def yyyymmdd(self) -> str:
        """Dạng lưu trữ tương thích schema cũ. Rỗng khi không có ngày."""
        return self.date.strftime("%Y%m%d") if self.date else ""

    @property
    def can_review(self) -> bool:
        """Có dấu hiệu cần người xem lại (các trường ngày mâu thuẫn nhau)."""
        return any(w.startswith("khac_") for w in self.warnings)

    def to_dict(self) -> dict:
        return {
            "publication_date": self.yyyymmdd,
            "publication_date_source": self.source_field or "",
            "publication_date_confidence": self.confidence,
            "publication_date_warnings": list(self.warnings),
        }


KHONG_CO_NGAY = PublicationDateResult(
    date=None,
    source_field=None,
    raw_value=None,
    confidence="none",
    warnings=("khong_co_du_lieu_ngay",),
)


def _mui_gio(ten: str) -> ZoneInfo:
    try:
        return ZoneInfo(ten)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        LOGGER.warning(
            "event=publication_date.timezone_unknown tz=%r fallback=UTC", ten
        )
        return ZoneInfo("UTC")


def epoch_hop_le(gia_tri: Any) -> tuple[Optional[float], str]:
    """Trả về (epoch giây, cảnh báo). Không đoán mò khi giá trị khả nghi."""
    if isinstance(gia_tri, bool) or not isinstance(gia_tri, (int, float)):
        return None, ""
    so = float(gia_tri)
    if so <= 0:
        return None, ""
    if EPOCH_NHO_NHAT <= so <= EPOCH_LON_NHAT:
        return so, ""
    if EPOCH_NHO_NHAT * 1000 <= so <= EPOCH_LON_NHAT * 1000:
        # Có thể là mili giây. KHÔNG tự chia 1000: hiểu sai đơn vị âm thầm còn
        # tệ hơn là bỏ qua rồi rơi xuống trường ngày dạng chuỗi.
        return None, "epoch_co_the_la_mili_giay"
    return None, "epoch_ngoai_khoang_hop_ly"


def ngay_tu_epoch(gia_tri: Any, ten_mui_gio: str = MUI_GIO_MAC_DINH) -> Optional[date]:
    """Epoch UTC -> ngày theo lịch của múi giờ hiển thị.

    Luôn gắn ``timezone.utc`` khi dựng datetime rồi mới ``astimezone``; không
    bao giờ để Python suy múi giờ từ máy đang chạy.
    """
    so, _ = epoch_hop_le(gia_tri)
    if so is None:
        return None
    return datetime.fromtimestamp(so, timezone.utc).astimezone(_mui_gio(ten_mui_gio)).date()


def ngay_tu_chuoi(gia_tri: Any) -> Optional[date]:
    """Chuỗi ``YYYYMMDD`` -> date. ``00000000``/sai định dạng -> None."""
    if not isinstance(gia_tri, str):
        return None
    chuoi = gia_tri.strip()
    if not _YYYYMMDD.fullmatch(chuoi) or chuoi == "00000000":
        return None
    try:
        return datetime.strptime(chuoi, "%Y%m%d").date()
    except ValueError:
        return None


class PublicationDateResolver:
    """Quyết định ngày đăng chính tắc từ metadata, kèm nguồn gốc."""

    def __init__(self, display_timezone: str = MUI_GIO_MAC_DINH):
        self.display_timezone = display_timezone

    def resolve(self, metadata: Optional[Mapping[str, Any]]) -> PublicationDateResult:
        metadata = metadata or {}
        canh_bao: list[str] = []

        ngay_upload = ngay_tu_chuoi(metadata.get("upload_date"))

        for ten in TRUONG_EPOCH:
            if ten not in metadata:
                continue
            _, loi = epoch_hop_le(metadata.get(ten))
            if loi:
                canh_bao.append(f"{ten}:{loi}")
                continue
            ngay = ngay_tu_epoch(metadata.get(ten), self.display_timezone)
            if ngay is None:
                continue
            if ngay_upload and ngay != ngay_upload:
                # Không phải lỗi: đây đúng là trường hợp UTC và giờ địa phương
                # rơi vào hai ngày khác nhau. Ghi lại để audit truy được.
                canh_bao.append("khac_upload_date")
            return PublicationDateResult(
                date=ngay,
                source_field=ten,
                raw_value=metadata.get(ten),
                confidence=DO_TIN_CAY[ten],
                warnings=tuple(dict.fromkeys(canh_bao)),
            )

        for ten in TRUONG_NGAY:
            ngay = ngay_tu_chuoi(metadata.get(ten))
            if ngay is None:
                if metadata.get(ten) not in (None, "", "00000000"):
                    canh_bao.append(f"{ten}:khong_doc_duoc")
                continue
            # Chuỗi YYYYMMDD không có giờ nên không quy đổi được múi giờ.
            canh_bao.append("khong_co_gio_de_quy_doi_mui_gio")
            if ten == "release_date" and ngay_upload and ngay != ngay_upload:
                canh_bao.append("khac_upload_date")
            return PublicationDateResult(
                date=ngay,
                source_field=ten,
                raw_value=metadata.get(ten),
                confidence=DO_TIN_CAY[ten],
                warnings=tuple(dict.fromkeys(canh_bao)),
            )

        ngay_ten_file = ngay_tu_chuoi(metadata.get("filename_date"))
        if ngay_ten_file is not None:
            canh_bao.append("suy_tu_ten_file")
            return PublicationDateResult(
                date=ngay_ten_file,
                source_field="filename",
                raw_value=metadata.get("filename_date"),
                confidence=DO_TIN_CAY["filename"],
                warnings=tuple(dict.fromkeys(canh_bao)),
            )

        return PublicationDateResult(
            date=None,
            source_field=None,
            raw_value=None,
            confidence="none",
            warnings=tuple(dict.fromkeys([*canh_bao, "khong_co_du_lieu_ngay"])),
        )


_MAC_DINH = PublicationDateResolver()


def resolve_publication_date(
    metadata: Optional[Mapping[str, Any]],
    display_timezone: str = MUI_GIO_MAC_DINH,
) -> PublicationDateResult:
    """Tiện ích dùng resolver mặc định; tránh mỗi nơi tự dựng một cái."""
    if display_timezone == MUI_GIO_MAC_DINH:
        return _MAC_DINH.resolve(metadata)
    return PublicationDateResolver(display_timezone).resolve(metadata)


def format_publication_date(gia_tri: Any) -> str:
    """Định dạng DUY NHẤT cho báo cáo: ``DD/MM/YYYY``. Không hợp lệ -> "".

    Nhận ``date``, ``PublicationDateResult`` hoặc chuỗi ``YYYYMMDD`` để mọi
    exporter dùng chung một hàm thay vì mỗi chỗ tự parse.
    """
    if isinstance(gia_tri, PublicationDateResult):
        gia_tri = gia_tri.date
    if isinstance(gia_tri, datetime):
        gia_tri = gia_tri.date()
    if isinstance(gia_tri, date):
        return gia_tri.strftime("%d/%m/%Y")
    ngay = ngay_tu_chuoi(gia_tri)
    return ngay.strftime("%d/%m/%Y") if ngay else ""


def ghi_log_chan_doan(video_id: str, ket_qua: PublicationDateResult, metadata: Mapping) -> None:
    """Log provenance. Không ghi credential, cookie hay URL có token."""
    LOGGER.debug(
        "event=publication_date.resolve video_id=%s selected=%s source=%s "
        "confidence=%s upload_date=%r timestamp=%r release_timestamp=%r",
        video_id,
        ket_qua.yyyymmdd or "-",
        ket_qua.source_field or "-",
        ket_qua.confidence,
        metadata.get("upload_date"),
        metadata.get("timestamp"),
        metadata.get("release_timestamp"),
    )
    if ket_qua.date is None:
        LOGGER.warning(
            "event=publication_date.missing video_id=%s warnings=%s",
            video_id,
            ",".join(ket_qua.warnings) or "-",
        )
    elif ket_qua.can_review:
        LOGGER.info(
            "event=publication_date.differs video_id=%s selected=%s source=%s "
            "upload_date=%r",
            video_id,
            ket_qua.yyyymmdd,
            ket_qua.source_field,
            metadata.get("upload_date"),
        )
