# -*- coding: utf-8 -*-
"""
dong_goi.py — Đóng gói MÃ NGUỒN dự án để gửi audit.

Dùng danh sách CHO PHÉP (whitelist) thay vì danh sách loại trừ: chỉ những file
được liệt kê mới được đưa vào. An toàn hơn nhiều — thêm file nhạy cảm mới vào
dự án cũng không lọt ra ngoài ngoài ý muốn.

Whitelist đuôi file KHÔNG đủ để chứng minh an toàn (audit TCP-11): ``cookies.txt``
có đuôi ``.txt`` hợp lệ, ``credentials/client.json`` có đuôi ``.json`` hợp lệ. Vì vậy
mỗi file còn phải qua ba lớp nữa:

1. Từng THÀNH PHẦN đường dẫn — thư mục ``credentials/``, ``secrets/``, ``.ssh/``…
2. Tên file — cookie, ``.env`` ở mọi cấp, khoá ``.pem/.key/.p12``, dữ liệu chạy riêng
   của máy (``clips_meta.json``, ``khos.json``, ``cau_hinh.json``…).
3. NỘI DUNG của file dữ liệu (``.json/.txt/.toml/.ini/.cfg/.yml/.yaml``) — khoá
   PEM, khoá service account, cookie Netscape. File ``.py``/``.md`` không bị quét
   nội dung vì test và tài liệu của chính dự án chứa marker giả để kiểm thử.

Cuối cùng ZIP được đọc lại bằng ``kiem_zip_doc_lap()`` — một bộ kiểm riêng, không
gọi lại bộ lọc ở trên, để một lỗi trong bộ lọc không tự xác nhận chính nó.

Chạy: python dong_goi.py
Kết quả: TimClipPro_source.zip ở thư mục hiện tại.
"""
import argparse
import os
import re
import stat
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
# Đuôi file khoá/chứng thư: không bao giờ là mã nguồn của dự án này.
DUOI_KHOA = {".pem", ".key", ".p12", ".pfx", ".ppk", ".jks", ".keystore", ".kdbx"}

# Thư mục mà MỌI thứ bên trong đều bị coi là nhạy cảm, ở bất kỳ cấp nào.
THU_MUC_NHAY_CAM = {"credentials", "credential", "secrets", "secret", ".ssh",
                    ".aws", ".gnupg", "keys", "private", "cookies", "cookie"}

# Dữ liệu chạy riêng của từng máy — đã nằm trong .gitignore, không phải mã nguồn.
FILE_DU_LIEU_RIENG = {"clips_meta.json", "downloaded.txt", "khos.json",
                      "cau_hinh.json", "watchlist.json", "lichsu.db"}

# --- Thư mục bỏ qua hoàn toàn ---
BO_QUA_TM = {"data", "ketqua", "bin", "__pycache__",
              ".pytest_cache", ".ruff_cache", ".git", ".venv", "venv",
              "node_modules", ".claude", ".worktrees", "_tam", "_hong"}

# Môi trường ảo có thể mang tên bất kỳ. Liệt kê cứng là không đủ: `.venv-claude`
# từng lọt qua và kéo theo 7.214 file / 108 MB site-packages vào gói "mã nguồn".
# Bắt theo TIỀN TỐ tên để không phải đoán trước mọi biến thể.
TIEN_TO_MOI_TRUONG_AO = (".venv", "venv", ".env", "env-", "virtualenv")


def la_thu_muc_bo_qua(ten: str) -> bool:
    """Thư mục này có bị loại hoàn toàn khỏi gói không?"""
    ten_thuong = ten.casefold()
    if ten_thuong in {x.casefold() for x in BO_QUA_TM}:
        return True
    return any(ten_thuong.startswith(t) for t in TIEN_TO_MOI_TRUONG_AO)

# File runtime/cá nhân không thuộc source package.
BO_QUA_FILE = {"requirements-lock.txt", "session.log", "watchlist.json"}

# --- Đuôi file được phép ---
# `.gs` là Google Apps Script chạy trên trang tính báo cáo — mã nguồn thật, từng bị
# bỏ sót khỏi gói audit chỉ vì đuôi không có trong danh sách.
DUOI_OK = {".py", ".md", ".txt", ".bat", ".ini", ".json", ".toml", ".yml",
           ".yaml", ".cfg", ".ps1", ".gs"}
# LICENSE đi kèm thư viện nhúng (audfprint, MIT) phải theo mã khi phân phối lại.
TEN_KHONG_CO_DUOI_OK = {"dockerfile", ".gitignore", ".dockerignore", "license"}

# File dữ liệu: loại duy nhất bị quét NỘI DUNG (xem docstring đầu module).
DUOI_DU_LIEU = {".json", ".txt", ".toml", ".ini", ".cfg", ".yml", ".yaml"}
MAU_NOI_DUNG_NHAY_CAM = (
    ("khoá PEM", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("khoá JSON", re.compile(r'"private_key"\s*:')),
    ("service account", re.compile(r'"type"\s*:\s*"service_account"')),
    ("client secret", re.compile(r'"client_secret"\s*:')),
    ("refresh token", re.compile(r'"refresh_token"\s*:')),
    ("cookie Netscape", re.compile(r"(?im)^#\s*(?:netscape\s+)?http\s+cookie\s+file")),
    ("dòng cookie", re.compile(
        r"(?m)^[^\t#\r\n]+\t(?:TRUE|FALSE)\t[^\t\r\n]*\t(?:TRUE|FALSE)\t\d+\t[^\t\r\n]+\t")),
)
GIOI_HAN_QUET_NOI_DUNG = 8 * 1024 * 1024


def la_file_nhay_cam(ten: str) -> bool:
    """Nhận dạng basename nhạy cảm không phân biệt hoa/thường."""
    ten_thuong = ten.casefold()
    duoi = os.path.splitext(ten_thuong)[1]
    if ten_thuong in {x.casefold() for x in CAM} or any(
        tu_khoa in ten_thuong for tu_khoa in TU_KHOA_NHAY_CAM
    ):
        return True
    if duoi in DUOI_KHOA:
        return True
    if ten_thuong == ".env" or ten_thuong.startswith(".env."):
        return True
    # File cookie: chặn mọi file DỮ LIỆU có chữ cookie. Không chặn .py/.md — test
    # `test_cookie_khong_ro_ri.py` của chính dự án là mã nguồn hợp lệ.
    return "cookie" in ten_thuong and duoi not in {".py", ".md"}


def la_duong_dan_nhay_cam(duong_dan_tuong_doi: str) -> bool:
    """Tên file HOẶC một thư mục cha bất kỳ thuộc nhóm nhạy cảm."""
    phan = [p for p in duong_dan_tuong_doi.replace("\\", "/").split("/") if p]
    if not phan:
        return False
    if any(p.casefold() in THU_MUC_NHAY_CAM for p in phan[:-1]):
        return True
    return la_file_nhay_cam(phan[-1])


def nen_lay(duong_dan_tuong_doi: str) -> bool:
    phan = duong_dan_tuong_doi.replace("\\", "/").split("/")
    ten = phan[-1]
    ten_thuong = ten.casefold()
    if la_duong_dan_nhay_cam(duong_dan_tuong_doi) or ten_thuong in BO_QUA_FILE:
        return False
    if ten_thuong in FILE_DU_LIEU_RIENG:
        return False
    if any(la_thu_muc_bo_qua(p) for p in phan[:-1]):
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


def ly_do_noi_dung_nhay_cam(du_lieu: bytes) -> str:
    """Trả mô tả loại bí mật tìm thấy trong nội dung, rỗng nếu sạch.

    Chỉ trả TÊN LOẠI, không bao giờ trả đoạn nội dung khớp.
    """
    van_ban = du_lieu[:GIOI_HAN_QUET_NOI_DUNG].decode("utf-8", errors="replace")
    for ten, mau in MAU_NOI_DUNG_NHAY_CAM:
        if mau.search(van_ban):
            return ten
    return ""


def _noi_dung_nhay_cam(duong_dan: str) -> str:
    if os.path.splitext(duong_dan)[1].lower() not in DUOI_DU_LIEU:
        return ""
    try:
        with open(duong_dan, "rb") as f:
            return ly_do_noi_dung_nhay_cam(f.read(GIOI_HAN_QUET_NOI_DUNG))
    except OSError:
        return "không đọc được để kiểm tra"


def _la_lien_ket(duong_dan: str) -> bool:
    """Symlink, junction hay reparse point bất kỳ — không bao giờ đi theo.

    Một junction trong dự án trỏ ra ``C:\\Users\\...`` sẽ kéo cả thư mục ngoài vào gói.
    """
    if os.path.islink(duong_dan):
        return True
    la_junction = getattr(os.path, "isjunction", None)
    if la_junction is not None and la_junction(duong_dan):
        return True
    try:
        thuoc_tinh = getattr(os.lstat(duong_dan), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(thuoc_tinh & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def liet_ke_source(goc_du_an: str = GOC) -> tuple[list, int]:
    """Trả danh sách file được phép và tổng byte, không ghi gì ra đĩa."""
    ds, tong = [], 0
    for goc, thu_muc, files in os.walk(goc_du_an):
        thu_muc[:] = [
            d for d in thu_muc
            if not la_thu_muc_bo_qua(d)
            and d.casefold() not in THU_MUC_NHAY_CAM
            and not _la_lien_ket(os.path.join(goc, d))
        ]
        for ten_file in files:
            day_du = os.path.join(goc, ten_file)
            tuong_doi = os.path.relpath(day_du, goc_du_an)
            if not nen_lay(tuong_doi) or _la_lien_ket(day_du):
                continue
            if _noi_dung_nhay_cam(day_du):
                continue
            ds.append(tuong_doi)
            tong += os.path.getsize(day_du)
    ds.sort()
    return ds, tong


def kiem_zip_doc_lap(duong_dan_zip: str) -> list[str]:
    """Đọc lại ZIP ĐÃ TẠO và liệt kê entry nhạy cảm. Rỗng nghĩa là sạch.

    Cố ý KHÔNG gọi ``nen_lay``/``liet_ke_source``: đây là lớp kiểm thứ hai trên
    byte thật trong ZIP. Chỉ trả tên entry và loại vi phạm, không trả nội dung.
    """
    loi = []
    with zipfile.ZipFile(duong_dan_zip) as z:
        for info in z.infolist():
            ten = info.filename
            phan = [p for p in ten.replace("\\", "/").split("/") if p]
            if not phan or info.is_dir():
                continue
            if any(p.casefold() in THU_MUC_NHAY_CAM for p in phan[:-1]):
                loi.append(f"{ten}: nằm trong thư mục nhạy cảm")
                continue
            if la_file_nhay_cam(phan[-1]):
                loi.append(f"{ten}: tên file nhạy cảm")
                continue
            if os.path.splitext(phan[-1])[1].lower() in DUOI_DU_LIEU:
                ly_do = ly_do_noi_dung_nhay_cam(z.read(info))
                if ly_do:
                    loi.append(f"{ten}: nội dung giống {ly_do}")
    return loi


def tao_goi(duong_dan_ra: str = RA, ghi_de: bool = False,
            goc: str = GOC) -> tuple[list, int]:
    """Tạo source zip; mặc định từ chối ghi đè archive đã tồn tại."""
    duong_dan_ra = os.path.abspath(duong_dan_ra)
    if os.path.exists(duong_dan_ra) and not ghi_de:
        raise FileExistsError(
            f"File đã tồn tại: {duong_dan_ra}. Dùng --overwrite nếu thật sự muốn ghi đè."
        )

    ds, tong = liet_ke_source(goc)
    lot = [t for t in ds if la_duong_dan_nhay_cam(t)]
    if lot:
        raise RuntimeError(f"Phát hiện file nhạy cảm trong danh sách đóng gói: {lot}")

    mode = "wb" if ghi_de else "xb"
    with open(duong_dan_ra, mode) as stream:
        try:
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
                for tuong_doi in ds:
                    z.write(os.path.join(goc, tuong_doi),
                            tuong_doi.replace("\\", "/"))
        except BaseException:
            stream.close()
            try:
                os.remove(duong_dan_ra)
            except OSError:
                pass
            raise

    xau = kiem_zip_doc_lap(duong_dan_ra)
    if xau:
        os.remove(duong_dan_ra)
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
