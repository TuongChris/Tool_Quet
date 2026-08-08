# -*- coding: utf-8 -*-
"""dong_goi_may_chay.py — Đóng gói bản CHẠY ĐƯỢC để đem sang máy khác.

KHÁC GÌ `dong_goi.py`?

`dong_goi.py` chỉ đóng gói MÃ NGUỒN để gửi audit. Bản này gói thêm những thứ máy
kia cần để quét được ngay: kho vân tay, metadata clip gốc, cấu hình, ffmpeg.

CÁI GÌ CẦN VÀ CÁI GÌ KHÔNG

Quét KHÔNG cần file audio gốc. `kho_thu_muc` chỉ được đọc để lấy `clips_meta.json`;
`liet_ke_media()` duy nhất chạy trong `build_database()` tức lúc TẠO vân tay. Đo
trên kho hiện tại:

    cần   : kho vân tay .pklz  343 MB + metadata 1,6 MB + bin 195 MB
    KHÔNG : clip gốc .opus 23 GB + data/downloads 173 GB

Nhờ vậy gói chỉ khoảng nửa GB thay vì gần 200 GB.

AN TOÀN

Dùng chung bộ nhận dạng file nhạy cảm với `dong_goi.py` — một nguồn sự thật duy
nhất. `google_key.json` và mọi file có từ khoá bí mật KHÔNG BAO GIỜ được đóng gói,
kể cả khi người dùng yêu cầu. Khoá Google phải tự chép sang máy kia bằng kênh riêng.

CHẠY

    python dong_goi_may_chay.py --kho SML --kho Cory
    python dong_goi_may_chay.py --kho SML --khong-kem-ffmpeg
    python dong_goi_may_chay.py --kho SML --liet-ke      # chỉ xem, không tạo file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile

from dong_goi import GOC, la_file_nhay_cam, liet_ke_source
from luu_tru import doc_json_an_toan

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Thư mục trong gói chứa metadata clip gốc, thay cho D:\ClipGoc* của máy nguồn.
THU_MUC_META = "kho_meta"


def _kich_thuoc(duong_dan: str) -> int:
    try:
        return os.path.getsize(duong_dan)
    except OSError:
        return 0


def _doc_khos(data_dir: str) -> dict:
    return doc_json_an_toan(os.path.join(data_dir, "khos.json"),
                            {"dang_dung": "", "danh_sach": []})


def gom_thanh_phan(ten_kho: list, kem_ffmpeg: bool,
                   goc: str = GOC) -> tuple[list, list]:
    """Trả (danh sách (đường_dẫn_thật, tên_trong_zip), cảnh_báo).

    Hàm thuần liệt kê — không ghi gì ra đĩa, nên test được trực tiếp.
    """
    data_dir = os.path.join(goc, "data")
    khos = _doc_khos(data_dir)
    theo_ten = {k.get("ten"): k for k in khos.get("danh_sach", [])}

    muc: list[tuple[str, str]] = []
    canh_bao: list[str] = []

    # 1) Mã nguồn — dùng đúng whitelist của dong_goi.py
    for tuong_doi in liet_ke_source(goc)[0]:
        muc.append((os.path.join(goc, tuong_doi), tuong_doi))

    # 2) Kho vân tay + metadata clip gốc
    danh_sach_moi = []
    for ten in ten_kho:
        k = theo_ten.get(ten)
        if not k:
            canh_bao.append(f"Không có kho tên «{ten}» trong khos.json — bỏ qua.")
            continue
        db = k.get("db") or ""
        db_that = os.path.join(data_dir, db)
        if not os.path.isfile(db_that):
            canh_bao.append(f"Kho «{ten}»: không thấy file vân tay {db} — bỏ qua.")
            continue
        muc.append((db_that, f"data/{db}"))

        thu_muc = k.get("thu_muc") or ""
        meta_that = os.path.join(thu_muc, "clips_meta.json") if thu_muc else ""
        if meta_that and os.path.isfile(meta_that):
            muc.append((meta_that, f"{THU_MUC_META}/{ten}/clips_meta.json"))
        else:
            canh_bao.append(
                f"Kho «{ten}»: không thấy clips_meta.json — báo cáo sẽ thiếu "
                "tên/link/thời lượng clip gốc."
            )
        # `thu_muc` được đặt lại lúc cài trên máy đích (thiet_lap_may_phu.py).
        danh_sach_moi.append({"ten": ten, "thu_muc": "", "db": db,
                              **({"shifts": k["shifts"]} if "shifts" in k else {})})

    if not danh_sach_moi:
        canh_bao.append("KHÔNG có kho nào hợp lệ — gói sẽ không quét được gì.")

    # 3) Snapshot metadata (nguồn phụ khi clips_meta thiếu mục)
    thu_muc_snapshot = os.path.join(data_dir, "metadata")
    if os.path.isdir(thu_muc_snapshot):
        giu = {k.get("db", "").rsplit(".", 1)[0] for k in danh_sach_moi}
        for ten_file in sorted(os.listdir(thu_muc_snapshot)):
            if ten_file.rsplit(".", 1)[0] in giu:
                muc.append((os.path.join(thu_muc_snapshot, ten_file),
                            f"data/metadata/{ten_file}"))

    # 4) ffmpeg/ffprobe — máy đích khỏi phải tải 100 MB
    if kem_ffmpeg:
        thu_muc_bin = os.path.join(goc, "bin")
        co = False
        for ten_file in ("ffmpeg.exe", "ffprobe.exe"):
            p = os.path.join(thu_muc_bin, ten_file)
            if os.path.isfile(p):
                muc.append((p, f"bin/{ten_file}"))
                co = True
        if not co:
            canh_bao.append("Không thấy bin/ffmpeg.exe — máy đích sẽ tự tải khi cài.")

    # Chốt an toàn: không file nhạy cảm nào được lọt vào, dù đến từ nguồn nào.
    lot = [t for _, t in muc if la_file_nhay_cam(os.path.basename(t))]
    if lot:
        raise RuntimeError(f"Phát hiện file nhạy cảm trong danh sách: {lot}")

    return muc, canh_bao


def noi_dung_sinh_them(ten_kho: list, goc: str = GOC) -> dict:
    """Các file được SINH RA cho gói (không chép nguyên từ máy nguồn)."""
    data_dir = os.path.join(goc, "data")
    khos = _doc_khos(data_dir)
    theo_ten = {k.get("ten"): k for k in khos.get("danh_sach", [])}

    danh_sach = []
    for ten in ten_kho:
        k = theo_ten.get(ten)
        if not k or not os.path.isfile(os.path.join(data_dir, k.get("db") or "")):
            continue
        m = {"ten": ten, "thu_muc": "", "db": k["db"]}
        if "shifts" in k:
            m["shifts"] = k["shifts"]
        danh_sach.append(m)

    ra = {
        "data/khos.json": json.dumps(
            {"dang_dung": danh_sach[0]["ten"] if danh_sach else "",
             "danh_sach": danh_sach},
            ensure_ascii=False, indent=2),
    }

    # Cấu hình: giữ tham số quét, bỏ các đường dẫn riêng của máy nguồn.
    cfg = doc_json_an_toan(os.path.join(data_dir, "cau_hinh.json"), {})
    if isinstance(cfg, dict) and cfg:
        cfg = dict(cfg)
        for khoa in ("kho_dir", "thu_muc_quet_gan_nhat"):
            cfg.pop(khoa, None)
        ra["data/cau_hinh.json"] = json.dumps(cfg, ensure_ascii=False, indent=2)
    return ra


def tao_goi(duong_dan_ra: str, ten_kho: list, kem_ffmpeg: bool = True,
            ghi_de: bool = False, goc: str = GOC) -> tuple[list, list, int]:
    duong_dan_ra = os.path.abspath(duong_dan_ra)
    if os.path.exists(duong_dan_ra) and not ghi_de:
        raise FileExistsError(
            f"File đã tồn tại: {duong_dan_ra}. Dùng --overwrite nếu thật sự muốn ghi đè.")

    muc, canh_bao = gom_thanh_phan(ten_kho, kem_ffmpeg, goc)
    sinh_them = noi_dung_sinh_them(ten_kho, goc)
    tong = sum(_kich_thuoc(p) for p, _ in muc)

    with open(duong_dan_ra, "wb" if ghi_de else "xb") as stream:
        try:
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
                for that, trong_zip in muc:
                    z.write(that, trong_zip)
                for trong_zip, noi_dung in sinh_them.items():
                    z.writestr(trong_zip, noi_dung)
        except BaseException:
            stream.close()
            try:
                os.remove(duong_dan_ra)
            except OSError:
                pass
            raise

    with zipfile.ZipFile(duong_dan_ra) as z:
        xau = [n for n in z.namelist() if la_file_nhay_cam(os.path.basename(n))]
    if xau:
        os.remove(duong_dan_ra)
        raise RuntimeError(f"Zip có file cấm: {xau}")
    return muc, canh_bao, tong


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kho", action="append", default=[],
                    help="Tên kho cần kèm; lặp lại cờ này cho nhiều kho")
    ap.add_argument("--output", default="", help="Đường dẫn zip đầu ra")
    ap.add_argument("--khong-kem-ffmpeg", action="store_true",
                    help="Bỏ bin/ffmpeg.exe cho gói nhẹ; máy đích tự tải khi cài")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--liet-ke", action="store_true",
                    help="Chỉ liệt kê sẽ đóng gói gì, không tạo file")
    args = ap.parse_args()

    if not args.kho:
        khos = _doc_khos(os.path.join(GOC, "data"))
        co = [k.get("ten") for k in khos.get("danh_sach", []) if k.get("ten")]
        print("Phải chọn ít nhất một kho bằng --kho.")
        print(f"Các kho đang có: {', '.join(co) or '(không có)'}")
        return 1

    kem_ffmpeg = not args.khong_kem_ffmpeg
    ra = args.output or os.path.join(
        GOC, "TimClipPro_MayChay_" + "_".join(args.kho) + ".zip")

    if args.liet_ke:
        muc, canh_bao = gom_thanh_phan(args.kho, kem_ffmpeg)
        tong = sum(_kich_thuoc(p) for p, _ in muc)
        nhom: dict[str, list[int]] = {}
        for that, trong_zip in muc:
            khoa = trong_zip.split("/")[0] if "/" in trong_zip else "(mã nguồn gốc)"
            n = nhom.setdefault(khoa, [0, 0])
            n[0] += 1
            n[1] += _kich_thuoc(that)
        print(f"Sẽ đóng gói {len(muc)} file, tổng {tong/1e6:.0f} MB:\n")
        for khoa, (so, byte) in sorted(nhom.items(), key=lambda kv: -kv[1][1]):
            print(f"  {khoa:<24}{so:>5} file{byte/1e6:>9.1f} MB")
        for c in canh_bao:
            print(f"\n  [!] {c}")
        return 0

    try:
        muc, canh_bao, tong = tao_goi(ra, args.kho, kem_ffmpeg, args.overwrite)
    except (FileExistsError, RuntimeError, OSError, zipfile.BadZipFile) as e:
        print(f"[X] {e}")
        return 1

    print(f"[OK] Đã tạo: {ra}")
    print(f"     {len(muc)} file, nguồn {tong/1e6:.0f} MB, "
          f"zip {_kich_thuoc(ra)/1e6:.0f} MB")
    print("[OK] Trong zip KHÔNG có khoá bí mật.")
    for c in canh_bao:
        print(f"[!] {c}")
    print("\nBước tiếp theo trên máy đích: xem docs/TRIEN_KHAI_MAY_PHU.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
