# -*- coding: utf-8 -*-
"""Giao kết quả lên Google Sheets ở luồng riêng, không chặn lượt quét.

Vì sao cần
==========
Trước đây `app.py` đẩy Sheets **một lần sau cả batch**. Hệ quả:

* video 1 xong vẫn phải chờ video 10 mới lên Sheets;
* Google chậm/timeout/rate-limit thì cả thao tác đẩy treo theo;
* Sheets lỗi là mất luôn phần đã đẩy được vì không có trạng thái từng video.

Module này tách hẳn hai khái niệm: **quét xong** và **giao hàng xong**. Scan worker
chỉ bỏ việc vào hàng đợi rồi đi tiếp; một thread giao hàng lo phần còn lại.

Không lưu bền qua lần chạy
==========================
Hàng đợi nằm trong bộ nhớ. Tắt app khi còn `pending` là mất phần chưa gửi — kết quả
quét thì vẫn còn trong SQLite nên đẩy lại được thủ công. Outbox bền vững (SQLite) là
bước sau, chỉ làm khi có nhu cầu thật; xem `docs/SCAN_PIPELINE_V2_DESIGN.md` §4.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Optional

LOGGER = logging.getLogger("scan.sheet")

# Trạng thái giao hàng — TÁCH BIỆT với trạng thái quét.
CHUA_CAU_HINH = "not_configured"
CHO_GUI = "pending"
DANG_GUI = "sending"
DA_GUI = "sent"
DANG_THU_LAI = "retrying"
THAT_BAI = "failed"

TRANG_THAI_KET_THUC = frozenset({DA_GUI, THAT_BAI, CHUA_CAU_HINH})

# Lỗi tạm — thử lại có ích. Lỗi vĩnh viễn — thử lại chỉ tốn thời gian và quota.
DAU_HIEU_TAM_THOI = (
    "429", "500", "502", "503", "504",
    "timeout", "timed out", "temporarily", "rate limit", "quota exceeded",
    "connection reset", "connection aborted", "broken pipe",
    "name resolution", "getaddrinfo", "ssl",
)
DAU_HIEU_VINH_VIEN = (
    "permission_denied", "403", "404", "invalid credential", "unauthorized",
    "not found", "invalid_grant", "malformed",
)


def phan_loai_loi(loi: BaseException) -> bool:
    """True nếu đáng thử lại. Không rõ thì coi là tạm thời nhưng có giới hạn lần thử."""
    text = f"{type(loi).__name__}: {loi}".lower()
    for dau in DAU_HIEU_VINH_VIEN:
        if dau in text:
            return False
    for dau in DAU_HIEU_TAM_THOI:
        if dau in text:
            return True
    return True


def khoa_giao_hang(
    sheet_id: str,
    worksheet: str,
    dang_bao_cao: str,
    scan_job_id: object,
    source_id: str,
    rows: list,
) -> str:
    """Khoá idempotency: cùng khoá = cùng một lần giao, không được gửi hai lần.

    Gồm cả ``scan_job_id`` (id bản ghi lịch sử của lượt quét) nên **quét lại cùng
    một video sẽ tạo khoá khác** — đúng nghiệp vụ: người dùng quét lại là muốn có
    dòng mới, không phải bị chặn vì trùng. Nội dung ``rows`` cũng vào khoá để hai
    báo cáo khác nhau của cùng job không bị coi là một.
    """
    van = repr([[("" if v is None else str(v)) for v in r] for r in rows])
    tho = "|".join([
        str(sheet_id), str(worksheet), str(dang_bao_cao),
        str(scan_job_id), str(source_id), van,
    ])
    return hashlib.sha256(tho.encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class SheetDelivery:
    """Một lần giao hàng. Bất biến — cập nhật bằng ``replace``."""

    delivery_key: str
    source_id: str
    source_name: str
    header: list
    rows: list
    status: str = CHO_GUI
    attempts: int = 0
    last_error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def xong(self) -> bool:
        return self.status in TRANG_THAI_KET_THUC


class SheetDeliveryWorker:
    """Thread giao hàng: nhận việc qua queue, thử lại có backoff, báo trạng thái.

    Scan worker gọi ``enqueue()`` rồi đi tiếp ngay — không bao giờ chờ Google.
    """

    def __init__(
        self,
        sender: Callable[[list, list], int],
        max_attempts: int = 4,
        base_delay: float = 2.0,
        queue_maxsize: int = 256,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.sender = sender
        self.max_attempts = max(1, int(max_attempts))
        self.base_delay = max(0.0, float(base_delay))
        self._sleep = sleep_fn
        self._viec: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self._trang_thai: dict[str, SheetDelivery] = {}
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._dung = threading.Event()

    # ---------- API cho scan worker ----------

    def enqueue(self, delivery: SheetDelivery) -> bool:
        """Xếp hàng. Trả về False nếu khoá này đã được xếp/gửi rồi (chống trùng)."""
        with self._lock:
            cu = self._trang_thai.get(delivery.delivery_key)
            if cu is not None:
                LOGGER.info(
                    "event=scan.sheet.duplicate_skipped key=%s status=%s",
                    delivery.delivery_key[:12], cu.status,
                )
                return False
            self._trang_thai[delivery.delivery_key] = delivery
        self._viec.put(delivery.delivery_key)
        LOGGER.info(
            "event=scan.sheet.queued key=%s video_id=%s rows=%d",
            delivery.delivery_key[:12], delivery.source_id, len(delivery.rows),
        )
        return True

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._dung.clear()
            self._thread = threading.Thread(
                target=self._vong_lap, name="sheet-delivery", daemon=True
            )
            self._thread.start()

    def stop(self, wait_seconds: float = 5.0) -> None:
        self._dung.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=wait_seconds)

    # ---------- API cho UI ----------

    def snapshot(self) -> dict[str, SheetDelivery]:
        with self._lock:
            return dict(self._trang_thai)

    def tom_tat(self) -> dict:
        with self._lock:
            ds = list(self._trang_thai.values())
        return {
            "tong": len(ds),
            "da_gui": sum(1 for d in ds if d.status == DA_GUI),
            "cho_gui": sum(1 for d in ds if d.status in (CHO_GUI, DANG_GUI, DANG_THU_LAI)),
            "that_bai": sum(1 for d in ds if d.status == THAT_BAI),
        }

    @property
    def con_viec(self) -> bool:
        with self._lock:
            return any(not d.xong for d in self._trang_thai.values())

    # ---------- vòng lặp ----------

    def _cap_nhat(self, key: str, **thay_doi) -> None:
        with self._lock:
            cu = self._trang_thai.get(key)
            if cu is not None:
                self._trang_thai[key] = replace(cu, updated_at=time.time(), **thay_doi)

    def _vong_lap(self) -> None:
        while not self._dung.is_set():
            try:
                key = self._viec.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._giao(key)
            except Exception:  # noqa: BLE001 - thread không được chết vì một việc lỗi
                LOGGER.exception("event=scan.sheet.worker_error key=%s", key[:12])
            finally:
                self._viec.task_done()

    def _giao(self, key: str) -> None:
        with self._lock:
            viec = self._trang_thai.get(key)
        if viec is None or viec.xong:
            return

        for lan in range(1, self.max_attempts + 1):
            if self._dung.is_set():
                return
            self._cap_nhat(key, status=DANG_GUI, attempts=lan)
            try:
                so_dong = self.sender(viec.header, viec.rows)
            except Exception as loi:  # noqa: BLE001
                co_the_thu_lai = phan_loai_loi(loi)
                mo_ta = f"{type(loi).__name__}: {loi}"[:300]
                if not co_the_thu_lai or lan >= self.max_attempts:
                    self._cap_nhat(key, status=THAT_BAI, last_error=mo_ta)
                    LOGGER.error(
                        "event=scan.sheet.failed key=%s attempts=%d retryable=%s",
                        key[:12], lan, co_the_thu_lai,
                    )
                    return
                self._cap_nhat(key, status=DANG_THU_LAI, last_error=mo_ta)
                cho = self.base_delay * (2 ** (lan - 1))
                LOGGER.warning(
                    "event=scan.sheet.retry key=%s attempt=%d wait=%.1fs",
                    key[:12], lan, cho,
                )
                self._sleep(cho)
                continue

            self._cap_nhat(key, status=DA_GUI, last_error="")
            LOGGER.info(
                "event=scan.sheet.sent key=%s video_id=%s rows=%s",
                key[:12], viec.source_id, so_dong,
            )
            return
