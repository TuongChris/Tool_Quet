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

import os
import re
from typing import Optional

TEN_FILE_KEY = "google_key.json"


def _lay_sheet_id(s: str) -> str:
    """Chấp nhận cả link đầy đủ lẫn ID trần."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", s or "")
    return m.group(1) if m else (s or "").strip()


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

    def _mo_worksheet(self, so_cot: int = 12):
        import gspread
        gc = gspread.service_account(filename=self.key_path)
        sh = gc.open_by_key(self.sheet_id)
        try:
            return sh.worksheet(self.worksheet)
        except gspread.WorksheetNotFound:
            return sh.add_worksheet(title=self.worksheet, rows=1000, cols=max(so_cot, 12))

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

        ws = self._mo_worksheet(len(header))
        if ghi_header_neu_trong and not ws.get_all_values():
            ws.append_row([str(x) for x in header], value_input_option="RAW")
        ws.append_rows([[("" if v is None else str(v)) for v in r] for r in rows],
                       value_input_option="RAW")
        return len(rows)
