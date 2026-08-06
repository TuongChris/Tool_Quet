# -*- coding: utf-8 -*-
"""
dong_goi.py — Đóng gói MÃ NGUỒN dự án để gửi audit.

Dùng danh sách CHO PHÉP (whitelist) thay vì danh sách loại trừ: chỉ những file
được liệt kê mới được đưa vào. An toàn hơn nhiều — thêm file nhạy cảm mới vào
dự án cũng không lọt ra ngoài ngoài ý muốn.

Chạy: python dong_goi.py
Kết quả: TimClipPro_source.zip ở thư mục hiện tại.
"""
import argparse
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
TU_KHOA_NHAY_CAM = (
    "credential", "secret", "token", "private_key", "google_key",
    "service_account", "service-account", "serviceaccount",
)

# --- Thư mục bỏ qua hoàn toàn ---
BO_QUA_TM = {"data", "ketqua", "bin", "__pycache__",
              ".pytest_cache", ".ruff_cache", ".git", ".venv", "venv",
              "node_modules"}

# File runtime/cá nhân không thuộc source package.
BO_QUA_FILE = {"requirements-lock.txt", "session.log", "watchlist.json"}

# --- Đuôi file được phép ---
DUOI_OK = {".py", ".md", ".txt", ".bat", ".ini", ".json", ".toml", ".yml",
           ".yaml", ".cfg", ".ps1"}
TEN_KHONG_CO_DUOI_OK = {"dockerfile", ".gitignore", ".dockerignore"}


def la_file_nhay_cam(ten: str) -> bool:
    """Nhận dạng basename nhạy cảm không phân biệt hoa/thường."""
    ten_thuong = ten.casefold()
    return ten_thuong in {x.casefold() for x in CAM} or any(
        tu_khoa in ten_thuong for tu_khoa in TU_KHOA_NHAY_CAM
    )


def nen_lay(duong_dan_tuong_doi: str) -> bool:
    phan = duong_dan_tuong_doi.replace("\\", "/").split("/")
    ten = phan[-1]
    ten_thuong = ten.casefold()
    if la_file_nhay_cam(ten) or ten_thuong in BO_QUA_FILE:
        return False
    if any(p in BO_QUA_TM for p in phan[:-1]):
        return False
    if (
        os.path.splitext(ten)[1].lower() not in DUOI_OK
        and ten_thuong not in TEN_KHONG_CO_DUOI_OK
    ):
        return False
    # Bỏ mọi file .json ở gốc trừ các file cấu hình đã biết
    if (
        len(phan) == 1
        and ten_thuong.endswith(".json")
        and ten_thuong not in {"watchlist.example.json"}
    ):
        return False
    return True


def liet_ke_source(goc_du_an: str = GOC) -> tuple[list, int]:
    """Trả danh sách file được phép và tổng byte, không ghi gì ra đĩa."""
    ds, tong = [], 0
    for goc, thu_muc, files in os.walk(goc_du_an):
        thu_muc[:] = [d for d in thu_muc if d not in BO_QUA_TM]
        for ten_file in files:
            day_du = os.path.join(goc, ten_file)
            tuong_doi = os.path.relpath(day_du, goc_du_an)
            if nen_lay(tuong_doi):
                ds.append(tuong_doi)
                tong += os.path.getsize(day_du)
    ds.sort()
    return ds, tong


def tao_goi(duong_dan_ra: str = RA, ghi_de: bool = False) -> tuple[list, int]:
    """Tạo source zip; mặc định từ chối ghi đè archive đã tồn tại."""
    duong_dan_ra = os.path.abspath(duong_dan_ra)
    if os.path.exists(duong_dan_ra) and not ghi_de:
        raise FileExistsError(
            f"File đã tồn tại: {duong_dan_ra}. Dùng --overwrite nếu thật sự muốn ghi đè."
        )

    ds, tong = liet_ke_source()
    lot = [t for t in ds if la_file_nhay_cam(os.path.basename(t))]
    if lot:
        raise RuntimeError(f"Phát hiện file nhạy cảm trong danh sách đóng gói: {lot}")

    mode = "wb" if ghi_de else "xb"
    with open(duong_dan_ra, mode) as stream:
        try:
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
                for tuong_doi in ds:
                    z.write(os.path.join(GOC, tuong_doi), tuong_doi)
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
        raise RuntimeError(f"Zip có file cấm: {xau}")
    return ds, tong


def main() -> int:
    parser = argparse.ArgumentParser(description="Đóng gói source TimClip Pro an toàn.")
    parser.add_argument("--output", default=RA, help="Đường dẫn file zip đầu ra")
    parser.add_argument("--overwrite", action="store_true", help="Cho phép ghi đè output")
    args = parser.parse_args()
    try:
        ds, tong = tao_goi(args.output, ghi_de=args.overwrite)
    except (FileExistsError, RuntimeError, OSError, zipfile.BadZipFile) as e:
        print(f"[X] {e}")
        return 1

    print(f"Sẽ đóng gói {len(ds)} file, tổng {tong/1024:.0f} KB:\n")
    for tuong_doi in ds:
        print("  ", tuong_doi)
    kich_thuoc = os.path.getsize(os.path.abspath(args.output))
    print(f"\n[OK] Đã tạo: {os.path.abspath(args.output)}")
    print(f"     Dung lượng: {kich_thuoc/1024:.0f} KB")
    print("[OK] Trong zip KHÔNG có file khoá bí mật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
