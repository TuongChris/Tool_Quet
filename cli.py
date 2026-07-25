# -*- coding: utf-8 -*-
r"""
cli.py — Giao diện DÒNG LỆNH, dùng CHUNG engine.py với giao diện web.
Hữu ích khi bạn muốn chạy tự động theo lịch (Task Scheduler) mà không cần mở trình duyệt.

  python cli.py kenh     "https://youtube.com/@TenKenh" --kho "D:\KhoClipGoc"
  python cli.py taodb    "D:\ClipGoc"
  python cli.py themclip "D:\ClipMoi"
  python cli.py youtube  https://youtu.be/xxx https://youtu.be/yyy
  python cli.py youtube  --file links.txt
  python cli.py file     "D:\VideoDai\a.mp4"
  python cli.py file     "D:\VideoDai"          (quét cả thư mục)
"""
import argparse
import os
import sys

from channel import ChannelSync
from engine import Engine, liet_ke_media

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def in_tien_do(pct, msg):
    sys.stdout.write(f"\r[{pct*100:5.1f}%] {msg[:90]:<90}")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description="TimClip Pro — bản dòng lệnh")
    ap.add_argument("lenh", choices=["kenh", "taodb", "themclip", "youtube", "file"])
    ap.add_argument("muc", nargs="*", help="Thư mục / link / đường dẫn file")
    ap.add_argument("--file", help="File .txt chứa danh sách link, mỗi dòng một link")
    ap.add_argument("--ncores", type=int, default=1)
    ap.add_argument("--kho", help="Thư mục kho clip gốc (dùng với lệnh 'kenh')")
    ap.add_argument("--limit", type=int, help="Chỉ lấy N video mới nhất")
    a = ap.parse_args()

    eng = Engine()
    eng.config.ncores = a.ncores

    if a.lenh == "kenh":
        if not a.muc or not a.kho:
            ap.error('Dùng: python cli.py kenh "https://youtube.com/@Kenh" --kho "D:\\KhoClipGoc"')
        cs = ChannelSync(a.kho)
        r = cs.sync(a.muc[0], a.limit, in_tien_do)
        print(f"\nXONG: tải mới {r['moi']} video, bỏ qua {r['bo_qua']} video đã có.")
        if r["loi"]:
            print("Lỗi:", *r["loi"][:10], sep="\n  - ")
        print("Tiếp theo: python cli.py themclip \"%s\"" % a.kho)
        return

    if a.lenh in ("taodb", "themclip"):
        if not a.muc:
            ap.error("Thiếu đường dẫn thư mục clip gốc.")
        r = eng.build_database(a.muc[0], "new" if a.lenh == "taodb" else "add", in_tien_do)
        print(f"\nXONG: {r['so_clip']} clip trong {r['giay']:.0f} giây.")
        return

    if a.lenh == "youtube":
        nguon = list(a.muc)
        if a.file:
            with open(a.file, encoding="utf-8-sig") as f:
                nguon += [x.strip() for x in f
                          if x.strip() and not x.strip().startswith("#")]
        if not nguon:
            ap.error("Chưa có link nào. Dùng --file links.txt hoặc liệt kê link trực tiếp.")
        ket = eng.scan_many(nguon, "youtube", in_tien_do)
    else:
        nguon = []
        for m in a.muc:
            nguon += liet_ke_media(m) if os.path.isdir(m) else [m]
        if not nguon:
            ap.error("Không tìm thấy file nào để quét.")
        ket = eng.scan_many(nguon, "file", in_tien_do)

    print("\n" + "=" * 78)
    for kq in ket:
        print(f"\n▸ {kq.source_name}")
        if kq.status != "ok":
            print(f"   LỖI: {kq.note}")
        elif not kq.matches:
            print("   Không tìm thấy clip gốc nào.")
        for m in kq.matches:
            print(f"   • {m.clip} | {m.start_hhmmss} → {m.end_hhmmss} "
                  f"| {m.hashes} hash ({m.confidence})")
    print("\n===> Báo cáo CSV:", eng.export_csv(ket))


if __name__ == "__main__":
    main()
