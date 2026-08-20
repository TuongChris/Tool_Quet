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
    """Kết nối đã mở, dùng lại giữa nhiều lần append/ghi đè."""

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


def _o_cot(so_cot: int) -> str:
    """Số thứ tự cột (1-based) -> chữ cái cột kiểu A1 (1 -> A, 34 -> AH)."""
    so_cot = max(1, int(so_cot))
    ten = ""
    while so_cot > 0:
        so_cot, du = divmod(so_cot - 1, 26)
        ten = chr(ord("A") + du) + ten
    return ten


def _o_sheets(gia_tri):
    """Ép một ô về dạng gửi lên Google Sheets.

    Ghi bằng ``value_input_option="RAW"`` nên Sheets lưu ĐÚNG kiểu được gửi: chuỗi
    "9" là văn bản và sắp xếp sau "10", còn số 9 mới sắp xếp đúng. Vì vậy giữ nguyên
    ``int``/``float``, chỉ ``str()`` những kiểu khác.

    ``bool`` phải loại riêng (nó là lớp con của ``int``) để cột không hiện TRUE/FALSE
    thay vì chữ. Chuỗi đã được ``o_bang_tinh_an_toan`` chặn công thức từ tầng trên —
    trừ đường ``ghi_de``, cố ý gửi chuỗi nguyên văn vì RAW vốn không phân tích công
    thức và dấu nháy đơn thêm vào sẽ hiện ra trong ô (xem docstring ``ghi_de``);
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
                tinh_trang = self._tinh_trang_header(ws, header)
                if tinh_trang == "trong":
                    ws.append_row([str(x) for x in header], value_input_option="RAW")
                elif tinh_trang == "thieu":
                    # Bảng có dữ liệu nhưng hàng 1 KHÔNG phải header — hầu như luôn
                    # là do hàng header bị xoá tay. Trước đây ta chỉ xem ô A1 có
                    # dữ liệu hay không, nên tình huống này bị hiểu nhầm thành «đã
                    # có header» và header không bao giờ được ghi lại. Hậu quả im
                    # lặng: mọi thứ đọc bảng theo TÊN CỘT (Apps Script, công thức)
                    # đều hỏng mà không báo gì.
                    ws.insert_row([str(x) for x in header], index=1,
                                  value_input_option="RAW")
                    LOGGER.warning(
                        "event=scan.sheet.header_restored worksheet=%r so_cot=%d",
                        self.worksheet, len(header),
                    )
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

    def ghi_de(self, header: list, rows: list, *, cho_phep_rong: bool = False) -> int:
        r"""Thay TOÀN BỘ nội dung trang tính bằng header + rows. Trả số dòng dữ liệu.

        Khác ``append`` ở một điểm quyết định: hàm này IDEMPOTENT — ghi đè cùng dữ
        liệu hai lần cho kết quả y hệt một lần, nên không bao giờ sinh dòng trùng
        và thử lại sau lỗi là an toàn.

        Bốn quyết định cần biết trước khi sửa hàm này:

        1) KHÔNG gọi ``ws.clear()``. Trong gspread, ``clear()`` chỉ gọi
           ``values_clear`` (xoá giá trị, KHÔNG đụng ``rowCount``), còn ``resize()``
           gửi ``updateSheetProperties/gridProperties`` — thu nhỏ là XOÁ HẲN ô ngoài
           lưới. Vì ``resize`` đưa lưới về ĐÚNG kích thước bảng mới và ``update``
           ghi trọn lưới đó từ A1 (bảng đã đệm chữ nhật), mọi ô hoặc bị xoá theo
           lưới hoặc bị ghi đè — không ô cũ nào sống sót. ``clear()`` xoá TOÀN BỘ
           bảng (còn ``resize`` chỉ xoá phần dôi ra) và tốn thêm một lượt gọi API,
           nên không thêm được gì.

           ĐỪNG hiểu nhầm đây là thao tác nguyên tử: khi bảng mới NGẮN HƠN bảng cũ,
           ``resize`` chạy xong là các dòng dôi ra đã mất vĩnh viễn, rồi ``update``
           mới chạy. Hàm này idempotent về KẾT QUẢ chứ không nguyên tử về QUÁ TRÌNH.
           Người gọi phải tự chặn bảng rỗng hoặc ngắn bất thường TRƯỚC khi gọi —
           ``danh_sach_video.day_len_sheet`` đã chặn ca rỗng.

        2) ``resize`` PHẢI đứng TRƯỚC ``update``: ``values.update`` KHÔNG tự nới
           lưới (khác ``values.append``). Kho 1717 clip → 1718 dòng, trong khi
           ``_mo_worksheet`` tạo tab mới chỉ 1000 dòng → lỗi 400 «exceeds grid
           limits». Gọi resize VÔ ĐIỀU KIỆN, không đọc ``ws.row_count`` để quyết
           định: gspread tự cộng dồn ``rowCount`` phía client trong ``append_rows``
           nên con số đó có thể LỚN HƠN lưới thật.

        3) Gọi ``update`` bằng KEYWORD. gspread 5.x là ``update(range_name, values)``,
           6.x là ``update(values, range_name)``; requirements.txt ghi ``gspread``
           trần, không ghim phiên bản.

        4) Thử lại ĐÚNG MỘT LẦN và CHỈ khi kết nối vừa dùng đến từ ``_CACHE``. Lỗi
           ngay ở ``_ket_noi`` (xác thực / sai link / mất quyền) thì thử lại vô ích.
           Lần thử thứ hai chính là đường cứu khi người dùng tự xoá tab trên trình
           duyệt giữa phiên: ``_bo_ket_noi`` bỏ Worksheet chết trong cache,
           ``_ket_noi`` mở lại và ``add_worksheet`` tạo lại tab.

        ``cho_phep_rong=False`` (mặc định) từ chối ``rows`` rỗng bằng ValueError để
        một kết quả rỗng do lỗi không âm thầm xoá trắng bảng của người dùng.
        """
        if not rows and not cho_phep_rong:
            raise ValueError("Không có dòng nào để ghi — từ chối xoá trắng trang tính.")
        if not self.san_sang():
            raise RuntimeError(self.thieu_gi())

        gia_tri = [[_o_sheets(v) for v in header]]
        gia_tri += [[_o_sheets(v) for v in r] for r in rows]
        so_cot = max(1, max((len(d) for d in gia_tri), default=1))
        # Đệm cho bảng CHỮ NHẬT: ``update`` chỉ ghi đúng những ô có trong body, dòng
        # ngắn hơn sẽ để lại ô CŨ ở cột cuối.
        gia_tri = [d + [""] * (so_cot - len(d)) for d in gia_tri]
        # so_dong CHÍNH XÁC bằng số dòng sẽ ghi — KHÔNG dùng ``max(..., 2)``: nếu
        # lưới rộng hơn phần được update thì dòng cũ ở phần thừa vẫn còn nguyên.
        so_dong = len(gia_tri)

        with _KHOA:
            tu_cache = self._khoa_cache() in _CACHE
        try:
            self._ghi_de_mot_lan(gia_tri, so_dong, so_cot)
        except Exception:
            if not tu_cache:
                raise
            # Kết nối lấy từ cache có thể đã chết (token hết hạn, hoặc người dùng
            # tự xoá tab nên sheetId trong Worksheet không còn). ``_ghi_de_mot_lan``
            # đã bỏ cache, nên lượt này mở kết nối mới và ``_mo_worksheet`` tạo lại
            # tab. An toàn vì ghi đè IDEMPOTENT — khác ``append``.
            self._ghi_de_mot_lan(gia_tri, so_dong, so_cot)
        return len(rows)

    def _ghi_de_mot_lan(self, gia_tri: list, so_dong: int, so_cot: int) -> None:
        """Một lượt ghi đè. Lỗi thì bỏ cache kết nối rồi ném tiếp cho ``ghi_de``."""
        ket_noi = self._ket_noi(so_cot)
        ws = ket_noi.worksheet
        try:
            ws.resize(rows=so_dong, cols=so_cot)
            ws.update(values=gia_tri, range_name="A1", value_input_option="RAW")
        except Exception:
            self._bo_ket_noi()
            raise
        # Header vừa được ghi lại; nhớ để lần ``append`` sau (nếu có) khỏi đọc ô A1.
        # Đặt SAU khi cả hai lệnh thành công — đặt trước là nói dối cache.
        ket_noi.da_co_header = True

    # Số tên cột tối thiểu phải khớp thì hàng 1 mới được coi là header. Đặt 3 để
    # một hàng DỮ LIỆU (toàn link, tên video, ngày giờ) gần như không thể đạt tới,
    # còn một header thật vẫn qua được kể cả khi người dùng đã đổi tên vài cột.
    SO_COT_KHOP_TOI_THIEU = 3

    @classmethod
    def _tinh_trang_header(cls, ws, header: list) -> str:
        """Trả về ``"trong"`` | ``"co"`` | ``"thieu"`` cho hàng 1 của trang tính.

        ``"thieu"`` nghĩa là bảng CÓ dữ liệu nhưng hàng 1 không phải header — gần
        như luôn do hàng header bị xoá tay. Phải phân biệt được ca này, vì đọc mỗi
        ô A1 như trước thì nó trông y hệt ca ``"co"``: A1 có dữ liệu nên header
        không bao giờ được ghi lại, và mọi thứ đọc bảng theo TÊN CỘT sẽ hỏng im
        lặng cho tới khi có người phát hiện bằng mắt.

        Vẫn chỉ đọc ĐÚNG MỘT hàng, không phải cả bảng: ``get_all_values()`` kéo về
        toàn bộ sheet chỉ để trả lời một câu hỏi về hàng đầu, chi phí tăng theo số
        dòng đã tích luỹ. Bản gspread cũ không có ``get_values`` thì lùi về cách cũ.
        """
        lay = getattr(ws, "get_values", None)
        if callable(lay):
            hang_dau = lay("A1:" + _o_cot(len(header)) + "1")
        else:
            hang_dau = ws.get_all_values()[:1]

        o = [str(x).strip() for x in (hang_dau[0] if hang_dau else [])]
        if not any(o):
            return "trong"

        mong_doi = {str(x).strip().casefold() for x in header if str(x).strip()}
        khop = sum(1 for x in o if x.casefold() in mong_doi)
        nguong = min(cls.SO_COT_KHOP_TOI_THIEU, len(mong_doi))
        return "co" if khop >= nguong else "thieu"

    @classmethod
    def _co_header(cls, ws, header: Optional[list] = None) -> bool:
        """Giữ lại cho mã cũ/test: hàng 1 có phải header dùng được không."""
        return cls._tinh_trang_header(ws, header or []) == "co"
