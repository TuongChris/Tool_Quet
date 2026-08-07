# -*- coding: utf-8 -*-
"""Bảng trạng thái quét phải chuyển sang Arrow được NGAY, không qua nhánh sửa dtype."""

from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pytest

from scan_jobs import QUET_CHO, QUET_DANG_CHAY, QUET_LOI, QUET_XONG, VideoState
from scan_ui import CHUA_CO, COT, build_scan_status_dataframe
from sheet_delivery import CHO_GUI, DA_GUI, THAT_BAI, SheetDelivery


def _video(index, trang_thai, matches=None, key=""):
    return VideoState(
        index=index, nguon=f"https://youtu.be/v{index}",
        scan_status=trang_thai, matches=matches,
        title=f"Video {index}", delivery_key=key,
    )


def _giao(key, trang_thai):
    return SheetDelivery(
        delivery_key=key, source_id="v", source_name="V",
        header=["A"], rows=[["1"]], status=trang_thai,
    )


# Đủ mọi tổ hợp trạng thái mà UI thực sự gặp trong một batch.
VIDEOS = [
    _video(1, QUET_XONG, matches=3, key="k1"),
    _video(2, QUET_XONG, matches=0, key="k2"),      # 0 khác hẳn "chưa quét"
    _video(3, QUET_XONG, matches=12, key="k3"),
    _video(4, QUET_LOI, matches=0),
    _video(5, QUET_DANG_CHAY),                      # matches=None
    _video(6, QUET_CHO),                            # matches=None
]
SHEETS = {
    "k1": _giao("k1", DA_GUI),
    "k2": _giao("k2", CHO_GUI),
    "k3": _giao("k3", THAT_BAI),
}


def test_chuyen_sang_arrow_thanh_cong_khong_can_streamlit_sua_dtype():
    """Đây chính là lỗi ArrowInvalid đã thấy trên terminal."""
    khung = build_scan_status_dataframe(VIDEOS, SHEETS)

    bang = pa.Table.from_pandas(khung)      # không được ném ArrowInvalid
    assert bang.num_rows == len(VIDEOS)


def test_moi_cot_deu_co_dtype_tuong_minh_khong_con_object():
    khung = build_scan_status_dataframe(VIDEOS, SHEETS)

    assert list(khung.columns) == list(COT)
    for cot in COT:
        assert khung[cot].dtype == pd.StringDtype(), (
            f"Cột {cot} là {khung[cot].dtype} — dtype object khiến Arrow phải đoán"
        )


def test_cot_doan_phan_biet_duoc_khong_khop_va_chua_quet():
    """0 nghĩa là đã quét mà không có đoạn nào; — nghĩa là chưa quét. Khác nhau."""
    khung = build_scan_status_dataframe(VIDEOS, SHEETS)
    doan = list(khung["Đoạn"])

    assert doan[0] == "3"
    assert doan[1] == "0"
    assert doan[2] == "12"
    assert doan[4] == CHUA_CO
    assert doan[5] == CHUA_CO


def test_cot_sheets_hien_dung_trang_thai_giao_hang():
    khung = build_scan_status_dataframe(VIDEOS, SHEETS)
    sheets = list(khung["Sheets"])

    assert sheets[0] == "✅ Đã gửi"
    assert sheets[1] == "Chờ gửi"
    assert sheets[2] == "❌ Lỗi"
    assert sheets[3] == CHUA_CO, "Video chưa xếp hàng Sheets thì để trống rõ ràng"


def test_khung_rong_van_co_schema_on_dinh():
    """Lần render đầu tiên (batch vừa bắt đầu) cũng không được rơi vào Arrow fallback."""
    khung = build_scan_status_dataframe([], {})

    assert list(khung.columns) == list(COT)
    for cot in COT:
        assert khung[cot].dtype == pd.StringDtype()
    pa.Table.from_pandas(khung)


def test_khong_co_trang_thai_sheet_van_dung_duoc():
    khung = build_scan_status_dataframe(VIDEOS)

    assert set(khung["Sheets"]) == {CHUA_CO}
    pa.Table.from_pandas(khung)


@pytest.mark.parametrize("so_video", [1, 10, 50])
def test_kich_thuoc_batch_khac_nhau_deu_arrow_safe(so_video):
    videos = [_video(i, QUET_XONG, matches=i) for i in range(1, so_video + 1)]
    pa.Table.from_pandas(build_scan_status_dataframe(videos, {}))


def test_delivery_key_la_khoa_khong_ton_tai_thi_khong_no():
    videos = [_video(1, QUET_XONG, matches=1, key="khong_ton_tai")]

    khung = build_scan_status_dataframe(videos, SHEETS)

    assert list(khung["Sheets"]) == [CHUA_CO]
