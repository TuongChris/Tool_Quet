# -*- coding: utf-8 -*-
"""Test khóa liên tiến trình và các điểm tích hợp."""

import os
import subprocess
import sys

import pytest

from khoa import DangChayRoi, KhoaTienTrinh
from watch import WatchList, chay_giam_sat


def test_lay_va_nha_khoa(tmp_path):
    path = str(tmp_path / "a.lock")

    with KhoaTienTrinh(path):
        pass
    with KhoaTienTrinh(path):
        pass

    assert os.path.isfile(path)


def test_khoa_thu_hai_bi_tu_choi(tmp_path):
    path = str(tmp_path / "a.lock")

    with KhoaTienTrinh(path, "tác vụ thứ nhất"):
        with pytest.raises(DangChayRoi, match="tác vụ thứ nhất"):
            with KhoaTienTrinh(path, "tác vụ thứ hai"):
                pass


def test_hai_file_khoa_hoat_dong_doc_lap(tmp_path):
    with KhoaTienTrinh(str(tmp_path / "a.lock")):
        with KhoaTienTrinh(str(tmp_path / "b.lock")):
            pass


def test_tu_tao_thu_muc_cha(tmp_path):
    path = tmp_path / "data" / "locks" / "a.lock"

    with KhoaTienTrinh(str(path)):
        assert path.exists()


def test_file_khoa_bi_xoa_khi_dang_giu_khong_lam_crash(tmp_path):
    path = tmp_path / "a.lock"

    with KhoaTienTrinh(str(path)):
        try:
            path.unlink()
        except PermissionError:
            pytest.skip("Windows không cho xóa file đang có handle mở")


def test_tien_trinh_bi_kill_thi_he_dieu_hanh_tu_nha_khoa(tmp_path):
    path = str(tmp_path / "a.lock")
    env = os.environ.copy()
    env["TIMCLIP_TEST_LOCK"] = path
    ma_lenh = (
        "import os, time\n"
        "from khoa import KhoaTienTrinh\n"
        "with KhoaTienTrinh(os.environ['TIMCLIP_TEST_LOCK'], 'tiến trình con'):\n"
        "    print('READY', flush=True)\n"
        "    time.sleep(60)\n"
    )
    tien_trinh = subprocess.Popen(
        [sys.executable, "-c", ma_lenh],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        assert tien_trinh.stdout is not None
        assert tien_trinh.stdout.readline().strip() == "READY"
        with pytest.raises(DangChayRoi, match="tiến trình con"):
            with KhoaTienTrinh(path):
                pass
    finally:
        tien_trinh.kill()
        tien_trinh.wait(timeout=5)

    with KhoaTienTrinh(path):
        pass


def test_chay_giam_sat_khi_dang_khoa_tra_bao_cao_loi(engine):
    path = os.path.join(engine.data_dir, "giamsat.lock")

    with KhoaTienTrinh(path, "lượt trước"):
        bao_cao = chay_giam_sat(engine, WatchList())

    assert bao_cao.loi
    assert "Đã có tiến trình khác" in bao_cao.loi[0]


def test_build_database_bi_chan_khi_tien_trinh_khac_dang_dung(engine):
    path = os.path.join(engine.data_dir, "kho.lock")

    with KhoaTienTrinh(path, "dựng kho lần trước"):
        with pytest.raises(DangChayRoi, match="dựng kho lần trước"):
            engine.build_database("không được xử lý tới đường dẫn này")
