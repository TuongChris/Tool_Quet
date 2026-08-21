# -*- coding: utf-8 -*-
"""Quản lý vòng đời kho đệm và thư mục job quét theo tuổi/ngân sách dung lượng."""

from __future__ import annotations

import os
import shutil
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


def _do_thu_muc(duong_dan: str) -> tuple:
    """Trả ``(tổng byte, mtime mới nhất, lỗi)`` của một thư mục job.

    Lấy mtime MỚI NHẤT trong các file con chứ không lấy mtime của chính thư mục:
    trên Windows, mtime thư mục chỉ đổi khi thêm/bớt mục trực tiếp bên trong, nên
    một lượt quét đang ghi liên tục vào ``chunks`` có thể để thư mục cha trông như
    đã cũ hàng giờ — đúng thứ khiến ta xoá nhầm job đang chạy.
    """
    tong = 0
    moi_nhat = 0.0
    loi = []
    for goc, _thu_muc_con, files in os.walk(duong_dan):
        for ten in files:
            duong = os.path.join(goc, ten)
            try:
                st = os.stat(duong)
            except OSError as e:
                loi.append(f"{duong}: {e}")
                continue
            tong += st.st_size
            moi_nhat = max(moi_nhat, st.st_mtime)
    if moi_nhat == 0.0:
        # Thư mục rỗng (hoặc không đọc được file nào) — dùng mtime của chính nó.
        try:
            moi_nhat = os.stat(duong_dan).st_mtime
        except OSError as e:
            loi.append(f"{duong_dan}: {e}")
    return tong, moi_nhat, loi


def don_job_quet(
    thu_muc: str,
    max_ngay: int = 7,
    thuc_hien: bool = True,
    bay_gio: Optional[float] = None,
) -> dict:
    """Xoá các thư mục job quét MỒ CÔI trong ``data/scan_jobs``.

    Bình thường không có gì để dọn: ``Engine._thu_muc_job()`` tạo thư mục trong một
    context manager có ``finally: shutil.rmtree(goc)``, nên quét xong là tự sạch.
    Thư mục còn sót lại chỉ sinh ra khi tiến trình CHẾT BẤT THƯỜNG — tắt máy, kill,
    hay crash. Mỗi thư mục như vậy giữ nguyên các chunk WAV đã giải mã, thực đo
    246 MB đến 3,2 GB một cái, và không bao giờ được dùng lại: tên thư mục là
    ``uuid.uuid4().hex`` nên mỗi lượt quét là một tên mới tinh.

    Trước bản này, ``don_kho_dem`` chỉ dọn kho đệm tải và bỏ qua hoàn toàn
    ``scan_jobs``, nên rác tích luỹ âm thầm cho tới khi đầy ổ.

    ``max_ngay <= 0`` nghĩa là KHÔNG có tiêu chí tuổi nên không xoá gì — giữ đúng
    quy ước của ``don_kho_dem``.

    Job ĐANG CHẠY được bảo vệ bằng cách tính tuổi theo file MỚI NHẤT bên trong
    (xem ``_do_thu_muc``): một lượt quét đang chạy ghi chunk liên tục nên tuổi của
    nó luôn tính bằng giây, không đời nào vượt ngưỡng tính bằng ngày.
    """
    ket_qua = {
        "tong_job": 0,
        "tong_gb": 0.0,
        "xoa_job": 0,
        "xoa_gb": 0.0,
        "bo_qua_dang_chay": 0,
        "loi": [],
    }
    if not os.path.isdir(thu_muc):
        return ket_qua

    try:
        cac_muc = list(os.scandir(thu_muc))
    except OSError as e:
        ket_qua["loi"].append(f"Không quét được thư mục job {thu_muc}: {e}")
        return ket_qua

    muc = []
    for entry in cac_muc:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError as e:
            ket_qua["loi"].append(f"{entry.path}: {e}")
            continue
        tong, moi_nhat, loi = _do_thu_muc(entry.path)
        ket_qua["loi"].extend(loi)
        muc.append(MucDem(path=entry.path, kich_thuoc=tong, lan_dung_cuoi=moi_nhat))

    ket_qua["tong_job"] = len(muc)
    ket_qua["tong_gb"] = sum(x.kich_thuoc for x in muc) / _BYTE_MOI_GB

    gioi_han = max_ngay * _GIAY_MOI_NGAY
    if gioi_han <= 0:
        return ket_qua

    # Chỉ lọc theo TUỔI, không theo ngân sách dung lượng: xoá thư mục job mới nhất
    # chỉ vì tổng dung lượng vượt ngưỡng thì rất dễ trúng job đang chạy.
    can_xoa = chon_can_xoa(muc, 0, gioi_han, bay_gio)
    ket_qua["bo_qua_dang_chay"] = len(muc) - len(can_xoa)

    if not thuc_hien:
        ket_qua["xoa_job"] = len(can_xoa)
        ket_qua["xoa_gb"] = sum(x.kich_thuoc for x in can_xoa) / _BYTE_MOI_GB
        return ket_qua

    da_xoa_byte = 0
    for item in can_xoa:
        try:
            shutil.rmtree(item.path)
        except OSError as e:
            ket_qua["loi"].append(f"{item.path}: {e}")
            continue
        ket_qua["xoa_job"] += 1
        da_xoa_byte += item.kich_thuoc
    ket_qua["xoa_gb"] = da_xoa_byte / _BYTE_MOI_GB
    return ket_qua
