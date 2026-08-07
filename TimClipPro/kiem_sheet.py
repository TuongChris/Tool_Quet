# -*- coding: utf-8 -*-
"""
kiem_sheet.py — Ghi THỬ một dòng giả vào Google Sheet để kiểm tra dữ liệu có rơi đúng cột.

Nhanh hơn nhiều so với đợi quét một video thật. Sau khi kiểm xong nhớ XOÁ dòng thử.

Chạy:  python kiem_sheet.py "<link Google Sheet>"
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if len(sys.argv) < 2:
    print('Cách dùng: python kiem_sheet.py "<link Google Sheet>"')
    sys.exit(1)
LINK = sys.argv[1]

import bang_ngang  # noqa: E402 - chỉ nạp dependency sau khi kiểm tra đối số
from bang_ngang import HEADER_NGANG  # noqa: E402
from engine import Match, ScanResult  # noqa: E402
from sheets import SheetsExporter  # noqa: E402

# --- Dòng giả, dễ nhận ra để xoá sau ---
kq = ScanResult(
    source_name="### DONG THU NGHIEM - XOA SAU KHI KIEM TRA ###",
    source_ref="https://www.youtube.com/watch?v=TEST12345",
    source_id="TEST12345",
    duration_s=10800,
    matches=[
        Match(clip="clip_mot.opus", start_s=850, end_s=1846, matched_s=996,
              clip_offset_s=39, hashes=17252, confidence="Rất chắc chắn",
              ty_le=64.2, vung="Đầu"),
        Match(clip="clip_hai.opus", start_s=7000, end_s=7859, matched_s=859,
              clip_offset_s=45, hashes=12751, confidence="Rất chắc chắn",
              ty_le=60.8, vung="Cuối"),
    ],
)
for ten, gt in [("channel_name", "KENH THU NGHIEM"), ("channel_id", "UCtest123"),
                ("channel_url", "https://www.youtube.com/channel/UCtest123"),
                ("upload_date", "20250115"), ("so_dat_nguong", 87)]:
    if hasattr(kq, ten):
        setattr(kq, ten, gt)

meta = {
    "clip_mot.opus": {"title": "Video goc mot", "upload_date": "20240310",
                      "duration": 1550, "url": "https://youtu.be/TESTgoc1"},
    "clip_hai.opus": {"title": "Video goc hai", "upload_date": "20231122",
                      "duration": 980, "url": "https://youtu.be/TESTgoc2"},
}

dong = bang_ngang.dung_dong_ngang(kq, meta)
print(f"Dòng có {len(dong)} ô, tiêu đề có {len(HEADER_NGANG)} cột.")
if len(dong) != len(HEADER_NGANG):
    print("[X] Lệch số ô — dừng lại.")
    sys.exit(1)

sx = SheetsExporter(sheet=LINK)
ok, tb = sx.kiem_tra()
print("Kết nối:", tb)
if not ok:
    sys.exit(1)

# Đọc tiêu đề ĐANG CÓ trong sheet để đối chiếu trước khi ghi
try:
    ws = sx._mo_worksheet(len(HEADER_NGANG))
    hien_co = ws.row_values(1)
except Exception as e:
    print("[X] Không đọc được hàng tiêu đề:", e)
    sys.exit(1)

print(f"\nTiêu đề trong sheet: {len(hien_co)} cột")
if not hien_co:
    print("[!] Sheet đang TRỐNG. Tool sẽ tự ghi hàng tiêu đề khi ghi dòng đầu tiên.")
else:
    lech = [(i + 1, HEADER_NGANG[i] if i < len(HEADER_NGANG) else "(THIẾU)",
             hien_co[i] if i < len(hien_co) else "(THIẾU)")
            for i in range(max(len(HEADER_NGANG), len(hien_co)))
            if (HEADER_NGANG[i] if i < len(HEADER_NGANG) else None)
            != (hien_co[i] if i < len(hien_co) else None)]
    if lech:
        print(f"[X] {len(lech)} cột LỆCH giữa code và sheet:\n")
        for so, code, sheet in lech:
            print(f"  Cột {so}:  code={code!r}\n           sheet={sheet!r}")
        print("\nSửa cho khớp rồi chạy lại. KHÔNG ghi gì để tránh làm bẩn bảng.")
        sys.exit(1)
    print("[OK] Tiêu đề trong sheet khớp hoàn toàn với code.")

n = sx.append(HEADER_NGANG, [dong])
print(f"\n[OK] Đã ghi {n} dòng thử vào sheet.")
print("Mở Google Sheet kiểm tra dòng cuối cùng, sau đó XOÁ dòng đó đi.")
