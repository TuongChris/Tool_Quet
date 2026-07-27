# -*- coding: utf-8 -*-
"""Lưu tùy chọn người dùng; không lưu khóa API, mật khẩu hay nội dung google_key.json."""

from __future__ import annotations

import os
from dataclasses import fields
from typing import Any

from luu_tru import LoiDuLieu, doc_json_an_toan, ghi_json_an_toan


TEN_FILE = "cau_hinh.json"

# Chỉ các tùy chọn giao diện không bí mật này được phép ghi cùng Config.
GIA_TRI_GIAO_DIEN_MAC_DINH = {
    "sheet_link": "",
    "sheet_auto": True,
    "sheet_dang_ngang": True,
    "kho_dir": "",
    "thu_muc_quet_gan_nhat": "",
}


def _duong_dan(data_dir: str) -> str:
    return os.path.join(data_dir, TEN_FILE)


def doc_cau_hinh(data_dir: str) -> dict:
    """Đọc cấu hình người dùng. Chưa có file thì trả về dict rỗng."""
    du_lieu = doc_json_an_toan(_duong_dan(data_dir), {})
    if not isinstance(du_lieu, dict):
        raise LoiDuLieu(
            f"Cấu hình tại {_duong_dan(data_dir)} phải là một đối tượng JSON."
        )
    return du_lieu


def ghi_cau_hinh(data_dir: str, du_lieu: dict) -> None:
    """Ghi cấu hình nguyên tử bằng lớp lưu trữ dùng chung."""
    ghi_json_an_toan(_duong_dan(data_dir), du_lieu)


def ap_vao_config(cfg: Any, du_lieu: dict) -> list:
    """
    Áp các khóa hợp lệ, đúng kiểu vào Config và trả lại danh sách khóa bị bỏ qua.
    """
    bi_bo_qua = []
    cac_khoa_config = {truong.name for truong in fields(cfg)}
    for khoa, gia_tri in du_lieu.items():
        if khoa not in cac_khoa_config:
            bi_bo_qua.append(khoa)
            continue
        gia_tri_hien_tai = getattr(cfg, khoa)
        if type(gia_tri) is not type(gia_tri_hien_tai):
            bi_bo_qua.append(khoa)
            continue
        setattr(cfg, khoa, gia_tri)
    return bi_bo_qua


def lay_tu_config(cfg: Any) -> dict:
    """Trích toàn bộ trường dataclass Config thành dict để lưu."""
    return {truong.name: getattr(cfg, truong.name) for truong in fields(cfg)}
