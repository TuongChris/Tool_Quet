# -*- coding: utf-8 -*-
"""Điều phối một batch quét: tiến độ, kết quả streaming, trạng thái giao Sheets.

Không phụ thuộc Streamlit — worker chỉ phát event; main thread của UI đọc snapshot.
Đây là đúng ranh giới mà ``fingerprint_progress.FingerprintJobController`` đã dùng và
đã có test; tái dùng pattern thay vì phát minh cái mới.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, replace
from typing import Callable, Optional

LOGGER = logging.getLogger("scan.job")

# Phase phản ánh đúng những gì engine thực sự làm (xem Engine.scan_youtube/scan_media).
PHASE_CHO = "queued"
PHASE_METADATA = "fetching_metadata"
PHASE_TAI = "downloading"
PHASE_CAT_KHUC = "chunking"
PHASE_SO_KHOP = "matching"
PHASE_TONG_HOP = "merging"
PHASE_XONG = "completed"
PHASE_LOI = "failed"
PHASE_HUY = "cancelled"

# Trạng thái QUÉT của một video — tách hẳn khỏi trạng thái giao Sheets.
QUET_CHO = "queued"
QUET_DANG_CHAY = "running"
QUET_XONG = "completed"
QUET_LOI = "failed"

_TU_KHOA_PHASE = (
    ("Đang lấy thông tin video", PHASE_METADATA),
    ("chuẩn bị tải", PHASE_METADATA),
    ("Đang tải", PHASE_TAI),
    ("Đã có sẵn audio", PHASE_TAI),
    ("Đang cắt khúc", PHASE_CAT_KHUC),
    ("Đang đo", PHASE_CAT_KHUC),
    ("Đang so khớp", PHASE_SO_KHOP),
    ("Đang nạp kho", PHASE_SO_KHOP),
    ("Xong —", PHASE_TONG_HOP),
)


def doan_phase(thong_bao: str) -> Optional[str]:
    """Suy phase từ thông báo tiến độ của engine.

    Engine đã phát thông báo tiếng Việt rất mô tả cho từng bước; ánh xạ chúng thành
    phase có cấu trúc rẻ hơn nhiều so với việc sửa chữ ký mọi hàm trong engine chỉ
    để mang thêm một tham số phase. Không khớp thì trả None và giữ phase cũ.
    """
    for tu_khoa, phase in _TU_KHOA_PHASE:
        if tu_khoa in thong_bao:
            return phase
    return None


@dataclass(frozen=True)
class ScanLaunchConfig:
    """Ảnh chụp cấu hình lúc bấm Bắt đầu quét.

    Thread nền **không có ScriptRunContext**, nên đọc ``st.session_state`` từ đó chỉ
    nhận một proxy rỗng — đó là nguyên nhân thật của «missing ScriptRunContext» và
    ``KeyError: sheet_link``, chứ không phải key chưa được khởi tạo. Main thread chụp
    cấu hình một lần rồi truyền xuống; worker chỉ đọc dữ liệu Python thuần.

    Bất biến còn có lợi về nghiệp vụ: đổi link Sheet giữa batch không làm batch đang
    chạy bắn sang bảng khác.
    """

    auto_sheet: bool = False
    sheet_link: str = ""
    dang_ngang: bool = True

    @property
    def sheet_id(self) -> str:
        """ID đã chuẩn hoá; dùng cho khoá idempotency."""
        from sheets import _lay_sheet_id

        return _lay_sheet_id(self.sheet_link)


@dataclass(frozen=True)
class VideoState:
    """Trạng thái một video trong batch. Bất biến; cập nhật bằng ``replace``."""

    index: int
    nguon: str
    scan_status: str = QUET_CHO
    phase: str = PHASE_CHO
    video_id: str = ""
    title: str = ""
    matches: Optional[int] = None
    so_dat_nguong: Optional[int] = None
    progress: float = 0.0
    message: str = ""
    error: str = ""
    delivery_key: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        return (self.finished_at or time.time()) - self.started_at


@dataclass(frozen=True)
class BatchSnapshot:
    """Ảnh chụp bất biến để UI vẽ mà không sợ dữ liệu đổi giữa chừng."""

    batch_id: str
    total: int
    current_index: int
    completed: int
    failed: int
    running: bool
    cancelled: bool
    elapsed_seconds: float
    eta_seconds: Optional[float]
    message: str
    videos: tuple = ()

    @property
    def batch_progress(self) -> float:
        if self.total <= 0:
            return 0.0
        xong = self.completed + self.failed
        dang = self.videos[self.current_index - 1].progress if (
            0 < self.current_index <= len(self.videos)
        ) else 0.0
        if self.videos and 0 < self.current_index <= len(self.videos):
            if self.videos[self.current_index - 1].scan_status != QUET_DANG_CHAY:
                dang = 0.0
        return max(0.0, min(1.0, (xong + dang) / self.total))


class ScanJobController:
    """Một batch, một worker thread, snapshot bất biến cho UI."""

    def __init__(self, engine, sheet_worker=None, recent_maxlen: int = 60):
        self.engine = engine
        self.sheet_worker = sheet_worker
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._batch_id = ""
        self._videos: list = []
        self._results: list = []
        self._recent: deque = deque(maxlen=recent_maxlen)
        self._events: queue.Queue = queue.Queue(maxsize=512)
        self._running = False
        self._cancelled = False
        self._started_mono: Optional[float] = None
        self._finished_mono: Optional[float] = None
        self._xong_gan_day: deque = deque(maxlen=10)
        self._message = ""
        self._error = ""

    # ---------- điều khiển ----------

    def start(
        self,
        nguon: list,
        source_type: str = "youtube",
        on_result: Optional[Callable] = None,
    ) -> str:
        with self._lock:
            if self._running or (self._thread and self._thread.is_alive()):
                raise RuntimeError("Đang có batch quét chạy; không tạo batch trùng.")
            self._batch_id = uuid.uuid4().hex
            self._videos = [
                VideoState(index=i, nguon=str(x)) for i, x in enumerate(nguon, 1)
            ]
            self._results = []
            self._recent.clear()
            self._xong_gan_day.clear()
            self._running = True
            self._cancelled = False
            self._error = ""
            self._message = "Đang chuẩn bị..."
            self._started_mono = time.monotonic()
            self._finished_mono = None
            batch_id = self._batch_id

        self.engine.cancel_event.clear()
        LOGGER.info(
            "event=scan.batch.started batch_id=%s total=%d type=%s",
            batch_id, len(nguon), source_type,
        )
        self._thread = threading.Thread(
            target=self._chay,
            args=(list(nguon), source_type, on_result),
            name=f"scan-{batch_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return batch_id

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._message = "Đang yêu cầu dừng; giữ nguyên kết quả đã xong..."
        LOGGER.warning("event=scan.batch.cancel_requested batch_id=%s", self._batch_id)
        self.engine.cancel()

    # ---------- worker ----------

    def _sua_video(self, index: int, **thay_doi) -> None:
        with self._lock:
            if 0 < index <= len(self._videos):
                self._videos[index - 1] = replace(self._videos[index - 1], **thay_doi)

    def _ghi_su_kien(self, noi_dung: str) -> None:
        with self._lock:
            self._recent.append((time.time(), noi_dung))
        try:
            self._events.put_nowait(noi_dung)
        except queue.Full:
            try:
                self._events.get_nowait()
                self._events.put_nowait(noi_dung)
            except (queue.Empty, queue.Full):
                pass

    def _chay(self, nguon: list, source_type: str, on_result: Optional[Callable]) -> None:
        try:
            def tien_do(pct: float, msg: str) -> None:
                # Engine gắn tiền tố "[i/n] " ở scan_iter; bóc ra để biết video nào.
                index, thong_bao = self._tach_chi_so(msg)
                if index is None:
                    with self._lock:
                        self._message = thong_bao
                    return
                phase = doan_phase(thong_bao)
                trong_video = self._pct_trong_video(pct, index, len(nguon))
                thay_doi = {
                    "scan_status": QUET_DANG_CHAY,
                    "progress": trong_video,
                    "message": thong_bao,
                }
                if phase:
                    thay_doi["phase"] = phase
                with self._lock:
                    hien_tai = self._videos[index - 1] if 0 < index <= len(self._videos) else None
                    if hien_tai is not None and hien_tai.started_at is None:
                        thay_doi["started_at"] = time.time()
                    self._message = thong_bao
                self._sua_video(index, **thay_doi)

            def sau_moi_video(index: int, tong: int, ket_qua) -> None:
                self._hoan_tat_video(index, ket_qua)
                if on_result:
                    on_result(index, tong, ket_qua)

            # Cờ huỷ đã được xoá ĐÚNG MỘT LẦN ở start(); scan_iter không xoá lại để một
            # cú bấm Dừng rơi vào khoảng giữa start() và lúc thread chạy không bị nuốt.
            for ket_qua in self.engine.scan_iter(
                nguon, source_type, tien_do, on_video=sau_moi_video, xoa_co_huy=False
            ):
                with self._lock:
                    self._results.append(ket_qua)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._error = str(exc)
            LOGGER.exception("event=scan.batch.failed batch_id=%s", self._batch_id)
        finally:
            with self._lock:
                self._running = False
                self._finished_mono = time.monotonic()
                if not self._error:
                    self._message = (
                        "Đã dừng theo yêu cầu." if self._cancelled else "Quét hoàn tất."
                    )
            LOGGER.info(
                "event=scan.batch.finished batch_id=%s completed=%d failed=%d",
                self._batch_id,
                sum(1 for v in self._videos if v.scan_status == QUET_XONG),
                sum(1 for v in self._videos if v.scan_status == QUET_LOI),
            )

    @staticmethod
    def _tach_chi_so(msg: str) -> tuple:
        if msg.startswith("[") and "]" in msg:
            dau, _, duoi = msg[1:].partition("]")
            phan = dau.split("/")
            if len(phan) == 2 and phan[0].strip().isdigit():
                return int(phan[0].strip()), duoi.strip()
        return None, msg

    @staticmethod
    def _pct_trong_video(pct_batch: float, index: int, tong: int) -> float:
        """scan_iter phát pct theo cả batch; đổi ngược lại thành pct của video."""
        if tong <= 0:
            return 0.0
        return max(0.0, min(1.0, pct_batch * tong - (index - 1)))

    def _hoan_tat_video(self, index: int, ket_qua) -> None:
        loi = getattr(ket_qua, "status", "ok") != "ok"
        so_match = len(getattr(ket_qua, "matches", []) or [])
        self._sua_video(
            index,
            scan_status=QUET_LOI if loi else QUET_XONG,
            phase=PHASE_LOI if loi else PHASE_XONG,
            progress=1.0,
            video_id=str(getattr(ket_qua, "source_id", "") or ""),
            title=str(getattr(ket_qua, "source_name", "") or ""),
            matches=so_match,
            so_dat_nguong=int(getattr(ket_qua, "so_dat_nguong", 0) or 0),
            error=str(getattr(ket_qua, "note", "") or "") if loi else "",
            finished_at=time.time(),
            message="Lỗi" if loi else f"Hoàn tất — {so_match} đoạn",
        )
        with self._lock:
            self._xong_gan_day.append(time.monotonic())
        LOGGER.info(
            "event=scan.video.completed batch_id=%s index=%d status=%s matches=%d",
            self._batch_id, index, "failed" if loi else "ok", so_match,
        )
        self._ghi_su_kien(
            f"Video {index}: " + ("lỗi" if loi else f"hoàn tất, {so_match} đoạn")
        )

    def ghi_nhan_giao_hang(self, index: int, delivery_key: str) -> None:
        self._sua_video(index, delivery_key=delivery_key)

    # ---------- đọc trạng thái ----------

    def _eta(self, con_lai: int) -> Optional[float]:
        with self._lock:
            moc = list(self._xong_gan_day)
        if con_lai <= 0 or len(moc) < 2:
            return None
        khoang = moc[-1] - moc[0]
        if khoang <= 0:
            return None
        return khoang / (len(moc) - 1) * con_lai

    def snapshot(self) -> BatchSnapshot:
        with self._lock:
            videos = tuple(self._videos)
            xong = sum(1 for v in videos if v.scan_status == QUET_XONG)
            loi = sum(1 for v in videos if v.scan_status == QUET_LOI)
            dang = next(
                (v.index for v in videos if v.scan_status == QUET_DANG_CHAY),
                xong + loi + 1 if xong + loi < len(videos) else len(videos),
            )
            moc_dau = self._started_mono
            moc_cuoi = self._finished_mono
            running = self._running or bool(self._thread and self._thread.is_alive())
            snapshot = BatchSnapshot(
                batch_id=self._batch_id,
                total=len(videos),
                current_index=dang,
                completed=xong,
                failed=loi,
                running=running,
                cancelled=self._cancelled,
                elapsed_seconds=(
                    0.0 if moc_dau is None
                    else (moc_cuoi or time.monotonic()) - moc_dau
                ),
                eta_seconds=None,
                message=self._message,
                videos=videos,
            )
        return replace(snapshot, eta_seconds=self._eta(len(videos) - xong - loi))

    def results(self) -> list:
        with self._lock:
            return list(self._results)

    def recent(self, n: int = 20) -> list:
        with self._lock:
            return list(self._recent)[-n:]

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running or bool(self._thread and self._thread.is_alive())

    @property
    def error(self) -> str:
        with self._lock:
            return self._error
