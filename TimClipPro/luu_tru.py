# -*- coding: utf-8 -*-
"""Đọc và ghi dữ liệu cấu hình theo cách nguyên tử, có khả năng phục hồi."""

from __future__ import annotations

import contextlib
import glob
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable

from khoa import DangChayRoi, KhoaTienTrinh


class LoiDuLieu(Exception):
    """File tồn tại nhưng không đọc được — khác với file chưa tồn tại."""


class LoiKhoaDuLieu(TimeoutError):
    """Chờ quá hạn mà process khác vẫn đang giữ khoá dữ liệu.

    Cố ý KHÔNG kế thừa ``LoiDuLieu``: khoá bận không có nghĩa là file hỏng, và các
    nơi bắt ``LoiDuLieu`` để "reset về rỗng" không được phản ứng với khoá bận.
    """


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


# =====================================================================
#  Khoá dữ liệu GIỮA CÁC PROCESS (audit TCP-03)
#
#  `threading.RLock` cũ chỉ có hiệu lực trong MỘT process: giao diện, Watch, đồng bộ
#  kênh và các công cụ sửa metadata chạy ở những process khác nhau, và hai process
#  từng dùng chung một file `.tmp` — writer A báo "ok" mà file chứa dữ liệu của B.
#
#  Khoá là KHOÁ HỆ ĐIỀU HÀNH (tái dùng `KhoaTienTrinh`) trên MỘT file mỗi THƯ MỤC,
#  không phải mỗi file JSON: bản ghi chẩn đoán có tên duy nhất, khoá theo file sẽ đẻ
#  ra một file `.lock` cho mỗi bản ghi và tích luỹ mãi. Mọi giao dịch JSON trong cùng
#  thư mục vì thế chạy tuần tự — chúng chỉ vài mili giây nên không đáng kể.
#
#  `RLock` vẫn giữ để cùng một thread vào lại được (đường phục hồi từ `.bak` ghi lại
#  file ngay bên trong lúc đọc), và để các thread trong cùng process không giành nhau
#  khoá OS.
#
#  Thứ tự khoá toàn dự án: `data/tool.lock` → khoá JSON của `data/` → khoá JSON khác.
#  Không lồng khoá JSON của hai thư mục khác nhau, không giữ khoá khi gọi mạng.
# =====================================================================

TEN_FILE_KHOA = ".timclip.lock"
HAN_CHO_KHOA_S = 60.0


class _KhoaThuMuc:
    def __init__(self) -> None:
        self.rlock = threading.RLock()
        self.do_sau = 0
        self.khoa_os: KhoaTienTrinh | None = None


_KHOA_THEO_THU_MUC: dict[str, _KhoaThuMuc] = {}
_KHOA_DANH_SACH = threading.Lock()


def _khoa_cua(thu_muc: str) -> _KhoaThuMuc:
    khoa = os.path.normcase(os.path.abspath(thu_muc))
    with _KHOA_DANH_SACH:
        if khoa not in _KHOA_THEO_THU_MUC:
            _KHOA_THEO_THU_MUC[khoa] = _KhoaThuMuc()
        return _KHOA_THEO_THU_MUC[khoa]


def _giu_khoa_os(duong_dan_khoa: str, ten: str, han_cho_s: float) -> KhoaTienTrinh:
    """Chờ có hạn cho tới khi giành được khoá OS; quá hạn thì nêu rõ ai đang giữ."""
    het_han = time.monotonic() + max(0.0, han_cho_s)
    cho = 0.01
    while True:
        khoa = KhoaTienTrinh(duong_dan_khoa, ten)
        try:
            khoa.__enter__()
            return khoa
        except DangChayRoi:
            if time.monotonic() >= het_han:
                raise LoiKhoaDuLieu(
                    f"Dữ liệu đang được process khác ghi quá {han_cho_s:.0f} giây "
                    f"({duong_dan_khoa}). {khoa.thong_tin_chu_khoa}"
                ) from None
            time.sleep(cho)
            cho = min(0.2, cho * 2)


@contextlib.contextmanager
def khoa_json(path: str, han_cho_s: float = HAN_CHO_KHOA_S):
    """Giữ khoá ghi cho thư mục chứa ``path`` — loại trừ cả thread lẫn process."""
    thu_muc = os.path.dirname(os.path.abspath(path))
    os.makedirs(thu_muc, exist_ok=True)
    k = _khoa_cua(thu_muc)
    if not k.rlock.acquire(timeout=max(0.0, han_cho_s)):
        raise LoiKhoaDuLieu(
            f"Dữ liệu trong {thu_muc} đang được một luồng khác của chính tool ghi "
            f"quá {han_cho_s:.0f} giây."
        )
    try:
        if k.do_sau == 0:
            k.khoa_os = _giu_khoa_os(
                os.path.join(thu_muc, TEN_FILE_KHOA),
                f"ghi dữ liệu {os.path.basename(path)}",
                han_cho_s,
            )
        k.do_sau += 1
        try:
            yield
        finally:
            k.do_sau -= 1
            if k.do_sau == 0 and k.khoa_os is not None:
                khoa_os, k.khoa_os = k.khoa_os, None
                khoa_os.__exit__(None, None, None)
    finally:
        k.rlock.release()


def _json_doc_duoc(path: str) -> bool:
    try:
        _doc_json(path)
        return True
    except (OSError, ValueError):
        return False


def _don_file_tam_mo_coi(duong_dan: str) -> None:
    """Xoá file tạm của writer đã chết. CHỈ gọi khi đang giữ khoá của thư mục:
    lúc đó không writer nào khác có thể đang ghi dở file tạm của đường dẫn này."""
    for cu in glob.glob(glob.escape(duong_dan) + "*.tmp"):
        with contextlib.suppress(OSError):
            os.remove(cu)


def _thay_the(src: str, dst: str, so_lan: int = 10) -> None:
    """``os.replace`` có thử lại: trên Windows reader khác đang mở file đích làm
    replace hỏng tạm thời (WinError 5/32). Hết lượt thì ném lỗi gốc."""
    cho = 0.05
    for lan in range(so_lan):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if lan == so_lan - 1:
                raise
            time.sleep(cho)
            cho = min(0.5, cho * 2)


def ghi_json_an_toan(
    path: str,
    du_lieu: Any,
    giu_ban_sao: bool = True,
) -> None:
    """Ghi JSON nguyên tử: thành công trọn vẹn hoặc file cũ còn nguyên.

    File tạm mang tên DUY NHẤT cho mỗi lần ghi, cùng thư mục với file đích. Bản sao
    ``.bak`` chỉ được làm mới từ file chính ĐỌC ĐƯỢC — file chính đang hỏng thì giữ
    nguyên ``.bak`` cũ, không thay bản sao tốt bằng rác.
    """
    duong_dan = os.path.abspath(path)
    file_bak = duong_dan + ".bak"
    with khoa_json(duong_dan):
        _don_file_tam_mo_coi(duong_dan)
        file_tam = f"{duong_dan}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            if giu_ban_sao and os.path.isfile(duong_dan) and _json_doc_duoc(duong_dan):
                file_bak_tam = f"{file_bak}.{uuid.uuid4().hex[:8]}.tmp"
                try:
                    with open(duong_dan, "rb") as nguon, open(file_bak_tam, "wb") as dich:
                        dich.write(nguon.read())
                        dich.flush()
                        os.fsync(dich.fileno())
                    _thay_the(file_bak_tam, file_bak)
                finally:
                    with contextlib.suppress(OSError):
                        os.remove(file_bak_tam)

            with open(file_tam, "w", encoding="utf-8") as f:
                json.dump(du_lieu, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            _thay_the(file_tam, duong_dan)
        except BaseException:
            with contextlib.suppress(OSError):
                if os.path.exists(file_tam):
                    os.remove(file_tam)
            raise


def cap_nhat_json(
    path: str,
    ham_sua: Callable[[Any], Any],
    mac_dinh: Any = None,
    *,
    giu_ban_sao: bool = True,
    han_cho_s: float = HAN_CHO_KHOA_S,
) -> Any:
    """Giao dịch đọc-sửa-ghi: đọc bản MỚI NHẤT, sửa, ghi — dưới cùng một khoá.

    Chỉ làm file tạm duy nhất thì chưa chữa được MẤT CẬP NHẬT: hai process cùng đọc
    bản cũ, mỗi bên thêm một entry, bên ghi sau xoá mất entry của bên kia. Ở đây
    ``ham_sua`` nhận dữ liệu vừa đọc trong lúc giữ khoá và SỬA TẠI CHỖ. Giá trị trả
    về của ``ham_sua`` chỉ được chuyển lại cho người gọi, không bao giờ được ghi thay
    cho dữ liệu. ``ham_sua`` ném lỗi thì không ghi gì; không đổi gì thì cũng không ghi.

    ``mac_dinh`` dùng khi file chưa tồn tại (được sao chép sâu, không bị sửa).
    """
    duong_dan = os.path.abspath(path)
    with khoa_json(duong_dan, han_cho_s=han_cho_s):
        du_lieu = doc_json_an_toan(duong_dan, None)
        if du_lieu is None:
            du_lieu = json.loads(json.dumps({} if mac_dinh is None else mac_dinh))
            truoc = None
        else:
            truoc = json.dumps(du_lieu, sort_keys=True, ensure_ascii=False)
        ket_qua = ham_sua(du_lieu)
        if truoc is None or json.dumps(du_lieu, sort_keys=True, ensure_ascii=False) != truoc:
            ghi_json_an_toan(duong_dan, du_lieu, giu_ban_sao=giu_ban_sao)
        return ket_qua


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

    with khoa_json(duong_dan):
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
                    # Giữ lại bản hỏng để còn điều tra, rồi mới phục hồi từ bản sao.
                    with contextlib.suppress(OSError):
                        os.replace(duong_dan, _duong_dan_file_hong(duong_dan))
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
