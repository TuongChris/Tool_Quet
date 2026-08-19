# -*- coding: utf-8 -*-
"""Tự cập nhật theo tag: phải an toàn tuyệt đối với dữ liệu và với việc tool chạy được.

Ba nguyên tắc được test ở đây (xem docstring `cap_nhat.py`):
1. Không bao giờ làm mất thay đổi chưa lưu của người dùng.
2. Không bao giờ để tool không chạy được — mọi lỗi đều phải "bỏ qua êm".
3. Không bao giờ tự lùi bản trên máy phát triển.

Test dựng repo git THẬT trong tmp_path nên không đụng repo của dự án và không cần mạng.
"""

import os
import subprocess

import cap_nhat
import pytest

GOC_DU_AN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


@pytest.fixture()
def repo(tmp_path):
    """Repo git thật, có 2 commit và tag v1.0 ở commit đầu."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "T")
    (r / "requirements.txt").write_text("streamlit\n", encoding="utf-8")
    (r / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "dau")
    _git(r, "tag", "v1.0")
    (r / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "sau")
    _git(r, "tag", "v2.0")
    return str(r)


@pytest.fixture()
def khong_fetch(monkeypatch):
    """Repo test không có remote; giả lập fetch thành công để khỏi cần mạng."""
    monkeypatch.setattr(cap_nhat, "lay_tag_moi", lambda repo: (True, ""))


# ------------------------------------------------ nguyên tắc 2: không chặn tool

def test_khong_co_git_thi_bo_qua_em(monkeypatch, tmp_path):
    monkeypatch.setattr(cap_nhat, "_git", lambda *a, **k: (False, "Chưa cài git"))
    kq = cap_nhat.cap_nhat(goc=str(tmp_path))
    assert kq.ok is False
    assert any("bỏ qua" in d.lower() for d in kq.thong_bao)


def test_ngoai_repo_git_thi_bo_qua_em(tmp_path):
    kq = cap_nhat.cap_nhat(goc=str(tmp_path))
    assert kq.ok is False and kq.thong_bao


def test_mat_mang_thi_van_chay_ban_cu(repo, monkeypatch):
    monkeypatch.setattr(cap_nhat, "lay_tag_moi",
                        lambda r: (False, "could not resolve host"))
    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is False
    assert any("Chạy tiếp bản đang có" in d for d in kq.thong_bao)


def test_khong_bao_gio_chay_git_o_thu_muc_hien_hanh(tmp_path):
    """Lỗi thật: `_git(..., goc=None)` chạy git ở cwd của tiến trình nên trả lời về
    MỘT REPO KHÁC mà không báo gì — sai âm thầm, nguy hiểm hơn báo lỗi."""
    for xau in (None, "", str(tmp_path / "khong-he-co")):
        ok, tin = cap_nhat._git(["rev-parse", "HEAD"], xau)
        assert ok is False, f"phải từ chối goc={xau!r}"
        assert "Không có thư mục" in tin


def test_ban_hien_tai_khong_muon_ket_qua_cua_repo_khac(tmp_path):
    assert cap_nhat.ban_hien_tai(str(tmp_path / "khong-he-co")) == "(không rõ)"


def test_git_treo_qua_lau_khong_lam_ket_tool(monkeypatch, tmp_path):
    def treo(*a, **k):
        raise subprocess.TimeoutExpired("git", 45)

    monkeypatch.setattr(cap_nhat.subprocess, "run", treo)
    ok, tin = cap_nhat._git(["status"], str(tmp_path))
    assert ok is False and "quá" in tin


def test_git_dat_bien_chan_hoi_mat_khau(monkeypatch, tmp_path):
    """Máy phụ chạy qua Task Scheduler không có ai nhập mật khẩu."""
    bat = {}

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    def gia(cmd, **kw):
        bat.update(kw.get("env") or {})
        return R()

    monkeypatch.setattr(cap_nhat.subprocess, "run", gia)
    cap_nhat._git(["status"], str(tmp_path))
    assert bat.get("GIT_TERMINAL_PROMPT") == "0"
    assert "BatchMode=yes" in bat.get("GIT_SSH_COMMAND", "")


# ------------------------------------------------ nguyên tắc 1: giữ việc người dùng

def test_cay_ban_thi_dung_lai_khong_ghi_de(repo, khong_fetch):
    _git(repo, "checkout", "-q", "v1.0")
    (os.path.join(repo, "a.py"))
    with open(os.path.join(repo, "a.py"), "w", encoding="utf-8") as f:
        f.write("nguoi_dung_sua = True\n")

    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is False
    assert any("DỪNG cập nhật" in d for d in kq.thong_bao)
    # Thay đổi phải còn nguyên
    assert "nguoi_dung_sua" in open(os.path.join(repo, "a.py"), encoding="utf-8").read()


def test_khong_bao_gio_dung_lenh_git_pha_huy():
    """Soi ĐỐI SỐ THẬT của mọi lệnh git trong cap_nhat.py.

    Kiểm bằng AST chứ không tìm chuỗi trong cả file: phần chú thích có nhắc tới
    `--force`/`stash` để giải thích vì sao KHÔNG dùng, tìm chuỗi thô sẽ báo nhầm.
    """
    import ast

    nguon = open(os.path.join(GOC_DU_AN, "cap_nhat.py"), encoding="utf-8").read()
    cam = {"--force", "-f", "stash", "--hard", "clean", "reset"}
    doi_so = []
    for nut in ast.walk(ast.parse(nguon)):
        if not isinstance(nut, ast.Call):
            continue
        ten = getattr(nut.func, "id", "") or getattr(nut.func, "attr", "")
        if ten != "_git":
            continue
        for tham in nut.args:
            if isinstance(tham, (ast.List, ast.Tuple)):
                doi_so += [p.value for p in tham.elts
                           if isinstance(p, ast.Constant) and isinstance(p.value, str)]
    assert doi_so, "không tìm thấy lệnh git nào — test này đã hỏng"
    xau = sorted(set(doi_so) & cam)
    assert not xau, f"lệnh git phá huỷ dữ liệu người dùng: {xau}"


# ------------------------------------------------ nguyên tắc 3: không tự lùi bản

def test_may_dev_di_truoc_tag_thi_khong_tu_lui(repo, khong_fetch):
    """Trên máy dev, main luôn đi trước tag mới nhất."""
    (open(os.path.join(repo, "a.py"), "w", encoding="utf-8")).write("x = 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "dang lam do")
    truoc = _git(repo, "rev-parse", "HEAD").stdout.strip()

    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is False
    assert any("đã đi trước tag" in d for d in kq.thong_bao)
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == truoc, "không được đổi HEAD"
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"


def test_ban_cu_thi_tien_len_ban_moi(repo, khong_fetch):
    _git(repo, "checkout", "-q", "v1.0")
    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is True
    assert kq.ban_cu == "v1.0" and kq.ban_moi == "v2.0"
    assert cap_nhat.ban_hien_tai(repo) == "v2.0"


def test_dang_o_ban_moi_nhat_thi_khong_lam_gi(repo, khong_fetch):
    _git(repo, "checkout", "-q", "v2.0")
    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is False
    assert any("mới nhất" in d for d in kq.thong_bao)


def test_chi_kiem_tra_thi_khong_doi_gi(repo, khong_fetch):
    _git(repo, "checkout", "-q", "v1.0")
    kq = cap_nhat.cap_nhat(goc=repo, chi_kiem_tra=True)
    assert kq.ok is False
    assert cap_nhat.ban_hien_tai(repo) == "v1.0", "chỉ xem thì không được đổi"


def test_chi_dinh_ban_ro_rang_thi_duoc_lui(repo, khong_fetch):
    """Lùi bản là hành động có chủ đích của người dùng — phải cho phép."""
    _git(repo, "checkout", "-q", "v2.0")
    kq = cap_nhat.cap_nhat(goc=repo, ban_muon="v1.0")
    assert kq.ok is True
    assert cap_nhat.ban_hien_tai(repo) == "v1.0"


# ------------------------------------------------ cài lại thư viện

def test_ma_thoat_phan_biet_ba_truong_hop():
    """`cmd` chỉ so sánh được errorlevel, và .bat phải biết khi nào cần khởi động lại
    chính nó (git checkout có thể vừa thay file .bat đang chạy)."""
    assert cap_nhat.ma_thoat(cap_nhat.KetQua(ok=False)) == cap_nhat.KHONG_DOI
    assert cap_nhat.ma_thoat(cap_nhat.KetQua(ok=True)) == cap_nhat.DA_DOI
    assert cap_nhat.ma_thoat(
        cap_nhat.KetQua(ok=True, can_cai_lai_thu_vien=True)) == cap_nhat.DA_DOI_CAN_PIP
    # `if errorlevel N` trong batch nghĩa là ">= N", nên thứ tự phải tăng dần.
    assert cap_nhat.KHONG_DOI < cap_nhat.DA_DOI < cap_nhat.DA_DOI_CAN_PIP


def test_bat_kiem_errorlevel_theo_thu_tu_giam_dan():
    """`if errorlevel 10` đúng cả khi mã là 11, nên phải kiểm 11 TRƯỚC 10."""
    for ten in ("ChayTool.bat", "ChayMayPhu.bat"):
        noi_dung = open(os.path.join(GOC_DU_AN, ten), encoding="utf-8",
                        errors="replace").read()
        vi_tri_11 = noi_dung.find("errorlevel 11")
        vi_tri_10 = noi_dung.find("errorlevel 10")
        assert vi_tri_11 != -1 and vi_tri_10 != -1, f"{ten} thiếu bước cập nhật"
        assert vi_tri_11 < vi_tri_10, f"{ten}: phải kiểm errorlevel 11 trước 10"


def test_bao_cai_lai_khi_requirements_doi(repo, khong_fetch):
    _git(repo, "checkout", "-q", "main")
    with open(os.path.join(repo, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("streamlit\npandas\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "them thu vien")
    _git(repo, "tag", "v3.0")
    _git(repo, "checkout", "-q", "v2.0")

    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is True and kq.can_cai_lai_thu_vien is True


def test_khong_bao_cai_lai_khi_chi_doi_ma(repo, khong_fetch):
    _git(repo, "checkout", "-q", "v1.0")
    kq = cap_nhat.cap_nhat(goc=repo)
    assert kq.ok is True and kq.can_cai_lai_thu_vien is False


# ------------------------------------------------ dữ liệu người dùng

@pytest.mark.parametrize("duong_dan", [
    "data/", "ketqua/", "bin/", "google_key.json", "cau_hinh.json", "watchlist.json",
])
def test_du_lieu_nguoi_dung_khong_bi_git_theo_doi(duong_dan):
    """Chặn hồi quy: thêm file dữ liệu mới mà quên .gitignore thì tự cập nhật sẽ ghi đè nó."""
    noi_dung = open(os.path.join(GOC_DU_AN, ".gitignore"), encoding="utf-8").read()
    assert duong_dan in noi_dung, f"{duong_dan} phải nằm trong .gitignore"


def test_watchlist_that_khong_con_bi_theo_doi():
    r = subprocess.run(["git", "ls-files", "watchlist.json"], cwd=GOC_DU_AN,
                       capture_output=True, text=True)
    assert not r.stdout.strip(), (
        "watchlist.json vẫn bị git theo dõi — mỗi lần tự cập nhật sẽ đè danh sách "
        "giám sát riêng của từng máy")


def test_watchlist_mau_van_con_de_nguoi_dung_biet_dinh_dang():
    assert os.path.isfile(os.path.join(GOC_DU_AN, "watchlist.example.json"))


# ------------------------------------------------ đóng gói: cấu hình riêng của máy

def test_goi_trien_khai_khong_mang_theo_duong_dan_cookie():
    """Lỗi thật 18/08: gói mang `D:\\cookies.txt` của máy nguồn sang máy khác, khiến
    rào chắn cookie ném lỗi và chặn MỌI lượt tải ở đó."""
    import dong_goi_may_chay
    assert "ytdlp_cookiefile" in dong_goi_may_chay.KHOA_RIENG_CUA_MAY
    assert "ytdlp_cookies_browser" in dong_goi_may_chay.KHOA_RIENG_CUA_MAY


def test_goi_trien_khai_van_giu_sheet_link():
    """Mục đích của máy phụ là dồn kết quả về CÙNG một Google Sheet."""
    import dong_goi_may_chay
    assert "sheet_link" not in dong_goi_may_chay.KHOA_RIENG_CUA_MAY


def test_cau_hinh_sinh_ra_da_bi_loc(tmp_path, monkeypatch):
    import json

    import dong_goi_may_chay

    data = tmp_path / "data"
    data.mkdir()
    (data / "khos.json").write_text(json.dumps({"dang_dung": "", "danh_sach": []}),
                                    encoding="utf-8")
    (data / "cau_hinh.json").write_text(json.dumps({
        "ytdlp_cookiefile": r"D:\cookies.txt",
        "ytdlp_cookies_browser": "chrome",
        "kho_dir": r"D:\ClipGocSML",
        "sheet_link": "https://docs.google.com/spreadsheets/d/abc",
        "ytdlp_sleep_requests_s": 2.5,
    }), encoding="utf-8")

    ra = dong_goi_may_chay.noi_dung_sinh_them([], goc=str(tmp_path))
    cfg = json.loads(ra["data/cau_hinh.json"])
    assert "ytdlp_cookiefile" not in cfg
    assert "ytdlp_cookies_browser" not in cfg
    assert "kho_dir" not in cfg
    assert cfg["sheet_link"].endswith("abc"), "phải giữ để máy phụ ghi đúng Sheet"
    assert cfg["ytdlp_sleep_requests_s"] == 2.5, "tham số chống chặn phải theo sang"
