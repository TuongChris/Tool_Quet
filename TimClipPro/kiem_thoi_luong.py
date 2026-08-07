# -*- coding: utf-8 -*-
"""Kiểm tra và bổ sung độ dài media thật cho metadata clip gốc.

VÌ SAO CẦN

`duration` trong `clips_meta.json` lấy từ yt-dlp, mà yt-dlp lấy `lengthSeconds` của
YouTube — một số nguyên ĐÃ LÀM TRÒN độ dài thật. Đo trên 60 clip kho SML: 58/60
khớp đúng `round(media)`, và ở 55% số clip nó lớn hơn `floor(media)` đúng một giây.
Vì trình phát hiển thị theo kiểu cắt phần lẻ, báo cáo dựa trên số nguyên đó sẽ dư
một giây ở hơn nửa số clip.

Trường `duration_media` lưu độ dài đo thẳng từ file trong kho. Độ tin cậy đã kiểm
chứng: file `.opus` của 3ixKzIN0et0 dài 675,858 giây, còn `video.duration` đọc ngay
trên trang YouTube là 675,861 giây — lệch 3 mili giây.

CÁCH DÙNG

    python kiem_thoi_luong.py                    # kiểm tra, KHÔNG ghi gì
    python kiem_thoi_luong.py --kho SML          # chỉ một kho
    python kiem_thoi_luong.py --sua              # thử ghi (vẫn chỉ in ra)
    python kiem_thoi_luong.py --sua --that-su    # ghi thật, có bản sao .bak

Không đụng tới kho vân tay, không tải lại gì, không gọi mạng.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

from luu_tru import doc_json_an_toan, ghi_json_an_toan

TRUONG = "duration_media"


def do_dai_media(path: str) -> float | None:
    """Độ dài thật của file, đo bằng ffprobe. Không đo được thì trả None."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        gia_tri = float(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return None
    return gia_tri if math.isfinite(gia_tri) and gia_tri > 0 else None


def hhmmss(giay: float) -> str:
    giay = max(0, int(giay))
    return f"{giay // 3600:02d}:{(giay % 3600) // 60:02d}:{giay % 60:02d}"


def _so_hop_le(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(float(x)) and float(x) > 0 else None


def kiem_mot_kho(ten_kho: str, thu_muc: str, sua: bool, that_su: bool,
                 gioi_han: int) -> dict:
    """Kiểm tra một kho. Trả về thống kê; chỉ ghi khi ``that_su`` bật."""
    meta_path = os.path.join(thu_muc, "clips_meta.json")
    if not os.path.isfile(meta_path):
        print(f"\n### {ten_kho}: không có clips_meta.json tại {thu_muc}")
        return {}

    meta = doc_json_an_toan(meta_path, {})
    if not isinstance(meta, dict):
        print(f"\n### {ten_kho}: clips_meta.json không phải object JSON")
        return {}

    tk = {"tong": len(meta), "co_duration": 0, "co_media": 0, "thieu_file": 0,
          "do_duoc": 0, "doi_hien_thi": 0, "da_ghi": 0}
    doi = []
    for ten, muc in meta.items():
        if not isinstance(muc, dict):
            continue
        d = _so_hop_le(muc.get("duration"))
        if d is not None:
            tk["co_duration"] += 1
        if _so_hop_le(muc.get(TRUONG)) is not None:
            tk["co_media"] += 1
            continue
        path = os.path.join(thu_muc, ten)
        if not os.path.exists(path):
            tk["thieu_file"] += 1
            continue
        if gioi_han and tk["do_duoc"] >= gioi_han:
            continue
        media = do_dai_media(path)
        if media is None:
            continue
        tk["do_duoc"] += 1
        if d is not None and hhmmss(d) != hhmmss(media):
            tk["doi_hien_thi"] += 1
            doi.append((ten, d, media))
        if sua:
            muc[TRUONG] = round(media, 3)
            tk["da_ghi"] += 1

    print(f"\n### {ten_kho}   ({thu_muc})")
    print(f"  tổng mục                    : {tk['tong']}")
    print(f"  có `duration` (yt-dlp)      : {tk['co_duration']}")
    print(f"  đã có `{TRUONG}`      : {tk['co_media']}")
    print(f"  đo được từ file             : {tk['do_duoc']}")
    print(f"  thiếu file trong kho        : {tk['thieu_file']}")
    if tk["do_duoc"]:
        pt = 100 * tk["doi_hien_thi"] / tk["do_duoc"]
        print(f"  ĐỔI hiển thị sau khi bổ sung: {tk['doi_hien_thi']} ({pt:.1f}%)")
    for ten, d, media in doi[:8]:
        print(f"      {hhmmss(d)} → {hhmmss(media)}   ({d:.0f} → {media:.3f})  "
              f"{ten[:44]}")

    if sua and that_su and tk["da_ghi"]:
        ghi_json_an_toan(meta_path, meta)   # tự tạo .bak
        print(f"  ĐÃ GHI {tk['da_ghi']} mục vào {meta_path} (bản sao: .bak)")
    elif sua and tk["da_ghi"]:
        print(f"  [thử] sẽ ghi {tk['da_ghi']} mục — thêm --that-su để ghi thật")
    return tk


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kho", default="", help="Chỉ kiểm một kho theo tên")
    ap.add_argument("--sua", action="store_true",
                    help=f"Bổ sung `{TRUONG}` (mặc định chỉ in ra)")
    ap.add_argument("--that-su", action="store_true",
                    help="Ghi thật xuống đĩa; không có cờ này thì chỉ thử")
    ap.add_argument("--gioi-han", type=int, default=0,
                    help="Chỉ đo tối đa ngần này clip mỗi kho (0 = tất cả)")
    args = ap.parse_args()

    import engine  # nhập muộn để --help không phải nạp cả engine

    eng = engine.Engine()
    khos = eng.list_khos()
    if args.kho:
        khos = [k for k in khos if k.get("ten") == args.kho]
        if not khos:
            sys.exit(f"Không có kho tên {args.kho!r}")

    print(f"Chế độ: {'GHI THẬT' if args.sua and args.that_su else ('thử ghi' if args.sua else 'chỉ kiểm tra')}")
    tong = {}
    for k in khos:
        thu_muc = k.get("thu_muc") or ""
        if not thu_muc:
            print(f"\n### {k.get('ten')}: chưa gán thư mục, bỏ qua")
            continue
        tk = kiem_mot_kho(k.get("ten", "?"), thu_muc, args.sua, args.that_su,
                          args.gioi_han)
        for khoa, v in tk.items():
            tong[khoa] = tong.get(khoa, 0) + v

    if tong:
        print("\n=== TỔNG ===")
        for khoa in ("tong", "co_duration", "co_media", "do_duoc",
                     "thieu_file", "doi_hien_thi", "da_ghi"):
            print(f"  {khoa:<14}{tong.get(khoa, 0)}")


if __name__ == "__main__":
    main()
