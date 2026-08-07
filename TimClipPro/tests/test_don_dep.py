# -*- coding: utf-8 -*-
"""Test quyết định và thực thi dọn kho đệm."""

import os
from types import SimpleNamespace

import don_dep
from don_dep import MucDem, chon_can_xoa, don_kho_dem


def test_xoa_theo_tuoi():
    muc = [
        MucDem("cu", 10, 100),
        MucDem("moi", 10, 950),
    ]

    ket_qua = chon_can_xoa(
        muc,
        max_byte=100,
        max_giay=500,
        bay_gio=1000,
    )

    assert [item.path for item in ket_qua] == ["cu"]


def test_xoa_theo_ngan_sach_cu_nhat_truoc():
    muc = [
        MucDem("moi", 40, 300),
        MucDem("cu-nhat", 40, 100),
        MucDem("cu-nhi", 40, 200),
    ]

    ket_qua = chon_can_xoa(
        muc,
        max_byte=50,
        max_giay=0,
        bay_gio=1000,
    )

    assert [item.path for item in ket_qua] == ["cu-nhat", "cu-nhi"]


def test_ca_hai_rang_buoc_cung_luc():
    muc = [
        MucDem("qua-tuoi", 30, 100),
        MucDem("cu", 60, 700),
        MucDem("moi", 60, 900),
    ]

    ket_qua = chon_can_xoa(
        muc,
        max_byte=60,
        max_giay=500,
        bay_gio=1000,
    )

    assert [item.path for item in ket_qua] == ["qua-tuoi", "cu"]


def test_gioi_han_bang_0_thi_khong_xoa():
    muc = [MucDem("rat-cu", 10_000, 0)]

    assert chon_can_xoa(
        muc,
        max_byte=0,
        max_giay=0,
        bay_gio=1000,
    ) == []


def test_co_bay_gio_thi_ham_thuan_khong_doc_dong_ho(monkeypatch):
    monkeypatch.setattr(
        don_dep.time,
        "time",
        lambda: (_ for _ in ()).throw(AssertionError("không được đọc đồng hồ")),
    )

    assert chon_can_xoa(
        [MucDem("moi", 1, 900)],
        max_byte=10,
        max_giay=500,
        bay_gio=1000,
    ) == []


def test_xem_truoc_khong_xoa_file_that(tmp_path):
    path = tmp_path / "cu.opus"
    path.write_bytes(b"x" * 20)
    os.utime(path, (100, 100))

    ket_qua = don_kho_dem(
        str(tmp_path),
        max_gb=0,
        max_ngay=1,
        thuc_hien=False,
    )

    assert ket_qua["xoa_file"] == 1
    assert ket_qua["xoa_gb"] > 0
    assert path.exists()


def test_file_moi_duoi_ngan_sach_khong_bi_xoa(tmp_path):
    path = tmp_path / "moi.opus"
    path.write_bytes(b"x" * 20)

    ket_qua = don_kho_dem(str(tmp_path), max_gb=1, max_ngay=7)

    assert ket_qua["xoa_file"] == 0
    assert path.exists()


def test_hai_gioi_han_bang_0_khong_xoa_file_that(tmp_path):
    path = tmp_path / "rat-cu.opus"
    path.write_bytes(b"x")
    os.utime(path, (100, 100))

    ket_qua = don_kho_dem(str(tmp_path), max_gb=0, max_ngay=0)

    assert ket_qua["xoa_file"] == 0
    assert path.exists()


def test_khong_xoa_file_dang_tai_do(tmp_path):
    dang_tai = tmp_path / "video.part"
    ytdl = tmp_path / "video.ytdl"
    hoan_chinh = tmp_path / "video.opus"
    for path in (dang_tai, ytdl, hoan_chinh):
        path.write_bytes(b"x")
        os.utime(path, (100, 100))

    ket_qua = don_kho_dem(
        str(tmp_path),
        max_gb=0,
        max_ngay=1,
    )

    assert dang_tai.exists()
    assert ytdl.exists()
    assert not hoan_chinh.exists()
    assert ket_qua["xoa_file"] == 1


def test_khong_de_quy_vao_thu_muc_con(tmp_path):
    thu_muc_con = tmp_path / "khac"
    thu_muc_con.mkdir()
    file_con = thu_muc_con / "cu.opus"
    file_con.write_bytes(b"x")
    os.utime(file_con, (100, 100))

    ket_qua = don_kho_dem(str(tmp_path), max_gb=0, max_ngay=1)

    assert ket_qua["tong_file"] == 0
    assert file_con.exists()


def test_thu_muc_khong_ton_tai_khong_bi_tao(tmp_path):
    path = tmp_path / "khong-co"

    ket_qua = don_kho_dem(str(path))

    assert ket_qua["tong_file"] == 0
    assert not path.exists()


def test_loi_xoa_mot_file_van_tiep_tuc_file_ke(tmp_path, monkeypatch):
    file_loi = tmp_path / "loi.opus"
    file_ok = tmp_path / "ok.opus"
    file_loi.write_bytes(b"x")
    file_ok.write_bytes(b"x")
    os.utime(file_loi, (100, 100))
    os.utime(file_ok, (100, 100))
    remove_that = os.remove

    def remove_gia(path):
        if path == str(file_loi):
            raise PermissionError("file đang mở")
        remove_that(path)

    monkeypatch.setattr(don_dep.os, "remove", remove_gia)
    ket_qua = don_kho_dem(str(tmp_path), max_gb=0, max_ngay=1)

    assert file_loi.exists()
    assert not file_ok.exists()
    assert ket_qua["xoa_file"] == 1
    assert len(ket_qua["loi"]) == 1


def test_giam_sat_van_don_dem_sau_khi_video_quet_loi(
    engine,
    monkeypatch,
):
    from watch import MucTheoDoi, WatchList, chay_giam_sat

    video = SimpleNamespace(id="x1", title="Video", url="u1")
    monkeypatch.setattr(engine, "list_jobs", lambda limit: [])
    monkeypatch.setattr(
        engine,
        "scan_youtube",
        lambda url, progress=None: (_ for _ in ()).throw(
            RuntimeError("quét lỗi")
        ),
    )
    monkeypatch.setattr(
        "watch.don_kho_dem",
        lambda *args, **kwargs: {
            "tong_file": 2,
            "tong_gb": 1.0,
            "xoa_file": 2,
            "xoa_gb": 0.5,
            "loi": [],
        },
    )

    bao_cao = chay_giam_sat(
        engine,
        WatchList(muc=[MucTheoDoi("kenh", "kenh-1")]),
        lister=lambda url, limit: [video],
    )

    assert bao_cao.da_don_file == 2
    assert bao_cao.da_don_gb == 0.5
    assert "Đã dọn kho đệm: 2 file (0.500 GB)" in bao_cao.tom_tat()


def test_cli_dondep_xem_truoc_khong_xoa(monkeypatch, capsys, tmp_path):
    import cli

    loi_goi = []
    engine_gia = SimpleNamespace(
        dl_dir=str(tmp_path),
        config=SimpleNamespace(
            ncores=1,
            dem_max_gb=20.0,
            dem_max_ngay=7,
        ),
    )
    monkeypatch.setattr("sys.argv", ["cli.py", "dondep", "--xem-truoc"])
    monkeypatch.setattr(cli, "Engine", lambda: engine_gia)
    monkeypatch.setattr(
        cli.don_dep,
        "don_kho_dem",
        lambda *args, **kwargs: (
            loi_goi.append((args, kwargs))
            or {
                "tong_file": 1,
                "tong_gb": 1.0,
                "xoa_file": 1,
                "xoa_gb": 1.0,
                "loi": [],
            }
        ),
    )

    cli.main()

    assert loi_goi[0][1]["thuc_hien"] is False
    assert "Sẽ xóa: 1 file" in capsys.readouterr().out


def test_config_co_ngan_sach_kho_dem_mac_dinh():
    from engine import Config

    config = Config()

    assert config.dem_max_gb == 20.0
    assert config.dem_max_ngay == 7
