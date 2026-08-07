# -*- coding: utf-8 -*-
"""Ngày đăng thật phải đi tới tên file và clips_meta.json — không gọi mạng.

Bối cảnh: kho cũ có 1717/1717 file mang tiền tố ``00000000`` vì
``list_channel()`` dùng ``extract_flat``, chế độ này yt-dlp không trả
``upload_date`` cho entry của kênh/playlist.
"""

from __future__ import annotations

import channel
from channel import ChannelSync, VideoInfo, bo_sung_video_info, ngay_dang_tu_info


# --------------------------------------------------------------------------
# Rút ngày đăng từ info yt-dlp
# --------------------------------------------------------------------------

def test_uu_tien_upload_date_hop_le():
    assert ngay_dang_tu_info({"upload_date": "20240115"}) == "20240115"


def test_bo_qua_upload_date_rac_va_00000000():
    assert ngay_dang_tu_info({"upload_date": "00000000"}) == ""
    assert ngay_dang_tu_info({"upload_date": "hom qua"}) == ""
    assert ngay_dang_tu_info({"upload_date": "20241332"}) == ""   # tháng 13
    assert ngay_dang_tu_info({}) == ""
    assert ngay_dang_tu_info(None) == ""


def test_dung_release_timestamp_khi_extract_flat_khong_co_upload_date():
    """Entry premiere/livestream ở chế độ flat có timestamp — lấy được miễn phí."""
    # 2024-01-15T00:00:00Z
    assert ngay_dang_tu_info({"release_timestamp": 1705276800}) == "20240115"
    assert ngay_dang_tu_info({"timestamp": 1705276800}) == "20240115"


def test_timestamp_vo_nghia_khong_thanh_ngay():
    assert ngay_dang_tu_info({"timestamp": 0}) == ""
    assert ngay_dang_tu_info({"timestamp": -5}) == ""
    assert ngay_dang_tu_info({"timestamp": "khong phai so"}) == ""


# --------------------------------------------------------------------------
# Bổ sung VideoInfo
# --------------------------------------------------------------------------

def test_bo_sung_khong_ghi_de_du_lieu_tot_bang_rong():
    goc = VideoInfo("abc12345678", "Tiêu đề gốc", "20230101", 500.0, "u")
    moi = bo_sung_video_info(goc, {"upload_date": "", "duration": 0, "title": ""})

    assert moi.upload_date == "20230101"
    assert moi.duration == 500.0
    assert moi.title == "Tiêu đề gốc"
    assert moi.url == "u"


def test_bo_sung_dien_ngay_that_vao_cho_dang_trong():
    goc = VideoInfo("abc12345678", "Tên từ flat", "", 0.0, "u")
    moi = bo_sung_video_info(
        goc, {"id": "abc12345678", "title": "Tên chính thức",
              "upload_date": "20240115", "duration": 612.0}
    )

    assert moi.upload_date == "20240115"
    assert moi.duration == 612.0
    assert moi.title == "Tên chính thức"


# --------------------------------------------------------------------------
# list_channel
# --------------------------------------------------------------------------

class _YoutubeDLGia:
    entries: list = []
    opts_da_dung: list = []

    def __init__(self, opts):
        type(self).opts_da_dung.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return {"entries": type(self).entries}


def _gan_yt_dlp(monkeypatch, entries):
    import yt_dlp

    _YoutubeDLGia.entries = entries
    _YoutubeDLGia.opts_da_dung = []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _YoutubeDLGia)


def test_list_channel_mac_dinh_nhanh_khong_goi_them_request(monkeypatch):
    _gan_yt_dlp(monkeypatch, [
        {"id": "aaaaaaaaaaa", "title": "Một", "duration": 100},
        {"id": "bbbbbbbbbbb", "title": "Hai", "duration": 200},
    ])

    def chi_tiet(video_id):
        raise AssertionError("Mặc định không được gọi trích xuất từng video")

    ds = ChannelSync.list_channel("https://youtube.com/@kenh", chi_tiet=chi_tiet)

    assert [v.id for v in ds] == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert [v.upload_date for v in ds] == ["", ""]
    assert _YoutubeDLGia.opts_da_dung[0]["extract_flat"] == "in_playlist"


def test_list_channel_lay_duoc_ngay_tu_timestamp_ma_khong_ton_request(monkeypatch):
    _gan_yt_dlp(monkeypatch, [
        {"id": "aaaaaaaaaaa", "title": "Premiere", "release_timestamp": 1705276800},
    ])

    ds = ChannelSync.list_channel(
        "https://youtube.com/@kenh",
        chi_tiet=lambda vid: (_ for _ in ()).throw(AssertionError("không được gọi")),
    )

    assert ds[0].upload_date == "20240115"


def test_list_channel_lay_ngay_dang_bo_sung_dung_video_con_thieu(monkeypatch):
    _gan_yt_dlp(monkeypatch, [
        {"id": "aaaaaaaaaaa", "title": "Thiếu ngày", "duration": 100},
        {"id": "bbbbbbbbbbb", "title": "Có sẵn", "release_timestamp": 1705276800},
        {"id": "ccccccccccc", "title": "Thiếu ngày 2", "duration": 300},
    ])
    da_goi = []

    def chi_tiet(video_id):
        da_goi.append(video_id)
        return {"id": video_id, "title": f"Chính thức {video_id}",
                "upload_date": "20240220", "duration": 999.0}

    tien_do = []
    ds = ChannelSync.list_channel(
        "https://youtube.com/@kenh",
        lay_ngay_dang=True,
        chi_tiet=chi_tiet,
        progress=lambda pct, msg: tien_do.append(pct),
    )

    # Chỉ hỏi lại video thiếu ngày, không hỏi video đã có.
    assert da_goi == ["aaaaaaaaaaa", "ccccccccccc"]
    assert [v.upload_date for v in ds] == ["20240220", "20240115", "20240220"]
    assert ds[1].title == "Có sẵn", "Video đã có ngày không được đụng tới"
    assert tien_do == [0.5, 1.0]


def test_list_channel_mot_video_loi_khong_lam_hong_ca_danh_sach(monkeypatch):
    _gan_yt_dlp(monkeypatch, [
        {"id": "aaaaaaaaaaa", "title": "Bị xoá", "duration": 100},
        {"id": "bbbbbbbbbbb", "title": "Bình thường", "duration": 200},
    ])

    def chi_tiet(video_id):
        if video_id == "aaaaaaaaaaa":
            raise RuntimeError("Video is private")
        return {"upload_date": "20240301"}

    ds = ChannelSync.list_channel(
        "https://youtube.com/@kenh", lay_ngay_dang=True, chi_tiet=chi_tiet
    )

    assert len(ds) == 2
    assert ds[0].upload_date == "", "Video lỗi phải để trống, không được bịa ngày"
    assert ds[1].upload_date == "20240301"


# --------------------------------------------------------------------------
# sync(): ngày thật lấy trong lượt tải, không tốn request thêm
# --------------------------------------------------------------------------

def test_sync_ghi_ngay_that_vao_ten_file_va_clips_meta(tmp_path, monkeypatch):
    cs = ChannelSync(str(tmp_path))
    videos = [VideoInfo("aaaaaaaaaaa", "Tên từ flat", "", 0.0,
                        "https://youtu.be/aaaaaaaaaaa")]
    monkeypatch.setattr(ChannelSync, "list_channel",
                        staticmethod(lambda url, limit=None, **kw: videos))
    monkeypatch.setattr(cs, "done_ids", lambda: set())
    monkeypatch.setattr(cs, "quet_id_tren_dia", lambda: {})
    monkeypatch.setattr(cs, "_mark_done", lambda vid: None)

    def tai_va_nen(v):
        """Giả lập đúng hành vi thật: lượt tải trả về info đầy đủ."""
        v = channel.bo_sung_video_info(v, {
            "id": v.id, "title": "Tên chính thức trên YouTube",
            "upload_date": "20240115", "duration": 612.0,
        })
        duong_dan = tmp_path / cs._ten_file(v)
        duong_dan.write_bytes(b"opus")
        return str(duong_dan), v

    monkeypatch.setattr(cs, "_tai_va_nen", tai_va_nen)

    ket_qua = cs.sync("https://youtube.com/@kenh")
    assert ket_qua["moi"] == 1

    ten_file = "20240115 - Tên chính thức trên YouTube [aaaaaaaaaaa].opus"
    assert (tmp_path / ten_file).is_file(), sorted(p.name for p in tmp_path.iterdir())

    muc = cs.load_meta()[ten_file]
    assert muc["upload_date"] == "20240115"
    assert muc["duration"] == 612.0
    assert muc["title"] == "Tên chính thức trên YouTube"
    assert muc["url"] == "https://youtu.be/aaaaaaaaaaa"


def test_sync_video_that_su_khong_co_ngay_van_dung_00000000(tmp_path, monkeypatch):
    """Không được bịa ngày hôm nay khi YouTube không trả ngày đăng."""
    cs = ChannelSync(str(tmp_path))
    videos = [VideoInfo("bbbbbbbbbbb", "Không rõ ngày", "", 0.0,
                        "https://youtu.be/bbbbbbbbbbb")]
    monkeypatch.setattr(ChannelSync, "list_channel",
                        staticmethod(lambda url, limit=None, **kw: videos))
    monkeypatch.setattr(cs, "done_ids", lambda: set())
    monkeypatch.setattr(cs, "quet_id_tren_dia", lambda: {})
    monkeypatch.setattr(cs, "_mark_done", lambda vid: None)

    def tai_va_nen(v):
        v = channel.bo_sung_video_info(v, {"upload_date": "00000000", "duration": 0})
        duong_dan = tmp_path / cs._ten_file(v)
        duong_dan.write_bytes(b"opus")
        return str(duong_dan), v

    monkeypatch.setattr(cs, "_tai_va_nen", tai_va_nen)
    cs.sync("https://youtube.com/@kenh")

    ten_file = "00000000 - Không rõ ngày [bbbbbbbbbbb].opus"
    assert (tmp_path / ten_file).is_file()
    assert cs.load_meta()[ten_file]["upload_date"] == ""
