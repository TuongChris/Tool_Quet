# -*- coding: utf-8 -*-
"""Lớp yt-dlp dùng chung: cookie, giãn nhịp, thứ tự client, diễn giải lỗi.

Bối cảnh 2026-08-18: sau một đợt tải dồn dập, YouTube chặn cả ĐỊA CHỈ MẠNG với
"Sign in to confirm you're not a bot" — đo thật: 8/8 video hỏng trên 5/5 player
client, kể cả những video vừa tải trót lọt một tiếng trước, trong khi liệt kê kênh
vẫn chạy. Đổi client không cứu được vì bot-check đánh ở khâu TRÍCH XUẤT.
"""

import json

import cau_hinh
import pytest
import ytdlp_chung as y
from engine import Config


# ---------------------------------------------------------------- cookie

def test_khong_cau_hinh_thi_khong_co_khoa_cookie():
    opts = y.CauHinhMang().tuy_chon()
    assert "cookiefile" not in opts and "cookiesfrombrowser" not in opts


def _cookie_hop_le(tmp_path, ten="cookies.txt"):
    p = tmp_path / ten
    p.write_text(
        "# Netscape HTTP Cookie File\n"
        + "\t".join([".youtube.com", "TRUE", "/", "TRUE", "9999999999", "SID", "gia_tri"])
        + "\n", encoding="utf-8")
    return p


def test_cookiefile_di_vao_dung_khoa(tmp_path):
    p = _cookie_hop_le(tmp_path)
    opts = y.CauHinhMang(cookiefile=str(p)).tuy_chon()
    assert opts["cookiefile"] == str(p)


@pytest.mark.parametrize("nhap,mong_doi", [
    ("chrome", ("chrome", None, None, None)),
    ("  Edge  ", ("edge", None, None, None)),
    ("edge:Profile 1", ("edge", "Profile 1", None, None)),
    ("firefox:", ("firefox", None, None, None)),
    ("", None),
    ("   ", None),
    (":khong-co-ten", None),
])
def test_phan_tich_cookies_browser(nhap, mong_doi):
    """yt-dlp nhận tuple (trình duyệt, profile, keyring, container) — KHÁC thứ tự
    của chuỗi trên dòng lệnh, nên không được truyền thẳng chuỗi người dùng gõ."""
    assert y.phan_tich_cookies_browser(nhap) == mong_doi


def test_co_cookie_nhan_dien_ca_hai_cach():
    assert not y.CauHinhMang().co_cookie
    assert y.CauHinhMang(cookiefile="x").co_cookie
    assert y.CauHinhMang(cookies_browser="chrome").co_cookie
    assert not y.CauHinhMang(cookiefile="   ").co_cookie


# ---------------------------------------------------------------- thứ tự client

def test_khong_cookie_thi_giu_nguyen_thu_tu():
    ds = ["android", "", "tv"]
    assert y.sap_xep_player_clients(ds, False) == ds


def test_co_cookie_thi_client_khong_ho_tro_lui_xuong_cuoi():
    """yt-dlp GỠ client không hỗ trợ cookie khi phiên đã đăng nhập; để chúng đứng đầu
    là mỗi video mất vài lượt thử vô ích."""
    ra = y.sap_xep_player_clients(["android", "", "tv", "ios", "web_safari"], True)
    assert ra[0] == "", "client mặc định hỗ trợ cookie nên phải được thử trước"
    assert set(ra[-2:]) == {"android", "ios"}
    assert sorted(ra) == sorted(["android", "", "tv", "ios", "web_safari"]), \
        "chỉ đổi thứ tự, không được mất client nào"


def test_client_khong_ho_tro_cookie_doc_duoc_tu_yt_dlp():
    khong = y.client_khong_ho_tro_cookie()
    assert "android" in khong and "ios" in khong
    assert "web" not in khong and "tv" not in khong


def test_toan_bo_danh_sach_khong_ho_tro_thi_van_con_duong_lui():
    ra = y.sap_xep_player_clients(["android", "ios"], True)
    assert ra[0] == "", "phải chèn client mặc định thay vì trả danh sách rỗng"


# ---------------------------------------------------------------- giãn nhịp

def test_gian_nhip_trich_xuat_dung_khoa_sleep_interval_requests():
    """`sleep_interval` chỉ tác dụng ở khâu TẢI. Bot-check đánh ở khâu TRÍCH XUẤT nên
    chỉ `sleep_interval_requests` mới đúng chỗ."""
    opts = y.CauHinhMang(sleep_requests_s=2.0).tuy_chon()
    assert opts["sleep_interval_requests"] == 2.0
    assert "sleep_interval" not in opts


def test_tat_gian_nhip_thi_khong_them_khoa():
    opts = y.CauHinhMang(sleep_requests_s=0.0).tuy_chon()
    assert "sleep_interval_requests" not in opts


def test_gian_nhip_tai_ke_ca_khi_quen_dat_max():
    opts = y.CauHinhMang(sleep_min_s=5.0, sleep_max_s=0.0).tuy_chon()
    assert opts["sleep_interval"] == 5.0
    assert opts["max_sleep_interval"] == 5.0, "max không được nhỏ hơn min"


def test_no_color_luon_bat():
    """Chữa tận gốc escape ANSI thay vì chỉ dọn lúc hiển thị."""
    assert y.CauHinhMang().tuy_chon()["no_color"] is True


def test_tuy_chon_rieng_de_len_tuy_chon_chung():
    opts = y.CauHinhMang(network_timeout_s=30).tuy_chon(socket_timeout=99, format="ba")
    assert opts["socket_timeout"] == 99 and opts["format"] == "ba"


# ---------------------------------------------------------------- diễn giải lỗi

def test_bot_check_duoc_giai_thich_la_chan_theo_dia_chi_mang():
    tin = y.giai_thich_loi(
        "ERROR: [youtube] abc: Sign in to confirm you're not a bot. "
        "Use --cookies-from-browser or --cookies for the authentication.")
    assert "ĐỊA CHỈ MẠNG" in tin
    assert "cookies-from-browser" not in tin, "cắt đuôi hướng dẫn dài của yt-dlp"
    assert y.giai_thich_loi(tin) == tin, "luỹ đẳng"


def test_bot_check_khong_bi_nham_thanh_gioi_han_do_tuoi():
    """Hai câu của YouTube đều mở đầu bằng 'Sign in to confirm...' — phân biệt sai thì
    lời khuyên đưa ra cũng sai."""
    bot = y.giai_thich_loi("Sign in to confirm you're not a bot.")
    tuoi = y.giai_thich_loi("Sign in to confirm your age. This video may be inappropriate.")
    assert "ĐỊA CHỈ MẠNG" in bot and "độ tuổi" not in bot
    assert "độ tuổi" in tuoi and "ĐỊA CHỈ MẠNG" not in tuoi


def test_go_ma_mau_ca_khi_thieu_ky_tu_escape():
    assert y.go_ma_mau("\x1b[0;31mERROR:\x1b[0m 403") == "ERROR: 403"
    assert y.go_ma_mau("[0;31mERROR:[0m 403") == "ERROR: 403"


def test_loi_khong_nhan_dien_duoc_thi_giu_nguyen():
    assert y.giai_thich_loi("Nén audio thất bại: abc") == "Nén audio thất bại: abc"


# ---------------------------------------------------------------- đường lui client

def test_thu_tung_client_tra_ve_ngay_khi_co_cai_chay():
    da = []

    def chay(opts):
        ten = (opts.get("extractor_args", {}).get("youtube", {})
               .get("player_client") or [""])[0]
        da.append(ten or "mặc định")
        if ten != "tv":
            raise RuntimeError("403 Forbidden")
        return "xong"

    assert y.thu_tung_client(["android", "", "tv", "ios"], chay, {}) == "xong"
    assert da == ["android", "mặc định", "tv"], "phải dừng ngay khi có cái chạy"


def test_thu_tung_client_khong_lam_ban_opts_goc():
    goc = {"format": "ba/b"}
    y.thu_tung_client(["android"], lambda o: None, goc)
    assert goc == {"format": "ba/b"}


def test_bo_qua_khong_kich_hoat_duong_lui():
    """Huỷ là ý người dùng — không được lặng lẽ thử tiếp cho hết danh sách."""
    class Huy(Exception):
        pass

    dem = []

    def chay(opts):
        dem.append(1)
        raise Huy()

    with pytest.raises(Huy):
        y.thu_tung_client(["android", "", "tv"], chay, {}, bo_qua=(Huy,))
    assert len(dem) == 1


def test_hong_het_thi_bao_du_danh_sach_va_khong_con_ma_mau():
    def chay(opts):
        raise RuntimeError("\x1b[0;31mERROR:\x1b[0m HTTP Error 403: Forbidden")

    with pytest.raises(RuntimeError) as ei:
        y.thu_tung_client(["android", "", "tv"], chay, {})
    tin = str(ei.value)
    assert "android" in tin and "mặc định" in tin and "tv" in tin
    assert "403" in tin and "\x1b" not in tin


# ---------------------------------------------------------------- nối với Config

def test_tu_config_doc_dung_cac_truong():
    cfg = Config()
    cfg.ytdlp_cookies_browser = "chrome"
    cfg.ytdlp_sleep_requests_s = 2.5
    cm = y.CauHinhMang.tu_config(cfg)
    assert cm.cookies_browser == "chrome"
    assert cm.sleep_requests_s == 2.5
    assert cm.network_timeout_s == cfg.network_timeout_s


def test_tu_config_chiu_duoc_config_thieu_truong():
    """Cấu hình cũ của người dùng chưa có các trường này."""
    class Cu:
        network_timeout_s = 30

    cm = y.CauHinhMang.tu_config(Cu())
    assert cm.cookiefile == "" and cm.sleep_requests_s == 1.0


def test_mac_dinh_co_gian_nhip_chu_khong_phai_0():
    """Không giãn nhịp là lý do YouTube chặn IP hôm 18/08."""
    assert Config().ytdlp_sleep_requests_s > 0


def test_config_moi_di_qua_duoc_vong_luu_va_nap(tmp_path):
    """cau_hinh.ap_vao_config so kiểu bằng `type(x) is not type(y)` — trường khai
    kiểu sai (vd Optional[str]) sẽ bị loại lặng lẽ khi nạp lại."""
    cfg = Config()
    cfg.ytdlp_cookiefile = r"D:\cookies.txt"
    cfg.ytdlp_cookies_browser = "edge:Profile 1"
    cfg.ytdlp_sleep_requests_s = 1.5
    cfg.ytdlp_sleep_min_s = 2.0
    cfg.ytdlp_sleep_max_s = 4.0

    cau_hinh.ghi_cau_hinh(str(tmp_path), cau_hinh.lay_tu_config(cfg))
    du_lieu = json.loads((tmp_path / cau_hinh.TEN_FILE).read_text(encoding="utf-8"))

    moi = Config()
    bi_bo_qua = cau_hinh.ap_vao_config(moi, du_lieu)
    assert not [k for k in bi_bo_qua if k.startswith("ytdlp_")], bi_bo_qua
    assert moi.ytdlp_cookiefile == r"D:\cookies.txt"
    assert moi.ytdlp_cookies_browser == "edge:Profile 1"
    assert moi.ytdlp_sleep_requests_s == 1.5
    moi.validate()


def test_validate_khong_doi_file_cookie_phai_ton_tai():
    """validate() chạy trong try/except lúc khởi động; ném lỗi ở đó sẽ RESET toàn bộ
    cấu hình người dùng về mặc định."""
    cfg = Config()
    cfg.ytdlp_cookiefile = r"D:\khong-he-ton-tai\cookies.txt"
    cfg.validate()


@pytest.mark.parametrize("truong,gia_tri", [
    ("ytdlp_sleep_requests_s", -1.0),
    ("ytdlp_sleep_requests_s", 61.0),
    ("ytdlp_sleep_min_s", -0.5),
])
def test_validate_chan_gia_tri_gian_nhip_vo_ly(truong, gia_tri):
    cfg = Config()
    setattr(cfg, truong, gia_tri)
    with pytest.raises(ValueError):
        cfg.validate()


def test_validate_chan_max_nho_hon_min():
    cfg = Config()
    cfg.ytdlp_sleep_min_s, cfg.ytdlp_sleep_max_s = 10.0, 2.0
    with pytest.raises(ValueError):
        cfg.validate()
