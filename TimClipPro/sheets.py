# -*- coding: utf-8 -*-
r"""
sheets.py — Tự động đẩy kết quả quét lên Google Sheets.

CÁCH THIẾT LẬP (làm một lần, ~10 phút):
 1. Vào https://console.cloud.google.com → tạo Project mới (tên gì cũng được).
 2. Menu «APIs & Services» → «Enable APIs» → bật 2 thứ: Google Sheets API và Google Drive API.
 3. «Credentials» → Create Credentials → **Service account** → đặt tên → Create.
 4. Bấm vào service account vừa tạo → tab «Keys» → Add key → Create new key → **JSON** → tải về.
 5. Đổi tên file JSON đó thành `google_key.json`, bỏ vào thư mục TimClipPro.
 6. Mở file JSON, tìm dòng "client_email" (dạng abc@ten-project.iam.gserviceaccount.com).
 7. Mở Google Sheet của bạn → nút Chia sẻ → dán email đó vào → quyền **Người chỉnh sửa**.
 8. Copy link Google Sheet dán vào giao diện, bấm «Kiểm tra kết nối».

Nếu chưa thiết lập, hệ thống vẫn chạy bình thường — chỉ là không đẩy lên Sheets.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Optional

TEN_FILE_KEY = "google_key.json"

LOGGER = logging.getLogger("scan.sheet")


@dataclass
class _KetNoi:
    """Kết nối đã mở, dùng lại giữa nhiều lần append."""

    worksheet: object
    da_co_header: bool = False


# Cache ở cấp MODULE chứ không phải cấp instance, vì `app.py` tạo một
# `SheetsExporter` mới cho mỗi lần đẩy (`lay_sheets()`); cache theo instance sẽ
# không bao giờ trúng. Khoá gồm mtime của file key nên thay khoá là tự kết nối lại.
_KHOA = threading.RLock()
_CACHE: dict[tuple, _KetNoi] = {}


def xoa_cache_ket_noi() -> None:
    """Buộc lần sau mở kết nối mới. Dùng khi đổi key/sheet hoặc trong test."""
    with _KHOA:
        _CACHE.clear()


def _lay_sheet_id(s: str) -> str:
    """Chấp nhận cả link đầy đủ lẫn ID trần."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", s or "")
    return m.group(1) if m else (s or "").strip()


def _o_sheets(gia_tri):
    """Ép một ô về dạng gửi lên Google Sheets.

    Ghi bằng ``value_input_option="RAW"`` nên Sheets lưu ĐÚNG kiểu được gửi: chuỗi
    "9" là văn bản và sắp xếp sau "10", còn số 9 mới sắp xếp đúng. Vì vậy giữ nguyên
    ``int``/``float``, chỉ ``str()`` những kiểu khác.

    ``bool`` phải loại riêng (nó là lớp con của ``int``) để cột không hiện TRUE/FALSE
    thay vì chữ. Chuỗi đã được ``o_bang_tinh_an_toan`` chặn công thức từ tầng trên;
    số thì không thể là công thức nên không cần rào thêm.
    """
    if gia_tri is None:
        return ""
    if isinstance(gia_tri, bool):
        return str(gia_tri)
    if isinstance(gia_tri, (int, float)):
        return gia_tri
    return str(gia_tri)


class SheetsExporter:
    """Đẩy dữ liệu lên Google Sheets. Tự vô hiệu hóa êm nếu chưa cấu hình."""

    def __init__(self, key_path: Optional[str] = None,
                 sheet: str = "", worksheet: str = "KetQuaQuet"):
        self.key_path = key_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), TEN_FILE_KEY)
        self.sheet_id = _lay_sheet_id(sheet)
        self.worksheet = worksheet or "KetQuaQuet"

    # ---------- kiểm tra ----------

    @staticmethod
    def thu_vien_san_sang() -> bool:
        try:
            import gspread  # noqa: F401
            return True
        except Exception:
            return False

    def co_key(self) -> bool:
        return os.path.isfile(self.key_path)

    def san_sang(self) -> bool:
        return self.thu_vien_san_sang() and self.co_key() and bool(self.sheet_id)

    def thieu_gi(self) -> str:
        if not self.thu_vien_san_sang():
            return "Chưa cài thư viện — chạy: pip install gspread google-auth"
        if not self.co_key():
            return f"Chưa có file {TEN_FILE_KEY} trong thư mục dự án (xem hướng dẫn ở đầu sheets.py)"
        if not self.sheet_id:
            return "Chưa nhập link Google Sheet"
        return ""

    def email_service_account(self) -> str:
        """Email cần chia sẻ quyền chỉnh sửa trên Google Sheet."""
        if not self.co_key():
            return ""
        try:
            import json
            with open(self.key_path, encoding="utf-8") as f:
                return json.load(f).get("client_email", "")
        except Exception:
            return ""

    # ---------- kết nối ----------

    def _khoa_cache(self) -> tuple:
        try:
            moc = os.stat(self.key_path).st_mtime_ns
        except OSError:
            moc = 0
        return (os.path.normcase(os.path.abspath(self.key_path)), moc,
                self.sheet_id, self.worksheet)

    def _mo_worksheet(self, so_cot: int = 12):
        """Mở worksheet MỚI. Không dùng cache — dành cho «Kiểm tra kết nối»."""
        import gspread
        gc = gspread.service_account(filename=self.key_path)
        sh = gc.open_by_key(self.sheet_id)
        try:
            return sh.worksheet(self.worksheet)
        except gspread.WorksheetNotFound:
            return sh.add_worksheet(title=self.worksheet, rows=1000, cols=max(so_cot, 12))

    def _ket_noi(self, so_cot: int = 12) -> _KetNoi:
        """Kết nối dùng lại: xác thực + mở bảng + mở trang tính đúng MỘT lần.

        Trước đây mỗi ``append()`` gọi lại ``service_account()`` →
        ``open_by_key()`` → ``worksheet()``, tức 3 lượt thiết lập mỗi video.
        """
        khoa = self._khoa_cache()
        with _KHOA:
            ket_noi = _CACHE.get(khoa)
            if ket_noi is not None:
                return ket_noi
            ket_noi = _KetNoi(worksheet=self._mo_worksheet(so_cot))
            _CACHE[khoa] = ket_noi
            LOGGER.info(
                "event=scan.sheet.connection_opened worksheet=%r", self.worksheet
            )
            return ket_noi

    def _bo_ket_noi(self) -> None:
        with _KHOA:
            _CACHE.pop(self._khoa_cache(), None)

    def kiem_tra(self) -> tuple:
        """Trả về (thành_công, thông_báo). Dùng cho nút «Kiểm tra kết nối»."""
        if not self.san_sang():
            return False, self.thieu_gi()
        try:
            ws = self._mo_worksheet()
            return True, (f"OK — đã kết nối bảng «{ws.spreadsheet.title}», "
                          f"trang tính «{ws.title}».")
        except Exception as e:  # noqa: BLE001
            goi_y = ""
            if "PERMISSION_DENIED" in str(e) or "403" in str(e):
                em = self.email_service_account()
                goi_y = (f" → Hãy mở Google Sheet, bấm Chia sẻ và cấp quyền "
                         f"«Người chỉnh sửa» cho: {em}")
            return False, f"Lỗi kết nối: {e}{goi_y}"

    # ---------- ghi dữ liệu ----------

    def append(self, header: list, rows: list, ghi_header_neu_trong: bool = True) -> int:
        """
        Nối thêm các dòng vào cuối trang tính. Trả về số dòng đã ghi.
        Ném exception nếu lỗi — bên gọi tự quyết định xử lý thế nào.
        """
        if not rows:
            return 0
        if not self.san_sang():
            raise RuntimeError(self.thieu_gi())

        ket_noi = self._ket_noi(len(header))
        ws = ket_noi.worksheet
        try:
            if ghi_header_neu_trong and not ket_noi.da_co_header:
                if not self._co_header(ws):
                    ws.append_row([str(x) for x in header], value_input_option="RAW")
                # Header đã tồn tại thì không thể biến mất giữa phiên; nhớ lại để
                # những lần append sau khỏi hỏi Google thêm lần nào nữa.
                ket_noi.da_co_header = True
            ws.append_rows(
                [[_o_sheets(v) for v in r] for r in rows],
                value_input_option="RAW",
            )
        except Exception:
            # Kết nối có thể đã hỏng (token/socket). Bỏ cache để lần sau mở lại,
            # nhưng KHÔNG tự thử lại append: một lần ghi có thể đã tới Google rồi,
            # thử lại ở đây sẽ tạo dòng trùng. Việc thử lại là của SheetDeliveryWorker.
            self._bo_ket_noi()
            raise
        return len(rows)

    @staticmethod
    def _co_header(ws) -> bool:
        """Kiểm tra ô A1 thay vì tải cả bảng.

        ``get_all_values()`` kéo về TOÀN BỘ sheet chỉ để trả lời «có trống không» —
        chi phí tăng theo số dòng đã tích luỹ. Đọc một ô là đủ và không đổi theo
        kích thước bảng. Bản gspread cũ không có ``get_values`` thì lùi về cách cũ.
        """
        lay = getattr(ws, "get_values", None)
        if callable(lay):
            return bool(lay("A1"))
        return bool(ws.get_all_values())
