# -*- coding: utf-8 -*-
"""
kiem_header.py — Đối chiếu HEADER_NGANG trong code với tiêu đề THẬT trong Google Sheet.

Lệch một ký tự là dữ liệu nằm sai cột mà nhìn qua vẫn tưởng đúng.
Chạy: python kiem_header.py
"""
import sys

# 33 tiêu đề lấy nguyên văn từ file Tool_Quét.xlsx người dùng cung cấp
CHUAN_33 = [
    "Thời gian quét",
    "Link kênh vi phạm",
    "Tên kênh vi phạm",
    "Id kênh vi phạm",
    "Link video vi phạm",
    "Tên video vi phạm",
    "Thời lượng video vi phạm",
    "Ngày đăng video vi phạm",
    "Đoạn vi phạm 1 trong video vi phạm",
    "Đoạn vi phạm 2 trong video vi phạm",
    "Đoạn vi phạm 3 trong video vi phạm",
    "Đoạn vi phạm 4 trong video vi phạm",
    "Đoạn vi phạm 5 trong video vi phạm",
    "Link video gốc 1", "Tên video gốc 1", "Ngày đăng video gốc 1", "Thời lượng video gốc 1",
    "Link video gốc 2", "Tên video gốc 2", "Ngày đăng video gốc 2", "Thời lượng video gốc 2",
    "Link video gốc 3", "Tên video gốc 3", "Ngày đăng video gốc 3", "Thời lượng video gốc 3",
    "Link video gốc 4", "Tên video gốc 4", "Ngày đăng video gốc 4", "Thời lượng video gốc 4",
    "Link video gốc 5", "Tên video gốc 5", "Ngày đăng video gốc 5", "Thời lượng video gốc 5",
]
COT_34 = "Tổng số đoạn phát hiện"
CHUAN = CHUAN_33 + [COT_34]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from bang_ngang import HEADER_NGANG
except Exception as e:
    print("[X] Không import được HEADER_NGANG từ bang_ngang.py:", e)
    sys.exit(1)

print(f"Số cột trong code : {len(HEADER_NGANG)}")
print(f"Số cột cần có     : {len(CHUAN)}")
print()

lech = []
for i in range(max(len(CHUAN), len(HEADER_NGANG))):
    a = CHUAN[i] if i < len(CHUAN) else "(THIẾU)"
    b = HEADER_NGANG[i] if i < len(HEADER_NGANG) else "(THIẾU)"
    if a != b:
        lech.append((i + 1, a, b))

if not lech:
    print("[OK] Toàn bộ 34 tiêu đề khớp chính xác từng ký tự.")
    sys.exit(0)

print(f"[X] Có {len(lech)} cột LỆCH:\n")
for so, chuan, code in lech:
    print(f"  Cột {so}:")
    print(f"     Sheet cần : {chuan!r}")
    print(f"     Code đang : {code!r}")
print()
print("Sửa HEADER_NGANG trong bang_ngang.py cho khớp cột 'Sheet cần'.")
sys.exit(1)