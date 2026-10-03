# -*- coding: utf-8 -*-
"""Dựng dữ liệu bảng trạng thái quét. **Không import streamlit.**

Vì sao tách ra
==============
Bảng trạng thái trước đây được dựng thẳng trong ``app.py`` bằng dict lồng biểu thức
điều kiện::

    "Đoạn": "—" if v.matches is None else v.matches

pandas suy ra dtype ``object`` vì cột trộn ``int`` và ``str``. Mỗi lần Streamlit vẽ
lại (0,75 giây một lần) PyArrow ném ``ArrowInvalid`` rồi Streamlit mới chạy nhánh
sửa dtype tự động — tức là **một exception cho mỗi lần render**, lặp suốt lượt quét.

Gốc rễ không phải "PyArrow khó tính" mà là **bảng UI không có schema**. Tách builder
ra đây để dtype được khai báo tường minh một chỗ và kiểm thử được mà không cần chạy
Streamlit.

Quyết định kiểu cho cột "Đoạn"
==============================
Ba trạng thái cần phân biệt: chưa quét, quét xong không có đoạn nào (0), quét xong
có N đoạn. Nếu dùng ``Int64`` + ``pd.NA`` thì "chưa quét" hiển thị thành ô trống —
dễ bị nhìn nhầm thành dữ liệu lỗi và khó phân biệt với 0.

Đây là bảng **trạng thái tạm thời** trong lúc quét, không phải bảng dữ liệu để sắp
xếp hay tính toán, nên ưu tiên đọc hiểu: toàn cột là ``string``, "chưa có" hiển thị
là ``—``. Kiểu tường minh nên Arrow chuyển đổi thành công ngay từ đầu.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import pandas as pd

import truy_cap_youtube as _tc
from common_original import (
    COT_SO_NGUON_CHUNG,
    HEADER_NGUON_CHUNG,
    TEN_TRANG_THAI_CAP,
    dong_bao_cao,
)


def dong_trang_thai_youtube(cd: Any, phien: Any = None) -> list:
    """Các dòng ``(mức, câu)`` cho mục «Trạng thái YouTube» ở thanh bên.

    ``mức`` ∈ success/info/warning/error. ``cd``: ``truy_cap_youtube.ChanDoanCookie`` (chỉ số
    đếm — không giá trị, không tên cookie). ``phien``: phiên YouTube của lượt chạy gần nhất
    (``Engine.phien_youtube_cuoi``) hoặc ``None``. Không đọc file, không gọi mạng.
    """
    ra: list = []
    if phien is not None and getattr(phien, "mo", False) is True:
        ra.append(("error", phien.thong_bao_dung()))
    elif phien is not None and getattr(phien, "cookie_bi_tu_choi", False):
        ra.append(("warning", "Cookie cấu hình không được YouTube chấp nhận ở lượt gần nhất — "
                              "tool đã tự chạy lại không cookie. Hãy xuất lại file cookie, hoặc "
                              "xoá trống ô cookie."))
    elif phien is not None and phien.tom_tat().get("youtube_operations"):
        ra.append(("success", "Lượt gần nhất: truy cập YouTube bình thường."))
    if not cd.cau_hinh:
        ra.append(("info", "Cookie: chưa cấu hình."))
    elif cd.trang_thai == _tc.COOKIE_TU_TRINH_DUYET:
        ra.append(("info", "Cookie lấy từ trình duyệt (bạn tự cấu hình) — tool không mở profile "
                           "trình duyệt để kiểm."))
    elif cd.trang_thai == _tc.COOKIE_KHONG_TON_TAI:
        ra.append(("warning", "Không thấy file cookie ở đường dẫn đã nhập."))
    elif cd.trang_thai == _tc.COOKIE_FILE_STRUCTURALLY_VALID:
        ra.append(("success",
                   f"File cookie đúng cấu trúc: {cd.so_ban_ghi} bản ghi "
                   f"({cd.so_ban_ghi_youtube} của YouTube, {cd.so_het_han} đã hết hạn), "
                   f"{'có' if cd.co_cookie_dang_nhap else 'KHÔNG có'} cookie đăng nhập. Đúng cấu "
                   "trúc chưa chắc YouTube còn chấp nhận phiên — chỉ lượt quét mới biết."))
    else:
        dong = ", ".join(str(x) for x in cd.dong_hong_dau)
        ra.append(("error",
                   f"File cookie sai cấu trúc (định dạng {cd.dinh_dang or '?'}, "
                   f"{cd.so_dong_hong} dòng hỏng{f' ở dòng {dong}' if dong else ''}"
                   f"{'' if cd.co_tieu_de else ', thiếu dòng tiêu đề Netscape'}) — yt-dlp sẽ "
                   "từ chối; hãy xuất lại bằng tiện ích trình duyệt."))
    return ra


def thong_bao_youtube_chan(ket_qua: Sequence[Any]) -> str:
    """Lý do cầu dao YouTube đã mở trong batch (rỗng nếu không): lấy từ chính kết quả "chưa
    quét" để không phụ thuộc trạng thái engine sau này."""
    for x in ket_qua:
        f = getattr(x, "loi_truy_cap", None)
        if getattr(f, "category", "") == _tc.BLOCKED_BY_BREAKER:
            cau = getattr(f, "human_message_vi", "") or ""
            return cau.split("Chưa quét — ", 1)[-1]
    return ""

# Ký hiệu "chưa có dữ liệu". Dùng chung để UI và test không lệch nhau.
CHUA_CO = "—"

COT = ("#", "Video", "Quét", "Đoạn", "Sheets")

TEN_TRANG_THAI_QUET = {
    "completed": "✅ Xong",
    "failed": "❌ Lỗi",
    "running": "⏳ Đang chạy",
    "queued": "Chờ",
}
TEN_TRANG_THAI_SHEET = {
    "pending": "Chờ gửi",
    "sending": "Đang gửi",
    "sent": "✅ Đã gửi",
    "retrying": "Đang thử lại",
    "failed": "❌ Lỗi",
    "not_configured": CHUA_CO,
}


GOI_Y_VUNG_LOI = "Nguồn có vùng lỗi hoặc file tải về thiếu: quét lại nguồn đó."
GOI_Y_TOP1 = ("Kết quả Top-1 lấy từ phần đầu video (tìm nhanh): cần quét trọn thì đặt "
              "Top-N lớn hơn 1, hoặc tắt `top1_tim_nhanh` trong `data/cau_hinh.json`.")
GOI_Y_TANG_DAN = ("Quét tăng dần đã dừng sớm hoặc chỉ tải phần đầu: tắt «Quét tăng dần "
                  "cho video rất dài» ở thanh bên → «⚙️ Tham số» → «Mở để tinh chỉnh».")


def goi_y_quet_mot_phan(ket_qua: Sequence[Any], cau_hinh: Any = None) -> list:
    """Lời khuyên cho các nguồn CHƯA quét trọn, theo ĐÚNG lý do (phản biện TCP-06).

    Tắt «Quét tăng dần» không giúp gì cho kết quả Top-1 tìm nhanh trên video ngắn hay cho
    vùng lỗi. Ngược lại, Top-1 dừng sớm BÊN TRONG một lượt tải một phần / quét tăng dần
    thì phải nói cả hai: chỉ tắt tìm nhanh, video dài vẫn dừng ở đoạn đầu (phản biện
    vòng 2).
    """
    def duong_di(r) -> str:
        return getattr(getattr(r, "chan_doan", None), "duong_di", "") or ""

    def do_tang_dan(r) -> bool:
        ly_do = getattr(r, "ly_do_pham_vi", "") or ""
        if ly_do == "gioi_han_tai":
            return True
        if ly_do != "dung_som":
            return False
        if duong_di(r) != "dung_som_vung_dau":
            return True
        # Top-1 tìm nhanh đã dừng: quét tăng dần CŨNG góp phần khi video vượt ngưỡng.
        nguong = float(getattr(cau_hinh, "quet_tang_dan_tu_gio", 0) or 0) * 3600
        return (bool(getattr(cau_hinh, "quet_tang_dan", False))
                and float(getattr(r, "duration_s", 0) or 0) > nguong)

    goi_y = []
    if any(getattr(r, "vung_loi", None) for r in ket_qua):
        goi_y.append(GOI_Y_VUNG_LOI)
    if any(duong_di(r) == "dung_som_vung_dau" for r in ket_qua):
        goi_y.append(GOI_Y_TOP1)
    if any(do_tang_dan(r) for r in ket_qua):
        goi_y.append(GOI_Y_TANG_DAN)
    return goi_y


def _mo_ta_sheet(delivery_key: str, trang_thai_sheet: Mapping[str, Any]) -> str:
    if not delivery_key:
        return CHUA_CO
    muc = trang_thai_sheet.get(delivery_key)
    if muc is None:
        return CHUA_CO
    trang_thai = getattr(muc, "status", "")
    return TEN_TRANG_THAI_SHEET.get(trang_thai, str(trang_thai) or CHUA_CO)


def build_scan_status_dataframe(
    videos: Sequence[Any],
    trang_thai_sheet: Optional[Mapping[str, Any]] = None,
) -> pd.DataFrame:
    """Bảng trạng thái từng video, dtype tường minh nên Arrow không phải đoán.

    ``videos``: các ``scan_jobs.VideoState``.
    ``trang_thai_sheet``: map ``delivery_key -> SheetDelivery`` (có thể rỗng).
    """
    trang_thai_sheet = trang_thai_sheet or {}
    dong = []
    for v in videos:
        so_doan = getattr(v, "matches", None)
        dong.append({
            "#": str(getattr(v, "index", "")),
            "Video": str(getattr(v, "title", "") or getattr(v, "nguon", ""))[:60],
            "Quét": TEN_TRANG_THAI_QUET.get(
                getattr(v, "scan_status", ""), str(getattr(v, "scan_status", ""))
            ),
            # 0 và "chưa quét" là hai chuyện khác nhau — phải phân biệt được.
            "Đoạn": CHUA_CO if so_doan is None else str(so_doan),
            "Sheets": _mo_ta_sheet(str(getattr(v, "delivery_key", "") or ""),
                                   trang_thai_sheet),
        })

    khung = pd.DataFrame(dong, columns=list(COT))
    # Khai báo dtype cho CẢ khung rỗng: bảng lúc mới bắt đầu quét cũng phải có
    # schema ổn định, nếu không lần render đầu vẫn rơi vào nhánh sửa dtype.
    return khung.astype({cot: "string" for cot in COT})


# =====================================================================
#  Chế độ «Một video gốc chung cho cả lô»
# =====================================================================

COT_NGUON_CHUNG = ("#", "Video", "Lượt quét", "Video gốc đang xét", "Phạm vi đã quét",
                   "Ghi chú")


def build_nguon_chung_status_dataframe(videos: Sequence[Any]) -> pd.DataFrame:
    """Bảng trạng thái lúc chạy (``common_original_jobs.VideoNguonChung``); toàn chuỗi."""
    dong = []
    for v in videos:
        trang_thai = str(getattr(v, "trang_thai", "") or "")
        loi = str(getattr(v, "loi", "") or "")
        dong.append({
            "#": str(getattr(v, "thu_tu", "")),
            "Video": ("⏳ " if getattr(v, "dang_quet", False) else "")
            + str(getattr(v, "tieu_de", "") or getattr(v, "nguon", ""))[:60],
            "Lượt quét": str(getattr(v, "so_luot", 0)),
            "Video gốc đang xét": TEN_TRANG_THAI_CAP.get(trang_thai, trang_thai or CHUA_CO),
            "Phạm vi đã quét": str(getattr(v, "pham_vi", "") or CHUA_CO),
            "Ghi chú": loi.splitlines()[0][:80] if loi else "",
        })
    khung = pd.DataFrame(dong, columns=list(COT_NGUON_CHUNG))
    return khung.astype({cot: "string" for cot in COT_NGUON_CHUNG})


def df_nguon_chung(kql: Any) -> pd.DataFrame:
    """Bảng kết quả lô (một dòng mỗi video) với cột số ĐÚNG KIỂU (xem CLAUDE.md mục 7)."""
    df = pd.DataFrame(dong_bao_cao(kql, an_toan=False), columns=HEADER_NGUON_CHUNG)
    for cot in COT_SO_NGUON_CHUNG:
        so = pd.to_numeric(df[cot], errors="coerce")
        khong_rong = so.dropna()
        if not khong_rong.empty and (khong_rong % 1 == 0).all():
            so = so.astype("Int64")
        df[cot] = so
    return df


def csv_nguon_chung(kql: Any) -> bytes:
    """CSV utf-8-sig của kết quả lô, ô đã chặn công thức bảng tính."""
    df = pd.DataFrame(dong_bao_cao(kql), columns=HEADER_NGUON_CHUNG)
    return df.to_csv(index=False).encode("utf-8-sig")
