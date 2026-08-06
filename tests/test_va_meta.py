# -*- coding: utf-8 -*-
"""Test vá metadata clip bằng fetcher giả, không gọi mạng."""

from channel import ChannelSync


def _meta_day_du(video_id: str) -> dict:
    return {
        "id": video_id,
        "title": f"Video {video_id}",
        "upload_date": "20240101",
        "duration": 120,
        "url": f"https://youtu.be/{video_id}",
    }


def test_file_meta_khong_ton_tai_tra_ket_qua_rong(tmp_path):
    channel = ChannelSync(str(tmp_path))

    assert channel.va_metadata(fetcher=lambda video_id: {}) == {
        "tong": 0,
        "da_va": 0,
        "bo_qua": 0,
        "loi": [],
    }


def test_chi_va_muc_thieu(tmp_path):
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({
        "du.opus": _meta_day_du("du1234"),
        "thieu.opus": {
            **_meta_day_du("thieu1"),
            "upload_date": "00000000",
        },
    })
    da_goi = []

    def fetcher(video_id):
        da_goi.append(video_id)
        return {"upload_date": "20250115", "duration": 180}

    ket_qua = channel.va_metadata(fetcher=fetcher)

    assert da_goi == ["thieu1"]
    assert ket_qua == {"tong": 2, "da_va": 1, "bo_qua": 1, "loi": []}
    assert channel.load_meta()["thieu.opus"]["upload_date"] == "20250115"


def test_khong_muc_nao_thieu_thi_khong_goi_fetcher(tmp_path):
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({
        "a.opus": _meta_day_du("aaaaaa"),
        "b.opus": _meta_day_du("bbbbbb"),
    })

    ket_qua = channel.va_metadata(
        fetcher=lambda video_id: (_ for _ in ()).throw(
            AssertionError("Không được gọi fetcher")
        ),
    )

    assert ket_qua == {"tong": 2, "da_va": 0, "bo_qua": 2, "loi": []}


def test_ghi_ngay_sau_moi_muc(tmp_path):
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({
        "mot.opus": {
            **_meta_day_du("mot123"),
            "upload_date": "",
        },
        "hai.opus": {
            **_meta_day_du("hai123"),
            "upload_date": "",
        },
    })

    def fetcher(video_id):
        if video_id == "hai123":
            raise RuntimeError("video đã bị xóa")
        return {"upload_date": "20250115", "duration": 200}

    ket_qua = channel.va_metadata(fetcher=fetcher)
    da_luu = channel.load_meta()

    assert da_luu["mot.opus"]["upload_date"] == "20250115"
    assert da_luu["hai.opus"]["upload_date"] == ""
    assert ket_qua["da_va"] == 1
    assert len(ket_qua["loi"]) == 1
    assert "video đã bị xóa" in ket_qua["loi"][0]


def test_upload_date_none_giu_nguyen_gia_tri_cu(tmp_path):
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({
        "clip.opus": {
            **_meta_day_du("abc123"),
            "upload_date": "00000000",
            "duration": 0,
        },
    })

    channel.va_metadata(
        fetcher=lambda video_id: {"upload_date": None, "duration": 90},
    )
    da_luu = channel.load_meta()["clip.opus"]

    assert da_luu["upload_date"] == "00000000"
    assert da_luu["duration"] == 90
    assert da_luu["upload_date"] != "None"


def test_chi_thieu_false_xu_ly_toan_bo(tmp_path):
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({"clip.opus": _meta_day_du("abc123")})
    da_goi = []

    ket_qua = channel.va_metadata(
        fetcher=lambda video_id: (
            da_goi.append(video_id)
            or {"upload_date": "20250115", "duration": 180}
        ),
        chi_thieu=False,
    )

    assert da_goi == ["abc123"]
    assert ket_qua == {"tong": 1, "da_va": 1, "bo_qua": 0, "loi": []}


def test_bao_tien_do_theo_tong_so_muc_can_va(tmp_path):
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({
        "a.opus": {**_meta_day_du("aaaaaa"), "duration": 0},
        "b.opus": {**_meta_day_du("bbbbbb"), "duration": 0},
    })
    tien_do = []

    channel.va_metadata(
        fetcher=lambda video_id: {"upload_date": "20250115", "duration": 10},
        progress=lambda pct, msg: tien_do.append((pct, msg)),
    )

    assert [pct for pct, _ in tien_do] == [0.5, 1.0]
    assert "[2/2]" in tien_do[-1][1]


def test_fetcher_mac_dinh_chi_lay_metadata_khong_tai_video(
    tmp_path,
    monkeypatch,
):
    import yt_dlp

    loi_goi = []

    class YoutubeDLGia:
        def __init__(self, opts):
            loi_goi.append(("opts", opts))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, download=False):
            loi_goi.append(("extract", url, download))
            return {"upload_date": "20250115", "duration": 180}

    channel = ChannelSync(str(tmp_path))
    channel.save_meta({
        "clip.opus": {
            **_meta_day_du("abc123"),
            "upload_date": "",
            "duration": 0,
        },
    })
    monkeypatch.setattr(yt_dlp, "YoutubeDL", YoutubeDLGia)

    ket_qua = channel.va_metadata()

    assert ket_qua["da_va"] == 1
    assert loi_goi[0][1]["skip_download"] is True
    assert loi_goi[0][1]["socket_timeout"] == 30
    assert loi_goi[1] == ("extract", "https://youtu.be/abc123", False)
