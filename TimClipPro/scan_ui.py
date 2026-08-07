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
