# -*- coding: utf-8 -*-
"""Test đóng gói bản chạy được cho máy phụ.

Phần quan trọng nhất là AN TOÀN: không khoá bí mật nào được lọt vào gói, và không
kéo theo môi trường ảo. Cả hai đều là lỗi im lặng — gói vẫn tạo thành công, chỉ có
điều mang theo thứ không nên mang.
"""

import json
import os
import zipfile

import dong_goi
import dong_goi_may_chay as dgmc
import pytest
from chia_watchlist import chia_muc, chia_watchlist


# =====================================================================
#  Bỏ qua môi trường ảo
# =====================================================================

@pytest.mark.parametrize("ten", [
    ".venv", "venv", ".venv-claude", ".venv-test", "venv312",
    "virtualenv", ".env", "env-cu",
])
def test_bo_qua_moi_truong_ao_du_dat_ten_gi(ten):
    """`.venv-claude` từng lọt và kéo 7.214 file / 108 MB site-packages vào gói."""
    assert dong_goi.la_thu_muc_bo_qua(ten)


@pytest.mark.parametrize("ten", ["docs", "tests", "audfprint-master", "kho_meta"])
def test_khong_bo_nham_thu_muc_that(ten):
    assert not dong_goi.la_thu_muc_bo_qua(ten)


def test_file_trong_moi_truong_ao_bi_loai(tmp_path):
    assert not dong_goi.nen_lay(os.path.join(".venv-claude", "Lib", "x.py"))
    assert dong_goi.nen_lay("engine.py")


# =====================================================================
#  Không bao giờ đóng gói khoá bí mật
# =====================================================================

@pytest.mark.parametrize("ten", [
    "google_key.json", "GOOGLE_KEY.JSON", "credentials.json", "token.json",
    "client_secret.json", "my-service-account.json", "abc_private_key.pem",
])
def test_nhan_dang_file_nhay_cam(ten):
    assert dong_goi.la_file_nhay_cam(ten)


def _kho_gia(tmp_path, co_khoa=False):
    """Dựng một cây dự án tối thiểu đủ để chạy gom_thanh_phan()."""
    goc = tmp_path / "duan"
    (goc / "data").mkdir(parents=True)
    (goc / "kho_goc").mkdir()
    (goc / "bin").mkdir()
    (goc / "engine.py").write_text("# ma nguon", encoding="utf-8")
    (goc / "data" / "kho_a.pklz").write_bytes(b"x" * 100)
    (goc / "data" / "khos.json").write_text(json.dumps({
        "dang_dung": "A",
        "danh_sach": [{"ten": "A", "thu_muc": str(goc / "kho_goc"),
                       "db": "kho_a.pklz"}],
    }), encoding="utf-8")
    (goc / "kho_goc" / "clips_meta.json").write_text("{}", encoding="utf-8")
    if co_khoa:
        (goc / "google_key.json").write_text('{"private_key":"x"}',
                                             encoding="utf-8")
    return goc


def test_khoa_google_khong_bao_gio_lot_vao_goi(tmp_path):
    """Kể cả khi khoá nằm ngay giữa thư mục dự án."""
    goc = _kho_gia(tmp_path, co_khoa=True)
    muc, _ = dgmc.gom_thanh_phan(["A"], kem_ffmpeg=False, goc=str(goc))
    ten_trong_zip = [t for _, t in muc]
    assert not any("google_key" in t.casefold() for t in ten_trong_zip)


def test_kho_van_tay_va_metadata_duoc_kem(tmp_path):
    goc = _kho_gia(tmp_path)
    muc, canh_bao = dgmc.gom_thanh_phan(["A"], kem_ffmpeg=False, goc=str(goc))
    ten = [t for _, t in muc]
    assert "data/kho_a.pklz" in ten
    assert "kho_meta/A/clips_meta.json" in ten
    assert not canh_bao


def test_bao_khi_kho_khong_ton_tai(tmp_path):
    goc = _kho_gia(tmp_path)
    muc, canh_bao = dgmc.gom_thanh_phan(["KhongCo"], kem_ffmpeg=False,
                                        goc=str(goc))
    assert any("KhongCo" in c for c in canh_bao)
    assert any("KHÔNG có kho nào hợp lệ" in c for c in canh_bao)


def test_thieu_clips_meta_thi_canh_bao_chu_khong_no(tmp_path):
    goc = _kho_gia(tmp_path)
    os.remove(goc / "kho_goc" / "clips_meta.json")
    muc, canh_bao = dgmc.gom_thanh_phan(["A"], kem_ffmpeg=False, goc=str(goc))
    assert any("clips_meta.json" in c for c in canh_bao)
    assert any(t == "data/kho_a.pklz" for _, t in muc), "vẫn phải kèm vân tay"


def test_khos_json_sinh_ra_xoa_duong_dan_may_nguon(tmp_path):
    """Máy phụ không có D:\\ClipGoc* nên `thu_muc` phải để trống chờ thiết lập."""
    goc = _kho_gia(tmp_path)
    ra = dgmc.noi_dung_sinh_them(["A"], goc=str(goc))
    khos = json.loads(ra["data/khos.json"])
    assert khos["danh_sach"][0]["thu_muc"] == ""
    assert khos["danh_sach"][0]["db"] == "kho_a.pklz"
    assert khos["dang_dung"] == "A"


def test_cau_hinh_bo_duong_dan_rieng_cua_may_nguon(tmp_path):
    goc = _kho_gia(tmp_path)
    (goc / "data" / "cau_hinh.json").write_text(json.dumps({
        "top_n": 1, "kho_dir": "D:/rieng", "thu_muc_quet_gan_nhat": "D:/rieng2",
        "sheet_link": "https://docs.google.com/spreadsheets/d/abc",
    }), encoding="utf-8")
    ra = dgmc.noi_dung_sinh_them(["A"], goc=str(goc))
    cfg = json.loads(ra["data/cau_hinh.json"])
    assert "kho_dir" not in cfg and "thu_muc_quet_gan_nhat" not in cfg
    assert cfg["top_n"] == 1, "tham số quét phải giữ nguyên"
    assert cfg["sheet_link"].startswith("https://"), "link Sheet không phải bí mật"


def test_zip_tao_ra_khong_co_file_cam(tmp_path):
    goc = _kho_gia(tmp_path, co_khoa=True)
    ra = tmp_path / "goi.zip"
    dgmc.tao_goi(str(ra), ["A"], kem_ffmpeg=False, goc=str(goc))
    with zipfile.ZipFile(ra) as z:
        ten = z.namelist()
    assert not any(dong_goi.la_file_nhay_cam(os.path.basename(t)) for t in ten)
    assert "data/khos.json" in ten


def test_khong_ghi_de_neu_chua_cho_phep(tmp_path):
    goc = _kho_gia(tmp_path)
    ra = tmp_path / "goi.zip"
    ra.write_bytes(b"cu")
    with pytest.raises(FileExistsError):
        dgmc.tao_goi(str(ra), ["A"], kem_ffmpeg=False, goc=str(goc))
    assert ra.read_bytes() == b"cu", "file cũ phải còn nguyên"


# =====================================================================
#  Chia watchlist
# =====================================================================

def test_chia_luan_phien_deu():
    phan = chia_muc(list(range(10)), 3)
    assert [len(p) for p in phan] == [4, 3, 3]
    assert sorted(x for p in phan for x in p) == list(range(10))


def test_chia_mot_may_thi_giu_nguyen():
    assert chia_muc([1, 2, 3], 1) == [[1, 2, 3]]


def test_chia_watchlist_giu_kho_va_gioi_han():
    wl = {"muc": [{"url": f"u{i}", "bat": True} for i in range(4)],
          "kho": "SML", "gioi_han_moi_lan": 20}
    ra = chia_watchlist(wl, 2)
    assert len(ra) == 2
    for d in ra:
        assert d["kho"] == "SML" and d["gioi_han_moi_lan"] == 20
        assert len(d["muc"]) == 2


def test_chia_watchlist_khong_lam_mat_muc_da_tat():
    wl = {"muc": [{"url": "a", "bat": True}, {"url": "b", "bat": False}],
          "kho": "SML"}
    ra = chia_watchlist(wl, 2)
    tat_ca = [m["url"] for d in ra for m in d["muc"]]
    assert sorted(tat_ca) == ["a", "b"]
    assert tat_ca.count("b") == 1, "mục đã tắt không được nhân bản"


def test_chia_nhieu_may_hon_so_muc():
    ra = chia_watchlist({"muc": [{"url": "a", "bat": True}], "kho": "K"}, 3)
    assert sum(len(d["muc"]) for d in ra) == 1
