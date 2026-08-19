# -*- coding: utf-8 -*-
"""Regression test cho các lỗi bảo mật và an toàn dữ liệu đã audit."""

import csv
import os

import pytest

from channel import ChannelSync, VideoInfo
from engine import Config, ScanResult
from luu_tru import LoiDuLieu
from sheets import SheetsExporter


@pytest.mark.parametrize("ten_file", [
    "../ngoai.pklz",
    r"..\ngoai.pklz",
    "thu_muc/kho.pklz",
    r"C:\ngoai.pklz",
    "khong-phai-pickle.txt",
])
def test_ten_file_kho_khong_duoc_thoat_data(engine, ten_file):
    with pytest.raises(LoiDuLieu):
        engine._duong_dan_db_kho(ten_file)


def test_xoa_kho_khong_xoa_file_ngoai_data(engine, tmp_path):
    file_ngoai = tmp_path / "ngoai.pklz"
    file_ngoai.write_bytes(b"du lieu phai duoc giu")
    engine._ghi_khos({
        "dang_dung": "Kho loi",
        "danh_sach": [{
            "ten": "Kho loi",
            "thu_muc": "",
            "db": "../ngoai.pklz",
        }],
    })

    with pytest.raises(LoiDuLieu):
        engine.delete_kho("Kho loi")

    assert file_ngoai.read_bytes() == b"du lieu phai duoc giu"


def test_export_csv_khong_ghi_de_file_co_san(engine, tmp_path):
    path = tmp_path / "bao_cao.csv"
    path.write_text("noi dung cu", encoding="utf-8")

    path_moi = engine.export_csv([ScanResult(source_name="video")], str(path))

    assert path.read_text(encoding="utf-8") == "noi dung cu"
    assert path_moi == str(tmp_path / "bao_cao_2.csv")
    assert os.path.isfile(path_moi)


@pytest.mark.parametrize(
    "gia_tri",
    ["=1+1", "+SUM(1,2)", "-2+3", "@cmd", "\t=1+1", " =1+1"],
)
def test_export_csv_vo_hieu_hoa_cong_thuc(engine, tmp_path, gia_tri):
    path = engine.export_csv(
        [ScanResult(source_name=gia_tri)],
        str(tmp_path / "bao_cao.csv"),
    )

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    assert rows[1][1] == "'" + gia_tri


def test_sheets_ghi_raw_de_khong_thuc_thi_cong_thuc(tmp_path, monkeypatch):
    class WorksheetGia:
        def __init__(self):
            self.calls = []

        def get_all_values(self):
            return []

        def append_row(self, row, value_input_option):
            self.calls.append(("row", row, value_input_option))

        def append_rows(self, rows, value_input_option):
            self.calls.append(("rows", rows, value_input_option))

    ws = WorksheetGia()
    exporter = SheetsExporter(
        key_path=str(tmp_path / "khong-can-doc.json"),
        sheet="sheet-id",
    )
    monkeypatch.setattr(exporter, "san_sang", lambda: True)
    monkeypatch.setattr(exporter, "_mo_worksheet", lambda so_cot: ws)

    assert exporter.append(["Tieu de"], [["=1+1"]]) == 1
    assert [call[2] for call in ws.calls] == ["RAW", "RAW"]


def test_dong_bo_huy_truoc_video_dau_khong_bao_tai_thanh_cong(tmp_path, monkeypatch):
    cs = ChannelSync(str(tmp_path))
    videos = [
        VideoInfo("abc123", "Một", "20250101", 10, "u1"),
        VideoInfo("def456", "Hai", "20250102", 10, "u2"),
    ]
    # **kwargs: sync() nay truyền thêm cau_hinh_mang (cookie + giãn nhịp) xuống
    # list_channel; bản giả chỉ quan tâm tới danh sách trả về.
    monkeypatch.setattr(cs, "list_channel", lambda url, limit, **kw: videos)
    monkeypatch.setattr(cs, "done_ids", lambda: set())
    monkeypatch.setattr(cs, "quet_id_tren_dia", lambda: {})
    monkeypatch.setattr(
        cs,
        "_tai_va_nen",
        lambda video: pytest.fail("Không được tải sau khi đã yêu cầu dừng"),
    )

    ket_qua = cs.sync("kenh", cancel_check=lambda: True)

    assert ket_qua["moi"] == 0
    assert ket_qua["da_huy"] is True


def test_download_youtube_co_timeout_va_retry_huu_han(engine, monkeypatch):
    import yt_dlp

    da_nhan = []

    class YoutubeDLGia:
        def __init__(self, opts):
            da_nhan.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def download(self, urls):
            assert urls == ["https://youtu.be/abc123"]
            dich = da_nhan[0]["outtmpl"]
            dich = dich.replace("%(id)s", "abc123").replace("%(ext)s", "opus")
            with open(dich, "wb") as f:
                f.write(b"audio gia")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", YoutubeDLGia)

    ket_qua = engine.download_audio("https://youtu.be/abc123", "abc123")

    assert os.path.isfile(ket_qua)
    assert da_nhan[0]["socket_timeout"] == 30
    assert da_nhan[0]["retries"] == 10
    assert da_nhan[0]["fragment_retries"] == 10


@pytest.mark.parametrize(("truong", "gia_tri"), [
    ("ncores", 65),
    ("shifts_kho", 9),
    ("shifts_quet", -1),
    ("max_matches", 0),
    ("dedup_s", -0.1),
    ("top_n", 0),
    ("dem_max_gb", -1.0),
    ("network_timeout_s", 4),
    ("network_timeout_s", 301),
])
def test_config_tu_choi_gia_tri_tai_nguyen_nguy_hiem(truong, gia_tri):
    config = Config()
    setattr(config, truong, gia_tri)

    with pytest.raises(ValueError):
        config.validate()
