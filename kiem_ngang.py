import csv
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from bang_ngang import HEADER_NGANG
from engine import Engine, Match, ScanResult

# --- Dựng một kết quả quét giả, mô phỏng video 3 tiếng chứa 2 đoạn vi phạm ---
kq = ScanResult(
    source_name="Video vi pham thu nghiem",
    source_ref="https://www.youtube.com/watch?v=ABC123xyz",
    source_id="ABC123xyz",
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
# Các trường do TASK C1 thêm — gán mềm để script vẫn chạy nếu tên khác
for ten, gia_tri in [("channel_name", "Kenh Vi Pham ABC"),
                     ("channel_id", "UCxxxxxxxxxxxxxxxxxxxxxx"),
                     ("channel_url", "https://www.youtube.com/channel/UCxxxx"),
                     ("upload_date", "20250115"),
                     ("so_dat_nguong", 87)]:
    if hasattr(kq, ten):
        setattr(kq, ten, gia_tri)
    else:
        print(f"[!] ScanResult KHÔNG có trường '{ten}' — kiểm lại TASK C1")

meta_gia = {
    "clip_mot.opus": {"id": "Lt_TfJbhgvI", "title": "Video goc so mot",
                      "upload_date": "20240310", "duration": 1550,
                      "url": "https://youtu.be/Lt_TfJbhgvI"},
    "clip_hai.opus": {"id": "MdYDnXTpBhI", "title": "Video goc so hai",
                      "upload_date": "00000000", "duration": 0,
                      "url": "https://youtu.be/MdYDnXTpBhI"},
}

# --- 1) Kiểm hàm dựng dòng ---
import bang_ngang
dong = bang_ngang.dung_dong_ngang(kq, meta_gia)
print(f"Số ô trong dòng : {len(dong)}")
print(f"Số cột tiêu đề  : {len(HEADER_NGANG)}")
if len(dong) != len(HEADER_NGANG):
    print("[X] LỆCH SỐ Ô — dừng lại, sửa dung_dong_ngang()")
    sys.exit(1)
print()
print("--- Từng ô (ô rỗng hiện là chuỗi trống) ---")
for i, (h, v) in enumerate(zip(HEADER_NGANG, dong), 1):
    print(f"{i:2}. {h:38} = {v!r}")

# --- 2) Kiểm xuất CSV thật ---
print()
e = Engine()
if not hasattr(e, "export_csv_ngang"):
    print("[X] Engine KHÔNG có method export_csv_ngang — kiểm lại TASK C3")
    sys.exit(1)
f = e.export_csv_ngang([kq])
print("File CSV đã tạo:", f)
with open(f, encoding="utf-8-sig", newline="") as fh:
    cac_dong = list(csv.reader(fh))
print("Số dòng trong CSV :", len(cac_dong), "(1 tiêu đề + dữ liệu)")
print("Số cột dòng tiêu đề:", len(cac_dong[0]))
print("Số cột dòng dữ liệu:", len(cac_dong[1]) if len(cac_dong) > 1 else "KHÔNG CÓ DÒNG DỮ LIỆU")

ok = len(cac_dong) >= 2 and len(cac_dong[0]) == 34 and len(cac_dong[1]) == 34
print()
print("[OK] Đường ống 34 cột hoạt động." if ok else "[X] CSV không đúng 34 cột.")
sys.exit(0 if ok else 1)
