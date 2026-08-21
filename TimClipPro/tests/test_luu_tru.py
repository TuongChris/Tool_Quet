# -*- coding: utf-8 -*-
"""Test lớp lưu trữ JSON nguyên tử và khả năng phục hồi dữ liệu."""

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

import luu_tru
from luu_tru import (
    LoiDuLieu,
    doc_json_an_toan,
    ghi_json_an_toan,
    ten_file_hop_le,
)


def test_file_chua_ton_tai_tra_mac_dinh_va_khong_tao_file(tmp_path):
    path = tmp_path / "chua_co.json"
    mac_dinh = {"muc": []}

    assert doc_json_an_toan(str(path), mac_dinh) is mac_dinh
    assert not path.exists()


def test_ghi_that_bai_thi_file_cu_con_nguyen(tmp_path, monkeypatch):
    path = tmp_path / "du_lieu.json"
    ghi_json_an_toan(str(path), {"lan": 1})

    def dump_loi(*args, **kwargs):
        raise OSError("ổ đĩa đầy")

    monkeypatch.setattr(luu_tru.json, "dump", dump_loi)
    with pytest.raises(OSError, match="ổ đĩa đầy"):
        ghi_json_an_toan(str(path), {"lan": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"lan": 1}
    assert not (tmp_path / "du_lieu.json.tmp").exists()


def test_file_hong_phuc_hoi_tu_ban_sao(tmp_path):
    path = tmp_path / "du_lieu.json"
    ghi_json_an_toan(str(path), {"lan": 1})
    ghi_json_an_toan(str(path), {"lan": 2})
    path.write_text("{hỏng", encoding="utf-8")

    assert doc_json_an_toan(str(path)) == {"lan": 1}
    assert json.loads(path.read_text(encoding="utf-8")) == {"lan": 1}


def test_file_hong_khong_cuu_duoc_thi_nem_loi_va_giu_file(tmp_path):
    path = tmp_path / "du_lieu.json"
    path.write_text("{file chính hỏng", encoding="utf-8")
    bak = tmp_path / "du_lieu.json.bak"
    bak.write_text("{bản sao cũng hỏng", encoding="utf-8")

    with pytest.raises(LoiDuLieu) as loi:
        doc_json_an_toan(str(path))

    cac_file_hong = list(tmp_path.glob("du_lieu.json.hong.*"))
    assert len(cac_file_hong) == 1
    assert cac_file_hong[0].read_text(encoding="utf-8") == "{file chính hỏng"
    assert bak.exists()
    assert str(cac_file_hong[0]) in str(loi.value)
    assert str(bak) in str(loi.value)


def test_khong_am_tham_tra_rong(tmp_path):
    path = tmp_path / "du_lieu.json"
    path.write_bytes(b"")

    with pytest.raises(LoiDuLieu):
        doc_json_an_toan(str(path), {})


def test_tieng_viet_duoc_doc_lai_nguyen_ven(tmp_path):
    path = tmp_path / "du_lieu.json"
    du_lieu = {"ghi_chu": "Kho clip ẩm thực Việt Nam"}

    ghi_json_an_toan(str(path), du_lieu)

    assert doc_json_an_toan(str(path)) == du_lieu
    assert "ẩm thực" in path.read_text(encoding="utf-8")


def test_hai_luong_ghi_khong_tao_json_bi_cut(tmp_path):
    path = tmp_path / "du_lieu.json"
    cac_gia_tri = [
        {"luong": i, "noi_dung": "dữ liệu" * 100}
        for i in range(20)
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda d: ghi_json_an_toan(str(path), d), cac_gia_tri))

    assert doc_json_an_toan(str(path)) in cac_gia_tri


def test_engine_canh_bao_khoi_dong_khi_khos_hong(tmp_path):
    from engine import Engine

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "khos.json").write_text("{hỏng", encoding="utf-8")

    engine = Engine(root=str(tmp_path))

    assert engine.canh_bao_khoi_dong
    assert "khos.json.hong." in engine.canh_bao_khoi_dong[0]
    assert len(list(data_dir.glob("khos.json.hong.*"))) == 1
    assert not (data_dir / "khos.json").exists()


def test_sua_archive_that_bai_giu_nguyen_file_cu(tmp_path, monkeypatch):
    import channel
    from channel import ChannelSync

    archive = tmp_path / "downloaded.txt"
    archive.write_text("youtube old123\n", encoding="utf-8")
    (tmp_path / "Video [new123].opus").write_bytes(b"audio")
    dong_cu = archive.read_text(encoding="utf-8")

    def replace_loi(*args, **kwargs):
        raise OSError("không thay được file")

    monkeypatch.setattr(channel.os, "replace", replace_loi)
    with pytest.raises(OSError, match="không thay được file"):
        ChannelSync(str(tmp_path)).sua_archive()

    assert archive.read_text(encoding="utf-8") == dong_cu
    assert not (tmp_path / "downloaded.txt.tmp").exists()


# =====================================================================
#  Đặt tên file: dấu hai chấm là bẫy IM LẶNG trên Windows
#
#  Lỗi thật 21/08/2026: `_luu_chan_doan` dùng `fingerprint_progress.ten_file_an_toan`
#  (hàm rút gọn tên cho LOG, chỉ lọc ký tự điều khiển) để dựng đường dẫn. Tiêu đề
#  «SML Movie: …» biến `open()` thành ghi vào NTFS Alternate Data Stream: nội dung
#  chui vào stream, `os.listdir` chỉ thấy «SML Movie», `glob("*.json")` không thấy gì.
#  Toàn bộ bản ghi chẩn đoán của kho SML mất trắng, để lại 5 file rác 0 byte mà chính
#  vòng dọn theo `glob("*.json")` cũng không nhìn thấy để xoá.
# =====================================================================

def test_dau_hai_cham_bi_thay_the():
    """Ký tự nguy hiểm nhất: không ném lỗi, chỉ lặng lẽ đổi nghĩa đường dẫn."""
    assert ":" not in ten_file_hop_le("SML Movie: The Purge! [reaction]")


@pytest.mark.parametrize("ky_tu", list(r'<>:"/\|?*'))
def test_moi_ky_tu_windows_cam_deu_bi_thay(ky_tu):
    assert ky_tu not in ten_file_hop_le(f"a{ky_tu}b")


def test_ten_thiet_bi_dos_khong_bao_gio_duoc_dung():
    """`open("CON.json", "w")` ghi ra console chứ không ra đĩa."""
    for ten in ("CON", "con.json", "NUL", "COM1.json", "LPT9"):
        assert ten_file_hop_le(ten) == "khong_ten", ten


def test_cat_dau_cham_va_khoang_trang_cuoi():
    """Windows tự bỏ chúng, nên "a. " và "a" là CÙNG một file — hai bản ghi đè nhau."""
    assert ten_file_hop_le("bao cao. ") == "bao cao"
    assert ten_file_hop_le("   ") == "khong_ten"


def test_cat_ngan_roi_van_khong_de_lo_dau_cham_cuoi():
    assert not ten_file_hop_le("x" * 119 + ". duoi", gioi_han=120).endswith(".")


def test_ten_binh_thuong_giu_nguyen():
    """Đừng băm nát tên đang tốt — người dùng còn phải đọc thư mục này."""
    assert ten_file_hop_le("Bao cao ngay 21-08 (ban 2)_123") ==         "Bao cao ngay 21-08 (ban 2)_123"


def test_ghi_json_voi_ten_da_lam_sach_thi_glob_TIM_RA(tmp_path):
    """Chốt chặn ở tầng hành vi: ghi xong phải TÌM LẠI ĐƯỢC bằng glob."""
    import glob
    import os

    ten = ten_file_hop_le("SML Movie: The Purge! [reaction]_123") + ".json"
    ghi_json_an_toan(os.path.join(str(tmp_path), ten), {"a": 1})

    ra = glob.glob(os.path.join(str(tmp_path), "*.json"))
    assert len(ra) == 1, "không glob ra được nghĩa là bản ghi coi như mất"
    assert json.load(open(ra[0], encoding="utf-8")) == {"a": 1}
    assert not [f for f in os.listdir(tmp_path)
                if os.path.getsize(tmp_path / f) == 0], "không được để lại file rác"
