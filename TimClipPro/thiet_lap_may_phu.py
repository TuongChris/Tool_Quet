# -*- coding: utf-8 -*-
"""thiet_lap_may_phu.py — Chạy MỘT LẦN trên máy phụ sau khi giải nén gói.

Máy nguồn trỏ kho vào `D:\\ClipGocSML`, `D:\\ClipGocCory`... — những thư mục đó
không tồn tại trên máy phụ. Script này trỏ lại vào `kho_meta\\<TênKho>` nằm ngay
trong thư mục cài, rồi tự kiểm tra xem còn thiếu gì.

    python thiet_lap_may_phu.py            # sửa đường dẫn + kiểm tra
    python thiet_lap_may_phu.py --kiem-tra # chỉ kiểm tra, không sửa gì
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from luu_tru import cap_nhat_json, doc_json_an_toan

GOC = os.path.dirname(os.path.abspath(__file__))
THU_MUC_META = "kho_meta"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sua_duong_dan_kho(goc: str = GOC, chi_kiem_tra: bool = False) -> list:
    """Trỏ `thu_muc` của từng kho về `kho_meta/<Tên>` trong thư mục cài."""
    path = os.path.join(goc, "data", "khos.json")
    khos = doc_json_an_toan(path, {})
    if not isinstance(khos, dict) or not khos.get("danh_sach"):
        return ["Không đọc được data/khos.json — gói có vẻ thiếu."]

    ghi_chu = []
    can_doi: dict[str, str] = {}
    for k in khos["danh_sach"]:
        ten = k.get("ten") or ""
        moi = os.path.join(goc, THU_MUC_META, ten)
        if not os.path.isdir(moi):
            ghi_chu.append(
                f"Kho «{ten}»: không có {THU_MUC_META}\\{ten} — báo cáo sẽ thiếu "
                "tên/link/thời lượng clip gốc (vẫn quét được).")
            continue
        if os.path.normcase(k.get("thu_muc") or "") != os.path.normcase(moi):
            ghi_chu.append(f"Kho «{ten}»: {k.get('thu_muc') or '(trống)'} → {moi}")
            can_doi[ten] = moi
    doi = bool(can_doi)

    if doi and not chi_kiem_tra:
        def sua(d: dict) -> None:
            # Đọc lại bản MỚI NHẤT dưới khoá rồi chỉ sửa đúng `thu_muc` của kho cần
            # đổi — không ghi đè cả sổ đăng ký bằng bản đọc từ đầu hàm.
            for kho in d.get("danh_sach", []):
                if isinstance(kho, dict) and kho.get("ten") in can_doi:
                    kho["thu_muc"] = can_doi[kho["ten"]]

        cap_nhat_json(path, sua, mac_dinh={"dang_dung": "", "danh_sach": []})
        ghi_chu.append("Đã ghi lại data/khos.json (bản sao: .bak)")
    elif doi:
        ghi_chu.append("[chỉ kiểm tra] chưa ghi — bỏ cờ --kiem-tra để sửa thật")
    return ghi_chu


def kiem_tra(goc: str = GOC) -> list:
    """Trả danh sách (đạt?, mô tả). Không sửa gì."""
    kq = []

    def them(dat: bool, mo_ta: str):
        kq.append((dat, mo_ta))

    khos = doc_json_an_toan(os.path.join(goc, "data", "khos.json"), {})
    ds = khos.get("danh_sach", []) if isinstance(khos, dict) else []
    them(bool(ds), f"khos.json: {len(ds)} kho")
    for k in ds:
        db = os.path.join(goc, "data", k.get("db") or "")
        them(os.path.isfile(db),
             f"kho «{k.get('ten')}»: vân tay {k.get('db')} "
             f"({os.path.getsize(db)/1e6:.0f} MB)" if os.path.isfile(db)
             else f"kho «{k.get('ten')}»: THIẾU file vân tay {k.get('db')}")
        meta = os.path.join(k.get("thu_muc") or "", "clips_meta.json")
        them(os.path.isfile(meta),
             f"kho «{k.get('ten')}»: clips_meta.json"
             + ("" if os.path.isfile(meta) else " THIẾU — báo cáo sẽ thiếu metadata"))

    them(os.path.isfile(os.path.join(goc, "audfprint-master", "audfprint.py")),
         "audfprint")
    co_ff = (os.path.isfile(os.path.join(goc, "bin", "ffmpeg.exe"))
             or shutil.which("ffmpeg") is not None)
    them(co_ff, "ffmpeg")
    co_fp = (os.path.isfile(os.path.join(goc, "bin", "ffprobe.exe"))
             or shutil.which("ffprobe") is not None)
    them(co_fp, "ffprobe")
    them(os.path.isdir(os.path.join(goc, ".venv")),
         ".venv (chưa có thì chạy cai_dat.bat)")

    # Google Sheets là TUỲ CHỌN và khoá phải tự chép sang, không nằm trong gói.
    co_khoa = os.path.isfile(os.path.join(goc, "google_key.json"))
    kq.append((None, "google_key.json: "
               + ("đã có" if co_khoa
                  else "CHƯA có — chỉ cần nếu muốn đẩy Google Sheets")))

    wl = [f for f in os.listdir(goc) if f.startswith("watchlist")
          and f.endswith(".json") and f != "watchlist.example.json"]
    kq.append((bool(wl), f"watchlist: {', '.join(wl) if wl else 'CHƯA có — chép watchlist.example.json thành watchlist.json'}"))
    return kq


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kiem-tra", action="store_true",
                    help="Chỉ kiểm tra, không sửa khos.json")
    args = ap.parse_args()

    print(f"Thư mục cài: {GOC}\n")
    print("=== Trỏ lại đường dẫn kho ===")
    for dong in sua_duong_dan_kho(GOC, args.kiem_tra) or ["Không có gì phải sửa."]:
        print(f"  {dong}")

    print("\n=== Kiểm tra ===")
    thieu = 0
    for dat, mo_ta in kiem_tra(GOC):
        if dat is None:
            dau = "  ·"
        elif dat:
            dau = "  ✓"
        else:
            dau = "  ✗"
            thieu += 1
        print(f"{dau} {mo_ta}")

    if thieu:
        print(f"\n[!] Còn {thieu} mục chưa đạt. Chạy cai_dat.bat rồi chạy lại script này.")
        return 1
    print("\n[OK] Sẵn sàng. Tiếp theo: tạo watchlist rồi đặt lịch ChayMayPhu.bat.")
    print("     Hướng dẫn: docs/TRIEN_KHAI_MAY_PHU.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
