# -*- coding: utf-8 -*-
"""Gói mã nguồn KHÔNG được mang cookie, khoá hay cấu hình riêng tư (TCP-11).

Danh sách kỳ vọng trong file này được viết TAY, độc lập với bộ lọc của
``dong_goi``: test đối chiếu nội dung ZIP thật với danh sách đó, không hỏi lại
chính helper đang được kiểm tra. Mọi "bí mật" ở đây đều là marker giả.
"""

import json
import os
import subprocess
import zipfile

import pytest

import dong_goi
import dong_goi_may_chay as dgmc

MARKER_COOKIE = "TIMCLIP-SYNTH-COOKIE-7f3a"
MARKER_KHOA = "TIMCLIP-SYNTH-KEY-91c2"
MARKER_ENV = "TIMCLIP-SYNTH-ENV-55d0"
MARKER_NGOAI = "TIMCLIP-SYNTH-OUTSIDE-0b8e"
PEM = (
    "-----BEGIN PRIVATE KEY-----\n" + MARKER_KHOA + "\n-----END PRIVATE KEY-----\n"
)


def _ghi(path, noi_dung: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(noi_dung, encoding="utf-8")


def _du_an_co_bi_mat(goc):
    """Cây dự án có cả mã nguồn hợp lệ lẫn đủ kiểu file nhạy cảm."""
    # --- phải được đóng gói ---
    _ghi(goc / "engine.py", "X = 1\n")
    _ghi(goc / "app.py", "import engine\n")
    _ghi(goc / "watchlist.example.json", json.dumps({"muc": [], "kho": ""}))
    _ghi(goc / "docs" / "huong_dan.md", "# Hướng dẫn\n")
    _ghi(goc / "apps_script" / "File02_Menu.gs", "function onOpen() {}\n")
    # Test của chính dự án nói về cookie; tên có chữ cookie nhưng là MÃ NGUỒN.
    _ghi(goc / "tests" / "test_cookie_khong_ro_ri.py",
         "def test_x():\n    assert 'cookie' in 'cookie'\n")
    _ghi(goc / "requirements.txt", "numpy\n")

    # --- tuyệt đối không được đóng gói ---
    _ghi(goc / "cookies.txt",
         "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\t"
         + MARKER_COOKIE + "\n")
    _ghi(goc / "YouTube_cookies.txt", "# HTTP Cookie File\n" + MARKER_COOKIE + "\n")
    _ghi(goc / "du_lieu" / "Mixed_Case_COOKIES.TXT", MARKER_COOKIE + "\n")
    _ghi(goc / "credentials" / "client_b.json",
         json.dumps({"private_key": MARKER_KHOA}))
    _ghi(goc / "nested" / ".env", "API=" + MARKER_ENV + "\n")
    _ghi(goc / "nested" / "sau" / ".env.local", "API=" + MARKER_ENV + "\n")
    # Tên KHÔNG chứa chữ "secret/key/token": chỉ nội dung mới lộ ra đây là khoá.
    _ghi(goc / "cau_hinh_mau" / "du_an_prod.json", json.dumps({
        "type": "service_account", "private_key": PEM,
    }))
    _ghi(goc / "ghi_chu" / "may_chu.txt", "khoá cũ:\n" + PEM)
    _ghi(goc / "khoa_rieng.pem", PEM)


KY_VONG_NGUON = {
    "engine.py",
    "app.py",
    "watchlist.example.json",
    "docs/huong_dan.md",
    "apps_script/File02_Menu.gs",
    "tests/test_cookie_khong_ro_ri.py",
    "requirements.txt",
}
MARKERS = (MARKER_COOKIE, MARKER_KHOA, MARKER_ENV, MARKER_NGOAI)


def _noi_dung_zip(duong_dan) -> dict:
    with zipfile.ZipFile(duong_dan) as z:
        return {ten: z.read(ten) for ten in z.namelist()}


def _khong_co_marker(noi_dung: dict) -> None:
    for ten, du_lieu in noi_dung.items():
        van_ban = du_lieu.decode("utf-8", errors="replace")
        for marker in MARKERS:
            assert marker not in van_ban, f"marker {marker} lọt vào {ten}"


def test_goi_nguon_chi_chua_dung_ma_nguon_va_khong_marker_nao(tmp_path):
    goc = tmp_path / "du an"
    _du_an_co_bi_mat(goc)
    ra = tmp_path / "nguon.zip"

    dong_goi.tao_goi(str(ra), goc=str(goc))

    noi_dung = _noi_dung_zip(ra)
    assert set(noi_dung) == KY_VONG_NGUON
    _khong_co_marker(noi_dung)


@pytest.mark.skipif(os.name != "nt", reason="junction là khái niệm NTFS")
def test_junction_tro_ra_ngoai_du_an_khong_bi_di_theo(tmp_path):
    goc = tmp_path / "du an"
    _du_an_co_bi_mat(goc)
    ngoai = tmp_path / "ngoai du an"
    _ghi(ngoai / "ghi_chu.md", MARKER_NGOAI + "\n")
    r = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(goc / "noi_ra_ngoai"), str(ngoai)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        pytest.skip(f"không tạo được junction: {r.stdout} {r.stderr}")
    ra = tmp_path / "nguon.zip"

    dong_goi.tao_goi(str(ra), goc=str(goc))

    noi_dung = _noi_dung_zip(ra)
    assert set(noi_dung) == KY_VONG_NGUON
    _khong_co_marker(noi_dung)


def test_symlink_toi_file_bi_mat_khong_bi_dong_goi(tmp_path):
    goc = tmp_path / "du an"
    _du_an_co_bi_mat(goc)
    try:
        os.symlink(goc / "cookies.txt", goc / "ghi_chu_vo_hai.txt")
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"máy không cho tạo symlink: {e}")
    ra = tmp_path / "nguon.zip"

    dong_goi.tao_goi(str(ra), goc=str(goc))

    noi_dung = _noi_dung_zip(ra)
    assert "ghi_chu_vo_hai.txt" not in noi_dung
    _khong_co_marker(noi_dung)


@pytest.mark.parametrize("duong_dan", [
    "cookies.txt",
    "YouTube_cookies.txt",
    "www.youtube.com_cookies.txt",
    "du_lieu/Mixed_Case_COOKIES.TXT",
    "credentials/client_b.json",
    "Credentials/ghi_chu.md",
    "nested/.env",
    "nested/sau/.env.local",
    "khoa_rieng.pem",
    "khoa.KEY",
    "chung_chi.p12",
])
def test_ten_hoac_thanh_phan_duong_dan_nhay_cam_bi_tu_choi(duong_dan):
    assert dong_goi.nen_lay(duong_dan) is False


@pytest.mark.parametrize("duong_dan", [
    "apps_script/File02_Menu.gs",
    "tests/test_cookie_khong_ro_ri.py",
    "tests/test_cookie_het_han.py",
    "watchlist.example.json",
])
def test_ma_nguon_hop_le_van_duoc_lay(duong_dan):
    assert dong_goi.nen_lay(duong_dan) is True


def test_hau_kiem_zip_doc_lap_bat_duoc_file_lot_vao(tmp_path):
    """Hậu kiểm không được gọi lại bộ lọc: zip dựng TAY có cookie vẫn phải bị bắt."""
    ra = tmp_path / "goi_tay.zip"
    with zipfile.ZipFile(ra, "w") as z:
        z.writestr("engine.py", "X = 1\n")
        z.writestr("ghi_chu.txt", "# Netscape HTTP Cookie File\n" + MARKER_COOKIE)
    loi = dong_goi.kiem_zip_doc_lap(str(ra))
    assert loi and any("ghi_chu.txt" in dong for dong in loi)


@pytest.mark.parametrize("ten", [
    "cookies.txt",
    "YouTube_cookies.txt",
    "www.youtube.com_cookies.txt",
    "credentials/client_b.json",
    "nested/.env",
    "khoa_rieng.pem",
])
def test_gitignore_chan_bien_the_ten_bi_mat(ten):
    """`git add .` không được vô tình đưa cookie/khoá vào lịch sử git."""
    goc = os.path.dirname(dong_goi.__file__)
    try:
        r = subprocess.run(["git", "check-ignore", "--no-index", "-q", ten],
                           cwd=goc, capture_output=True)
    except FileNotFoundError:
        pytest.skip("máy không có git")
    if r.returncode == 128:
        pytest.skip("không chạy trong repo git")
    assert r.returncode == 0, f"{ten} chưa được .gitignore chặn"


def test_dockerignore_chan_cookie_va_thu_muc_khoa():
    with open(os.path.join(os.path.dirname(dong_goi.__file__), ".dockerignore"),
              encoding="utf-8") as f:
        noi_dung = f.read()
    for mau in ("cookies.txt", "[Cc][Oo][Oo][Kk][Ii][Ee]", "**/credentials/",
                "clips_meta.json", "khos.json", "cau_hinh.json"):
        assert mau in noi_dung, mau


def _du_an_may_chay(goc):
    _du_an_co_bi_mat(goc)
    (goc / "data").mkdir(exist_ok=True)
    (goc / "kho_goc").mkdir(exist_ok=True)
    (goc / "data" / "kho_a.pklz").write_bytes(b"x" * 100)
    (goc / "data" / "khos.json").write_text(json.dumps({
        "dang_dung": "A",
        "danh_sach": [{"ten": "A", "thu_muc": str(goc / "kho_goc"), "db": "kho_a.pklz"}],
    }), encoding="utf-8")
    (goc / "kho_goc" / "clips_meta.json").write_text("{}", encoding="utf-8")
    (goc / "data" / "cau_hinh.json").write_text(json.dumps({
        "top_n": 1, "ytdlp_cookiefile": str(goc / "cookies.txt"),
    }), encoding="utf-8")


def test_goi_may_chay_khong_mang_bi_mat_nhung_van_du_kho(tmp_path):
    goc = tmp_path / "du an"
    _du_an_may_chay(goc)
    ra = tmp_path / "may_chay.zip"

    dgmc.tao_goi(str(ra), ["A"], kem_ffmpeg=False, goc=str(goc))

    noi_dung = _noi_dung_zip(ra)
    ky_vong = KY_VONG_NGUON | {
        "data/kho_a.pklz",
        "kho_meta/A/clips_meta.json",
        "data/khos.json",
        "data/cau_hinh.json",
    }
    assert set(noi_dung) == ky_vong
    _khong_co_marker(noi_dung)
    cfg = json.loads(noi_dung["data/cau_hinh.json"])
    assert "ytdlp_cookiefile" not in cfg
