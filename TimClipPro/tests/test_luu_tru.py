# -*- coding: utf-8 -*-
"""Test lớp lưu trữ JSON nguyên tử và khả năng phục hồi dữ liệu."""

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

import luu_tru
from luu_tru import LoiDuLieu, doc_json_an_toan, ghi_json_an_toan


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
