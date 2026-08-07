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
        "da_them_tu_dia": 0,
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
    assert ket_qua == {
        "tong": 2, "da_va": 1, "bo_qua": 1, "da_them_tu_dia": 0, "loi": [],
    }
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

    assert ket_qua == {
        "tong": 2, "da_va": 0, "bo_qua": 2, "da_them_tu_dia": 0, "loi": [],
    }


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
    assert ket_qua == {
        "tong": 1, "da_va": 1, "bo_qua": 0, "da_them_tu_dia": 0, "loi": [],
    }


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


def _tao_clip(tmp_path, ten: str) -> None:
    (tmp_path / ten).write_bytes(b"opus gia")


def test_clip_tren_dia_chua_co_entry_van_duoc_va(tmp_path):
    """Tái hiện kho Cory: file trên đĩa nhiều hơn hẳn số entry trong clips_meta.

    Trước bản vá, va_metadata() chỉ lặp qua clips_meta nên các clip tải từ trước
    khi có tính năng metadata không bao giờ lấy được ngày đăng/thời lượng.
    """
    _tao_clip(tmp_path, "00000000 - Clip cu mot [aaaaaaaaaaa].opus")
    _tao_clip(tmp_path, "00000000 - Clip cu hai [bbbbbbbbbbb].opus")
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({"00000000 - Da co [ccccccccccc].opus": _meta_day_du("ccccccccccc")})

    da_goi = []

    def fetcher(video_id):
        da_goi.append(video_id)
        return {"upload_date": "20250115", "duration": 300}

    ket_qua = channel.va_metadata(fetcher=fetcher)
    da_luu = channel.load_meta()

    assert ket_qua["da_them_tu_dia"] == 2
    assert ket_qua["tong"] == 3
    assert ket_qua["da_va"] == 2
    assert sorted(da_goi) == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    for ten in ("00000000 - Clip cu mot [aaaaaaaaaaa].opus",
                "00000000 - Clip cu hai [bbbbbbbbbbb].opus"):
        assert da_luu[ten]["upload_date"] == "20250115"
        assert da_luu[ten]["duration"] == 300
        assert da_luu[ten]["url"] == f"https://youtu.be/{da_luu[ten]['id']}"
    # Entry sẵn có, đã đầy đủ, không bị fetcher đụng tới.
    assert da_luu["00000000 - Da co [ccccccccccc].opus"]["upload_date"] == "20240101"


def test_seed_khong_tao_rac_cho_file_khong_co_video_id(tmp_path):
    _tao_clip(tmp_path, "ban ghi tay khong co id.opus")
    _tao_clip(tmp_path, "ghi chu.txt")
    channel = ChannelSync(str(tmp_path))

    meta, them = channel.seed_meta_tu_dia()

    assert them == 0
    assert meta == {}


def test_seed_khong_ghi_de_metadata_that_bang_du_lieu_ten_file(tmp_path):
    ten = "20240101 - Tieu de cu [dddddddddddd].opus"
    _tao_clip(tmp_path, ten)
    channel = ChannelSync(str(tmp_path))
    channel.save_meta({ten: {
        "id": "dddddddddddd",
        "title": "Tiêu đề CHÍNH THỨC từ YouTube",
        "url": "https://youtu.be/dddddddddddd",
        "upload_date": "20240101",
        "duration": 555,
    }})

    meta, them = channel.seed_meta_tu_dia()

    assert them == 0
    assert meta[ten]["title"] == "Tiêu đề CHÍNH THỨC từ YouTube"
    assert meta[ten]["duration"] == 555


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
