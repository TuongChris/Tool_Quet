# -*- coding: utf-8 -*-
"""Kiểm tra source package và Docker context không mang dữ liệu nhạy cảm."""

import zipfile
from pathlib import Path

import pytest

import dong_goi


@pytest.mark.parametrize("ten", [
    "google_key.json",
    "Google_Key.JSON",
    "nested/Service_Credential.json",
    "nested/service-account-prod.json",
    "nested/client-SECRET.json",
    "nested/access-token.json",
])
def test_source_package_tu_choi_ten_nhay_cam_khong_phan_biet_hoa_thuong(ten):
    assert dong_goi.nen_lay(ten) is False


def test_source_package_bo_runtime_va_giu_file_build_quan_trong():
    assert dong_goi.nen_lay("data/lichsu.db") is False
    assert dong_goi.nen_lay("watchlist.json") is False
    assert dong_goi.nen_lay("Dockerfile") is True
    assert dong_goi.nen_lay(".dockerignore") is True
    assert dong_goi.nen_lay("audfprint-master/audfprint.py") is True
    assert dong_goi.nen_lay("watchlist.example.json") is True


def test_tao_source_zip_khong_ghi_de_va_khong_co_file_cam(tmp_path):
    output = tmp_path / "source.zip"

    ds, _ = dong_goi.tao_goi(str(output))

    assert output.is_file()
    assert "Dockerfile" in ds
    assert "audfprint-master\\audfprint.py" in ds or "audfprint-master/audfprint.py" in ds
    with zipfile.ZipFile(output) as z:
        names = z.namelist()
    assert not any(dong_goi.la_file_nhay_cam(name.rsplit("/", 1)[-1]) for name in names)
    with pytest.raises(FileExistsError):
        dong_goi.tao_goi(str(output))


def test_dockerignore_chan_du_cac_nhom_bat_buoc():
    noi_dung = (Path(dong_goi.GOC) / ".dockerignore").read_text(encoding="utf-8")
    for mau in ("google_key.json", "data/", "ketqua/", ".venv/", "bin/", "*.log"):
        assert mau in noi_dung


def test_dockerfile_copy_constraint_truoc_khi_cai_requirements():
    noi_dung = (Path(dong_goi.GOC) / "Dockerfile").read_text(encoding="utf-8")
    copy = noi_dung.index("COPY requirements.txt constraints.txt ./")
    cai = noi_dung.index("pip install --no-cache-dir -r requirements.txt")
    assert copy < cai
