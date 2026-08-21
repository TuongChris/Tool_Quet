# -*- coding: utf-8 -*-
"""Đọc và ghi dữ liệu cấu hình theo cách nguyên tử, có khả năng phục hồi."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import datetime
from typing import Any


class LoiDuLieu(Exception):
    """File tồn tại nhưng không đọc được — khác với file chưa tồn tại."""


# Ký tự Windows CẤM trong tên file. Nguy hiểm nhất là DẤU HAI CHẤM: nó không ném lỗi
# mà lặng lẽ đổi nghĩa đường dẫn. Ghi vào ``thu_muc\SML Movie: Abc.json`` tạo ra một
# file RỖNG tên «SML Movie» kèm một NTFS Alternate Data Stream tên «Abc.json»; nội dung
# nằm trong stream đó, ``os.listdir`` chỉ thấy «SML Movie», và ``glob("*.json")`` không
# thấy gì cả.
#
# Đo trên máy thật 21/08/2026: mọi bản ghi chẩn đoán của video có dấu hai chấm trong
# tiêu đề đều mất trắng — tức gần như toàn bộ kho SML («SML Movie: …», «SML ROBLOX: …»,
# «SML Parody: …») — để lại 5 file rác 0 byte mà chính vòng dọn theo ``glob("*.json")``
# cũng không nhìn thấy để xoá. Lỗi im lặng tuyệt đối vì nơi gọi bọc trong
# ``contextlib.suppress(Exception)``.
_KY_TU_CAM_TEN_FILE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Tên thiết bị DOS: ``open("CON.json", "w")`` ghi ra console chứ không ra đĩa.
_TEN_THIET_BI = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


def ten_file_hop_le(ten: str, mac_dinh: str = "khong_ten",
                    gioi_han: int = 120) -> str:
    """Biến một chuỗi tuỳ ý thành tên file AN TOÀN trên Windows lẫn POSIX.

    ĐỪNG dùng ``fingerprint_progress.ten_file_an_toan`` cho việc này: hàm đó sinh ra để
    RÚT GỌN tên cho log và giao diện (chỉ lọc ký tự điều khiển), không phải để dựng
    đường dẫn. Dùng nhầm chính là nguyên nhân của lỗi mô tả ở ``_KY_TU_CAM_TEN_FILE``.

    Cắt cả dấu chấm và khoảng trắng ở CUỐI: Windows tự bỏ chúng khi tạo file, nên
    ``"a. "`` và ``"a"`` trỏ về cùng một file — hai bản ghi khác nhau sẽ đè lên nhau.
    Cắt độ dài TRƯỚC rồi mới cắt lại đuôi, vì cắt ngắn có thể lòi ra dấu chấm mới.
    """
    sach = _KY_TU_CAM_TEN_FILE.sub("_", str(ten or "")).strip(" .")
    sach = sach[:gioi_han].strip(" .")
    if not sach or sach.split(".")[0].upper() in _TEN_THIET_BI:
        return mac_dinh
    return sach


_KHOA_THEO_DUONG_DAN: dict[str, threading.RLock] = {}
_KHOA_DANH_SACH = threading.Lock()


def _lay_khoa(path: str) -> threading.RLock:
    duong_dan = os.path.abspath(path)
    with _KHOA_DANH_SACH:
        if duong_dan not in _KHOA_THEO_DUONG_DAN:
            _KHOA_THEO_DUONG_DAN[duong_dan] = threading.RLock()
        return _KHOA_THEO_DUONG_DAN[duong_dan]


def ghi_json_an_toan(
    path: str,
    du_lieu: Any,
    giu_ban_sao: bool = True,
) -> None:
    """Ghi JSON nguyên tử: thành công trọn vẹn hoặc file cũ còn nguyên."""
    duong_dan = os.path.abspath(path)
    thu_muc = os.path.dirname(duong_dan)
    file_tam = duong_dan + ".tmp"
    file_bak = duong_dan + ".bak"
    os.makedirs(thu_muc, exist_ok=True)

    with _lay_khoa(duong_dan):
        try:
            if giu_ban_sao and os.path.isfile(duong_dan):
                shutil.copyfile(duong_dan, file_bak)

            with open(file_tam, "w", encoding="utf-8") as f:
                json.dump(du_lieu, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(file_tam, duong_dan)
        except BaseException:
            try:
                if os.path.exists(file_tam):
                    os.remove(file_tam)
            except OSError:
                pass
            raise


def _doc_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _duong_dan_file_hong(path: str) -> str:
    dau_thoi_gian = datetime.now().strftime("%Y%m%d_%H%M%S")
    goc = f"{path}.hong.{dau_thoi_gian}"
    duong_dan = goc
    thu_tu = 2
    while os.path.exists(duong_dan):
        duong_dan = f"{goc}_{thu_tu}"
        thu_tu += 1
    return duong_dan


def doc_json_an_toan(
    path: str,
    mac_dinh: Any = None,
    tu_phuc_hoi: bool = True,
) -> Any:
    """
    Đọc JSON, phục hồi từ bản sao khi có thể và không âm thầm nuốt file hỏng.
    """
    duong_dan = os.path.abspath(path)
    file_bak = duong_dan + ".bak"

    with _lay_khoa(duong_dan):
        if not os.path.exists(duong_dan):
            return mac_dinh

        try:
            return _doc_json(duong_dan)
        except Exception as loi_file_chinh:
            if tu_phuc_hoi and os.path.isfile(file_bak):
                try:
                    du_lieu_bak = _doc_json(file_bak)
                except Exception:
                    pass
                else:
                    ghi_json_an_toan(
                        duong_dan,
                        du_lieu_bak,
                        giu_ban_sao=False,
                    )
                    return du_lieu_bak

            file_hong = _duong_dan_file_hong(duong_dan)
            try:
                os.rename(duong_dan, file_hong)
            except OSError as loi_doi_ten:
                raise LoiDuLieu(
                    f"Không đọc được JSON tại {duong_dan}; "
                    f"không giữ được bản lỗi dưới tên mới: {loi_doi_ten}. "
                    f"Bản sao: {file_bak}."
                ) from loi_file_chinh
            raise LoiDuLieu(
                f"Không đọc được JSON. File hỏng đã giữ tại {file_hong}. "
                f"Bản sao: {file_bak}."
            ) from loi_file_chinh
