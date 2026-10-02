# -*- coding: utf-8 -*-
"""Lược đồ ``lichsu.db`` có phiên bản — lịch sử quét gắn với KHO (audit TCP-07).

PHIÊN BẢN LƯỢC ĐỒ (``PRAGMA user_version``)

* 0 — bản cũ: không biết video được quét bằng kho nào, quét tới đâu, theo chính sách
  nào. Chỉ cần một lượt "ok" ở BẤT KỲ kho nào là Watch của mọi kho bỏ qua video đó.
* 1 — thêm cột kho / phiên bản kho / chính sách / phạm vi. CHỈ THÊM CỘT.

Nguyên tắc nâng cấp:

* Dòng cũ giữ nguyên; cột mới để trống nghĩa là "chưa rõ kho". Không gán lịch sử cũ
  cho kho đang dùng và không xoá lịch sử.
* DB đã có dữ liệu thì sao lưu TRƯỚC bằng SQLite backup API — bản sao nhất quán kể cả
  khi tiến trình khác đang đọc — và làm ngay trong giao dịch ghi, nên không ai chen
  được vào giữa lúc sao lưu và lúc nâng cấp.
* Chạy lại bao nhiêu lần cũng được; hai tiến trình cùng mở app thì một bên nâng cấp,
  bên kia thấy đã xong. Lần chạy sau khi đã nâng cấp chỉ ĐỌC.
* Bản 4b7e5bd vẫn đọc/ghi được DB đã nâng cấp (nó ghi theo tên cột, cột mới có giá
  trị mặc định) — quay lui code không cần đụng dữ liệu.

Chạy tay (mặc định chỉ thống kê, không ghi gì):

    python lich_su.py --kiem data/lichsu.db
    python lich_su.py --nang-cap data/lichsu.db
    python lich_su.py --khoi-phuc data/lichsu.db.v0_20261001_120000.bak ban_khoi_phuc.db
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PHIEN_BAN = 1

# (tên cột, kiểu) thêm ở phiên bản 1. ``day_du``/``dat_muc_tieu`` để NULL ở dòng cũ:
# NULL là "không biết", khác hẳn 0 là "biết là chưa trọn".
COT_MOI = (
    ("kho_id", "TEXT DEFAULT ''"),
    ("kho_ten", "TEXT DEFAULT ''"),
    ("kho_phien_ban", "TEXT DEFAULT ''"),
    ("chinh_sach", "TEXT DEFAULT ''"),
    ("day_du", "INTEGER"),
    ("dat_muc_tieu", "INTEGER"),
    ("pham_vi", "TEXT DEFAULT ''"),
)

_DDL_GOC = (
    """CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, source_type TEXT, source_name TEXT, source_ref TEXT,
        duration_s REAL, status TEXT, n_matches INTEGER, note TEXT,
        source_id TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER,
        clip TEXT, start_s REAL, end_s REAL, matched_s REAL,
        clip_offset_s REAL, hashes INTEGER, confidence TEXT)""",
)
_CHI_MUC = (
    "CREATE INDEX IF NOT EXISTS idx_jobs_source_id ON jobs(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_matches_job_id ON matches(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_kho_source ON jobs(kho_id, source_id)",
)

CHUA_RO = "Chưa rõ (lịch sử cũ — cần rà soát)"
_LY_DO = {
    "dung_som": "dừng sớm vì đã đủ bằng chứng",
    "gioi_han_tai": "chỉ tải phần đầu video",
    "loi_khuc": "có vùng không xử lý được",
    "tai_thieu": "file tải về thiếu phần cuối",
    "huy": "đã huỷ",
    # Lượt TRỌN nhưng có điều kiện: hai lần tải độc lập cùng ngắn hơn lengthSeconds.
    "am_thanh_ngan_hon": "âm thanh YouTube ngắn hơn thời lượng video — đã tải lại kiểm",
}


def _cot_jobs(con: sqlite3.Connection) -> list:
    return [r[1] for r in con.execute("PRAGMA table_info(jobs)")]


def _co_bang(con: sqlite3.Connection, ten: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (ten,)).fetchone() is not None


def _can_nang_cap(con: sqlite3.Connection) -> bool:
    if con.execute("PRAGMA user_version").fetchone()[0] < PHIEN_BAN:
        return True
    cot = set(_cot_jobs(con))
    return not cot or any(ten not in cot for ten, _ in COT_MOI)


def _co_du_lieu(con: sqlite3.Connection) -> bool:
    for bang in ("jobs", "matches"):
        if _co_bang(con, bang) and con.execute(
                f"SELECT 1 FROM {bang} LIMIT 1").fetchone() is not None:
            return True
    return False


def _sao_luu_bang_ket_noi(con: sqlite3.Connection, dich: str) -> None:
    dst = sqlite3.connect(dich)
    try:
        con.backup(dst)
    finally:
        dst.close()


def _sao_luu_duong_dan(nguon: str, dich: str, han_cho_s: float) -> None:
    """Sao lưu qua một kết nối ĐỌC riêng.

    Không backup được từ chính kết nối đang giữ khoá ghi: SQLite trả SQLITE_LOCKED và
    ``Connection.backup`` thử lại mãi mãi (đã gặp: treo vô hạn). Kết nối đọc riêng vẫn
    lấy được khoá SHARED khi kết nối kia mới giữ RESERVED, và không ai ghi chen được.
    """
    src = sqlite3.connect(nguon, timeout=han_cho_s)
    try:
        _sao_luu_bang_ket_noi(src, dich)
    finally:
        src.close()


def _ten_ban_sao(path: str, nhan: str) -> str:
    """``<path>.<nhan>_<thời điểm>.bak``, không bao giờ trùng file đã có."""
    moc = datetime.now().strftime("%Y%m%d_%H%M%S")
    ten = f"{path}.{nhan}_{moc}.bak"
    i = 1
    while os.path.exists(ten):
        i += 1
        ten = f"{path}.{nhan}_{moc}_{i}.bak"
    return ten


def dam_bao_luoc_do(path: str, *, sao_luu: bool = True, han_cho_s: float = 30.0) -> dict:
    """Tạo mới hoặc nâng cấp ``lichsu.db`` lên ``PHIEN_BAN``. Idempotent.

    Trả về ``{"da_nang_cap", "sao_luu", "phien_ban_cu", "phien_ban"}``. ``sao_luu`` là
    đường dẫn bản sao (rỗng khi không cần — DB mới tạo hoặc đã ở phiên bản mới).
    """
    thu_muc = os.path.dirname(os.path.abspath(path))
    os.makedirs(thu_muc, exist_ok=True)
    con = sqlite3.connect(path, timeout=han_cho_s)
    try:
        # Đường nhanh, CHỈ ĐỌC: mọi lần mở app sau khi đã nâng cấp đi qua đây.
        if not _can_nang_cap(con):
            return {"da_nang_cap": False, "sao_luu": "", "phien_ban": PHIEN_BAN,
                    "phien_ban_cu": PHIEN_BAN}
        con.execute("BEGIN IMMEDIATE")
        try:
            # Kiểm lại SAU khi giữ khoá ghi: tiến trình khác có thể vừa nâng cấp xong.
            cu = con.execute("PRAGMA user_version").fetchone()[0]
            if not _can_nang_cap(con):
                con.rollback()
                return {"da_nang_cap": False, "sao_luu": "", "phien_ban": PHIEN_BAN,
                        "phien_ban_cu": cu}
            ban_sao = ""
            if sao_luu and _co_du_lieu(con):
                ban_sao = _ten_ban_sao(path, f"v{cu}")
                _sao_luu_duong_dan(path, ban_sao, han_cho_s)
            for lenh in _DDL_GOC:
                con.execute(lenh)
            cot = set(_cot_jobs(con))
            if "source_id" not in cot:      # DB của bản rất cũ, trước cả cột source_id
                con.execute("ALTER TABLE jobs ADD COLUMN source_id TEXT DEFAULT ''")
            for ten, kieu in COT_MOI:
                if ten not in cot:
                    con.execute(f"ALTER TABLE jobs ADD COLUMN {ten} {kieu}")
            for lenh in _CHI_MUC:
                con.execute(lenh)
            # Không bao giờ HẠ phiên bản: DB do bản mới hơn tạo chỉ được bổ sung cột thiếu.
            con.execute(f"PRAGMA user_version = {max(int(cu), PHIEN_BAN)}")
            con.commit()
        except BaseException:
            con.rollback()
            raise
        return {"da_nang_cap": True, "sao_luu": ban_sao, "phien_ban": PHIEN_BAN,
                "phien_ban_cu": cu}
    finally:
        con.close()


def _mo_chi_doc(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def thong_ke(path: str) -> dict:
    """Chạy thử: trạng thái lược đồ và số dòng bị ảnh hưởng. KHÔNG ghi gì."""
    if not os.path.isfile(path):
        return {"ton_tai": False, "phien_ban": None, "so_dong": 0,
                "so_dong_chua_ro_kho": 0, "so_match": 0, "cot_se_them": [],
                "can_nang_cap": True}
    con = _mo_chi_doc(path)
    try:
        phien_ban = con.execute("PRAGMA user_version").fetchone()[0]
        co_jobs = _co_bang(con, "jobs")
        cot = set(_cot_jobs(con)) if co_jobs else set()
        so_dong = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] if co_jobs else 0
        if "kho_id" in cot:
            chua_ro = con.execute(
                "SELECT COUNT(*) FROM jobs WHERE kho_id IS NULL OR kho_id = ''"
            ).fetchone()[0]
        else:
            chua_ro = so_dong
        so_match = (con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                    if _co_bang(con, "matches") else 0)
        se_them = [ten for ten, _ in COT_MOI if ten not in cot]
        return {
            "ton_tai": True,
            "phien_ban": phien_ban,
            "so_dong": so_dong,
            "so_dong_chua_ro_kho": chua_ro,
            "so_match": so_match,
            "cot_se_them": se_them,
            "can_nang_cap": phien_ban < PHIEN_BAN or bool(se_them),
        }
    finally:
        con.close()


def khoi_phuc(ban_sao: str, dich: str, *, ghi_de: bool = False) -> str:
    """Khôi phục bản sao lưu ra ``dich`` bằng backup API.

    Mặc định KHÔNG ghi đè file đang có — khôi phục ra file mới rồi mới đổi tên bằng
    tay khi đã dừng app. ``ghi_de=True`` vẫn chụp lại bản hiện tại trước khi ghi đè.
    Trả về đường dẫn bản chụp trước khi ghi đè (rỗng nếu không có).
    """
    if not os.path.isfile(ban_sao):
        raise FileNotFoundError(ban_sao)
    truoc = ""
    if os.path.exists(dich):
        if not ghi_de:
            raise FileExistsError(
                f"{dich} đã tồn tại — khôi phục ra file khác, hoặc dùng ghi_de=True.")
        truoc = _ten_ban_sao(dich, "truoc_khoi_phuc")
        src_hien_tai = sqlite3.connect(dich)
        try:
            _sao_luu_bang_ket_noi(src_hien_tai, truoc)
        finally:
            src_hien_tai.close()
    src = _mo_chi_doc(ban_sao)
    try:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError(f"Bản sao lưu hỏng: {ban_sao}")
        _sao_luu_bang_ket_noi(src, dich)
    finally:
        src.close()
    return truoc


# ---------------------------------------------------------------------------
#  Mô tả cho giao diện — hàm thuần trên một dòng ``jobs`` (dict)
# ---------------------------------------------------------------------------

def _hhmmss(giay: float) -> str:
    giay = max(0, int(giay or 0))
    return f"{giay // 3600:02d}:{(giay % 3600) // 60:02d}:{giay % 60:02d}"


def mo_ta_kho(hang: dict) -> str:
    """Tên kho của một lần quét; lịch sử cũ thì nói rõ là chưa rõ."""
    if not (hang.get("kho_id") or ""):
        return CHUA_RO
    return hang.get("kho_ten") or hang.get("kho_id")


def mo_ta_pham_vi(hang: dict) -> str:
    """Phạm vi thật của một lần quét, đủ để người đọc không hiểu nhầm là quét trọn."""
    if hang.get("day_du") is None:
        return CHUA_RO
    pham_vi = {}
    with contextlib.suppress(ValueError, TypeError):
        pham_vi = json.loads(hang.get("pham_vi") or "{}") or {}
    if hang.get("day_du") == 1:
        ly_do = _LY_DO.get(pham_vi.get("ly_do") or "", "")
        return "Trọn video" + (f" ({ly_do})" if ly_do else "")
    vung = pham_vi.get("vung_da_khop")
    tong = float(hang.get("duration_s") or 0)
    if vung is None:
        phan = "không rõ đã so khớp bao nhiêu"
    else:
        da = sum(max(0.0, float(b) - float(a)) for a, b in vung)
        phan = f"đã so khớp {_hhmmss(da)}" + (f"/{_hhmmss(tong)}" if tong else "")
    ly_do = _LY_DO.get(pham_vi.get("ly_do") or "", "")
    return f"Một phần — {phan}" + (f" ({ly_do})" if ly_do else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tra / nâng cấp / khôi phục lichsu.db")
    nhom = ap.add_mutually_exclusive_group()
    nhom.add_argument("--kiem", action="store_true", help="Chạy thử: chỉ thống kê (mặc định)")
    nhom.add_argument("--nang-cap", action="store_true", help="Sao lưu rồi nâng cấp")
    nhom.add_argument("--khoi-phuc", metavar="BAN_SAO",
                      help="Khôi phục bản sao lưu ra file DB đích (không ghi đè)")
    ap.add_argument("db", help="Đường dẫn lichsu.db (hoặc file đích khi khôi phục)")
    a = ap.parse_args(argv)
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.khoi_phuc:
        khoi_phuc(a.khoi_phuc, a.db)
        print(f"Đã khôi phục {a.khoi_phuc} -> {a.db}")
        print(json.dumps(thong_ke(a.db), ensure_ascii=False, indent=2))
        return 0
    if a.nang_cap:
        kq = dam_bao_luoc_do(a.db)
        print(json.dumps(kq, ensure_ascii=False, indent=2))
    print(json.dumps(thong_ke(a.db), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
