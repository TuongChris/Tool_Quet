# -*- coding: utf-8 -*-
"""Test cấu hình bền vững, không chạm dữ liệu thật của người dùng."""

import json

from cau_hinh import (
    TEN_FILE,
    ap_vao_config,
    doc_cau_hinh,
    ghi_cau_hinh,
    lay_tu_config,
)
from engine import Config, Engine


def test_luu_roi_doc_lai_giu_nguyen(tmp_path):
    engine = Engine(root=str(tmp_path))
    engine.config.chunk_s = 1800
    engine.config.ncores = 3
    engine.luu_cau_hinh({
        "sheet_link": "https://docs.google.com/spreadsheets/d/abc",
        "sheet_auto": False,
        "sheet_dang_ngang": False,
        "kho_dir": "D:/Kho clip",
        "thu_muc_quet_gan_nhat": "D:/Video dài",
    })

    engine_moi = Engine(root=str(tmp_path))

    assert engine_moi.config.chunk_s == 1800
    assert engine_moi.config.ncores == 3
    assert engine_moi.cau_hinh_da_luu["sheet_auto"] is False
    assert engine_moi.cau_hinh_da_luu["kho_dir"] == "D:/Kho clip"


def test_khoa_la_bi_bo_qua():
    cfg = Config()

    bi_bo_qua = ap_vao_config(
        cfg,
        {"chunk_s": 2400, "khoa_phien_ban_cu": "giá trị cũ"},
    )

    assert cfg.chunk_s == 2400
    assert bi_bo_qua == ["khoa_phien_ban_cu"]


def test_sai_kieu_bi_bo_qua():
    cfg = Config()

    bi_bo_qua = ap_vao_config(
        cfg,
        {"chunk_s": "1800", "ncores": True, "min_match_s": 7.5},
    )

    assert cfg.chunk_s == Config().chunk_s
    assert cfg.ncores == Config().ncores
    assert cfg.min_match_s == 7.5
    assert bi_bo_qua == ["chunk_s", "ncores"]


def test_file_hong_van_khoi_dong_duoc(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / TEN_FILE).write_text("{JSON hỏng", encoding="utf-8")

    engine = Engine(root=str(tmp_path))

    assert engine.config == Config()
    assert engine.canh_bao_khoi_dong
    assert "cấu hình người dùng" in engine.canh_bao_khoi_dong[0]
    assert list(data_dir.glob(f"{TEN_FILE}.hong.*"))


def test_khong_luu_khoa_bi_mat(tmp_path):
    engine = Engine(root=str(tmp_path))
    engine.luu_cau_hinh({
        "sheet_link": "https://docs.google.com/spreadsheets/d/abc",
        "google_key.json": "BI_MAT_GOOGLE",
        "api_key": "BI_MAT_API",
        "token": "BI_MAT_TOKEN",
    })

    noi_dung = (tmp_path / "data" / TEN_FILE).read_text(encoding="utf-8")
    du_lieu = json.loads(noi_dung)

    assert du_lieu["sheet_link"].endswith("/abc")
    assert "google_key.json" not in du_lieu
    assert "api_key" not in du_lieu
    assert "token" not in du_lieu
    assert "BI_MAT" not in noi_dung


def test_khoi_phuc_mac_dinh(tmp_path):
    engine = Engine(root=str(tmp_path))
    engine.config.chunk_s = 1800
    engine.luu_cau_hinh({"sheet_auto": False})
    path = tmp_path / "data" / TEN_FILE
    assert path.exists()

    engine.khoi_phuc_cau_hinh_mac_dinh()

    assert engine.config == Config()
    assert engine.cau_hinh_da_luu == {}
    assert not path.exists()
    assert doc_cau_hinh(str(tmp_path / "data")) == {}


def test_file_chua_ton_tai_khong_bi_tao(tmp_path):
    assert doc_cau_hinh(str(tmp_path)) == {}
    assert not (tmp_path / TEN_FILE).exists()


def test_cau_hinh_khong_hop_le_quay_ve_mac_dinh(tmp_path):
    du_lieu = lay_tu_config(Config())
    du_lieu["chunk_s"] = 300
    du_lieu["overlap_s"] = 600
    ghi_cau_hinh(str(tmp_path / "data"), du_lieu)

    engine = Engine(root=str(tmp_path))

    assert engine.config == Config()
    assert any("đang dùng mặc định" in msg for msg in engine.canh_bao_khoi_dong)
