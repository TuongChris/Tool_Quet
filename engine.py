# -*- coding: utf-8 -*-
r"""
engine.py — LÕI của hệ thống TimClip Pro.

Nhiệm vụ: tải audio từ YouTube, cắt khúc, so khớp vân tay âm thanh với kho clip gốc,
lưu lịch sử vào SQLite và trả về kết quả dưới dạng dữ liệu Python thuần.

NGUYÊN TẮC THIẾT KẾ QUAN TRỌNG:
    File này KHÔNG BIẾT nó đang được gọi từ đâu (Streamlit, CLI, FastAPI, hay desktop app).
    Nó không print ra màn hình, không đọc bàn phím. Mọi thông tin tiến độ được gửi ra ngoài
    qua hàm callback `progress(pct, msg)`. Nhờ vậy bạn có thể thay giao diện bất cứ lúc nào
    mà không phải sửa một dòng nào trong file này.

Cách dùng từ code khác:
    from engine import Engine, Config
    eng = Engine()
    eng.build_database(r"D:\ClipGoc", mode="new", progress=print_ra_dau_do)
    kq = eng.scan_youtube("https://youtu.be/xxxx")
    for m in kq.matches:
        print(m.clip, m.start_hhmmss, m.end_hhmmss, m.confidence)
"""

from __future__ import annotations

import contextlib
import csv
import glob
import io
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Optional

import channel
import cau_hinh
import dossier
from clip_metadata import (
    ClipMetadataResolver,
    MetadataAudit,
    MetadataRepairResult,
    basename_compatible,
    load_metadata_strict,
    source_from_mapping,
)
from fingerprint_progress import (
    dong_fingerprint_logger,
    FingerprintProgress,
    FingerprintProgressTracker,
    tao_fingerprint_logger,
    ten_file_an_toan,
)
from khoa import KhoaTienTrinh
from luu_tru import LoiDuLieu, doc_json_an_toan, ghi_json_an_toan
from process_runner import ProcessSnapshot, run_observed_process


LOGGER_METADATA = logging.getLogger("clip_metadata")

# Phase mà wrapper audfprint được phép áp cho một clip đang chạy. Danh sách hẹp để
# một dòng stdout bị hỏng không đẩy job sang trạng thái kết thúc giả.
PHASES_FINGERPRINT = frozenset({"decoding", "fingerprinting", "probing"})

# =====================================================================
#  Kiểu dữ liệu
# =====================================================================

# Các đuôi file được coi là media khi quét thư mục clip gốc
MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m4v",
              ".mpg", ".mpeg", ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"}


@dataclass
class Config:
    """Toàn bộ tham số điều chỉnh được của hệ thống."""
    chunk_s: int = 3600        # Độ dài mỗi khúc audio khi cắt video dài (giây)
    overlap_s: int = 600       # Khúc gối đề xuất khi không có metadata thời lượng
    overlap_max_s: int = 180   # Trần khúc gối; giảm quét lặp, mặc định 3 phút
    overlap_tu_dong: bool = True  # Tự tính overlap theo clip dài nhất trong kho
    min_hash: int = 15         # Số hash khớp tối thiểu để tính là kết quả
    min_match_s: float = 5.0   # Đoạn khớp phải dài tối thiểu bao nhiêu giây
    max_matches: int = 200     # Số kết quả tối đa audfprint trả về mỗi khúc
    ncores: int = 0            # 0 = tự dò theo số nhân CPU
    dedup_s: float = 20.0      # Ngưỡng gộp 2 kết quả trùng nhau (do các khúc gối nhau)
    # Shifts cao hơn tăng độ chính xác nhưng chạy chậm và làm kho lớn hơn; 0 = hành vi cũ.
    shifts_kho: int = 4        # Subframe shifts khi tạo kho vân tay
    shifts_quet: int = 4       # Subframe shifts khi quét video dài
    ytdlp_format: str = "ba/b"  # Định dạng yt-dlp: chỉ lấy audio tốt nhất cho nhẹ
    network_timeout_s: int = 30  # Timeout socket cho request/tải YouTube
    keep_downloads: bool = True  # Giữ lại audio đã tải để lần sau khỏi tải lại
    ghi_tung_phan: bool = True   # Ghi Sheets ngay sau mỗi video giám sát
    dem_max_gb: float = 20.0    # Ngân sách kho đệm; đặt 0 để tắt giới hạn dung lượng
    dem_max_ngay: int = 7       # Tuổi tối đa của file đệm; đặt 0 để tắt giới hạn tuổi

    # --- Chọn lọc kết quả cuối cùng ---
    top_n: int = 5               # Chỉ giữ lại bao nhiêu kết quả tốt nhất
    min_hash_floor: int = 1000   # Dưới ngưỡng này: LOẠI HẲN, không đưa vào báo cáo
    min_hash_strong: int = 5000  # Từ ngưỡng này: coi là bằng chứng mạnh, ưu tiên chọn
    phan_bo_deu: bool = True     # Chia video vi phạm thành N vùng, mỗi vùng lấy 1 kết quả
    uu_tien_clip_khac_nhau: bool = True  # Ưu tiên 5 clip GỐC KHÁC NHAU thay vì trùng lặp

    def validate(self, overlap_s: Optional[int] = None) -> None:
        if self.chunk_s <= 60:
            raise ValueError("chunk_s phải lớn hơn 60 giây.")
        if self.overlap_max_s < 60:
            raise ValueError("overlap_max_s phải >= 60 giây.")
        if self.overlap_max_s >= self.chunk_s:
            raise ValueError("overlap_max_s phải nhỏ hơn chunk_s.")
        de_xuat = self.overlap_s if overlap_s is None else overlap_s
        overlap = min(self.overlap_max_s, de_xuat)
        if self.chunk_s <= overlap:
            raise ValueError("chunk_s phải lớn hơn overlap_s.")
        if overlap < 60:
            raise ValueError("overlap_s nên >= 60 giây để không bỏ sót clip nằm vắt qua ranh giới.")
        if self.min_hash < 1:
            raise ValueError("min_hash phải >= 1.")
        if self.min_match_s < 0:
            raise ValueError("min_match_s không được âm.")
        if self.max_matches < 1:
            raise ValueError("max_matches phải >= 1.")
        if not 0 <= self.ncores <= 64:
            raise ValueError("ncores phải nằm trong khoảng 0..64.")
        if not 5 <= self.network_timeout_s <= 300:
            raise ValueError("network_timeout_s phải nằm trong khoảng 5..300 giây.")
        if self.dedup_s < 0:
            raise ValueError("dedup_s không được âm.")
        if not 0 <= self.shifts_kho <= 8 or not 0 <= self.shifts_quet <= 8:
            raise ValueError("shifts_kho và shifts_quet phải nằm trong khoảng 0..8.")
        if self.top_n < 1:
            raise ValueError("top_n phải >= 1.")
        if self.min_hash_floor < 0 or self.min_hash_strong < 0:
            raise ValueError("Ngưỡng hash chọn lọc không được âm.")
        if self.dem_max_gb < 0 or self.dem_max_ngay < 0:
            raise ValueError("Giới hạn kho đệm không được âm.")


@dataclass
class Match:
    """Một lần clip gốc xuất hiện trong video dài."""
    clip: str              # tên file clip gốc
    start_s: float         # thời điểm clip bắt đầu trong video dài
    end_s: float           # đến giây thứ mấy
    matched_s: float       # độ dài đoạn khớp đã xác nhận
    clip_offset_s: float   # khớp bắt đầu từ giây thứ mấy CỦA CLIP GỐC
    hashes: int            # số hash khớp — bằng chứng, càng cao càng chắc
    confidence: str        # đánh giá dạng chữ
    ty_le: float = 0.0     # % vân tay của clip gốc khớp được (chỉ số CHUẨN HOÁ)
    vung: str = ""         # Đầu / Giữa / Cuối video vi phạm
    clip_bat_dau_s: float = 0.0  # thời điểm CLIP bắt đầu trong video dài
    vung_khop_s: float = 0.0     # thời điểm VÙNG KHỚP bắt đầu

    @property
    def start_hhmmss(self) -> str:
        return hhmmss(self.start_s)

    @property
    def clip_bat_dau_hhmmss(self) -> str:
        return hhmmss(self.clip_bat_dau_s)

    @property
    def end_hhmmss(self) -> str:
        return hhmmss(self.end_s)


@dataclass
class ScanResult:
    """Kết quả quét một nguồn (1 link YouTube hoặc 1 file)."""
    source_name: str
    source_ref: str = ""
    source_id: str = ""      # ID video YouTube (để tạo link nhảy tới đúng mốc)
    duration_s: float = 0.0
    matches: list = field(default_factory=list)        # kết quả ĐÃ CHỌN (top N)
    matches_loai: list = field(default_factory=list)   # bị loại vì dưới ngưỡng
    status: str = "ok"      # ok | error
    note: str = ""
    job_id: Optional[int] = None
    channel_name: str = ""
    channel_id: str = ""
    channel_url: str = ""
    upload_date: str = ""
    so_dat_nguong: int = 0


class Cancelled(Exception):
    """Ném ra khi người dùng bấm Dừng."""


# =====================================================================
#  Hàm tiện ích dùng chung
# =====================================================================

def hhmmss(giay: float) -> str:
    giay = max(0, int(round(giay)))
    return f"{giay // 3600:02d}:{(giay % 3600) // 60:02d}:{giay % 60:02d}"


def o_bang_tinh_an_toan(gia_tri):
    """Ép chuỗi có thể bị spreadsheet hiểu là công thức thành dữ liệu thuần."""
    if not isinstance(gia_tri, str):
        return gia_tri
    noi_dung = gia_tri.lstrip(" \t\r\n")
    if noi_dung.startswith(("=", "+", "-", "@")):
        return "'" + gia_tri
    return gia_tri


def _mo_file_text_moi(path: str, **kwargs):
    """Mở file text bằng mode độc quyền và thêm hậu tố nếu tên đã tồn tại."""
    goc, duoi = os.path.splitext(path)
    thu_tu = 1
    while True:
        ung_vien = path if thu_tu == 1 else f"{goc}_{thu_tu}{duoi}"
        try:
            return open(ung_vien, "x", **kwargs), ung_vien
        except FileExistsError:
            thu_tu += 1


def so_nhan_nen_dung() -> int:
    """Tự chọn số nhân CPU cho tác vụ nền, luôn chừa ít nhất một nhân cho hệ thống."""
    so_nhan = os.cpu_count() or 1
    return max(1, min(8, so_nhan - 1))


def danh_gia(so_hash: int) -> str:
    if so_hash >= 100:
        return "Rất chắc chắn"
    if so_hash >= 40:
        return "Chắc chắn"
    return "Nên kiểm tra lại"


def liet_ke_media(thumuc: str) -> list:
    """Liệt kê mọi file media trong thư mục (kể cả thư mục con)."""
    ds = []
    for goc, _, files in os.walk(thumuc):
        for f in files:
            if os.path.splitext(f)[1].lower() in MEDIA_EXTS:
                ds.append(os.path.join(goc, f))
    return sorted(ds)


# Dòng kết quả của audfprint:
# Matched  54.5 s starting at 402.7 s in <khúc> to time 2.7 s in <clip gốc> with 321 of 605 common hashes at rank 0
RE_MATCH = re.compile(
    r"Matched\s+([\d.]+)\s+s\s+starting\s+at\s+([\d.]+)\s+s\s+in\s+(.+?)"
    r"\s+to\s+time\s+([\d.]+)\s+s\s+in\s+(.+?)\s+with\s+(\d+)\s+of\s+(\d+)\s+common\s+hashes"
)


# =====================================================================
#  Engine
# =====================================================================

class Engine:
    """Lõi xử lý. Không phụ thuộc vào bất kỳ giao diện nào."""

    def __init__(self, root: Optional[str] = None, config: Optional[Config] = None,
                 data_dir: Optional[str] = None, out_dir: Optional[str] = None):
        self.root = os.path.abspath(root or os.path.dirname(os.path.abspath(__file__)))
        self.config = config or Config()
        self.canh_bao_khoi_dong: list = []
        self.canh_bao_gop: list = []
        self.cau_hinh_da_luu: dict = {}

        self.bin_dir = os.path.join(self.root, "bin")
        self.data_dir = os.path.abspath(data_dir or os.path.join(self.root, "data"))
        self.db_file = os.path.join(self.data_dir, "db.pklz")  # sẽ được _init_kho ghi đè
        self.kho_dang_dung = ""
        self.kho_thu_muc = ""
        self.dl_dir = os.path.join(self.data_dir, "downloads")
        self.chunk_dir = os.path.join(self.data_dir, "chunks")
        self.out_dir = os.path.abspath(out_dir or os.path.join(self.root, "ketqua"))
        self.sqlite_file = os.path.join(self.data_dir, "lichsu.db")

        for d in (self.data_dir, self.dl_dir, self.out_dir):
            os.makedirs(d, exist_ok=True)

        # Cho phép đặt ffmpeg/ffprobe trong bin\ mà không cần sửa PATH hệ thống
        if self.bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = self.bin_dir + os.pathsep + os.environ.get("PATH", "")

        self.kho_file = os.path.join(self.data_dir, "khos.json")
        self.audfprint = self._tim_audfprint()
        self.cancel_event = threading.Event()
        self._cache_khoa = None
        self._cache_clips = []
        self._metadata_cache_key = None
        self._metadata_resolver_cache: Optional[ClipMetadataResolver] = None
        self.canh_bao_metadata: list[str] = []
        self._nap_cau_hinh()
        self._init_sqlite()
        self._init_kho()

    def _nap_cau_hinh(self) -> None:
        """Nạp cấu hình bền vững; mọi lỗi đều được hạ thành cảnh báo khởi động."""
        try:
            du_lieu = cau_hinh.doc_cau_hinh(self.data_dir)
            self.cau_hinh_da_luu = du_lieu
            bi_bo_qua = cau_hinh.ap_vao_config(self.config, du_lieu)
            bi_bo_qua = [
                khoa for khoa in bi_bo_qua
                if khoa not in cau_hinh.GIA_TRI_GIAO_DIEN_MAC_DINH
            ]
            if bi_bo_qua:
                self.canh_bao_khoi_dong.append(
                    "Đã bỏ qua khóa cấu hình lạ hoặc sai kiểu: "
                    + ", ".join(sorted(bi_bo_qua))
                )
            if du_lieu:
                self.config.validate()
        except Exception as e:  # noqa: BLE001
            self.config = Config()
            self.cau_hinh_da_luu = {}
            self.canh_bao_khoi_dong.append(
                f"Không nạp được cấu hình người dùng; đang dùng mặc định: {e}"
            )

    def luu_cau_hinh(self, them: dict | None = None) -> None:
        """Lưu Config và các tùy chọn giao diện không bí mật được cho phép."""
        self.config.validate()
        du_lieu = cau_hinh.lay_tu_config(self.config)
        for khoa, mac_dinh in cau_hinh.GIA_TRI_GIAO_DIEN_MAC_DINH.items():
            if them and khoa in them and type(them[khoa]) is type(mac_dinh):
                du_lieu[khoa] = them[khoa]
        cau_hinh.ghi_cau_hinh(self.data_dir, du_lieu)
        self.cau_hinh_da_luu = dict(du_lieu)

    def khoi_phuc_cau_hinh_mac_dinh(self) -> None:
        """Xóa cấu hình đã lưu và áp Config mặc định ngay trong phiên hiện tại."""
        duong_dan = os.path.join(self.data_dir, cau_hinh.TEN_FILE)
        for hau_to in ("", ".bak", ".tmp"):
            with contextlib.suppress(FileNotFoundError):
                os.remove(duong_dan + hau_to)
        self.config = Config()
        self.cau_hinh_da_luu = {}

    # =================================================================
    #  QUẢN LÝ NHIỀU KHO CLIP GỐC
    #  Mỗi kho = 1 tên + 1 thư mục + 1 file vân tay riêng.
    #  Ví dụ: kho "Ẩm thực", kho "Du lịch", kho "Review" — quét video vi phạm
    #  nào thì chọn đúng kho tương ứng, vừa nhanh vừa ít báo nhầm.
    # =================================================================

    @staticmethod
    def _slug(ten: str) -> str:
        import hashlib
        sach = re.sub(r"[^a-zA-Z0-9]+", "_", ten).strip("_").lower()[:30]
        return (sach or "kho") + "_" + hashlib.md5(ten.encode("utf-8")).hexdigest()[:6]

    def _doc_khos(self) -> dict:
        return doc_json_an_toan(
            self.kho_file,
            {"dang_dung": "", "danh_sach": []},
        )

    def _ghi_khos(self, d: dict) -> None:
        ghi_json_an_toan(self.kho_file, d)

    def _duong_dan_db_kho(self, ten_file: str) -> str:
        """Chỉ chấp nhận basename `.pklz` nằm trực tiếp trong data_dir."""
        if not isinstance(ten_file, str) or not ten_file:
            raise LoiDuLieu("Tên file vân tay trong khos.json không hợp lệ.")
        if (
            os.path.isabs(ten_file)
            or os.path.basename(ten_file) != ten_file
            or not ten_file.lower().endswith(".pklz")
        ):
            raise LoiDuLieu(
                "Tên file vân tay trong khos.json phải là một file .pklz "
                "nằm trực tiếp trong thư mục data."
            )
        duong_dan = os.path.abspath(os.path.join(self.data_dir, ten_file))
        try:
            nam_trong_data = os.path.commonpath(
                [self.data_dir, duong_dan]
            ) == os.path.commonpath([self.data_dir])
        except ValueError:
            nam_trong_data = False
        if not nam_trong_data:
            raise LoiDuLieu("Đường dẫn file vân tay thoát khỏi thư mục data.")
        return duong_dan

    def _init_kho(self) -> None:
        """Nạp kho đang dùng. Tự chuyển đổi dữ liệu từ phiên bản cũ (1 kho duy nhất)."""
        try:
            d = self._doc_khos()
        except LoiDuLieu as e:
            self.canh_bao_khoi_dong.append(str(e))
            self._ap_dung_kho(
                "",
                {"dang_dung": "", "danh_sach": []},
            )
            return
        # Nâng cấp: đã có db.pklz kiểu cũ mà chưa khai báo kho nào
        if not d["danh_sach"] and os.path.exists(os.path.join(self.data_dir, "db.pklz")):
            d = {"dang_dung": "Kho mặc định",
                 "danh_sach": [{"ten": "Kho mặc định", "thu_muc": "", "db": "db.pklz"}]}
            self._ghi_khos(d)
        try:
            self._ap_dung_kho(d.get("dang_dung", ""), d)
        except LoiDuLieu as e:
            self.canh_bao_khoi_dong.append(str(e))
            self._ap_dung_kho("", {"dang_dung": "", "danh_sach": []})

    def _ap_dung_kho(self, ten: str, d: Optional[dict] = None) -> None:
        d = d or self._doc_khos()
        kho = next((k for k in d["danh_sach"] if k["ten"] == ten), None)
        if kho is None and d["danh_sach"]:
            kho = d["danh_sach"][0]
        self.db_file = self._duong_dan_db_kho(kho["db"]) if kho else \
            os.path.join(self.data_dir, "db.pklz")
        self.kho_dang_dung = kho["ten"] if kho else ""
        self.kho_thu_muc = kho.get("thu_muc", "") if kho else ""
        self._cache_khoa = None   # đổi kho -> đọc lại danh sách clip
        self._invalidate_metadata_cache()

    def _invalidate_metadata_cache(self) -> None:
        """Buộc dựng lại metadata index ở lần đọc kế tiếp."""
        self._metadata_cache_key = None
        self._metadata_resolver_cache = None
        self.canh_bao_metadata = []

    def list_khos(self) -> list:
        """Danh sách các kho + trạng thái (đã có vân tay chưa, bao nhiêu clip)."""
        d = self._doc_khos()
        ds = []
        for k in d["danh_sach"]:
            db = self._duong_dan_db_kho(k["db"])
            ds.append({**k, "duong_dan_db": db, "co_van_tay": os.path.exists(db),
                       "dang_dung": k["ten"] == self.kho_dang_dung})
        return ds

    def add_kho(self, ten: str, thu_muc: str = "") -> dict:
        ten = (ten or "").strip()
        if not ten:
            raise RuntimeError("Tên kho không được để trống.")
        d = self._doc_khos()
        if any(k["ten"] == ten for k in d["danh_sach"]):
            raise RuntimeError(f"Đã có kho tên «{ten}» rồi.")
        kho = {"ten": ten, "thu_muc": thu_muc.strip('" '),
               "db": f"kho_{self._slug(ten)}.pklz"}
        d["danh_sach"].append(kho)
        d["dang_dung"] = ten
        self._ghi_khos(d)
        self._ap_dung_kho(ten, d)
        return kho

    def use_kho(self, ten: str) -> None:
        d = self._doc_khos()
        if not any(k["ten"] == ten for k in d["danh_sach"]):
            raise RuntimeError(f"Không có kho tên «{ten}».")
        d["dang_dung"] = ten
        self._ghi_khos(d)
        self._ap_dung_kho(ten, d)

    def update_kho(self, ten: str, thu_muc: str) -> None:
        d = self._doc_khos()
        for k in d["danh_sach"]:
            if k["ten"] == ten:
                k["thu_muc"] = thu_muc.strip('" ')
        self._ghi_khos(d)
        self._ap_dung_kho(d.get("dang_dung", ""), d)

    def delete_kho(self, ten: str, xoa_van_tay: bool = True) -> None:
        """Xoá kho khỏi danh sách. KHÔNG bao giờ đụng vào file video/audio gốc."""
        d = self._doc_khos()
        kho = next((k for k in d["danh_sach"] if k["ten"] == ten), None)
        if not kho:
            return
        if xoa_van_tay:
            self._cache_khoa = None
            self._xoa_an_toan(self._duong_dan_db_kho(kho["db"]))
        d["danh_sach"] = [k for k in d["danh_sach"] if k["ten"] != ten]
        if d.get("dang_dung") == ten:
            d["dang_dung"] = d["danh_sach"][0]["ten"] if d["danh_sach"] else ""
        self._ghi_khos(d)
        self._ap_dung_kho(d.get("dang_dung", ""), d)

    # ---------- hạ tầng ----------

    def _tim_audfprint(self) -> Optional[str]:
        for ten in ("audfprint-master", "audfprint"):
            p = os.path.join(self.root, ten, "audfprint.py")
            if os.path.isfile(p):
                return p
        return None

    def _init_sqlite(self) -> None:
        with self._db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS jobs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT, source_type TEXT, source_name TEXT, source_ref TEXT,
                duration_s REAL, status TEXT, n_matches INTEGER, note TEXT,
                source_id TEXT DEFAULT '')""")
            # Nâng cấp DB tạo bởi phiên bản cũ
            with contextlib.suppress(sqlite3.OperationalError):
                c.execute("ALTER TABLE jobs ADD COLUMN source_id TEXT DEFAULT ''")
            c.execute("""CREATE TABLE IF NOT EXISTS matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER,
                clip TEXT, start_s REAL, end_s REAL, matched_s REAL,
                clip_offset_s REAL, hashes INTEGER, confidence TEXT)""")
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_source_id "
                "ON jobs(source_id)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_matches_job_id "
                "ON matches(job_id)"
            )

    @contextlib.contextmanager
    def _db(self):
        con = sqlite3.connect(self.sqlite_file)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _bao(progress: Optional[Callable], pct: float, msg: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, pct)), msg)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def _run_stream(
        self,
        lenh: list,
        on_line: Optional[Callable] = None,
        *,
        on_heartbeat: Optional[Callable[[ProcessSnapshot], None]] = None,
        logger=None,
        process_name: str = "audfprint",
        include_in_tail: Optional[Callable[[str], bool]] = None,
        heartbeat_seconds: float = 10.0,
    ) -> tuple:
        """
        Chạy lệnh con, đọc stdout từng dòng (để báo tiến độ), hỗ trợ hủy giữa chừng.
        Trả về (return_code, 30 dòng cuối) — dòng cuối dùng để báo lỗi cho ra hồn.

        QUAN TRỌNG — vì sao phải ép UTF-8:
        Windows tiếng Việt dùng bảng mã cp1258/cp1252. audfprint mở file danh sách bằng
        open() không chỉ định encoding, nên khi đường dẫn có dấu tiếng Việt nó sẽ chết
        ngay với UnicodeDecodeError → không in ra dòng nào → tiến độ đứng ở 0%.
        Đặt PYTHONUTF8=1 buộc tiến trình con dùng UTF-8, sửa triệt để mà KHÔNG phải
        sửa thư viện bên thứ ba.
        """
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"          # ép open() mặc định UTF-8
        env["PYTHONIOENCODING"] = "utf-8"  # in tên file tiếng Việt không lỗi
        env["PYTHONUNBUFFERED"] = "1"     # đẩy tiến độ ra ngay, không đệm

        result = run_observed_process(
            lenh,
            on_line=on_line,
            on_heartbeat=on_heartbeat,
            cancel_event=self.cancel_event,
            logger=logger,
            process_name=process_name,
            heartbeat_seconds=heartbeat_seconds,
            slow_warning_seconds=120.0,
            include_in_tail=include_in_tail,
            env=env,
        )
        if result.cancelled:
            raise Cancelled()
        return result.returncode, list(result.tail)

    # ---------- kiểm tra môi trường ----------

    def check_env(self) -> dict:
        """Trả về tình trạng từng thành phần — giao diện dùng để hiển thị đèn xanh/đỏ."""
        try:
            import yt_dlp  # noqa: F401
            co_ytdlp, ver_ytdlp = True, yt_dlp.version.__version__
        except Exception:
            co_ytdlp, ver_ytdlp = False, ""
        return {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "yt_dlp": co_ytdlp,
            "yt_dlp_version": ver_ytdlp,
            "audfprint": self.audfprint is not None,
            "database": os.path.exists(self.db_file),
        }

    def require(self, can_ytdlp: bool = False, can_db: bool = False) -> None:
        env = self.check_env()
        thieu = []
        if not env["ffmpeg"]:
            thieu.append("ffmpeg.exe (đặt vào thư mục bin\\ hoặc cài vào PATH)")
        if not env["ffprobe"]:
            thieu.append("ffprobe.exe (đặt vào thư mục bin\\ hoặc cài vào PATH)")
        if not env["audfprint"]:
            thieu.append("thư mục audfprint-master\\")
        if can_ytdlp and not env["yt_dlp"]:
            thieu.append("thư viện yt-dlp (chạy: pip install -U yt-dlp)")
        if can_db and not env["database"]:
            thieu.append("kho vân tay clip gốc (hãy tạo ở tab \"Kho clip gốc\")")
        if thieu:
            raise RuntimeError("Còn thiếu: " + "; ".join(thieu))

    # ---------- thông tin media ----------

    @staticmethod
    def duration_of(path: str) -> Optional[float]:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            return float(r.stdout.strip().splitlines()[-1])
        except Exception:
            return None

    # =================================================================
    #  1) KHO VÂN TAY CLIP GỐC
    # =================================================================

    def db_clips(self, bo_cache: bool = False) -> list:
        """
        Đọc danh sách clip trong kho vân tay.

        QUAN TRỌNG — vì sao KHÔNG dùng hash_table.HashTable(path):
        Hàm load_pkl() của thư viện gọi gzip.open() mà KHÔNG đóng file.
        Trên Windows, một handle còn mở là đủ để chặn os.remove() → WinError 32
        "The process cannot access the file because it is being used by another
        process". Ở đây ta tự đọc toàn bộ file vào RAM trong khối `with`
        (đảm bảo đóng 100%) rồi mới giải nén — không bao giờ giữ handle.

        Kèm cache theo (đường dẫn, mtime, kích thước): Streamlit vẽ lại màn hình
        liên tục, mỗi lần đọc lại file vân tay hàng trăm MB sẽ rất chậm.
        """
        if not os.path.exists(self.db_file) or not self.audfprint:
            return []
        try:
            st_ = os.stat(self.db_file)
            khoa = (self.db_file, st_.st_mtime_ns, st_.st_size)
        except OSError:
            return []
        if not bo_cache and getattr(self, "_cache_khoa", None) == khoa:
            return self._cache_clips

        thu_muc_af = os.path.dirname(self.audfprint)
        if thu_muc_af not in sys.path:
            sys.path.insert(0, thu_muc_af)
        ds = []
        try:
            import gzip
            import pickle
            # Đọc trọn vào RAM rồi ĐÓNG NGAY — chốt chặn WinError 32
            with gzip.open(self.db_file, "rb") as f:
                raw = f.read()
            with contextlib.redirect_stdout(io.StringIO()):
                ht = pickle.loads(raw, encoding="latin1")
            del raw
            for i, ten in enumerate(getattr(ht, "names", []) or []):
                if not ten:
                    continue
                hpid = getattr(ht, "hashesperid", [])
                so_hash = hpid[i] if i < len(hpid) else 0
                ds.append({"ten": os.path.basename(ten), "duong_dan": ten,
                           "so_hash": int(so_hash)})
            del ht
        except Exception:
            ds = []
        self._cache_khoa, self._cache_clips = khoa, ds
        return ds

    # ---------- xử lý file bị khoá trên Windows ----------

    @staticmethod
    def _xoa_an_toan(path: str, so_lan: int = 6) -> bool:
        """
        Xoá file, chịu được việc Windows/phần mềm diệt virus tạm khoá file.
        Trả về True nếu xoá được. KHÔNG ném lỗi.
        """
        import gc
        if not os.path.exists(path):
            return True
        gc.collect()   # ép Python đóng mọi handle còn sót
        for i in range(so_lan):
            try:
                os.remove(path)
                return True
            except PermissionError:
                time.sleep(0.4 * (i + 1))   # chờ tăng dần: 0.4s, 0.8s, 1.2s...
                gc.collect()
            except OSError:
                return False
        return not os.path.exists(path)

    def _metadata_snapshot_path(self) -> str:
        """Đường dẫn snapshot riêng, ổn định và không thể thoát khỏi data_dir."""
        dinh_danh = self.kho_dang_dung or os.path.splitext(
            os.path.basename(self.db_file)
        )[0]
        ten_file = f"kho_{self._slug(dinh_danh or 'mac_dinh')}.json"
        thu_muc = os.path.abspath(os.path.join(self.data_dir, "metadata"))
        duong_dan = os.path.abspath(os.path.join(thu_muc, ten_file))
        try:
            hop_le = os.path.commonpath([thu_muc, duong_dan]) == thu_muc
        except ValueError:
            hop_le = False
        if not hop_le:
            raise LoiDuLieu("Đường dẫn snapshot metadata thoát khỏi thư mục data.")
        return duong_dan

    @staticmethod
    def _metadata_file_signature(path: str) -> tuple:
        try:
            stat = os.stat(path)
        except OSError:
            return os.path.normcase(os.path.abspath(path)), False, 0, 0
        return (
            os.path.normcase(os.path.abspath(path)),
            True,
            stat.st_mtime_ns,
            stat.st_size,
        )

    def _metadata_source_candidates(self, clips: list[dict]) -> list[tuple[str, str, int]]:
        """Nguồn chỉ thuộc kho active, theo thứ tự xác định; không dùng set last-wins."""
        candidates: list[tuple[str, str, int]] = []
        seen: set[str] = set()

        def add(path: str, kind: str, priority: int) -> None:
            absolute = os.path.abspath(path)
            key = os.path.normcase(absolute)
            if key not in seen:
                seen.add(key)
                candidates.append((absolute, kind, priority))

        if self.kho_dang_dung:
            add(self._metadata_snapshot_path(), "snapshot", 0)
        if self.kho_thu_muc:
            add(os.path.join(self.kho_thu_muc, "clips_meta.json"), "live", 10)

        # Legacy fallback: chỉ các directory thực sự được tham chiếu bởi DB active.
        thu_muc_db = sorted({
            os.path.abspath(os.path.dirname(str(clip.get("duong_dan") or "")))
            for clip in clips
            if os.path.dirname(str(clip.get("duong_dan") or ""))
        }, key=os.path.normcase)
        for index, folder in enumerate(thu_muc_db, start=20):
            add(os.path.join(folder, "clips_meta.json"), "legacy_db_folder", index)

        # Chỉ kho mặc định kiểu cũ mới được phép đọc metadata ở data_dir. Không
        # áp dụng vô điều kiện vì sẽ trộn metadata giữa nhiều kho.
        if self.kho_dang_dung in {"", "Kho mặc định"}:
            add(os.path.join(self.data_dir, "clips_meta.json"), "legacy_data", 100)
        return candidates

    def _metadata_cache_signature(
        self,
        candidates: list[tuple[str, str, int]],
    ) -> tuple:
        db_signature = self._metadata_file_signature(self.db_file)
        source_signatures = tuple(
            (
                kind,
                priority,
                self._metadata_file_signature(path),
                self._metadata_file_signature(path + ".bak"),
            )
            for path, kind, priority in candidates
        )
        return (
            self.kho_dang_dung,
            os.path.normcase(os.path.abspath(self.kho_thu_muc))
            if self.kho_thu_muc else "",
            db_signature,
            source_signatures,
        )

    def clip_metadata_resolver(self, bo_cache: bool = False) -> ClipMetadataResolver:
        """Dựng/cached index exact, canonical và YouTube-ID của đúng kho active."""
        clips = self.db_clips()
        candidates = self._metadata_source_candidates(clips)
        cache_key = self._metadata_cache_signature(candidates)
        if (
            not bo_cache
            and self._metadata_cache_key == cache_key
            and self._metadata_resolver_cache is not None
        ):
            return self._metadata_resolver_cache

        sources = []
        for path, kind, priority in candidates:
            expected = self.kho_dang_dung if kind == "snapshot" else ""
            source = load_metadata_strict(
                path,
                kind=kind,
                priority=priority,
                expected_warehouse=expected,
            )
            sources.append(source)
            # Backup chỉ là fallback đọc; tuyệt đối không phục hồi/rename file chính.
            bi_loi = bool(source.warnings) and not source.entries
            if (bi_loi or not source.exists) and os.path.isfile(path + ".bak"):
                backup = load_metadata_strict(
                    path + ".bak",
                    kind=kind + "_backup",
                    priority=priority + 1,
                    expected_warehouse=expected,
                )
                if backup.entries:
                    sources.append(backup)

        resolver = ClipMetadataResolver(sources, windows_semantics=os.name == "nt")
        audit = resolver.audit(
            clips,
            warehouse=self.kho_dang_dung,
            database_file=self.db_file,
            warehouse_folder=self.kho_thu_muc,
            sample_limit=0,
        )
        warnings = []
        for source in sources:
            for warning in source.warnings:
                warnings.append(
                    f"{os.path.basename(source.path) or source.kind}: {warning}"
                )
        if resolver.conflicts:
            warnings.append(
                f"Phát hiện {len(set(resolver.conflicts))} xung đột metadata; "
                "các ánh xạ mơ hồ không được tự động chọn."
            )
        if audit.total_db_clips and audit.complete < audit.total_db_clips:
            warnings.append(
                f"Metadata kho chưa đầy đủ: {audit.complete}/{audit.total_db_clips} "
                "clip có đủ ID, title, URL, ngày đăng và thời lượng."
            )
        self.canh_bao_metadata = list(dict.fromkeys(warnings))
        self._metadata_cache_key = cache_key
        self._metadata_resolver_cache = resolver

        LOGGER_METADATA.info(
            "event=metadata.index warehouse=%r db_clips=%d metadata_entries=%d "
            "complete=%d partial=%d fallback=%d unresolved=%d ambiguous=%d",
            self.kho_dang_dung,
            audit.total_db_clips,
            audit.metadata_entries,
            audit.complete,
            audit.partial,
            audit.filename_fallbacks,
            audit.missing,
            audit.ambiguous,
        )
        if self.canh_bao_metadata:
            LOGGER_METADATA.warning(
                "event=metadata.coverage warehouse=%r warnings=%d complete=%d total=%d",
                self.kho_dang_dung,
                len(self.canh_bao_metadata),
                audit.complete,
                audit.total_db_clips,
            )
        return resolver

    def clip_meta(self) -> dict:
        """Compatibility mapping đã validate; call site báo cáo dùng resolver trực tiếp."""
        return self.clip_metadata_resolver().compatibility_mapping()

    def resolve_metadata_for_matches(self, matches: Iterable) -> tuple:
        """Resolve một batch đúng thứ tự và giữ duplicate đoạn ↔ clip."""
        resolver = self.clip_metadata_resolver()
        return tuple(resolver.resolve(str(match.clip)) for match in matches)

    def metadata_coverage(self, matches: Iterable):
        names = [
            str(item.clip) if hasattr(item, "clip") else str(item)
            for item in matches
        ]
        return self.clip_metadata_resolver().coverage(names)

    def kiem_tra_metadata_kho(self, sample_limit: int = 20) -> MetadataAudit:
        """Audit chỉ đọc; không sửa clips_meta, snapshot hay database fingerprint."""
        resolver = self.clip_metadata_resolver(bo_cache=True)
        audit = resolver.audit(
            self.db_clips(),
            warehouse=self.kho_dang_dung,
            database_file=self.db_file,
            warehouse_folder=self.kho_thu_muc,
            sample_limit=max(0, min(int(sample_limit), 20)),
        )
        LOGGER_METADATA.info(
            "event=metadata.audit warehouse=%r db_clips=%d metadata_entries=%d "
            "exact=%d normalized=%d id=%d fallback=%d missing=%d ambiguous=%d",
            self.kho_dang_dung,
            audit.total_db_clips,
            audit.metadata_entries,
            audit.exact_matches + audit.exact_basename_matches,
            audit.normalized_matches,
            audit.id_matches,
            audit.filename_fallbacks,
            audit.missing,
            audit.ambiguous,
        )
        return audit

    @staticmethod
    def _snapshot_entry(item) -> dict:
        entry = item.public_dict()
        entry["resolution_method"] = item.resolution_method
        return entry

    def _khoi_phuc_metadata_offline_da_khoa(
        self,
        *,
        dry_run: bool,
        preserve_existing: bool = True,
    ) -> MetadataRepairResult:
        clips = self.db_clips(bo_cache=True)
        resolver = self.clip_metadata_resolver(bo_cache=True)
        audit = resolver.audit(
            clips,
            warehouse=self.kho_dang_dung,
            database_file=self.db_file,
            warehouse_folder=self.kho_thu_muc,
            sample_limit=20,
        )
        snapshot_path = self._metadata_snapshot_path()
        existing_source = load_metadata_strict(
            snapshot_path,
            kind="snapshot",
            priority=0,
            expected_warehouse=self.kho_dang_dung,
        )
        backup_source = None
        if not existing_source.exists and os.path.isfile(snapshot_path + ".bak"):
            backup_source = load_metadata_strict(
                snapshot_path + ".bak",
                kind="snapshot_backup",
                priority=1,
                expected_warehouse=self.kho_dang_dung,
            )
        seed_source = backup_source if backup_source and backup_source.entries else existing_source
        existing = {
            entry.key: {
                **entry.public_dict(),
                "resolution_method": entry.origin_method or "exact",
            }
            for entry in seed_source.entries
        }
        output = dict(existing) if preserve_existing else {}
        updated = unchanged = skipped_ambiguous = unresolved = 0
        errors: list[str] = []

        if not os.path.isfile(self.db_file):
            errors.append("Database fingerprint của kho không tồn tại; không ghi snapshot.")
        elif not clips:
            errors.append(
                "Database tồn tại nhưng API không đọc được clip; không ghi snapshot rỗng."
            )
        if existing_source.exists and existing_source.warnings and not existing_source.entries:
            errors.append(
                "Snapshot chính hiện có nhưng không hợp lệ; từ chối ghi để không phá "
                "bản chính hoặc .bak. Hãy kiểm tra/chuyển file lỗi thủ công trước."
            )

        for clip in clips:
            name = str(clip.get("ten") or basename_compatible(clip.get("duong_dan")))
            path = str(clip.get("duong_dan") or "")
            item = resolver.resolve(name, path)
            if item.status == "ambiguous":
                skipped_ambiguous += 1
                continue
            if item.status == "unresolved":
                unresolved += 1
                continue
            candidate = self._snapshot_entry(item)
            if output.get(name) == candidate:
                unchanged += 1
            else:
                output[name] = candidate
                updated += 1

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = {
            "schema_version": 1,
            "warehouse": self.kho_dang_dung,
            "warehouse_id": self._slug(self.kho_dang_dung or "mac_dinh"),
            "database": os.path.basename(self.db_file),
            "updated_at": now,
            "sources": [
                {"kind": source.kind, "file": os.path.basename(source.path)}
                for source in resolver.sources
                if source.entries and not source.kind.startswith("snapshot")
            ],
            "stats": {
                "database_clips": len(clips),
                "complete": audit.complete,
                "partial": audit.partial,
                "filename_fallbacks": audit.filename_fallbacks,
                "unresolved": unresolved,
                "ambiguous": skipped_ambiguous,
            },
            "clips": output,
        }
        validated = source_from_mapping(
            payload["clips"],
            path=snapshot_path,
            kind="snapshot",
            priority=0,
        )
        if validated.invalid_entries:
            errors.append(
                f"Snapshot mới có {validated.invalid_entries} entry sai schema."
            )

        if not dry_run and not errors:
            try:
                ghi_json_an_toan(snapshot_path, payload)
                self._invalidate_metadata_cache()
                LOGGER_METADATA.info(
                    "event=metadata.snapshot_write warehouse=%r entries=%d updated=%d",
                    self.kho_dang_dung,
                    len(output),
                    updated,
                )
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"Không ghi được snapshot: {type(exc).__name__}: {exc}")
                LOGGER_METADATA.exception(
                    "event=metadata.snapshot_error warehouse=%r category=%s",
                    self.kho_dang_dung,
                    type(exc).__name__,
                )

        return MetadataRepairResult(
            dry_run=dry_run,
            snapshot_path=snapshot_path,
            total_db_clips=len(clips),
            updated=updated,
            unchanged=unchanged,
            skipped_ambiguous=skipped_ambiguous,
            unresolved=unresolved,
            errors=tuple(errors),
            audit=audit,
        )

    def khoi_phuc_metadata_offline(
        self,
        *,
        dry_run: bool = True,
    ) -> MetadataRepairResult:
        """Tạo/merge snapshot từ dữ liệu local; mặc định dry-run và không gọi mạng."""
        if dry_run:
            return self._khoi_phuc_metadata_offline_da_khoa(dry_run=True)
        with KhoaTienTrinh(
            os.path.join(self.data_dir, "tool.lock"),
            "khôi phục metadata offline",
        ):
            return self._khoi_phuc_metadata_offline_da_khoa(dry_run=False)

    def _cap_nhat_snapshot_sau_build(self, mode: str) -> list[str]:
        """Snapshot là hậu xử lý best-effort sau khi DB fingerprint đã an toàn."""
        try:
            result = self._khoi_phuc_metadata_offline_da_khoa(
                dry_run=False,
                preserve_existing=mode != "new",
            )
        except Exception as exc:  # noqa: BLE001 - DB đã commit, chỉ hạ snapshot thành warning
            LOGGER_METADATA.exception(
                "event=metadata.snapshot_after_build_error warehouse=%r category=%s",
                self.kho_dang_dung,
                type(exc).__name__,
            )
            return [
                "Kho vân tay đã ghi thành công nhưng snapshot metadata chưa cập nhật: "
                f"{exc}"
            ]
        return list(result.errors)

    def va_metadata_thieu(
        self,
        progress: Optional[Callable] = None,
        *,
        fetcher: Optional[Callable[[str], dict]] = None,
        max_retries: int = 3,
    ) -> dict:
        """Vá field thiếu vào snapshot; chỉ caller rõ ràng mới kích hoạt I/O mạng."""
        max_retries = max(1, min(int(max_retries), 5))
        prepared = self.khoi_phuc_metadata_offline(dry_run=False)
        if prepared.errors:
            raise RuntimeError("; ".join(prepared.errors))

        if fetcher is None:
            def fetcher(video_id: str) -> dict:
                import yt_dlp

                options = {
                    "quiet": True,
                    "no_warnings": True,
                    "skip_download": True,
                    "noplaylist": True,
                    "socket_timeout": self.config.network_timeout_s,
                    "retries": 2,
                }
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(
                        f"https://youtu.be/{video_id}",
                        download=False,
                    )
                return {
                    "id": info.get("id") or video_id,
                    "title": info.get("title") or "",
                    "url": info.get("webpage_url") or f"https://youtu.be/{video_id}",
                    # Dùng chung cách rút ngày với channel.list_channel/sync để
                    # ba đường lấy metadata không hiểu khác nhau.
                    "upload_date": channel.ngay_dang_tu_info(info),
                    "duration": info.get("duration"),
                }

        with KhoaTienTrinh(
            os.path.join(self.data_dir, "tool.lock"),
            "vá metadata thiếu từ YouTube",
        ):
            snapshot_path = self._metadata_snapshot_path()
            source = load_metadata_strict(
                snapshot_path,
                kind="snapshot",
                priority=0,
                expected_warehouse=self.kho_dang_dung,
            )
            if source.warnings or not source.entries:
                raise RuntimeError(
                    "Snapshot metadata chưa hợp lệ; hãy audit/khôi phục offline trước."
                )
            records = {
                entry.key: {
                    **entry.public_dict(),
                    "resolution_method": entry.origin_method or "exact",
                }
                for entry in source.entries
            }
            resolver = self.clip_metadata_resolver(bo_cache=True)
            candidates = []
            for clip in self.db_clips():
                name = str(
                    clip.get("ten") or basename_compatible(clip.get("duong_dan"))
                )
                item = resolver.resolve(name, str(clip.get("duong_dan") or ""))
                if item.video_id and not item.complete and item.status != "ambiguous":
                    candidates.append((name, item))

            total = len(candidates)
            updated = unchanged = 0
            errors: list[str] = []
            for index, (name, current) in enumerate(candidates, start=1):
                self._check_cancel()
                fetched = None
                last_error = None
                for attempt in range(1, max_retries + 1):
                    try:
                        fetched = fetcher(current.video_id)
                        break
                    except Exception as exc:  # noqa: BLE001 - retry có giới hạn
                        last_error = exc
                        if attempt < max_retries:
                            time.sleep(min(2.0, 0.5 * (2 ** (attempt - 1))))
                if fetched is None:
                    errors.append(
                        f"{basename_compatible(name)}: "
                        f"{type(last_error).__name__ if last_error else 'UnknownError'}: "
                        f"{last_error or 'không có dữ liệu'}"
                    )
                    LOGGER_METADATA.warning(
                        "event=metadata.network_patch_failed warehouse=%r clip=%r "
                        "video_id=%s category=%s",
                        self.kho_dang_dung,
                        basename_compatible(name),
                        current.video_id,
                        type(last_error).__name__ if last_error else "UnknownError",
                    )
                elif not isinstance(fetched, dict):
                    errors.append(f"{basename_compatible(name)}: response không phải object.")
                else:
                    raw = {
                        "id": fetched.get("id") or current.video_id,
                        "title": fetched.get("title") or "",
                        "url": fetched.get("url") or f"https://youtu.be/{current.video_id}",
                        "upload_date": str(fetched.get("upload_date") or ""),
                        "duration": fetched.get("duration"),
                    }
                    validated = source_from_mapping(
                        {name: raw},
                        kind="network_patch",
                        priority=0,
                    )
                    entry = validated.entries[0] if validated.entries else None
                    if entry is None or entry.video_id != current.video_id:
                        errors.append(
                            f"{basename_compatible(name)}: metadata trả về sai identity/schema."
                        )
                    else:
                        old = dict(records.get(name) or current.public_dict())
                        patched = dict(old)
                        official = entry.public_dict()
                        replace_inferred = current.resolution_method == "filename_fallback"
                        for field in ("id", "title", "url", "upload_date", "duration"):
                            value = official.get(field)
                            if value not in ("", None) and (
                                replace_inferred or patched.get(field) in ("", None)
                            ):
                                patched[field] = value
                        patched["resolution_method"] = (
                            "video_id"
                            if all(
                                patched.get(field) not in ("", None)
                                for field in ("id", "title", "url", "upload_date", "duration")
                            )
                            else current.resolution_method
                        )
                        if patched == old:
                            unchanged += 1
                        else:
                            records[name] = patched
                            updated += 1
                            payload = {
                                "schema_version": 1,
                                "warehouse": self.kho_dang_dung,
                                "warehouse_id": self._slug(
                                    self.kho_dang_dung or "mac_dinh"
                                ),
                                "database": os.path.basename(self.db_file),
                                "updated_at": datetime.now().astimezone().isoformat(
                                    timespec="seconds"
                                ),
                                "sources": [{
                                    "kind": "explicit_network_patch",
                                    "file": "YouTube metadata API via yt-dlp",
                                }],
                                "stats": {
                                    "database_clips": len(self.db_clips()),
                                    "network_updated": updated,
                                    "network_errors": len(errors),
                                },
                                "clips": records,
                            }
                            ghi_json_an_toan(snapshot_path, payload)
                if progress:
                    progress(
                        index / total if total else 1.0,
                        f"[{index}/{total}] Metadata: {basename_compatible(name)}",
                    )

        self._invalidate_metadata_cache()
        LOGGER_METADATA.info(
            "event=metadata.network_patch_complete warehouse=%r total=%d "
            "updated=%d unchanged=%d errors=%d",
            self.kho_dang_dung,
            total,
            updated,
            unchanged,
            len(errors),
        )
        return {
            "tong": total,
            "da_va": updated,
            "bo_qua": unchanged,
            "loi": errors,
            "snapshot_path": snapshot_path,
        }

    def _audfprint_cmd(
        self,
        sub: str,
        *them: str,
        db_file: Optional[str] = None,
    ) -> list:
        ncores = self.config.ncores
        if ncores <= 0:
            ncores = so_nhan_nen_dung()
        return [sys.executable, "-u", self.audfprint, sub, "--dbase", db_file or self.db_file,
                "--ncores", str(ncores), "--continue-on-error", *them]

    def _audfprint_build_cmd(
        self,
        sub: str,
        *them: str,
        db_file: str,
    ) -> list:
        """Bọc audfprint để nhận event per-file, không sửa code vendored."""
        lenh_goc = self._audfprint_cmd(sub, *them, db_file=db_file)
        wrapper = os.path.join(self.root, "audfprint_progress_runner.py")
        return [sys.executable, "-u", wrapper, self.audfprint, *lenh_goc[3:]]

    def build_database(
        self,
        thumuc: str,
        mode: str = "new",
        progress: Optional[Callable] = None,
        progress_event: Optional[Callable[[FingerprintProgress], None]] = None,
        job_id: Optional[str] = None,
    ) -> dict:
        """Tạo/bổ sung vân tay với progress event thật và khóa liên tiến trình."""
        # Reset trước khi chờ khóa. Nếu người dùng bấm Dừng trong lúc chờ khóa,
        # _build_database_da_khoa phải nhìn thấy cờ đó thay vì xóa mất yêu cầu.
        self.cancel_event.clear()
        job_id = job_id or uuid.uuid4().hex
        tracker = FingerprintProgressTracker(
            job_id,
            callback=progress_event,
            legacy_callback=progress,
            logger=tao_fingerprint_logger(self.out_dir),
        )
        tracker.discovering()
        try:
            with KhoaTienTrinh(
                os.path.join(self.data_dir, "tool.lock"),
                "dựng kho vân tay",
            ):
                return self._build_database_da_khoa(
                    thumuc,
                    mode=mode,
                    progress=progress,
                    tracker=tracker,
                )
        except Cancelled:
            tracker.cancelled(
                "Đã dừng. Kho vân tay trước job vẫn nguyên; phần chưa ghi không được tính."
            )
            state = tracker.state
            return {
                "so_clip": state.total,
                "da_xu_ly": state.processed_count,
                "thanh_cong": 0,
                "da_tinh_xong_chua_ghi": state.success_count,
                "bo_qua": state.skipped_count,
                "that_bai": state.failed_count,
                "da_huy": True,
                "loi_file": [x["message"] for x in tracker.errors],
                "giay": state.elapsed_seconds,
                "canh_bao": [
                    f"{state.success_count} clip đã tính xong trong workspace tạm nhưng "
                    "chưa commit khi hủy; kho trước job vẫn nguyên."
                ],
            }
        except Exception as exc:
            tracker.logger.exception(
                "job_id=%s event=job_exception category=%s",
                job_id,
                type(exc).__name__,
            )
            if tracker.state.status != "failed":
                tracker.failed(
                    f"Không thể hoàn tất tạo vân tay: {exc}",
                    type(exc).__name__,
                )
            raise
        finally:
            dong_fingerprint_logger(tracker.logger)

    def _build_database_da_khoa(
        self,
        thumuc: str,
        mode: str = "new",
        progress: Optional[Callable] = None,
        tracker: Optional[FingerprintProgressTracker] = None,
    ) -> dict:
        """
        Tạo (mode='new') hoặc bổ sung (mode='add') kho vân tay từ thư mục clip gốc.
        Trả về {'so_clip': n, 'giay': t}.
        """
        tracker = tracker or FingerprintProgressTracker(
            uuid.uuid4().hex,
            legacy_callback=progress,
            logger=tao_fingerprint_logger(self.out_dir),
        )
        if mode not in {"new", "add"}:
            raise ValueError("mode tạo vân tay phải là 'new' hoặc 'add'.")
        self.require()
        self._check_cancel()
        if not os.path.isdir(thumuc):
            raise RuntimeError(f"Không tìm thấy thư mục: {thumuc}")
        files = liet_ke_media(thumuc)
        tracker.set_files(files)
        if not files:
            raise RuntimeError(f"Thư mục không có file media nào: {thumuc}")

        if self.kho_dang_dung:
            self.update_kho(self.kho_dang_dung, thumuc)

        shifts_kho = max(0, int(self.config.shifts_kho))
        db_da_ton_tai = os.path.exists(self.db_file)
        shifts_da_luu = 0
        if self.kho_dang_dung:
            dang_ky = self._doc_khos()
            kho_hien_tai = next(
                (k for k in dang_ky["danh_sach"]
                 if k["ten"] == self.kho_dang_dung),
                None,
            )
            if kho_hien_tai:
                shifts_da_luu = max(0, int(kho_hien_tai.get("shifts", 0) or 0))

        canh_bao = []
        if db_da_ton_tai and mode != "new" and shifts_da_luu != shifts_kho:
            canh_bao.append(
                f"Kho «{self.kho_dang_dung or os.path.basename(self.db_file)}» "
                f"được tạo với shifts={shifts_da_luu}, nhưng cấu hình hiện tại là "
                f"shifts={shifts_kho}. Nên tạo lại kho từ đầu để đồng bộ."
            )

        tong = len(files)
        da_co = set()
        if mode != "new" and os.path.exists(self.db_file):
            da_co = {
                os.path.normcase(os.path.abspath(clip["duong_dan"]))
                for clip in self.db_clips(bo_cache=True)
                if int(clip.get("so_hash", 0)) > 0
            }
        can_xu_ly = []
        for path in files:
            if os.path.normcase(os.path.abspath(path)) in da_co:
                tracker.skipped(path)
            else:
                can_xu_ly.append(path)

        if not can_xu_ly:
            tracker.saving()
            canh_bao.extend(self._cap_nhat_snapshot_sau_build(mode))
            tracker.completed("Mọi clip đều đã có vân tay; không cần ghi lại kho.", db_written=False)
            state = tracker.state
            return {
                "so_clip": tong,
                "da_xu_ly": state.processed_count,
                "thanh_cong": state.success_count,
                "bo_qua": state.skipped_count,
                "that_bai": state.failed_count,
                "da_huy": False,
                "loi_file": [],
                "giay": state.elapsed_seconds,
                "canh_bao": canh_bao,
            }

        workspace = os.path.join(self.data_dir, "fingerprint_jobs", tracker.job_id)
        os.makedirs(workspace, exist_ok=True)
        listfile = os.path.join(workspace, "clips.txt")
        db_tam = os.path.join(workspace, "database.pklz")
        with open(listfile, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(can_xu_ly))
        sub = "new"
        if mode != "new" and os.path.exists(self.db_file):
            tracker.phase("validating", "Đang tạo bản làm việc an toàn của kho hiện có...")
            with open(self.db_file, "rb") as nguon, open(db_tam, "xb") as dich:
                while True:
                    self._check_cancel()
                    khoi = nguon.read(8 * 1024 * 1024)
                    if not khoi:
                        break
                    dich.write(khoi)
                dich.flush()
                os.fsync(dich.fileno())
            shutil.copystat(self.db_file, db_tam)
            sub = "add"

        loi_file = []
        structured_seen = False
        started_paths: set[str] = set()

        def key(path: str) -> str:
            return os.path.normcase(os.path.abspath(path))

        def on_line(dong: str):
            nonlocal structured_seen
            if dong.startswith("TIMCLIP_FINGERPRINT_EVENT "):
                structured_seen = True
                try:
                    event = json.loads(dong.split(" ", 1)[1])
                    path = str(event.get("file") or "")
                    if event.get("event") == "clip_started" and path:
                        started_paths.add(key(path))
                        tracker.clip_started(path, int(event.get("process_pid") or 0) or None)
                    elif event.get("event") == "clip_phase" and path:
                        # Phase thật do chính tiến trình đang giải mã phát ra, không
                        # phải suy đoán từ việc bắt gặp tiến trình ffmpeg khi lấy mẫu.
                        phase = str(event.get("phase") or "")
                        if phase in PHASES_FINGERPRINT:
                            tracker.phase(
                                phase,
                                (
                                    f"Đang giải mã audio: {ten_file_an_toan(path)}"
                                    if phase == "decoding"
                                    else f"Đang tạo vân tay: {ten_file_an_toan(path)}"
                                ),
                                path,
                                int(event.get("process_pid") or 0) or None,
                            )
                    elif event.get("event") == "clip_finished" and path:
                        tracker.clip_finished(
                            path,
                            success=event.get("status") == "success",
                            elapsed=float(event.get("elapsed_seconds") or 0.0),
                            error_category=str(event.get("category") or ""),
                            message=str(event.get("message") or ""),
                        )
                        if tracker.state.processed_count >= tong:
                            tracker.saving(tracker.state.active_subprocess_pid)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    loi_file.append(f"Progress event không hợp lệ: {exc}")
                return
            if "ingesting #" in dong and not structured_seen:
                ten = dong.split(":", 1)[-1].replace("...", "").strip()
                started_paths.add(key(ten))
                tracker.clip_started(ten)
            if "Saved fprints for" in dong:
                tracker.saving(tracker.state.active_subprocess_pid)
            if any(k in dong for k in ("Error", "error", "Traceback", "Failed", "Cannot")):
                loi_file.append(dong)

        def on_heartbeat(snapshot: ProcessSnapshot) -> None:
            ffmpeg = [child for child in snapshot.children if "ffmpeg" in child.name]
            workers = [child for child in snapshot.children if "python" in child.name]
            phase = (
                "saving"
                if tracker.state.phase == "saving"
                else ("decoding" if ffmpeg else "fingerprinting")
            )
            detail = (
                f"Job vẫn hoạt động — audfprint PID {snapshot.pid}, "
                f"worker {len(workers)}, FFmpeg {len(ffmpeg)}, "
                f"im lặng {snapshot.silent_seconds:.0f} giây."
            )
            tracker.heartbeat(snapshot.pid, detail, phase=phase)

        # --maxtimebits 16: cho phép clip gốc dài tới ~25 phút vẫn định vị đúng mốc thời gian
        tham_so = ["--maxtimebits", "16"]
        if shifts_kho > 0:
            tham_so.extend(["--shifts", str(shifts_kho)])
        tham_so.extend(["--list", listfile])
        try:
            rc, duoi = self._run_stream(
                self._audfprint_build_cmd(sub, *tham_so, db_file=db_tam),
                on_line,
                on_heartbeat=on_heartbeat,
                logger=tracker.logger,
                process_name="audfprint-build",
                include_in_tail=lambda line: not line.startswith(
                    "TIMCLIP_FINGERPRINT_EVENT "
                ),
            )
            if rc != 0:
                chi_tiet = "\n".join(duoi[-12:]) or "(không có thông báo nào)"
                raise RuntimeError(
                    f"audfprint kết thúc với mã lỗi {rc}.\n\n"
                    f"Thông báo cuối cùng:\n{chi_tiet}"
                )

            # Tương thích adapter/test cũ: nếu không có structured event nhưng process
            # thành công, chỉ lúc này mới đánh dấu các file còn lại thành công.
            if not structured_seen:
                for path in can_xu_ly:
                    if key(path) not in started_paths:
                        tracker.clip_started(path)
                    tracker.clip_finished(path, success=True, elapsed=0.0)

            if not os.path.isfile(db_tam):
                raise RuntimeError("audfprint báo thành công nhưng không tạo database tạm.")
            tracker.saving(tracker.state.active_subprocess_pid)
            self._cache_khoa = None
            try:
                os.replace(db_tam, self.db_file)
            except PermissionError:
                ten_moi = (
                    f"kho_{self._slug(self.kho_dang_dung or 'kho')}_"
                    f"{uuid.uuid4().hex[:6]}.pklz"
                )
                db_moi = os.path.join(self.data_dir, ten_moi)
                os.replace(db_tam, db_moi)
                dang_ky = self._doc_khos()
                for kho in dang_ky["danh_sach"]:
                    if kho["ten"] == self.kho_dang_dung:
                        kho["db_cu"] = kho["db"]
                        kho["db"] = ten_moi
                self._ghi_khos(dang_ky)
                self._ap_dung_kho(self.kho_dang_dung, dang_ky)
                canh_bao.append(
                    "File vân tay cũ đang bị khóa; đã ghi kết quả vào file mới an toàn."
                )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        # Chỉ đổi metadata khi toàn bộ kho vừa được tạo mới, hoặc khi phần bổ sung
        # dùng đúng shifts cũ. Kho add lệch shifts phải tiếp tục mang metadata cũ
        # để những lượt sau vẫn cảnh báo cho tới khi người dùng chủ động tạo lại.
        if self.kho_dang_dung and (sub == "new" or shifts_da_luu == shifts_kho):
            dang_ky = self._doc_khos()
            for kho in dang_ky["danh_sach"]:
                if kho["ten"] == self.kho_dang_dung:
                    kho["shifts"] = shifts_kho
                    break
            self._ghi_khos(dang_ky)

        canh_bao.extend(self._cap_nhat_snapshot_sau_build(mode))
        tracker.completed()
        state = tracker.state
        return {
            "so_clip": tong,
            "da_xu_ly": state.processed_count,
            "thanh_cong": state.success_count,
            "bo_qua": state.skipped_count,
            "that_bai": state.failed_count,
            "da_huy": False,
            "loi_file": [*loi_file, *[x["message"] for x in tracker.errors]],
            "giay": state.elapsed_seconds,
            "canh_bao": canh_bao,
        }

    # =================================================================
    #  2) TẢI AUDIO TỪ YOUTUBE (dùng yt-dlp như một THƯ VIỆN)
    # =================================================================

    def youtube_info(self, url: str) -> dict:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": self.config.network_timeout_s,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "id": info.get("id", ""),
            "title": info.get("title", url),
            "duration": info.get("duration") or 0,
            "uploader": info.get("uploader", ""),
            "channel": info.get("channel") or info.get("uploader") or "",
            "channel_id": info.get("channel_id", ""),
            "channel_url": (
                info.get("channel_url") or info.get("uploader_url") or ""
            ),
            "upload_date": str(info.get("upload_date") or ""),
        }

    def download_audio(self, url: str, video_id: str,
                       progress: Optional[Callable] = None) -> str:
        """Tải RIÊNG phần audio (nhẹ hơn video hàng chục lần). Trả về đường dẫn file."""
        import yt_dlp

        san_co = [f for f in glob.glob(os.path.join(self.dl_dir, video_id + ".*"))
                  if not f.endswith((".part", ".ytdl"))]
        if san_co:
            self._bao(progress, 0.40, "Đã có sẵn audio, bỏ qua bước tải.")
            return san_co[0]

        def hook(d):
            self._check_cancel()
            if d.get("status") == "downloading":
                tong = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                da = d.get("downloaded_bytes") or 0
                ty_le = (da / tong) if tong else 0
                mb = da / 1024 / 1024
                self._bao(progress, 0.40 * ty_le,
                          f"Đang tải audio... {mb:,.0f} MB" +
                          (f" ({ty_le*100:.0f}%)" if tong else ""))
            elif d.get("status") == "finished":
                self._bao(progress, 0.40, "Tải xong, đang chuẩn bị xử lý...")

        opts = {
            "format": self.config.ytdlp_format,
            "outtmpl": os.path.join(self.dl_dir, "%(id)s.%(ext)s"),
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "continuedl": True,          # đứt mạng thì lần sau tải tiếp
            "retries": 10, "fragment_retries": 10,
            "socket_timeout": self.config.network_timeout_s,
            "progress_hooks": [hook],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        san_co = [f for f in glob.glob(os.path.join(self.dl_dir, video_id + ".*"))
                  if not f.endswith((".part", ".ytdl"))]
        if not san_co:
            raise RuntimeError("Tải audio thất bại (không thấy file sau khi tải).")
        return san_co[0]

    # =================================================================
    #  3) CẮT KHÚC + SO KHỚP
    # =================================================================

    def _overlap_thuc_te(
        self,
        progress: Optional[Callable] = None,
        pct: float = 0.0,
    ) -> int:
        """Tính overlap hiệu lực từ metadata, không làm thay đổi cấu hình gốc."""
        cfg = self.config
        tran = int(cfg.overlap_max_s)
        san = min(120, tran)
        de_xuat = int(cfg.overlap_s)
        clip_dai_nhat = 0.0

        if cfg.overlap_tu_dong:
            for meta in self.clip_meta().values():
                try:
                    duration = float(meta.get("duration") or 0)
                except (TypeError, ValueError):
                    continue
                if duration > clip_dai_nhat:
                    clip_dai_nhat = duration

            if clip_dai_nhat > 0:
                de_xuat = max(san, math.ceil(clip_dai_nhat + 30))

        overlap = min(tran, de_xuat)
        cfg.validate(overlap)
        if clip_dai_nhat > 0:
            thong_tin = (
                f"Khúc gối thực tế: {overlap} giây "
                f"(clip dài nhất: {math.ceil(clip_dai_nhat)} giây)."
            )
        else:
            thong_tin = (
                f"Khúc gối thực tế: {overlap} giây "
                "(không có metadata thời lượng, dùng cấu hình hiện tại)."
            )
        self._bao(progress, pct, thong_tin)
        return overlap

    def _cut_chunks(self, media: str, progress: Optional[Callable] = None,
                    pct0: float = 0.40, pct1: float = 0.60) -> tuple:
        cfg = self.config
        overlap = self._overlap_thuc_te(progress, pct0)
        shutil.rmtree(self.chunk_dir, ignore_errors=True)
        os.makedirs(self.chunk_dir, exist_ok=True)

        tong = self.duration_of(media)
        if not tong:
            raise RuntimeError(f"Không đọc được thời lượng file: {media}")

        buoc = cfg.chunk_s - overlap
        moc = [
            bat_dau
            for bat_dau in range(0, int(tong) + 1, buoc)
            if bat_dau < tong
        ]
        ds = []
        for i, bat_dau in enumerate(moc):
            self._check_cancel()
            out = os.path.join(self.chunk_dir, f"chunk_{int(bat_dau):07d}.wav")
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", str(bat_dau), "-t", str(cfg.chunk_s), "-i", media,
                 "-vn", "-ac", "1", "-ar", "11025", out],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024:
                ds.append(out)
            self._bao(progress, pct0 + (pct1 - pct0) * (i + 1) / len(moc),
                      f"Đang cắt khúc {i+1}/{len(moc)} (mốc {hhmmss(bat_dau)})...")
        return ds, tong

    def _match_chunks(self, chunks: list, progress: Optional[Callable] = None,
                      pct0: float = 0.60, pct1: float = 0.95) -> list:
        listfile = os.path.join(self.data_dir, "_ds_khuc.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            f.write("\n".join(chunks))
        opfile = os.path.join(self.data_dir, "_raw_match.txt")
        if os.path.exists(opfile):
            os.remove(opfile)

        dem = {"n": 0}

        def on_line(dong: str):
            if "Analyzed #" in dong:
                dem["n"] += 1
                self._bao(progress, pct0 + (pct1 - pct0) * dem["n"] / max(1, len(chunks)),
                          f"Đang so khớp vân tay... khúc {dem['n']}/{len(chunks)}")

        tham_so = [
            "--find-time-range", "--sortbytime", "--exact-count",
            "--min-count", "10", "--max-matches", str(self.config.max_matches),
        ]
        shifts_quet = max(0, int(self.config.shifts_quet))
        if shifts_quet > 0:
            tham_so.extend(["--shifts", str(shifts_quet)])
        tham_so.extend(["--opfile", opfile, "--list", listfile])
        self._bao(
            progress,
            pct0,
            "Đang nạp kho vân tay và bắt đầu so khớp...",
        )
        rc, duoi = self._run_stream(
            self._audfprint_cmd("match", *tham_so),
            on_line,
        )
        if rc != 0:
            raise RuntimeError("Lỗi khi so khớp:\n" + "\n".join(duoi[-10:]))

        tho = []
        if os.path.exists(opfile):
            with open(opfile, "r", encoding="utf-8", errors="replace") as f:
                for dong in f:
                    m = RE_MATCH.search(dong.strip())
                    if not m:
                        continue
                    khop = float(m.group(1))
                    t_khuc = float(m.group(2))
                    file_khuc = m.group(3).strip()
                    t_clip = float(m.group(4))
                    file_clip = m.group(5).strip()
                    so_hash = int(m.group(6))
                    mk = re.search(r"chunk_(\d+)\.wav", os.path.basename(file_khuc))
                    offset = int(mk.group(1)) if mk else 0
                    tho.append({"clip": file_clip, "bat_dau": offset + t_khuc,
                                "khop": khop, "t_clip": t_clip, "hash": so_hash,
                                "align": (offset + t_khuc) - t_clip})
        return tho

    def _merge(self, tho: list) -> list:
        """
        Lọc và gộp các mảnh cùng lần xuất hiện.

        ``dedup_s`` vừa là dung sai align, vừa là khoảng trống tối đa giữa hai
        interval. Hash được tích phân theo mật độ tốt nhất trên từng đoạn con
        của hợp interval, tránh đếm đôi vùng overlap nhưng vẫn giữ đủ bằng
        chứng khi clip bị chia qua ranh giới khúc.
        """
        cfg = self.config
        self.canh_bao_gop = []
        loc = [
            x for x in tho
            if x["hash"] >= cfg.min_hash
            and x["khop"] >= cfg.min_match_s
            and x["khop"] > 0
        ]
        loc.sort(key=lambda x: (x["clip"], x["align"], -x["hash"]))

        try:
            tong_hash = {
                os.path.basename(c["ten"]): int(c["so_hash"])
                for c in self.db_clips()
                if c.get("ten") and int(c.get("so_hash") or 0) > 0
            }
        except Exception as e:  # kho lỗi vẫn phải trả được kết quả chưa kẹp
            tong_hash = {}
            self.canh_bao_gop.append(
                f"Không đọc được tổng hash trong kho để áp cận trên: {e}"
            )

        def khoang_cach_interval(a: dict, b: dict) -> float:
            a0, a1 = a["bat_dau"], a["bat_dau"] + a["khop"]
            b0, b1 = b["bat_dau"], b["bat_dau"] + b["khop"]
            return max(0.0, max(a0, b0) - min(a1, b1))

        def tinh_hash_va_hop(manh: list) -> tuple:
            bien = sorted({
                moc
                for x in manh
                for moc in (x["bat_dau"], x["bat_dau"] + x["khop"])
                if x["khop"] > 0
            })
            cong_don = 0.0
            do_dai_hop = 0.0
            for a, b in zip(bien, bien[1:]):
                if b <= a:
                    continue
                phu = [
                    x for x in manh
                    if x["khop"] > 0
                    and x["bat_dau"] <= a
                    and b <= x["bat_dau"] + x["khop"]
                ]
                if not phu:
                    continue
                mat_do_tot_nhat = max(x["hash"] / x["khop"] for x in phu)
                do_dai_hop += b - a
                cong_don += (b - a) * mat_do_tot_nhat
            return round(cong_don), do_dai_hop

        gop = []
        for x in loc:
            trung = next(
                (
                    g for g in gop
                    if g["clip"] == x["clip"]
                    and abs(g["align"] - x["align"]) <= cfg.dedup_s
                    and any(
                        khoang_cach_interval(cu, x) <= cfg.dedup_s
                        for cu in g["manh"]
                    )
                ),
                None,
            )
            if trung is None:
                gop.append({
                    "clip": x["clip"],
                    "align": x["align"],
                    "manh": [dict(x)],
                })
            else:
                trung["manh"].append(dict(x))

        ket_qua = []
        for g in gop:
            manh = g["manh"]
            som_nhat = min(manh, key=lambda x: (x["bat_dau"], x["t_clip"]))
            vung_khop_s = min(x["bat_dau"] for x in manh)
            end_s = max(x["bat_dau"] + x["khop"] for x in manh)
            hash_uoc, do_dai_hop = tinh_hash_va_hop(manh)
            ten_clip = os.path.basename(g["clip"])
            gioi_han = tong_hash.get(ten_clip)
            if gioi_han is None:
                self.canh_bao_gop.append(
                    f"Không tra được tổng hash của clip «{ten_clip}»; "
                    f"giữ kết quả ước tính {hash_uoc}, không áp cận trên."
                )
                hashes = hash_uoc
            else:
                hashes = min(hash_uoc, gioi_han)
                if hash_uoc > gioi_han:
                    self.canh_bao_gop.append(
                        f"Hash ước tính của clip «{ten_clip}» là {hash_uoc}, "
                        f"đã chạm cận trên {gioi_han}; có dấu hiệu đếm trùng."
                    )
            clip_bat_dau_s = max(
                0.0,
                som_nhat["bat_dau"] - som_nhat["t_clip"],
            )
            ket_qua.append(Match(
                clip=ten_clip,
                start_s=clip_bat_dau_s,
                end_s=end_s,
                matched_s=do_dai_hop,
                clip_offset_s=vung_khop_s - clip_bat_dau_s,
                hashes=hashes,
                confidence=danh_gia(hashes),
                clip_bat_dau_s=clip_bat_dau_s,
                vung_khop_s=vung_khop_s,
            ))
        return sorted(ket_qua, key=lambda m: m.start_s)

    def _gan_chi_so(self, ds: list, duration: float) -> None:
        """Tính tỷ lệ vân tay khớp (%) và vùng vị trí cho từng kết quả."""
        tong_hash = {c["ten"]: c["so_hash"] for c in self.db_clips() if c["so_hash"]}
        for m in ds:
            goc = tong_hash.get(m.clip, 0)
            m.ty_le = min(100.0, round(100.0 * m.hashes / goc, 1)) if goc else 0.0
            if duration:
                p = m.start_s / duration
                m.vung = "Đầu" if p < 1 / 3 else ("Giữa" if p < 2 / 3 else "Cuối")

    def _chon_loc(self, ds: list, duration: float) -> tuple:
        """
        Chọn ra top N kết quả tốt nhất, PHÂN BỔ ĐỀU theo vị trí trong video vi phạm.

        Vì sao phải phân bổ đều: một video vi phạm 3 tiếng thường ghép 9–18 clip gốc.
        Nếu chỉ lấy 5 cái nhiều hash nhất, chúng có thể nằm sát nhau ở đầu video —
        làm hồ sơ khiếu nại sẽ yếu vì trông như chỉ vi phạm một đoạn. Chia video
        thành N vùng đều nhau rồi mỗi vùng lấy một bằng chứng mạnh nhất thì hồ sơ
        chứng minh được vi phạm trải dài toàn bộ video.

        Trả về (danh_sách_chọn, danh_sách_bị_loại).
        """
        cfg = self.config
        dat = [m for m in ds if m.hashes >= cfg.min_hash_floor]
        loai = [m for m in ds if m.hashes < cfg.min_hash_floor]
        if not dat:
            return [], loai

        def uu_tien(m, da_dung: set) -> tuple:
            """Xếp hạng: mạnh trước, clip chưa dùng trước, rồi tới số hash."""
            return (m.hashes >= cfg.min_hash_strong,
                    (m.clip not in da_dung) if cfg.uu_tien_clip_khac_nhau else True,
                    m.hashes)

        n = max(1, cfg.top_n)
        if not cfg.phan_bo_deu or not duration or len(dat) <= n:
            chon = sorted(dat, key=lambda m: -m.hashes)[:n]
        else:
            con = list(dat)
            chon, da_dung = [], set()
            buoc = duration / n
            # Lượt 1: mỗi vùng thời gian lấy 1 kết quả tốt nhất
            for i in range(n):
                t0, t1 = i * buoc, (i + 1) * buoc
                uv = [m for m in con if t0 <= m.start_s < t1]
                if uv:
                    tot = max(uv, key=lambda m: uu_tien(m, da_dung))
                    chon.append(tot)
                    con.remove(tot)
                    da_dung.add(tot.clip)
            # Lượt 2: vùng nào trống thì bù bằng kết quả mạnh nhất còn lại
            while len(chon) < n and con:
                tot = max(con, key=lambda m: uu_tien(m, da_dung))
                chon.append(tot)
                con.remove(tot)
                da_dung.add(tot.clip)
            loai = loai + con

        chon.sort(key=lambda m: m.start_s)   # xếp theo thời gian cho dễ đọc
        return chon, loai

    # =================================================================
    #  4) CÁC HÀM QUÉT CẤP CAO (giao diện chỉ cần gọi những hàm này)
    # =================================================================

    def scan_media(self, path: str, label: Optional[str] = None, ref: str = "",
                   source_type: str = "file", progress: Optional[Callable] = None,
                   luu_lich_su: bool = True, pct_start: float = 0.0) -> ScanResult:
        """
        Quét 1 file media dài có sẵn trên đĩa.
        pct_start: mốc % bắt đầu — bằng 0 khi quét file trực tiếp, bằng 0.40 khi
        được gọi sau bước tải YouTube (để thanh tiến độ chạy liền mạch 0 -> 100%).
        """
        self.require(can_db=True)
        p_cut1 = pct_start + (0.60 - 0.40) if pct_start else 0.35
        p_match1 = 0.95
        if source_type == "file":
            self.cancel_event.clear()
        ten = label or os.path.basename(path)
        kq = ScanResult(source_name=ten, source_ref=ref or path)
        try:
            if not os.path.isfile(path):
                raise RuntimeError(f"Không tìm thấy file: {path}")
            chunks, tong = self._cut_chunks(path, progress, pct_start, p_cut1)
            kq.duration_s = tong
            if not chunks:
                raise RuntimeError("Không cắt được khúc nào từ file này.")
            tho = self._match_chunks(chunks, progress, p_cut1, p_match1)
            tat_ca = self._merge(tho)
            if self.canh_bao_gop:
                kq.note = "\n".join(self.canh_bao_gop)
                for canh_bao in self.canh_bao_gop:
                    self._bao(progress, p_match1, f"⚠️ {canh_bao}")
            # Chặn tự khớp: nếu chính file đang quét cũng nằm trong kho vân tay
            # (do lỡ để chung thư mục), nó sẽ khớp 100% với chính nó — vô nghĩa.
            goc = os.path.basename(path).lower()
            tat_ca = [m for m in tat_ca if m.clip.lower() != goc]
            self._gan_chi_so(tat_ca, tong)
            kq.so_dat_nguong = len([
                m for m in tat_ca
                if m.hashes >= self.config.min_hash_floor
            ])
            kq.matches, kq.matches_loai = self._chon_loc(tat_ca, tong)
            tb = f"Xong — chọn {len(kq.matches)} kết quả tốt nhất"
            if kq.matches_loai:
                tb += f" (loại {len(kq.matches_loai)} kết quả yếu)"
            self._bao(progress, 1.0, tb + ".")
        except Cancelled:
            kq.status, kq.note = "error", "Đã hủy theo yêu cầu."
        except Exception as e:
            kq.status, kq.note = "error", str(e)
        finally:
            shutil.rmtree(self.chunk_dir, ignore_errors=True)
        if luu_lich_su:
            kq.job_id = self.save_job(kq, source_type)
        return kq

    def scan_youtube(self, url: str, progress: Optional[Callable] = None,
                     luu_lich_su: bool = True) -> ScanResult:
        """Tải audio 1 link YouTube rồi quét."""
        self.require(can_ytdlp=True, can_db=True)
        self.cancel_event.clear()
        kq = ScanResult(source_name=url, source_ref=url)
        try:
            self._bao(progress, 0.02, "Đang lấy thông tin video...")
            info = self.youtube_info(url)
            kq.source_name = info["title"] or url
            kq.source_id = info["id"]
            kq.channel_name = info["channel"]
            kq.channel_id = info["channel_id"]
            kq.channel_url = info["channel_url"]
            kq.upload_date = info["upload_date"]
            self._bao(progress, 0.05,
                      f"{kq.source_name} ({hhmmss(info['duration'])}) — chuẩn bị tải audio...")
            f = self.download_audio(url, info["id"], progress)
            r = self.scan_media(f, label=kq.source_name, ref=url,
                                source_type="youtube", progress=progress,
                                luu_lich_su=False, pct_start=0.40)
            r.source_ref = url
            r.source_id = info["id"]
            r.channel_name = info["channel"]
            r.channel_id = info["channel_id"]
            r.channel_url = info["channel_url"]
            r.upload_date = info["upload_date"]
            if not self.config.keep_downloads:
                with contextlib.suppress(Exception):
                    os.remove(f)
            kq = r
        except Cancelled:
            kq.status, kq.note = "error", "Đã hủy theo yêu cầu."
        except Exception as e:
            kq.status, kq.note = "error", str(e)
        if luu_lich_su:
            kq.job_id = self.save_job(kq, "youtube")
        return kq

    def scan_many(self, nguon: Iterable, source_type: str = "youtube",
                  progress: Optional[Callable] = None) -> list:
        """Quét lần lượt nhiều nguồn. progress nhận thêm tiền tố [i/n]."""
        nguon = list(nguon)
        ket = []
        for i, x in enumerate(nguon, 1):
            def p(pct, msg, i=i):
                self._bao(progress, (i - 1 + pct) / len(nguon), f"[{i}/{len(nguon)}] {msg}")
            ket.append(self.scan_youtube(x, p) if source_type == "youtube"
                       else self.scan_media(x, progress=p))
        return ket

    def cancel(self) -> None:
        self.cancel_event.set()

    # =================================================================
    #  5) LỊCH SỬ (SQLite) & XUẤT BÁO CÁO
    # =================================================================

    def save_job(self, kq: ScanResult, source_type: str) -> int:
        with self._db() as c:
            cur = c.execute(
                "INSERT INTO jobs(created_at, source_type, source_name, source_ref,"
                " duration_s, status, n_matches, note, source_id)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), source_type,
                 kq.source_name, kq.source_ref, kq.duration_s, kq.status,
                 len(kq.matches), kq.note, kq.source_id))
            job_id = cur.lastrowid
            for m in kq.matches:
                c.execute("INSERT INTO matches(job_id, clip, start_s, end_s, matched_s,"
                          " clip_offset_s, hashes, confidence) VALUES(?,?,?,?,?,?,?,?)",
                          (job_id, m.clip, m.start_s, m.end_s, m.matched_s,
                           m.clip_offset_s, m.hashes, m.confidence))
        return job_id

    def list_jobs(self, limit: int = 200) -> list:
        with self._db() as c:
            rows = c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def ids_da_quet(self, chi_thanh_cong: bool = True) -> set:
        """Trả về tập source_id đã quét, truy vấn thẳng trong SQLite."""
        dieu_kien = "source_id IS NOT NULL AND source_id != ''"
        if chi_thanh_cong:
            dieu_kien += " AND status = 'ok'"
        with self._db() as c:
            rows = c.execute(
                f"SELECT DISTINCT source_id FROM jobs WHERE {dieu_kien}"
            ).fetchall()
        return {row["source_id"] for row in rows}

    def job_matches(self, job_id: int) -> list:
        with self._db() as c:
            rows = c.execute("SELECT * FROM matches WHERE job_id=? ORDER BY start_s",
                             (job_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_job(self, job_id: int) -> None:
        with self._db() as c:
            c.execute("DELETE FROM matches WHERE job_id=?", (job_id,))
            c.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    HEADER = ["Thời điểm quét", "Nguồn video dài", "Link / đường dẫn",
              "Clip gốc tìm thấy", "Tên video gốc (YouTube)", "Link video gốc",
              "Vùng", "Clip bắt đầu từ", "Vùng khớp từ", "Đến",
              "🔗 Nhảy tới đúng mốc vi phạm",
              "Đoạn khớp (giây)", "Khớp từ giây thứ (của clip)", "Số hash khớp",
              "Tỷ lệ vân tay khớp (%)", "Đánh giá"]

    @staticmethod
    def link_moc(source_id: str, source_ref: str, giay: float) -> str:
        """Tạo link YouTube mở thẳng tới đúng giây xảy ra vi phạm."""
        if source_id:
            return f"https://youtu.be/{source_id}?t={int(giay)}"
        if "youtu" in (source_ref or ""):
            noi = "&" if "?" in source_ref else "?"
            return f"{source_ref}{noi}t={int(giay)}"
        return ""

    def to_rows(self, ket: Iterable) -> list:
        """Chuyển danh sách ScanResult thành các dòng phẳng để xuất CSV / hiện bảng."""
        resolver = self.clip_metadata_resolver()
        luc = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for kq in ket:
            dau = [luc, kq.source_name, kq.source_ref]
            if kq.status != "ok":
                rows.append(dau + [f"(LỖI: {kq.note})"] + [""] * 12)
            elif not kq.matches:
                gc = "(không có kết quả nào đạt ngưỡng)" if kq.matches_loai \
                     else "(không tìm thấy clip nào)"
                rows.append(dau + [gc] + [""] * 12)
            else:
                for m in kq.matches:
                    mt = resolver.resolve(m.clip)
                    rows.append(dau + [
                        m.clip, mt.title, mt.url,
                        m.vung, m.start_hhmmss, hhmmss(m.vung_khop_s),
                        m.end_hhmmss,
                        Engine.link_moc(kq.source_id, kq.source_ref, m.start_s),
                        f"{m.matched_s:.0f}", f"{m.clip_offset_s:.0f}",
                        m.hashes, m.ty_le, m.confidence])
        return rows

    def export_csv(self, ket: Iterable, ten_file: Optional[str] = None) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        ten_file = ten_file or os.path.join(
            self.out_dir, "ketqua_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
        f, ten_file = _mo_file_text_moi(
            ten_file, newline="", encoding="utf-8-sig"
        )
        with f:
            w = csv.writer(f)
            w.writerow(self.HEADER)
            w.writerows([
                [o_bang_tinh_an_toan(o) for o in dong]
                for dong in self.to_rows(ket)
            ])
        return ten_file

    def to_rows_ngang(self, ket: Iterable) -> list:
        """Mỗi ScanResult -> đúng 1 dòng 34 cột. Bỏ qua kết quả status != 'ok'."""
        import bang_ngang

        resolver = self.clip_metadata_resolver()
        return [
            bang_ngang.dung_dong_ngang(kq, resolver=resolver)
            for kq in ket
            if kq.status == "ok" and kq.matches
        ]

    def export_csv_ngang(self, ket: Iterable, ten_file: Optional[str] = None) -> str:
        """Xuất CSV dạng ngang, encoding utf-8-sig. Trả về đường dẫn."""
        import bang_ngang

        rows = self.to_rows_ngang(ket)
        if not rows:
            return ""
        os.makedirs(self.out_dir, exist_ok=True)
        ten_file = ten_file or os.path.join(
            self.out_dir,
            "ketqua_ngang_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv",
        )
        f, ten_file = _mo_file_text_moi(
            ten_file, newline="", encoding="utf-8-sig"
        )
        with f:
            w = csv.writer(f)
            w.writerow(bang_ngang.HEADER_NGANG)
            w.writerows([
                [o_bang_tinh_an_toan(o) for o in dong]
                for dong in rows
            ])
        return ten_file

    def export_ho_so(self, ket: Iterable, ten_file: Optional[str] = None) -> list:
        """Xuất mỗi ScanResult thành một file .md. Trả về danh sách đường dẫn đã tạo."""
        os.makedirs(self.out_dir, exist_ok=True)
        resolver = self.clip_metadata_resolver()
        duong_dan_da_tao = []

        for kq in ket:
            if kq.status != "ok" or not kq.matches:
                continue

            ho_so = dossier.dung_ho_so(kq, resolver=resolver)
            noi_dung = dossier.render_markdown(ho_so)
            if ten_file:
                goc_ten, _ = os.path.splitext(ten_file)
                duong_dan = goc_ten + ".md"
            else:
                ten_nguon = channel.lam_sach_ten(kq.source_name)
                dau_thoi_gian = datetime.now().strftime("%Y%m%d_%H%M%S")
                duong_dan = os.path.join(
                    self.out_dir,
                    f"hoso_{ten_nguon}_{dau_thoi_gian}.md",
                )

            goc_ten, duoi = os.path.splitext(duong_dan)
            so_hau_to = 2
            while os.path.exists(duong_dan):
                duong_dan = f"{goc_ten}_{so_hau_to}{duoi}"
                so_hau_to += 1

            with open(duong_dan, "w", encoding="utf-8") as f:
                f.write(noi_dung)
            duong_dan_da_tao.append(duong_dan)

        return duong_dan_da_tao
