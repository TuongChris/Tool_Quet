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
  python cli.py watch
"""
import argparse
import os
import sys

import don_dep
import watch
from channel import ChannelSync
from dung_lai import YeuCauDung
from engine import Engine, liet_ke_media

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def in_tien_do(pct, msg):
    sys.stdout.write(f"\r[{pct*100:5.1f}%] {msg[:90]:<90}")
    sys.stdout.flush()


def _file_dung_mac_dinh() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data",
        "DUNG",
    )


def main():
    ap = argparse.ArgumentParser(description="TimClip Pro — bản dòng lệnh")
    ap.add_argument(
        "lenh",
        choices=[
            "kenh",
            "taodb",
            "themclip",
            "youtube",
            "file",
            "watch",
            "vameta",
            "dondep",
            "dung",
        ],
    )
    ap.add_argument("muc", nargs="*", help="Thư mục / link / đường dẫn file")
    ap.add_argument(
        "--file",
        help=(
            "File link cho lệnh youtube; file watchlist cho lệnh watch "
            "(mặc định: watchlist.json)"
        ),
    )
    ap.add_argument("--ncores", type=int, default=1)
    ap.add_argument(
        "--kho",
        help="Thư mục kho clip gốc (dùng với lệnh kenh/vameta)",
    )
    ap.add_argument("--limit", type=int, help="Chỉ lấy N video mới nhất")
    ap.add_argument("--sheet", default="", help="Link Google Sheet cho lệnh watch")
    ap.add_argument(
        "--gioi-han",
        type=int,
        default=0,
        help="Số video tối đa cho lệnh watch; 0 = dùng giá trị trong file",
    )
    ap.add_argument(
        "--dang-doc",
        action="store_true",
        help="Xuất báo cáo watch theo dạng dọc cũ",
    )
    ap.add_argument(
        "--xem-truoc",
        action="store_true",
        help="Chỉ xem các file sẽ xóa với lệnh dondep",
    )
    a = ap.parse_args()

    if a.lenh == "dung":
        file_dung = _file_dung_mac_dinh()
        os.makedirs(os.path.dirname(file_dung), exist_ok=True)
        with open(file_dung, "w", encoding="utf-8") as f:
            f.write("Yêu cầu dừng từ CLI.\n")
        print(f"Đã gửi yêu cầu dừng qua file: {file_dung}")
        return

    if a.lenh == "vameta":
        if not a.kho:
            ap.error("Lệnh vameta cần --kho trỏ tới thư mục kho clip gốc.")
        ket_qua = ChannelSync(a.kho).va_metadata(in_tien_do)
        print(
            f"\nXONG: đã vá {ket_qua['da_va']}/{ket_qua['tong']} mục metadata, "
            f"bỏ qua {ket_qua['bo_qua']} mục đã đủ."
        )
        if ket_qua["loi"]:
            print("Lỗi:", *ket_qua["loi"], sep="\n  - ")
        return

    eng = Engine()
    eng.config.ncores = a.ncores

    if a.lenh == "dondep":
        ket_qua = don_dep.don_kho_dem(
            eng.dl_dir,
            max_gb=eng.config.dem_max_gb,
            max_ngay=eng.config.dem_max_ngay,
            thuc_hien=not a.xem_truoc,
        )
        hanh_dong = "Sẽ xóa" if a.xem_truoc else "Đã xóa"
        print(
            f"Kho đệm: {ket_qua['tong_file']} file, "
            f"{ket_qua['tong_gb']:.3f} GB.\n"
            f"{hanh_dong}: {ket_qua['xoa_file']} file, "
            f"{ket_qua['xoa_gb']:.3f} GB."
        )
        if ket_qua["loi"]:
            print("Lỗi:", *ket_qua["loi"], sep="\n  - ")
        return

    if a.lenh == "watch":
        watchlist_path = a.file or "watchlist.json"
        wl = watch.doc_watchlist(watchlist_path)
        dung_lai = YeuCauDung(
            eng,
            os.path.join(eng.data_dir, "DUNG"),
        )
        dung_lai.bat_tin_hieu()
        if not wl.muc:
            print(
                f"Không có mục theo dõi trong {watchlist_path}.\n"
                "Hãy tạo file watchlist.json theo mẫu:\n"
                "{\n"
                '  "muc": [\n'
                "    {\n"
                '      "loai": "kenh",\n'
                '      "url": "https://www.youtube.com/@TenKenh",\n'
                '      "ghi_chu": "Kênh cần theo dõi",\n'
                '      "bat": true\n'
                "    },\n"
                "    {\n"
                '      "loai": "link",\n'
                '      "url": "https://youtu.be/dQw4w9WgXcQ",\n'
                '      "ghi_chu": "",\n'
                '      "bat": true\n'
                "    }\n"
                "  ],\n"
                '  "kho": "Kho mặc định",\n'
                '  "gioi_han_moi_lan": 20\n'
                "}"
            )
            dung_lai.don_file_dung()
            return
        if a.gioi_han > 0:
            wl.gioi_han_moi_lan = a.gioi_han
        try:
            bc = watch.chay_giam_sat(
                eng,
                wl,
                in_tien_do,
                sheet_link=a.sheet,
                dang_ngang=not a.dang_doc,
                dung_lai=dung_lai,
            )
        finally:
            dung_lai.don_file_dung()
        print("\n" + bc.tom_tat())
        if bc.loi:
            raise SystemExit(1)
        return

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
