# -*- coding: utf-8 -*-
"""Test đường lui giữa các player client khi tải audio.

Bối cảnh 2026-08-18: YouTube trả HTTP 403 cho client mặc định ở MỌI video tải mới,
trong khi trích metadata vẫn chạy — nên tool lấy được tiêu đề rồi mới chết ở khâu
tải, rất dễ tưởng là hỏng link. Client `android` lúc đó vẫn tải bình thường.
"""

import os

import pytest
from engine import Cancelled, Config, Engine


class _YdlGia:
    """Giả yt_dlp.YoutubeDL: chỉ client trong `chay_duoc` mới tải thành công."""

    def __init__(self, chay_duoc, nhat_ky, dl_dir, video_id="v1"):
        self.chay_duoc = chay_duoc
        self.nhat_ky = nhat_ky
        self.dl_dir = dl_dir
        self.video_id = video_id

    def __call__(self, opts):
        args = (opts.get("extractor_args") or {}).get("youtube", {})
        client = (args.get("player_client") or [""])[0]
        return _Phien(client, self)


class _Phien:
    def __init__(self, client, cha):
        self.client = client
        self.cha = cha

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        self.cha.nhat_ky.append(self.client or "mặc định")
        if self.client not in self.cha.chay_duoc:
            raise RuntimeError("unable to download video data: HTTP Error 403: Forbidden")
        with open(os.path.join(self.cha.dl_dir,
                               f"{self.cha.video_id}.webm"), "wb") as f:
            f.write(b"audio gia")


def _eng(tmp_path, clients):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "ra"))
    e.config = Config(ytdlp_player_clients=clients)
    return e


def _vá(monkeypatch, eng, chay_duoc, nhat_ky):
    import yt_dlp
    monkeypatch.setattr(yt_dlp, "YoutubeDL",
                        _YdlGia(chay_duoc, nhat_ky, eng.dl_dir))


def test_client_dau_tien_chay_thi_khong_thu_them(tmp_path, monkeypatch):
    e = _eng(tmp_path, ["android", "", "tv"])
    nk = []
    _vá(monkeypatch, e, {"android"}, nk)
    assert e.download_audio("https://youtu.be/v1", "v1").endswith("v1.webm")
    assert nk == ["android"], "chạy được rồi thì đừng thử tiếp"


def test_lui_sang_client_sau_khi_cai_dau_bi_403(tmp_path, monkeypatch):
    """Đúng tình huống thật: mặc định 403, android tải được."""
    e = _eng(tmp_path, ["", "android"])
    nk = []
    _vá(monkeypatch, e, {"android"}, nk)
    assert e.download_audio("https://youtu.be/v1", "v1")
    assert nk == ["mặc định", "android"]


def test_moi_client_deu_hong_thi_bao_loi_kem_danh_sach_da_thu(tmp_path, monkeypatch):
    e = _eng(tmp_path, ["android", "", "tv"])
    nk = []
    _vá(monkeypatch, e, set(), nk)
    with pytest.raises(RuntimeError) as ei:
        e.download_audio("https://youtu.be/v1", "v1")
    tin = str(ei.value)
    assert "android" in tin and "mặc định" in tin and "tv" in tin
    assert "403" in tin, "phải giữ lại lỗi gốc để chẩn đoán"


def test_nguoi_dung_bam_dung_thi_khong_thu_client_khac(tmp_path, monkeypatch):
    """Huỷ là ý người dùng — không được lặng lẽ thử tiếp cho hết danh sách."""
    e = _eng(tmp_path, ["android", "", "tv"])
    nk = []
    import yt_dlp

    class _Huy(_YdlGia):
        def __call__(self, opts):
            nk.append("thu")
            raise Cancelled()

    monkeypatch.setattr(yt_dlp, "YoutubeDL", _Huy(set(), nk, e.dl_dir))
    with pytest.raises(Cancelled):
        e.download_audio("https://youtu.be/v1", "v1")
    assert len(nk) == 1


def test_co_cache_thi_khong_goi_mang(tmp_path, monkeypatch):
    e = _eng(tmp_path, ["android"])
    with open(os.path.join(e.dl_dir, "v1.webm"), "wb") as f:
        f.write(b"cu")
    nk = []
    _vá(monkeypatch, e, set(), nk)
    assert e.download_audio("https://youtu.be/v1", "v1").endswith("v1.webm")
    assert nk == [], "đã có file thì không được tải lại"


def test_cau_hinh_mac_dinh_uu_tien_client_co_format_chi_tieng():
    """Client mặc định đứng đầu vì chỉ nó có format audio-only.

    `android` không trả format audio-only nên `ba` rơi xuống `b` và tải CẢ VIDEO —
    đo 19/08 trên video 121 tiếng: 31,27 GB thay vì 2,75 GB.
    """
    ds = Config().ytdlp_player_clients
    assert ds[0] == "", "client mặc định phải được thử trước"
    assert "android" in ds, "vẫn giữ android làm đường lui khi mặc định bị chặn"


def test_dinh_dang_quet_co_chan_tran_bitrate():
    """audfprint hạ mẫu về 11025 Hz nên bitrate cao là lãng phí thuần tuý.

    Đo thật: 48 kbps cho 100,3% số hash so với 128 kbps, ở 39% dung lượng.
    """
    fmt = Config().ytdlp_format
    assert "abr<=" in fmt, "phải chặn trần bitrate cho đường quét"
    assert fmt.endswith("/ba/b"), "phải có đường lui khi video không có format nhẹ"
