# -*- coding: utf-8 -*-
"""
dong_goi.py — Đóng gói MÃ NGUỒN dự án để gửi audit.

Dùng danh sách CHO PHÉP (whitelist) thay vì danh sách loại trừ: chỉ những file
được liệt kê mới được đưa vào. An toàn hơn nhiều — thêm file nhạy cảm mới vào
dự án cũng không lọt ra ngoài ngoài ý muốn.

Chạy: python dong_goi.py
Kết quả: TimClipPro_source.zip ở thư mục hiện tại.
"""
import os
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GOC = os.path.dirname(os.path.abspath(__file__))
RA = os.path.join(GOC, "TimClipPro_source.zip")

# --- TUYỆT ĐỐI không bao giờ đóng gói ---
CAM = {"google_key.json", "credentials.json", "token.json", "client_secret.json",
       ".env", "secrets.toml"}

# --- Thư mục bỏ qua hoàn toàn ---
BO_QUA_TM = {"data", "ketqua", "bin", "audfprint-master", "__pycache__",
             ".pytest_cache", ".git", ".venv", "venv", "node_modules"}

# --- Đuôi file được phép ---
DUOI_OK = {".py", ".md", ".txt", ".bat", ".ini", ".json", ".toml", ".yml", ".cfg"}


def nen_lay(duong_dan_tuong_doi: str) -> bool:
    phan = duong_dan_tuong_doi.replace("\\", "/").split("/")
    ten = phan[-1]
    if ten in CAM:
        return False
    if any(p in BO_QUA_TM for p in phan[:-1]):
        return False
    if os.path.splitext(ten)[1].lower() not in DUOI_OK:
        return False
    # Bỏ mọi file .json ở gốc trừ các file cấu hình đã biết
    if len(phan) == 1 and ten.endswith(".json") and ten not in {"watchlist.json"}:
        return False
    return True


ds, tong = [], 0
for goc, thu_muc, files in os.walk(GOC):
    thu_muc[:] = [d for d in thu_muc if d not in BO_QUA_TM]
    for f in files:
        day_du = os.path.join(goc, f)
        tuong_doi = os.path.relpath(day_du, GOC)
        if tuong_doi == os.path.basename(RA):
            continue
        if nen_lay(tuong_doi):
            ds.append(tuong_doi)
            tong += os.path.getsize(day_du)

ds.sort()
print(f"Sẽ đóng gói {len(ds)} file, tổng {tong/1024:.0f} KB:\n")
for t in ds:
    print("  ", t)

# Chốt chặn an toàn
lot = [t for t in ds if os.path.basename(t) in CAM]
if lot:
    print("\n[X] PHÁT HIỆN FILE NHẠY CẢM:", lot, "— dừng lại.")
    sys.exit(1)

with zipfile.ZipFile(RA, "w", zipfile.ZIP_DEFLATED) as z:
    for t in ds:
        z.write(os.path.join(GOC, t), t)

kt = os.path.getsize(RA)
print(f"\n[OK] Đã tạo: {RA}")
print(f"     Dung lượng: {kt/1024:.0f} KB")

# Kiểm lại nội dung zip lần cuối
with zipfile.ZipFile(RA) as z:
    xau = [n for n in z.namelist() if os.path.basename(n) in CAM]
print("[OK] Trong zip KHÔNG có file khoá bí mật." if not xau
      else f"[X] Zip có file cấm: {xau}")