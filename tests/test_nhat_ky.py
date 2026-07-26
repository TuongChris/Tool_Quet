# -*- coding: utf-8 -*-
"""Test ghi song song và thời hạn lưu nhật ký."""

from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

import nhat_ky
from nhat_ky import dong_nhat_ky, mo_nhat_ky


@pytest.fixture(autouse=True)
def luon_dong_nhat_ky():
    yield
    dong_nhat_ky()


def test_ghi_song_song_ra_file_va_man_hinh(tmp_path, capsys):
    path = mo_nhat_ky(str(tmp_path))
    print("Dòng tiêu chuẩn")
    print("Dòng lỗi", file=sys.stderr)
    dong_nhat_ky()

    man_hinh = capsys.readouterr()
    noi_dung_file = Path(path).read_text(encoding="utf-8")
    assert "Dòng tiêu chuẩn" in man_hinh.out
    assert "Dòng lỗi" in man_hinh.err
    assert "Dòng tiêu chuẩn" in noi_dung_file
    assert "Dòng lỗi" in noi_dung_file


def test_chay_hai_lan_trong_ngay_noi_cung_file(tmp_path):
    path_1 = mo_nhat_ky(str(tmp_path))
    print("Lần một")
    dong_nhat_ky()
    path_2 = mo_nhat_ky(str(tmp_path))
    print("Lần hai")
    dong_nhat_ky()

    noi_dung = Path(path_1).read_text(encoding="utf-8")
    assert path_1 == path_2
    assert "Lần một" in noi_dung
    assert "Lần hai" in noi_dung


def test_don_log_cu(tmp_path):
    cu = datetime.now().date() - timedelta(days=31)
    moi = datetime.now().date() - timedelta(days=5)
    file_cu = tmp_path / f"giamsat_{cu:%Y-%m-%d}.log"
    file_moi = tmp_path / f"giamsat_{moi:%Y-%m-%d}.log"
    file_cu.write_text("cũ", encoding="utf-8")
    file_moi.write_text("mới", encoding="utf-8")

    mo_nhat_ky(str(tmp_path), giu_ngay=30)
    dong_nhat_ky()

    assert not file_cu.exists()
    assert file_moi.exists()


def test_khong_xoa_file_ten_la(tmp_path):
    file_la = tmp_path / "giamsat_khong-phai-ngay.log"
    file_la.write_text("giữ lại", encoding="utf-8")

    mo_nhat_ky(str(tmp_path), giu_ngay=1)
    dong_nhat_ky()

    assert file_la.exists()


def test_giu_ngay_0_khong_don(tmp_path):
    file_cu = tmp_path / "giamsat_2000-01-01.log"
    file_cu.write_text("giữ lại", encoding="utf-8")

    mo_nhat_ky(str(tmp_path), giu_ngay=0)
    dong_nhat_ky()

    assert file_cu.exists()


def test_khong_mo_duoc_log_van_chay_tiep(tmp_path, capsys):
    file_thay_vi_thu_muc = tmp_path / "khong-phai-thu-muc"
    file_thay_vi_thu_muc.write_text("x", encoding="utf-8")

    path = mo_nhat_ky(str(file_thay_vi_thu_muc / "con"))
    print("Chương trình vẫn chạy")

    assert path.endswith(".log")
    assert "Chương trình vẫn chạy" in capsys.readouterr().out


def test_cli_watch_ngoai_le_van_dong_nhat_ky(
    tmp_path,
    monkeypatch,
):
    import cli

    loi_goi = []
    engine = type(
        "EngineGia",
        (),
        {
            "config": type("ConfigGia", (), {"ncores": 1})(),
            "out_dir": str(tmp_path),
        },
    )()
    monkeypatch.setattr("sys.argv", ["cli.py", "watch", "--log"])
    monkeypatch.setattr(cli, "Engine", lambda: engine)
    monkeypatch.setattr(
        cli,
        "_chay_lenh_watch",
        lambda *args: (_ for _ in ()).throw(RuntimeError("lỗi giữa chừng")),
    )
    monkeypatch.setattr(
        cli.nhat_ky,
        "mo_nhat_ky",
        lambda path: loi_goi.append(("mở", path)) or "log",
    )
    monkeypatch.setattr(
        cli.nhat_ky,
        "dong_nhat_ky",
        lambda: loi_goi.append(("đóng",)),
    )

    with pytest.raises(RuntimeError, match="lỗi giữa chừng"):
        cli.main()

    assert loi_goi == [("mở", str(tmp_path)), ("đóng",)]
