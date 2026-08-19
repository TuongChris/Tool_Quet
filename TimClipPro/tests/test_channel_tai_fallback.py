# -*- coding: utf-8 -*-
"""Đường lui giữa các player client khi ĐỒNG BỘ KÊNH (channel.py).

Bối cảnh 2026-08-18: bản vá 403 hôm đó chỉ áp cho đường quét (`engine.download_audio`),
còn `ChannelSync._tai_va_nen` vẫn dùng client mặc định nên đồng bộ kênh tiếp tục
chết với `unable to download video data: HTTP Error 403: Forbidden` — đo thật trên
kho SML: 12/14 video còn thiếu tải được ngay khi ép client `android`.
"""

import channel
import pytest
from channel import ChannelSync, VideoInfo


class _Phien:
    def __init__(self, client, cha):
        self.client, self.cha = client, cha

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        self.cha.nhat_ky.append(self.client or "mặc định")
        if self.client not in self.cha.chay_duoc:
            raise RuntimeError(
                "\x1b[0;31mERROR:\x1b[0m unable to download video data: "
                "HTTP Error 403: Forbidden")
        return {"id": "v1", "title": "Clip thử", "duration": 12.0}


class _YdlGia:
    """Giả yt_dlp.YoutubeDL: chỉ client trong `chay_duoc` mới tải thành công."""

    def __init__(self, chay_duoc, nhat_ky):
        self.chay_duoc, self.nhat_ky = chay_duoc, nhat_ky

    def __call__(self, opts):
        args = (opts.get("extractor_args") or {}).get("youtube", {})
        return _Phien((args.get("player_client") or [""])[0], self)


@pytest.fixture()
def _va(monkeypatch):
    def dung(chay_duoc, nhat_ky):
        import yt_dlp
        monkeypatch.setattr(yt_dlp, "YoutubeDL", _YdlGia(chay_duoc, nhat_ky))
    return dung


def _cs(tmp_path, clients=None):
    return ChannelSync(str(tmp_path), player_clients=clients)


def test_client_dau_tien_chay_thi_khong_thu_them(tmp_path, _va):
    nk = []
    _va({"android"}, nk)
    cs = _cs(tmp_path, ["android", "", "tv"])
    assert cs._tai_thu_tung_client("https://youtu.be/v1", {})["id"] == "v1"
    assert nk == ["android"], "chạy được rồi thì đừng thử tiếp"


def test_lui_sang_client_sau_khi_cai_dau_bi_403(tmp_path, _va):
    """Đúng tình huống thật: mặc định 403, android tải được."""
    nk = []
    _va({"android"}, nk)
    assert _cs(tmp_path, ["", "android"])._tai_thu_tung_client("u", {})
    assert nk == ["mặc định", "android"]


def test_moi_client_hong_thi_bao_loi_kem_danh_sach_da_thu(tmp_path, _va):
    nk = []
    _va(set(), nk)
    with pytest.raises(RuntimeError) as ei:
        _cs(tmp_path, ["android", "", "tv"])._tai_thu_tung_client("u", {})
    tin = str(ei.value)
    assert "android" in tin and "mặc định" in tin and "tv" in tin
    assert "403" in tin, "phải giữ lại lỗi gốc để chẩn đoán"
    assert "\x1b" not in tin, "mã màu ANSI phải được dọn trước khi lên giao diện"


def test_opts_goc_khong_bi_ban_extractor_args(tmp_path, _va):
    """Mỗi vòng phải dùng bản sao; nếu không, client trước rò sang client sau."""
    nk = []
    _va({"tv"}, nk)
    opts = {"format": "ba/b"}
    _cs(tmp_path, ["android", "tv"])._tai_thu_tung_client("u", opts)
    assert opts == {"format": "ba/b"}


def test_mac_dinh_uu_tien_android_va_giu_duong_lui_mac_dinh(tmp_path):
    """android đứng trước vì đo thật ngày 18/08 chỉ nó còn tải được."""
    ds = _cs(tmp_path).player_clients
    assert ds[0] == "android"
    assert "" in ds, "vẫn phải giữ đường mặc định của yt-dlp làm dự phòng"


def test_engine_va_channel_dung_chung_mot_danh_sach():
    """Bug gốc: hai đường tải lệch nhau nên chỉ một bên được vá."""
    from engine import Config
    assert Config().ytdlp_player_clients == channel.PLAYER_CLIENTS_MAC_DINH


@pytest.mark.parametrize("xau", ["", [], "android", ["android", 1]])
def test_player_clients_sai_kieu_bi_tu_choi(tmp_path, xau):
    with pytest.raises(ValueError):
        ChannelSync(str(tmp_path), player_clients=xau)


def test_go_ma_mau_va_giai_thich_loi():
    assert channel.go_ma_mau("\x1b[0;31mERROR:\x1b[0m 403") == "ERROR: 403"
    # Không có ESC ở đầu (log đã bị nuốt ký tự điều khiển) vẫn phải dọn được.
    assert channel.go_ma_mau("[0;31mERROR:[0m 403") == "ERROR: 403"
    tin = channel.giai_thich_loi("ERROR: Sign in to confirm your age.")
    assert "độ tuổi" in tin and "KHÔNG phải lỗi tool" in tin
    assert "gỡ hoặc để riêng tư" in channel.giai_thich_loi("This video is not available")
    assert channel.giai_thich_loi("Nén audio thất bại") == "Nén audio thất bại"


def test_giai_thich_loi_luy_dang_va_cat_huong_dan():
    """Lỗi đi qua hai lớp (helper gói lại, sync ghi báo cáo) — chú thích chỉ được dán 1 lần.

    Bản vá đầu dán hai lần vào cùng một dòng; đây là test giữ cho lỗi đó không quay lại.
    """
    tho = ("ERROR: [youtube] gHAxs_-oaMQ: Sign in to confirm your age. Use "
           "--cookies-from-browser or --cookies for the authentication. See  "
           "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")
    mot_lan = channel.giai_thich_loi(tho)
    assert mot_lan.count("giới hạn độ tuổi") == 1
    assert channel.giai_thich_loi(mot_lan) == mot_lan, "gọi lại không được nhân đôi"
    assert "cookies-from-browser" not in mot_lan, "cắt đuôi hướng dẫn của yt-dlp"
    assert "github.com" not in mot_lan
    assert mot_lan.startswith("ERROR: [youtube] gHAxs_-oaMQ: Sign in to confirm your age.")


def test_loi_khong_nhan_dien_duoc_thi_giu_nguyen():
    assert channel.giai_thich_loi("Nén audio thất bại: abc") == "Nén audio thất bại: abc"


def test_sync_bao_loi_da_duoc_don_sach(tmp_path, monkeypatch, _va):
    """Lỗi trả về cho giao diện không được còn mã màu ANSI."""
    nk = []
    _va(set(), nk)
    cs = _cs(tmp_path, ["android"])
    monkeypatch.setattr(ChannelSync, "list_channel", staticmethod(
        lambda *a, **k: [VideoInfo("v1", "Clip thử", "20260101", 10.0,
                                   "https://youtu.be/v1")]))
    r = cs.sync("https://youtube.com/@x")
    assert r["moi"] == 0 and len(r["loi"]) == 1
    assert "\x1b" not in r["loi"][0] and "403" in r["loi"][0]
