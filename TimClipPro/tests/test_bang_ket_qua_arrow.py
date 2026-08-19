# -*- coding: utf-8 -*-
"""Bảng kết quả không được sập khi một lượt quét trộn nguồn tốt và nguồn lỗi.

Bối cảnh 2026-08-18: quét một watchlist mà vài link bị YouTube chặn (bot-check) làm
cả trang kết quả sập với

    ArrowInvalid: ("Could not convert '' with type str: tried to convert to int64",
                   'Conversion failed for column Số hash khớp with type object')

Nguyên nhân: `Engine.to_rows` điền chuỗi rỗng vào các cột SỐ ở dòng của nguồn lỗi /
không có kết quả, còn dòng có kết quả điền số thật. Cột thành dtype `object` lẫn hai
kiểu, và PyArrow — thứ Streamlit dùng để vẽ bảng — từ chối.

Điểm quan trọng: KHÔNG chỉ một cột. Sửa mỗi "Số hash khớp" thì lỗi nhảy sang
"Tỷ lệ vân tay khớp (%)" ngay lần quét sau.
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
from engine import Engine, Match, ScanResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _ket_qua_tron() -> list:
    """Đúng tình huống thật: một nguồn khớp, một nguồn lỗi, một nguồn không ra gì."""
    khop = ScanResult(source_name="Video vi phạm", source_ref="https://youtu.be/aaa",
                      source_id="aaa", duration_s=3600.0)
    khop.matches = [Match(clip="20260101 - Clip [xyz].opus", start_s=61.4, end_s=612.6,
                          matched_s=551.2, clip_offset_s=0.6, hashes=1234,
                          confidence="Rất chắc", ty_le=87.5, vung="Đầu")]
    loi = ScanResult(source_name="Video bị chặn", source_ref="https://youtu.be/bbb",
                     status="error", note="Sign in to confirm you're not a bot.")
    rong = ScanResult(source_name="Video sạch", source_ref="https://youtu.be/ccc")
    return [khop, loi, rong]


@pytest.fixture()
def rows(tmp_path):
    eng = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
                 out_dir=str(tmp_path / "ra"))
    return eng.to_rows(_ket_qua_tron())


def _ep_kieu(df: pd.DataFrame) -> pd.DataFrame:
    """Bản sao quy tắc ép kiểu của `app.df_ket_qua` (app.py import Streamlit nên
    không nạp thẳng được trong unit test)."""
    for cot in Engine.COT_SO:
        df[cot] = pd.to_numeric(df[cot], errors="coerce")
    return df


def test_tai_hien_dung_loi_arrow_khi_khong_ep_kieu(rows):
    """Chốt lại nguyên nhân — nếu ngày nào đó không còn nổ thì test này phải đỏ."""
    df = pd.DataFrame(rows, columns=Engine.HEADER)
    with pytest.raises(pa.ArrowInvalid):
        pa.Table.from_pandas(df)


def test_ep_kieu_xong_thi_arrow_chuyen_duoc(rows):
    bang = pa.Table.from_pandas(_ep_kieu(pd.DataFrame(rows, columns=Engine.HEADER)))
    assert bang.num_rows == len(rows) == 3


@pytest.mark.parametrize("cot", Engine.COT_SO)
def test_moi_cot_so_deu_ra_kieu_so(rows, cot):
    """Không cột nào được sót: vá một cột thì lỗi chỉ nhảy sang cột kế bên."""
    df = _ep_kieu(pd.DataFrame(rows, columns=Engine.HEADER))
    assert pd.api.types.is_numeric_dtype(df[cot]), cot


def test_dong_loi_de_trong_chu_khong_bia_so_0(rows):
    """Ô trống phải là NaN. Điền 0 sẽ biến 'không đo được' thành 'đo được và bằng 0'."""
    df = _ep_kieu(pd.DataFrame(rows, columns=Engine.HEADER))
    dong_loi = df[df["Clip gốc tìm thấy"].str.startswith("(LỖI")]
    assert len(dong_loi) == 1
    assert dong_loi[list(Engine.COT_SO)].isna().all().all()


def test_gia_tri_so_giu_dung_do_lon(rows):
    df = _ep_kieu(pd.DataFrame(rows, columns=Engine.HEADER))
    dong = df[df["Số hash khớp"].notna()].iloc[0]
    assert dong["Số hash khớp"] == 1234
    assert dong["Tỷ lệ vân tay khớp (%)"] == pytest.approx(87.5)
    assert dong["Đoạn khớp (giây)"] == 551      # round(551.2)
    assert dong["Khớp từ giây thứ (của clip)"] == 1   # round(0.6)


def test_to_rows_khong_con_ep_so_thanh_chuoi(rows):
    """Trước đây hai cột giây bị f-string ép thành chuỗi nên Sheets (ghi RAW) sắp xếp
    sai: '9' đứng sau '10'."""
    i_doan = Engine.HEADER.index("Đoạn khớp (giây)")
    i_offset = Engine.HEADER.index("Khớp từ giây thứ (của clip)")
    dong_khop = [d for d in rows if d[i_doan] != ""][0]
    assert isinstance(dong_khop[i_doan], int)
    assert isinstance(dong_khop[i_offset], int)


def test_giao_dien_ve_bang_qua_df_ket_qua():
    """Chặn hồi quy kiểu 'sửa engine nhưng giao diện vẫn dựng DataFrame thô'.

    app.py chạy Streamlit ngay lúc import nên không nạp hàm ra kiểm tra trực tiếp
    được; đọc mã nguồn là cách rẻ nhất giữ đúng ràng buộc này.
    """
    nguon = APP_PY.read_text(encoding="utf-8")
    assert "st.dataframe(df_ket_qua(rows)" in nguon
    assert "pd.DataFrame(rows, columns=eng.HEADER)" in nguon.split("def df_ket_qua")[1]
