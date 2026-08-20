# -*- coding: utf-8 -*-
"""Test metadata YouTube và số đoạn đạt ngưỡng, không gọi mạng."""

from conftest import M

from engine import ScanResult


class _YoutubeDLGia:
    def __init__(self, info):
        self.info = info

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def extract_info(self, url, download=False):
        return self.info


def test_scanresult_co_truong_moi_voi_mac_dinh():
    r = ScanResult(source_name="x")

    assert r.channel_name == ""
    assert r.channel_id == ""
    assert r.channel_url == ""
    assert r.upload_date == ""
    assert r.so_dat_nguong == 0


def test_youtube_info_lay_du_khoa(engine, monkeypatch):
    import yt_dlp

    info = {
        "id": "abc123",
        "title": "Video",
        "duration": 125,
        "uploader": "Người đăng",
        "channel": "Tên kênh",
        "channel_id": "UC123",
        "channel_url": "https://youtube.com/channel/UC123",
        "upload_date": "20260726",
        "timestamp": 1785060000,        # 2026-07-26 10:00:00 UTC -> 17:00 giờ VN
    }
    monkeypatch.setattr(
        yt_dlp,
        "YoutubeDL",
        lambda opts: _YoutubeDLGia(info),
    )

    ket_qua = engine.youtube_info("https://youtu.be/abc123")
    # youtube_info nay chot luon ngay dang chinh tac + nguon goc.
    assert ket_qua.pop("upload_date_raw") == "20260726"
    assert ket_qua.pop("publication_date_source") == "timestamp"
    assert ket_qua.pop("publication_date_confidence") == "high"

    assert ket_qua == {
        "id": "abc123",
        "title": "Video",
        "duration": 125,
        "uploader": "Người đăng",
        "channel": "Tên kênh",
        "channel_id": "UC123",
        "channel_url": "https://youtube.com/channel/UC123",
        "upload_date": "20260726",
    }


def test_youtube_info_dung_uploader_lam_du_phong(engine, monkeypatch):
    import yt_dlp

    info = {
        "uploader": "Người đăng",
        "uploader_url": "https://youtube.com/@nguoidang",
    }
    monkeypatch.setattr(
        yt_dlp,
        "YoutubeDL",
        lambda opts: _YoutubeDLGia(info),
    )

    ket_qua = engine.youtube_info("https://youtu.be/abc123")

    assert ket_qua["channel"] == "Người đăng"
    assert ket_qua["channel_url"] == "https://youtube.com/@nguoidang"


def test_upload_date_none_tra_chuoi_rong(engine, monkeypatch):
    import yt_dlp

    monkeypatch.setattr(
        yt_dlp,
        "YoutubeDL",
        lambda opts: _YoutubeDLGia({"upload_date": None}),
    )

    ket_qua = engine.youtube_info("https://youtu.be/abc123")

    assert ket_qua["upload_date"] == ""


def test_scan_media_dem_so_doan_dat_nguong_truoc_khi_cat_top_n(
    engine,
    monkeypatch,
    tmp_path,
):
    media = tmp_path / "nguon.mp4"
    media.write_bytes(b"gia")
    tat_ca = [
        M("a.opus", hashes=999),
        M("b.opus", hashes=1000),
        M("c.opus", hashes=1500),
    ]
    engine.config.min_hash_floor = 1000
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    # scan_media đọc thời lượng TRƯỚC khi cắt, để chia đoạn cho quét tăng dần.
    monkeypatch.setattr(engine, "duration_of", lambda p: 100.0)
    monkeypatch.setattr(
        engine,
        "_cut_chunks",
        lambda *args, **kwargs: (["chunk.wav"], 100.0),
    )
    monkeypatch.setattr(engine, "_match_chunks", lambda *args, **kwargs: [])
    monkeypatch.setattr(engine, "_merge", lambda tho: tat_ca)
    monkeypatch.setattr(engine, "_gan_chi_so", lambda ds, duration: None)
    monkeypatch.setattr(engine, "_chon_loc", lambda ds, duration: (ds[:1], ds[1:]))

    ket_qua = engine.scan_media(str(media), luu_lich_su=False)

    assert ket_qua.so_dat_nguong == 2
    assert len(ket_qua.matches) == 1
    assert ket_qua.channel_name == ""
    assert ket_qua.channel_id == ""
    assert ket_qua.channel_url == ""
    assert ket_qua.upload_date == ""


def test_scan_media_tat_ca_rong_co_so_dat_nguong_bang_khong(
    engine,
    monkeypatch,
    tmp_path,
):
    media = tmp_path / "nguon.mp4"
    media.write_bytes(b"gia")
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    # scan_media đọc thời lượng TRƯỚC khi cắt, để chia đoạn cho quét tăng dần.
    monkeypatch.setattr(engine, "duration_of", lambda p: 100.0)
    monkeypatch.setattr(
        engine,
        "_cut_chunks",
        lambda *args, **kwargs: (["chunk.wav"], 100.0),
    )
    monkeypatch.setattr(engine, "_match_chunks", lambda *args, **kwargs: [])
    monkeypatch.setattr(engine, "_merge", lambda tho: [])
    monkeypatch.setattr(engine, "_gan_chi_so", lambda ds, duration: None)
    monkeypatch.setattr(engine, "_chon_loc", lambda ds, duration: ([], []))

    ket_qua = engine.scan_media(str(media), luu_lich_su=False)

    assert ket_qua.so_dat_nguong == 0


def test_scan_youtube_gan_metadata_vao_ket_qua_scan_media(engine, monkeypatch):
    info = {
        "id": "abc123",
        "title": "Video",
        "duration": 100,
        "uploader": "Người đăng",
        "channel": "Tên kênh",
        "channel_id": "UC123",
        "channel_url": "https://youtube.com/channel/UC123",
        "upload_date": "20260726",
    }
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    monkeypatch.setattr(engine, "youtube_info", lambda url: info)
    monkeypatch.setattr(engine, "download_audio", lambda *args: "audio.opus")
    monkeypatch.setattr(
        engine,
        "scan_media",
        lambda *args, **kwargs: ScanResult(source_name="Video"),
    )

    ket_qua = engine.scan_youtube(
        "https://youtu.be/abc123",
        luu_lich_su=False,
    )

    assert ket_qua.source_id == "abc123"
    assert ket_qua.channel_name == "Tên kênh"
    assert ket_qua.channel_id == "UC123"
    assert ket_qua.channel_url == "https://youtube.com/channel/UC123"
    assert ket_qua.upload_date == "20260726"


def test_scan_youtube_giu_metadata_khi_buoc_sau_nem_loi(engine, monkeypatch):
    info = {
        "id": "abc123",
        "title": "Video",
        "duration": 100,
        "uploader": "Người đăng",
        "channel": "Tên kênh",
        "channel_id": "UC123",
        "channel_url": "https://youtube.com/channel/UC123",
        "upload_date": "20260726",
    }
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)
    monkeypatch.setattr(engine, "youtube_info", lambda url: info)
    monkeypatch.setattr(
        engine,
        "download_audio",
        lambda *args: (_ for _ in ()).throw(RuntimeError("không tải được")),
    )

    ket_qua = engine.scan_youtube(
        "https://youtu.be/abc123",
        luu_lich_su=False,
    )

    assert ket_qua.status == "error"
    assert ket_qua.channel_name == "Tên kênh"
    assert ket_qua.channel_id == "UC123"
    assert ket_qua.channel_url == "https://youtube.com/channel/UC123"
    assert ket_qua.upload_date == "20260726"
