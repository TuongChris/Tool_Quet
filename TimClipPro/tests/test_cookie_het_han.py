# -*- coding: utf-8 -*-
"""Cookie hết hiệu lực không được làm hỏng cả lượt quét.

Ca thật 18/08/2026, đo trên 8 link người dùng gửi + 2 video đối chứng, cùng máy cùng
lúc:

    không cookie : 24 format, có 139/249/140/251 (audio-only)  -> 8/8 link chạy
    có cookie    :  4 format, TOÀN storyboard (ảnh thu nhỏ)    -> 0/8 link chạy

Cookie chết khiến YouTube trả phản hồi không có media. Tool xin `bestaudio`, không có
gì để chọn, nên yt-dlp báo "Requested format is not available" — câu chữ chẳng liên
quan gì tới nguyên nhân, đẩy người dùng đi tìm nhầm phía link.

Điểm mấu chốt: **cookie chết còn TỆ HƠN không có cookie**, nên phải tự lùi về.
Và hạn ghi trong file KHÔNG phản ánh việc phiên còn sống — file vẫn "còn 400 ngày"
trong khi YouTube đã huỷ phiên.
"""

import pytest
import ytdlp_chung as y

LOI_THAT = ("ERROR: [youtube] s5lLFCSzPn8: Requested format is not available. "
            "Use --list-formats for a list of available formats")
LOI_THAT_2 = ("ERROR: [youtube] r9UeXL5-Yvk: No video formats found!; please report "
              "this issue on https://github.com/yt-dlp/yt-dlp/issues")

CO_COOKIE = y.CauHinhMang(cookiefile=r"D:\cookies.txt")
KHONG_COOKIE = y.CauHinhMang()


# ---------------------------------------------------------------- nhận dạng

@pytest.mark.parametrize("tin", [LOI_THAT, LOI_THAT_2,
                                 "requested format is not available"])
def test_nhan_dien_dau_hieu_cookie_chet(tin):
    assert y.la_dau_hieu_cookie_chet(tin)


@pytest.mark.parametrize("tin", [
    "ERROR: Sign in to confirm you're not a bot.",
    "ERROR: HTTP Error 403: Forbidden",
    "ERROR: This video is not available",
    "Nén audio thất bại",
])
def test_khong_nham_lo_i_khac_thanh_cookie_chet(tin):
    assert not y.la_dau_hieu_cookie_chet(tin)


# ---------------------------------------------------------------- bỏ cookie

def test_bo_cookie_giu_nguyen_tham_so_khac():
    goc = y.CauHinhMang(cookiefile="c.txt", cookies_browser="chrome",
                        sleep_requests_s=3.0, network_timeout_s=77)
    sach = goc.bo_cookie()
    assert sach.co_cookie is False
    assert sach.cookiefile == "" and sach.cookies_browser == ""
    assert sach.sleep_requests_s == 3.0, "nhịp tải phải giữ"
    assert sach.network_timeout_s == 77
    assert goc.co_cookie is True, "bản gốc không được đổi (dataclass bất biến)"


# ---------------------------------------------------------------- đường lui

def test_cookie_chet_thi_tu_chay_lai_khong_cookie():
    """Đúng ca thật: có cookie thì hỏng, bỏ cookie ra thì chạy."""
    da_goi = []

    def chay(ch):
        da_goi.append(ch.co_cookie)
        if ch.co_cookie:
            raise RuntimeError(LOI_THAT)
        return "24 format"

    assert y.chay_kem_duong_lui_cookie(CO_COOKIE, chay) == "24 format"
    assert da_goi == [True, False], "phải thử có cookie trước, rồi mới bỏ"


def test_bao_cho_ben_tren_biet_da_phai_bo_cookie():
    """Người dùng phải được cảnh báo để đi sửa gốc, không im lặng chạy tiếp mãi."""
    nhan = []

    def chay(ch):
        if ch.co_cookie:
            raise RuntimeError(LOI_THAT)
        return "ok"

    y.chay_kem_duong_lui_cookie(CO_COOKIE, chay, khi_bo_cookie=nhan.append)
    assert len(nhan) == 1 and y.la_dau_hieu_cookie_chet(nhan[0])


def test_khong_co_cookie_thi_khong_thu_lai():
    """Không cookie mà vẫn lỗi đó nghĩa là video thật sự hỏng — thử lại là vô ích."""
    dem = []

    def chay(ch):
        dem.append(1)
        raise RuntimeError(LOI_THAT)

    with pytest.raises(RuntimeError):
        y.chay_kem_duong_lui_cookie(KHONG_COOKIE, chay)
    assert len(dem) == 1


def test_loi_khac_khong_kich_hoat_duong_lui():
    """Bot-check, 403, huỷ... phải ném nguyên ra, không được che bằng việc bỏ cookie."""
    dem = []

    def chay(ch):
        dem.append(1)
        raise RuntimeError("ERROR: Sign in to confirm you're not a bot.")

    with pytest.raises(RuntimeError, match="not a bot"):
        y.chay_kem_duong_lui_cookie(CO_COOKIE, chay)
    assert len(dem) == 1


def test_bo_cookie_van_hong_thi_bao_loi_GOC():
    """Cookie không phải nguyên nhân — phải cho người dùng thấy vấn đề thật của video,
    đừng dẫn họ đi sửa cookie."""
    def chay(ch):
        if ch.co_cookie:
            raise RuntimeError(LOI_THAT)
        raise RuntimeError("ERROR: This video is not available")

    with pytest.raises(RuntimeError) as ei:
        y.chay_kem_duong_lui_cookie(CO_COOKIE, chay)
    assert "Requested format is not available" in str(ei.value)


def test_chay_duoc_ngay_lan_dau_thi_khong_dung_toi_duong_lui():
    dem = []
    assert y.chay_kem_duong_lui_cookie(
        CO_COOKIE, lambda ch: dem.append(1) or "ok") == "ok"
    assert len(dem) == 1


# ---------------------------------------------------------------- diễn giải

def test_giai_thich_dung_khi_co_cookie():
    tin = y.giai_thich_loi(LOI_THAT, co_cookie=True)
    assert "hết hiệu lực" in tin
    assert "XOÁ TRỐNG" in tin, "phải nói rõ người dùng cần làm gì"


def test_khong_do_cho_cookie_khi_phien_khong_co_cookie():
    """Cùng câu lỗi đó, không cookie thì nghĩa là video thật sự không còn định dạng
    nào — đổ cho cookie sẽ đẩy người dùng đi sửa nhầm chỗ."""
    tin = y.giai_thich_loi(LOI_THAT, co_cookie=False)
    assert "hết hiệu lực" not in tin


def test_giai_thich_van_luy_dang():
    mot = y.giai_thich_loi(LOI_THAT, co_cookie=True)
    assert y.giai_thich_loi(mot, co_cookie=True) == mot


def test_bot_check_van_duoc_uu_tien_dung():
    """Có cookie mà gặp bot-check thì vẫn phải nói là chặn theo IP."""
    tin = y.giai_thich_loi("Sign in to confirm you're not a bot.", co_cookie=True)
    assert "ĐỊA CHỈ MẠNG" in tin and "hết hiệu lực" not in tin


# ---------------------------------------------------------------- nối vào engine

def test_engine_va_channel_deu_dung_duong_lui_cookie():
    """Bài học mục 6b/9 trong CLAUDE.md: vá một đường là chưa xong."""
    import os
    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for ten in ("engine.py", "channel.py"):
        nguon = open(os.path.join(goc, ten), encoding="utf-8").read()
        assert "chay_kem_duong_lui_cookie" in nguon, f"{ten} thiếu đường lui cookie"


def test_engine_canh_bao_len_giao_dien(tmp_path):
    """Cảnh báo phải tới được người dùng, không chỉ nằm trong file log."""
    from engine import Engine

    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "d"),
               out_dir=str(tmp_path / "r"))
    e.canh_bao_mang = []
    e._canh_bao_cookie_chet(RuntimeError(LOI_THAT))
    assert len(e.canh_bao_mang) == 1
    assert "hết hiệu lực" in e.canh_bao_mang[0]
    e._canh_bao_cookie_chet(RuntimeError(LOI_THAT))
    assert len(e.canh_bao_mang) == 1, "không lặp lại cùng một cảnh báo cho mỗi video"


def test_canh_bao_mang_khong_bi_merge_xoa_mat(tmp_path):
    """`_merge()` xoá trắng `canh_bao_gop` ở mỗi lượt khớp, mà cảnh báo mạng sinh ra
    TRƯỚC đó — dùng chung danh sách là mất trắng, người dùng không bao giờ biết cookie
    đã chết."""
    import inspect

    from engine import Engine

    nguon = inspect.getsource(Engine._merge)
    assert "self.canh_bao_gop = []" in nguon, "test này giả định _merge xoá canh_bao_gop"
    assert "canh_bao_mang" not in nguon, "_merge không được đụng tới cảnh báo mạng"
