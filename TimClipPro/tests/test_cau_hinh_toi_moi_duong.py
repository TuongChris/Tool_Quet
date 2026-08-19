# -*- coding: utf-8 -*-
"""Cookie và nhịp tải phải tới ĐƯỢC mọi đường gọi mạng, không sót đường nào.

Bối cảnh 2026-08-18: đây là lần thứ tư trong một ngày cùng một loại lỗi tái diễn —
thêm tính năng ở tầng chung nhưng chỉ nối vào vài nơi gọi, những nơi còn lại âm thầm
rơi về mặc định. Lần này bản vá đầu chỉ nối 2/6 nơi; bốn nơi còn lại vẫn gọi mạng mà
không có cookie, trong đó có vòng giám sát tự động — chỗ tích luỹ nguy cơ bị chặn
cao nhất.

Test ở đây kiểm ĐƯỜNG DẪN của cấu hình chứ không kiểm hành vi mạng, nên chạy offline.
"""

import channel
import pytest
import watch
import ytdlp_chung as y
from channel import ChannelSync, VideoInfo


@pytest.fixture()
def cau_hinh():
    return y.CauHinhMang(cookies_browser="chrome", sleep_requests_s=7.5,
                         network_timeout_s=99)


class _BatOpts:
    """Ghi lại opts của MỌI lượt dựng YoutubeDL để soi cấu hình có tới nơi không."""

    def __init__(self, info=None):
        self.opts = []
        self.info = info if info is not None else {"id": "v1", "title": "T", "duration": 5}

    def __call__(self, opts):
        self.opts.append(opts)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        return self.info


@pytest.fixture()
def bat(monkeypatch):
    def dung(info=None):
        import yt_dlp
        b = _BatOpts(info)
        monkeypatch.setattr(yt_dlp, "YoutubeDL", b)
        return b
    return dung


def _co_cookie(opts: dict) -> bool:
    return "cookiefile" in opts or "cookiesfrombrowser" in opts


# ---------------------------------------------------------------- ChannelSync

def test_lay_info_video_nhan_cau_hinh(bat, cau_hinh):
    b = bat()
    ChannelSync.lay_info_video("v1", 99, cau_hinh_mang=cau_hinh)
    assert _co_cookie(b.opts[0])
    assert b.opts[0]["sleep_interval_requests"] == 7.5


def test_list_channel_nhan_cau_hinh(bat, cau_hinh):
    b = bat({"entries": [{"id": "v1", "title": "T"}]})
    ChannelSync.list_channel("https://youtube.com/@x", cau_hinh_mang=cau_hinh)
    assert _co_cookie(b.opts[0])


def test_lay_ngay_dang_cung_mang_cau_hinh_xuong_tung_video(bat, cau_hinh):
    """Đây là vòng MỘT REQUEST MỖI VIDEO — nặng hơn hẳn lượt liệt kê phẳng, và đúng
    chỗ bot-check đánh. Bản vá đầu bỏ sót đúng chỗ này."""
    b = bat({"entries": [{"id": "v1", "title": "T"}, {"id": "v2", "title": "U"}]})
    ChannelSync.list_channel("https://youtube.com/@x", lay_ngay_dang=True,
                             cau_hinh_mang=cau_hinh)
    assert len(b.opts) >= 2, "phải có lượt liệt kê + lượt chi tiết"
    for i, o in enumerate(b.opts):
        assert _co_cookie(o), f"lượt gọi thứ {i} mất cookie"
        assert o["sleep_interval_requests"] == 7.5, f"lượt gọi thứ {i} mất nhịp tải"


def test_chi_tiet_do_nguoi_goi_truyen_giu_nguyen_chu_ky_mot_doi_so(bat, cau_hinh):
    """`chi_tiet` là điểm nối cho test offline; không được đổi hợp đồng của nó."""
    b = bat({"entries": [{"id": "v1", "title": "T"}]})
    da_goi = []
    ChannelSync.list_channel(
        "https://youtube.com/@x", lay_ngay_dang=True, cau_hinh_mang=cau_hinh,
        chi_tiet=lambda vid: da_goi.append(vid) or {"id": vid, "upload_date": "20260101"})
    assert da_goi == ["v1"]
    assert len(b.opts) == 1, "đã có chi_tiet thì không được gọi mạng thêm"


def test_sync_va_kiem_tra_thieu_dung_cau_hinh_cua_kho(tmp_path, monkeypatch, cau_hinh):
    cs = ChannelSync(str(tmp_path), cau_hinh_mang=cau_hinh)
    nhan = {}

    def gia(url, limit=None, **kw):
        nhan.update(kw)
        return [VideoInfo("v1", "T", "20260101", 1.0, "u")]

    monkeypatch.setattr(cs, "list_channel", gia)
    cs.kiem_tra_thieu("https://youtube.com/@x")
    assert nhan.get("cau_hinh_mang") is cs.cau_hinh_mang


# ---------------------------------------------------------------- timeout

def test_khong_truyen_timeout_thi_giu_gia_tri_cua_cau_hinh(tmp_path, cau_hinh):
    """Trước đây tham số mặc định 30 giây âm thầm ghi đè giá trị người dùng đặt."""
    cs = ChannelSync(str(tmp_path), cau_hinh_mang=cau_hinh)
    assert cs.cau_hinh_mang.network_timeout_s == 99
    assert cs.network_timeout_s == 99


def test_truyen_timeout_ro_rang_thi_no_thang(tmp_path, cau_hinh):
    cs = ChannelSync(str(tmp_path), network_timeout_s=45, cau_hinh_mang=cau_hinh)
    assert cs.cau_hinh_mang.network_timeout_s == 45


def test_cookie_van_giu_khi_ghi_de_timeout(tmp_path, cau_hinh):
    cs = ChannelSync(str(tmp_path), network_timeout_s=45, cau_hinh_mang=cau_hinh)
    assert cs.cau_hinh_mang.cookies_browser == "chrome"
    assert cs.cau_hinh_mang.sleep_requests_s == 7.5


# ---------------------------------------------------------------- watch

def test_giam_sat_dung_lister_mang_cau_hinh_cua_engine():
    """Vòng giám sát chạy lặp theo lịch nên là nơi dễ bị chặn nhất."""
    class EngineGia:
        def cau_hinh_mang(self):
            return y.CauHinhMang(cookies_browser="edge", sleep_requests_s=3.0)

    nhan = {}

    def gia(url, limit=None, **kw):
        nhan.update(kw)
        return []

    lister = watch._lister_theo_cau_hinh(EngineGia())
    goc = ChannelSync.list_channel
    try:
        channel.ChannelSync.list_channel = staticmethod(gia)
        lister("https://youtube.com/@x", 10)
    finally:
        channel.ChannelSync.list_channel = staticmethod(goc)
    assert nhan["cau_hinh_mang"].cookies_browser == "edge"


def test_lister_chiu_duoc_engine_khong_co_cau_hinh_mang():
    """Test cũ dựng engine giả tối giản; không được vỡ vì thiếu phương thức mới."""
    lister = watch._lister_theo_cau_hinh(object())
    assert callable(lister)


# ---------------------------------------------------------------- đọc từ đĩa

def test_tu_file_cau_hinh_doc_duoc_ma_khong_can_engine(tmp_path):
    """`cli.py vameta` cố tình không dựng Engine nhưng vẫn phải có cookie."""
    import json
    (tmp_path / "cau_hinh.json").write_text(json.dumps({
        "ytdlp_cookiefile": r"D:\c.txt",
        "ytdlp_cookies_browser": "firefox",
        "ytdlp_sleep_requests_s": 4.5,
        "network_timeout_s": 77,
    }), encoding="utf-8")
    cm = y.CauHinhMang.tu_file_cau_hinh(str(tmp_path))
    assert cm.cookiefile == r"D:\c.txt"
    assert cm.cookies_browser == "firefox"
    assert cm.sleep_requests_s == 4.5
    assert cm.network_timeout_s == 77


def test_tu_file_cau_hinh_chap_nhan_so_nguyen(tmp_path):
    """RUNBOOK bảo người dùng sửa tay JSON; gõ `2` thay `2.0` vẫn phải có tác dụng."""
    import json
    (tmp_path / "cau_hinh.json").write_text(
        json.dumps({"ytdlp_sleep_requests_s": 2}), encoding="utf-8")
    assert y.CauHinhMang.tu_file_cau_hinh(str(tmp_path)).sleep_requests_s == 2.0


@pytest.mark.parametrize("noi_dung", ["", "khong-phai-json", "[1,2,3]"])
def test_tu_file_cau_hinh_hong_thi_ve_mac_dinh(tmp_path, noi_dung):
    (tmp_path / "cau_hinh.json").write_text(noi_dung, encoding="utf-8")
    assert y.CauHinhMang.tu_file_cau_hinh(str(tmp_path)) == y.CauHinhMang()


def test_thieu_file_cau_hinh_thi_ve_mac_dinh(tmp_path):
    assert y.CauHinhMang.tu_file_cau_hinh(str(tmp_path)) == y.CauHinhMang()


def test_so_nguyen_trong_json_vao_duoc_truong_so_thuc():
    """cau_hinh.ap_vao_config so kiểu nghiêm ngặt; JSON không phân biệt 2 với 2.0."""
    import cau_hinh
    from engine import Config

    cfg = Config()
    bo_qua = cau_hinh.ap_vao_config(cfg, {"ytdlp_sleep_requests_s": 3})
    assert "ytdlp_sleep_requests_s" not in bo_qua
    assert cfg.ytdlp_sleep_requests_s == 3.0


def test_bool_khong_bi_coi_la_so():
    """`bool` là lớp con của `int`; True không được lặng lẽ thành 1.0."""
    import cau_hinh
    from engine import Config

    cfg = Config()
    bo_qua = cau_hinh.ap_vao_config(cfg, {"ytdlp_sleep_requests_s": True})
    assert "ytdlp_sleep_requests_s" in bo_qua
    assert cfg.ytdlp_sleep_requests_s == Config().ytdlp_sleep_requests_s
