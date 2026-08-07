# -*- coding: utf-8 -*-
"""Quản lý vòng đời kho đệm theo đồng thời tuổi và ngân sách dung lượng."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


_BYTE_MOI_GB = 1024 ** 3
_GIAY_MOI_NGAY = 24 * 60 * 60
_DUOI_DANG_TAI = (".part", ".ytdl")


@dataclass
class MucDem:
    path: str
    kich_thuoc: int
    lan_dung_cuoi: float


def chon_can_xoa(
    muc: list,
    max_byte: int,
    max_giay: float,
    bay_gio: Optional[float] = None,
) -> list:
    """Chọn các mục quá tuổi, rồi chọn mục cũ nhất tới khi lọt ngân sách."""
    moc_hien_tai = time.time() if bay_gio is None else bay_gio
    can_xoa = []
    con_lai = []

    for item in muc:
        if (
            max_giay > 0
            and moc_hien_tai - item.lan_dung_cuoi > max_giay
        ):
            can_xoa.append(item)
        else:
            con_lai.append(item)

    if max_byte <= 0:
        return can_xoa

    tong_con_lai = sum(item.kich_thuoc for item in con_lai)
    if tong_con_lai <= max_byte:
        return can_xoa

    for item in sorted(con_lai, key=lambda x: x.lan_dung_cuoi):
        can_xoa.append(item)
        tong_con_lai -= item.kich_thuoc
        if tong_con_lai <= max_byte:
            break
    return can_xoa


def don_kho_dem(
    thu_muc: str,
    max_gb: float = 20.0,
    max_ngay: int = 7,
    thuc_hien: bool = True,
) -> dict:
    """Quét và dọn các file trực tiếp trong kho đệm, không đi vào thư mục con."""
    ket_qua = {
        "tong_file": 0,
        "tong_gb": 0.0,
        "xoa_file": 0,
        "xoa_gb": 0.0,
        "loi": [],
    }
    if not os.path.isdir(thu_muc):
        return ket_qua

    tat_ca = []
    co_the_xoa = []
    try:
        cac_muc = list(os.scandir(thu_muc))
    except OSError as e:
        ket_qua["loi"].append(f"Không quét được kho đệm {thu_muc}: {e}")
        return ket_qua

    for entry in cac_muc:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            stat = entry.stat(follow_symlinks=False)
        except OSError as e:
            ket_qua["loi"].append(f"{entry.path}: {e}")
            continue
        item = MucDem(
            path=entry.path,
            kich_thuoc=stat.st_size,
            lan_dung_cuoi=stat.st_mtime,
        )
        tat_ca.append(item)
        if not entry.name.lower().endswith(_DUOI_DANG_TAI):
            co_the_xoa.append(item)

    ket_qua["tong_file"] = len(tat_ca)
    ket_qua["tong_gb"] = (
        sum(item.kich_thuoc for item in tat_ca) / _BYTE_MOI_GB
    )
    can_xoa = chon_can_xoa(
        co_the_xoa,
        int(max_gb * _BYTE_MOI_GB),
        max_ngay * _GIAY_MOI_NGAY,
    )

    if not thuc_hien:
        ket_qua["xoa_file"] = len(can_xoa)
        ket_qua["xoa_gb"] = (
            sum(item.kich_thuoc for item in can_xoa) / _BYTE_MOI_GB
        )
        return ket_qua

    da_xoa_byte = 0
    for item in can_xoa:
        try:
            os.remove(item.path)
        except OSError as e:
            ket_qua["loi"].append(f"{item.path}: {e}")
            continue
        ket_qua["xoa_file"] += 1
        da_xoa_byte += item.kich_thuoc
    ket_qua["xoa_gb"] = da_xoa_byte / _BYTE_MOI_GB
    return ket_qua
