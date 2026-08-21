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
        data_dir=str(tmp_path),
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


# ---------------------------------------------------------------------------
# Dọn thư mục job quét mồ côi trong data/scan_jobs
# ---------------------------------------------------------------------------

def _job_gia(goc, ten, tuoi_giay, so_chunk=2, bay_gio=None):
    """Dựng một thư mục job giả kèm chunk, rồi lùi mtime của FILE về đúng tuổi."""
    import time as _t

    moc = (bay_gio if bay_gio is not None else _t.time()) - tuoi_giay
    d = goc / ten
    (d / "chunks").mkdir(parents=True)
    (d / "_ds_khuc.txt").write_bytes(b"x" * 10)
    for i in range(so_chunk):
        (d / "chunks" / f"chunk_{i:07d}.wav").write_bytes(b"y" * 1000)
    for f in d.rglob("*"):
        if f.is_file():
            os.utime(f, (moc, moc))
    os.utime(d, (moc, moc))
    return d


def test_don_job_xoa_thu_muc_qua_tuoi(tmp_path):
    bay_gio = 1_000_000.0
    cu = _job_gia(tmp_path, "cu", 30 * 24 * 3600, bay_gio=bay_gio)
    moi = _job_gia(tmp_path, "moi", 60, bay_gio=bay_gio)

    kq = don_dep.don_job_quet(str(tmp_path), max_ngay=7, bay_gio=bay_gio)

    assert kq["tong_job"] == 2
    assert kq["xoa_job"] == 1
    assert kq["bo_qua_dang_chay"] == 1
    assert not cu.exists()
    assert moi.exists()


def test_don_job_khong_bao_gio_xoa_job_vua_ghi(tmp_path):
    """Chốt chặn quan trọng nhất: `max_ngay=1` không được giết lượt quét đang chạy.

    Một video 30 tiếng ghi chunk liên tục hàng giờ. Nếu ngưỡng tuổi được lấy
    nguyên như người dùng đặt, thư mục của lượt đang chạy vẫn có thể lọt vào diện
    xoá — mất trắng công việc đang làm dở, và lỗi hiện ra ở chỗ chẳng liên quan.
    """
    bay_gio = 1_000_000.0
    dang_chay = _job_gia(tmp_path, "dang_chay", 120, bay_gio=bay_gio)  # 2 phút trước

    kq = don_dep.don_job_quet(str(tmp_path), max_ngay=1, bay_gio=bay_gio)

    assert kq["xoa_job"] == 0
    assert kq["bo_qua_dang_chay"] == 1
    assert dang_chay.exists()


def test_don_job_max_ngay_khong_duong_thi_khong_xoa_gi(tmp_path):
    """Giữ đúng quy ước của `don_kho_dem`: không có tiêu chí tuổi = không xoá."""
    bay_gio = 1_000_000.0
    cu = _job_gia(tmp_path, "rat_cu", 365 * 24 * 3600, bay_gio=bay_gio)

    kq = don_dep.don_job_quet(str(tmp_path), max_ngay=0, bay_gio=bay_gio)

    assert kq["xoa_job"] == 0
    assert kq["tong_job"] == 1
    assert cu.exists()


def test_don_job_tuoi_tinh_theo_file_moi_nhat_ben_trong(tmp_path):
    """Trên Windows mtime thư mục không đổi khi ghi vào thư mục con.

    Nếu đọc mtime của chính thư mục job, một lượt quét đang ghi chunk sẽ trông như
    đã cũ hàng giờ và bị xoá nhầm. Test dựng đúng cảnh đó: thư mục mang mtime rất
    cũ, nhưng bên trong có một chunk vừa mới ghi.
    """
    bay_gio = 1_000_000.0
    d = _job_gia(tmp_path, "vo_cu_ruot_moi", 30 * 24 * 3600, bay_gio=bay_gio)
    moi = d / "chunks" / "chunk_9999999.wav"
    moi.write_bytes(b"z" * 500)
    os.utime(moi, (bay_gio - 30, bay_gio - 30))   # vừa ghi 30 giây trước

    kq = don_dep.don_job_quet(str(tmp_path), max_ngay=7, bay_gio=bay_gio)

    assert kq["xoa_job"] == 0, "thư mục có file vừa ghi thì phải giữ lại"
    assert d.exists()


def test_don_job_xem_truoc_khong_xoa(tmp_path):
    bay_gio = 1_000_000.0
    cu = _job_gia(tmp_path, "cu", 30 * 24 * 3600, bay_gio=bay_gio)

    kq = don_dep.don_job_quet(
        str(tmp_path), max_ngay=7, thuc_hien=False, bay_gio=bay_gio)

    assert kq["xoa_job"] == 1
    assert kq["xoa_gb"] > 0
    assert cu.exists(), "chế độ xem trước tuyệt đối không được xoá"


def test_don_job_bo_qua_file_le_va_thu_muc_khong_ton_tai(tmp_path):
    bay_gio = 1_000_000.0
    (tmp_path / "mot_file_le.txt").write_bytes(b"x")
    _job_gia(tmp_path, "cu", 30 * 24 * 3600, bay_gio=bay_gio)

    kq = don_dep.don_job_quet(str(tmp_path), max_ngay=7, bay_gio=bay_gio)
    assert kq["tong_job"] == 1, "file lẻ không được tính là job"
    assert (tmp_path / "mot_file_le.txt").exists()

    trong = don_dep.don_job_quet(str(tmp_path / "khong_co"), max_ngay=7)
    assert trong["tong_job"] == 0 and trong["loi"] == []


def test_don_job_loi_xoa_duoc_ghi_lai_va_khong_nem_ra(tmp_path, monkeypatch):
    bay_gio = 1_000_000.0
    _job_gia(tmp_path, "cu", 30 * 24 * 3600, bay_gio=bay_gio)

    def rmtree_hong(path, *a, **k):
        raise OSError("file đang bị khoá")

    monkeypatch.setattr(don_dep.shutil, "rmtree", rmtree_hong)
    kq = don_dep.don_job_quet(str(tmp_path), max_ngay=7, bay_gio=bay_gio)

    assert kq["xoa_job"] == 0
    assert len(kq["loi"]) == 1
    assert "đang bị khoá" in kq["loi"][0]
