# -*- coding: utf-8 -*-
"""Test hàm dựng báo cáo dạng ngang 34 cột."""

import csv

from conftest import M

from bang_ngang import (
    HEADER_NGANG,
    dinh_dang_doan,
    dinh_dang_ngay,
    dung_dong_ngang,
)
from engine import ScanResult


HEADER_MONG_DOI = [
    "Thời gian quét",
    "Link kênh vi phạm",
    "Tên kênh vi phạm",
    "Id kênh vi phạm",
    "Link video vi phạm",
    "Tên video vi phạm",
    "Thời lượng video vi phạm",
    "Ngày đăng video vi phạm",
    "Đoạn vi phạm 1 trong video vi phạm",
    "Đoạn vi phạm 2 trong video vi phạm",
    "Đoạn vi phạm 3 trong video vi phạm",
    "Đoạn vi phạm 4 trong video vi phạm",
    "Đoạn vi phạm 5 trong video vi phạm",
    "Link video gốc 1",
    "Tên video gốc 1",
    "Ngày đăng video gốc 1",
    "Thời lượng video gốc 1",
    "Link video gốc 2",
    "Tên video gốc 2",
    "Ngày đăng video gốc 2",
    "Thời lượng video gốc 2",
    "Link video gốc 3",
    "Tên video gốc 3",
    "Ngày đăng video gốc 3",
    "Thời lượng video gốc 3",
    "Link video gốc 4",
    "Tên video gốc 4",
    "Ngày đăng video gốc 4",
    "Thời lượng video gốc 4",
    "Link video gốc 5",
    "Tên video gốc 5",
    "Ngày đăng video gốc 5",
    "Thời lượng video gốc 5",
    "Tổng số đoạn phát hiện",
]


def _dong_34(kq=None, clips_meta=None):
    dong = dung_dong_ngang(kq or ScanResult(source_name="x"), clips_meta)
    assert len(dong) == len(HEADER_NGANG) == 34
    return dong


def test_header_ngang_dung_chinh_xac_34_cot():
    _dong_34()

    assert HEADER_NGANG == HEADER_MONG_DOI


def test_tieu_de_doan_vi_pham_dung_nguyen_van():
    _dong_34()

    assert HEADER_NGANG[8] == "Đoạn vi phạm 1 trong video vi phạm"


def test_luon_du_34_cot():
    dong = _dong_34(ScanResult(source_name="x"))

    assert all(isinstance(gia_tri, (str, int)) for gia_tri in dong)


def test_dinh_dang_ngay():
    _dong_34()

    assert dinh_dang_ngay("20250115") == "15/01/2025"
    assert dinh_dang_ngay("00000000") == ""
    assert dinh_dang_ngay("") == ""
    assert dinh_dang_ngay("20251340") == ""
    assert dinh_dang_ngay("2025A115") == ""


def test_dinh_dang_doan_co_va_khong_co_link():
    _dong_34()
    match = M(start=850, matched=996)

    assert dinh_dang_doan(
        match,
        "abc123",
        "",
    ) == "00:14:10 – 00:30:46 · https://youtu.be/abc123?t=850"
    assert dinh_dang_doan(
        match,
        "",
        "D:/video.mp4",
    ) == "00:14:10 – 00:30:46"


def test_dung_day_du_thong_tin_nguon_va_clip_goc():
    match = M("clip.opus", start=60, matched=30)
    kq = ScanResult(
        source_name="Video vi phạm",
        source_ref="https://youtu.be/abc123",
        source_id="abc123",
        duration_s=3600,
        matches=[match],
        channel_name="Kênh vi phạm",
        channel_id="UC123",
        channel_url="https://youtube.com/channel/UC123",
        upload_date="20250115",
        so_dat_nguong=7,
    )
    dong = _dong_34(kq, {
        "clip.opus": {
            "url": "https://youtu.be/goc123",
            "title": "Video gốc",
            "upload_date": "20240102",
            "duration": 125,
        },
    })

    assert dong[1:8] == [
        "https://youtube.com/channel/UC123",
        "Kênh vi phạm",
        "UC123",
        "https://youtu.be/abc123",
        "Video vi phạm",
        "01:00:00",
        "15/01/2025",
    ]
    assert dong[13:17] == [
        "https://youtu.be/goc123",
        "Video gốc",
        "02/01/2024",
        "00:02:05",
    ]
    assert dong[33] == 7


def test_matches_rong_de_cac_o_doan_va_goc_rong():
    dong = _dong_34(ScanResult(source_name="x", so_dat_nguong=4))

    assert dong[8:33] == [""] * 25
    assert dong[33] == 4


def test_hai_match_de_cac_nhom_con_lai_rong():
    kq = ScanResult(
        source_name="x",
        matches=[M("a.opus"), M("b.opus", start=100)],
    )
    dong = _dong_34(kq)

    assert dong[10:13] == ["", "", ""]
    assert dong[21:33] == [""] * 12


def test_chi_lay_5_doan_dau():
    matches = [
        M(f"clip-{i}.opus", start=i * 100, matched=10)
        for i in range(7)
    ]
    dong = _dong_34(ScanResult(source_name="x", matches=matches))

    assert dong[12] == "00:06:40 – 00:06:50"
    assert all("00:08:20" not in str(o) and "00:10:00" not in str(o) for o in dong)


def test_meta_thieu_clip_de_bon_o_rong():
    kq = ScanResult(source_name="x", matches=[M("khong-co-meta.opus")])
    dong = _dong_34(kq, {})

    assert dong[13:17] == ["", "", "", ""]


def test_ket_qua_loi_van_du_34_o_va_bo_cac_doan():
    kq = ScanResult(
        source_name="x",
        matches=[M("clip.opus")],
        status="error",
        note="nguồn hỏng",
        so_dat_nguong=2,
    )
    dong = _dong_34(kq)

    assert dong[5] == "(LỖI: nguồn hỏng)"
    assert dong[8:33] == [""] * 25
    assert dong[33] == 2


def test_to_rows_ngang_bo_qua_ket_qua_loi(engine, monkeypatch):
    so_lan_doc_meta = 0

    def clip_meta():
        nonlocal so_lan_doc_meta
        so_lan_doc_meta += 1
        return {}

    monkeypatch.setattr(engine, "clip_meta", clip_meta)
    ok = ScanResult(source_name="ok", matches=[M()])
    loi = ScanResult(source_name="lỗi", matches=[M()], status="error")

    rows = engine.to_rows_ngang([ok, loi])

    assert so_lan_doc_meta == 1
    assert len(rows) == 1
    assert len(rows[0]) == len(HEADER_NGANG) == 34


def test_export_csv_ngang_co_bom_utf8(engine, tmp_path, monkeypatch):
    engine.out_dir = str(tmp_path)
    monkeypatch.setattr(engine, "clip_meta", lambda: {})
    kq = ScanResult(source_name="Tiếng Việt", matches=[M()])

    path = engine.export_csv_ngang([kq])

    assert path.endswith(".csv")
    assert tmp_path.joinpath(path).read_bytes()[:3] == b"\xef\xbb\xbf"
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 2
    assert len(rows[0]) == len(rows[1]) == len(HEADER_NGANG) == 34
    assert rows[0] == HEADER_NGANG
    assert "Tiếng Việt" in rows[1]


def test_export_csv_ngang_khong_tao_file_khi_khong_co_dong(
    engine,
    tmp_path,
):
    thu_muc_xuat = tmp_path / "out"
    engine.out_dir = str(thu_muc_xuat)

    path = engine.export_csv_ngang([
        ScanResult(source_name="rỗng"),
        ScanResult(source_name="lỗi", matches=[M()], status="error"),
    ])

    assert len(HEADER_NGANG) == 34
    assert path == ""
    assert not thu_muc_xuat.exists()
