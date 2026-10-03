# -*- coding: utf-8 -*-
"""Phân loại lỗi truy cập YouTube, che bí mật và chẩn đoán cookie — phần THUẦN.

Mọi chuỗi lỗi dưới đây là văn bản TỔNG HỢP dựng theo đúng khuôn câu của yt-dlp 2026.08.19
(`yt_dlp/extractor/youtube/_video.py`, `_base.py`, `cookies.py`), cộng chữ ký thật đã gặp ở
Tier 2 (Job 43: ``ERROR: [youtube] oNgXYOLAJWk: Video unavailable``). Không có cookie, token
hay khoá thật nào; ``BI_MAT`` là chuỗi giả.
"""

import json
import os
import time

import pytest

import nhat_ky
import truy_cap_youtube as t
import ytdlp_chung as y

BI_MAT = "GIA_TRI_BI_MAT_GIA_7f3a9c"

_HUONG_DAN = ("Use --cookies-from-browser or --cookies for the authentication. See  "
              "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp  for "
              "how to manually pass cookies.")

BOT = [
    f"ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you’re not a bot. {_HUONG_DAN}",
    "ERROR: [youtube] abcdefghijk: Sign in to confirm you're not a bot. This helps protect",
    "ERROR: [youtube] abcdefghijk: Video unavailable. YouTube is requiring a captcha challenge "
    "before playback",
    "ERROR: [youtube] abcdefghijk: All player responses are invalid. Your IP is likely being "
    "blocked by Youtube",
]
AUTH = [
    f"ERROR: [youtube] abcdefghijk: Sign in to confirm your age. This video may be "
    f"inappropriate for some users. {_HUONG_DAN}",
    "ERROR: [youtube] abcdefghijk: Join this channel to get access to members-only content "
    "like this video, and other exclusive perks.",
    "ERROR: [youtube] abcdefghijk: This video is available to this channel's members on "
    "level: Fan (or any higher level).",
    f"ERROR: [youtube:tab] UCabc: Login details are needed to download this content. "
    f"{_HUONG_DAN}",
]
VINH_VIEN = [
    "ERROR: [youtube] oNgXYOLAJWk: Video unavailable",        # Tier 2, Job 43 — nguyên văn
    "ERROR: [youtube] abcdefghijk: Video unavailable. This video is no longer available "
    "because the YouTube account associated with this video has been terminated.",
    f"ERROR: [youtube] abcdefghijk: Private video. Sign in if you've been granted access to "
    f"this video. {_HUONG_DAN}",
    "ERROR: [youtube] abcdefghijk: This video has been removed for violating YouTube's "
    "Terms of Service",
    "ERROR: [youtube] abcdefghijk: Video unavailable. This video is not available",
    "ERROR: [youtube] abcdefghijk: The uploader has not made this video available in your "
    "country",
    "ERROR: [youtube] abc: Incomplete YouTube ID abc. URL https://youtu.be/abc looks truncated.",
    "ERROR: [youtube:tab] @khongtontai: This channel does not exist.",
]
GIOI_HAN_429 = [
    "ERROR: [youtube] abcdefghijk: Unable to download API page: HTTP Error 429: Too Many "
    "Requests",
    "ERROR: unable to download video data: HTTP Error 429: Too Many Requests",
]
GIOI_HAN_PHIEN = [
    "ERROR: [youtube] abcdefghijk: This content isn't available, try again later. The current "
    "session has been rate-limited by YouTube for up to an hour.",
]
CAM_403 = [
    "ERROR: unable to download video data: HTTP Error 403: Forbidden",
    "Không tải được audio. Đã thử: mặc định, android. Lỗi cuối: ERROR: unable to download "
    "video data: HTTP Error 403: Forbidden",
]
TAM_THOI = [
    "ERROR: [youtube] abcdefghijk: Unable to download API page: The read operation timed out",
    "ERROR: [youtube] abcdefghijk: Unable to download webpage: ('Connection aborted.', "
    "ConnectionResetError(10054, 'An existing connection was forcibly closed by the remote "
    "host', None, 10054, None))",
    "ERROR: [youtube] abcdefghijk: Unable to download webpage: <urlopen error [Errno 11001] "
    "getaddrinfo failed>",
    "ERROR: unable to download video data: HTTP Error 503: Service Unavailable",
    "ERROR: [youtube] abcdefghijk: Unable to download API page: HTTP Error 500: Internal "
    "Server Error",
    "ERROR: [youtube] abcdefghijk: Incomplete data received",
    "ERROR: [youtube] abcdefghijk: Unable to download webpage: Remote end closed connection "
    "without response",
]
DINH_DANG = [
    "ERROR: [youtube] s5lLFCSzPn8: Requested format is not available. Use --list-formats for "
    "a list of available formats",
    "ERROR: [youtube] r9UeXL5-Yvk: No video formats found!; please report this issue",
    "ERROR: [youtube] abcdefghijk: The page needs to be reloaded.",
    "ERROR: [youtube] abcdefghijk: n challenge solving failed: Some formats may be missing.",
    "ERROR: [youtube] abcdefghijk: This video is DRM protected",
]
TAI_HONG = [
    "Tải audio thất bại (không thấy file sau khi tải).",
    "ERROR: Did not get any data blocks",
    "ERROR: The downloaded file is empty",
]
KHONG_RO = [
    "ERROR: [youtube] abcdefghijk: This live event will begin in a few moments.",
    "Nén audio thất bại: abc",
]

BANG = ([(x, t.BOT_CHALLENGE) for x in BOT] + [(x, t.AUTH_REQUIRED) for x in AUTH]
        + [(x, t.PERMANENT_UNAVAILABLE) for x in VINH_VIEN]
        + [(x, t.RATE_LIMITED) for x in GIOI_HAN_429 + GIOI_HAN_PHIEN]
        + [(x, t.HTTP_FORBIDDEN) for x in CAM_403]
        + [(x, t.TRANSIENT_NETWORK) for x in TAM_THOI]
        + [(x, t.FORMAT_OR_EXTRACTOR_ERROR) for x in DINH_DANG]
        + [(x, t.PARTIAL_OR_CORRUPT_DOWNLOAD) for x in TAI_HONG]
        + [(x, t.UNKNOWN_YOUTUBE_ERROR) for x in KHONG_RO])


# =====================================================================
#  Phân loại
# =====================================================================

@pytest.mark.parametrize("tin,loai", BANG)
def test_phan_loai_dung_tung_khuon_cau(tin, loai):
    assert t.phan_loai_loi(RuntimeError(tin)).category == loai


@pytest.mark.parametrize("tin,loai", BANG)
def test_phan_loai_chiu_duoc_ma_mau_ansi(tin, loai):
    """yt-dlp tô màu chữ ERROR; bản ghi cũ trong lịch sử còn nguyên escape."""
    assert t.phan_loai_loi(RuntimeError("\x1b[0;31m" + tin + "\x1b[0m")).category == loai


@pytest.mark.parametrize("tin", VINH_VIEN)
def test_video_bi_go_khong_bao_gio_la_bot_hay_cookie(tin):
    """Tier 2 Job 43/130: video thật sự bị gỡ — không được đẩy người dùng đi sửa cookie."""
    f = t.phan_loai_loi(RuntimeError(tin))
    assert f.category == t.PERMANENT_UNAVAILABLE
    assert not f.retryable and not f.auth_related and not f.rate_limited


def test_chu_sign_in_cua_video_rieng_tu_khong_bi_coi_la_can_dang_nhap():
    """Câu riêng tư của YouTube có "Sign in if you've been granted access" — luật kiểu
    ``"sign" in loi`` sẽ nhầm thành lỗi đăng nhập."""
    for tin in ("ERROR: [youtube] x: Private video. Sign in if you've been granted access",
                "ERROR: [youtube] x: Signature mismatch while parsing player"):
        assert t.phan_loai_loi(RuntimeError(tin)).category != t.AUTH_REQUIRED


@pytest.mark.parametrize("tin", BOT + AUTH)
def test_bot_va_dang_nhap_khong_duoc_thu_lai(tin):
    f = t.phan_loai_loi(RuntimeError(tin))
    assert not f.retryable
    assert f.auth_related


@pytest.mark.parametrize("tin", TAM_THOI)
def test_loi_mang_tam_thoi_duoc_thu_lai(tin):
    assert t.phan_loai_loi(RuntimeError(tin)).retryable


@pytest.mark.parametrize("tin", GIOI_HAN_429)
def test_http_429_la_gioi_han_va_thu_lai_co_gioi_han(tin):
    f = t.phan_loai_loi(RuntimeError(tin))
    assert f.rate_limited and f.retryable


@pytest.mark.parametrize("tin", GIOI_HAN_PHIEN)
def test_phien_bi_gioi_han_toi_mot_tieng_thi_khong_thu_lai(tin):
    f = t.phan_loai_loi(RuntimeError(tin))
    assert f.category == t.RATE_LIMITED and f.rate_limited and not f.retryable


@pytest.mark.parametrize("tin", CAM_403 + DINH_DANG + TAI_HONG + KHONG_RO + VINH_VIEN)
def test_loi_khong_tam_thoi_thi_khong_thu_lai(tin):
    assert not t.phan_loai_loi(RuntimeError(tin)).retryable


def test_403_khong_tu_suy_ra_cookie_hong_hay_bot():
    f = t.phan_loai_loi(RuntimeError(CAM_403[0]))
    assert f.category == t.HTTP_FORBIDDEN
    assert not f.auth_related
    thap = f.human_message_vi.lower()
    assert "cookie" not in thap or "chưa đủ" in thap


class _HTTPErrorGia(Exception):
    """Giống `yt_dlp.networking.exceptions.HTTPError`: mang mã ở `.status`."""

    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


class _DownloadErrorGia(Exception):
    """Giống `yt_dlp.utils.DownloadError`: lỗi gốc nằm ở `exc_info[1]`."""

    def __init__(self, msg, goc):
        super().__init__(msg)
        self.exc_info = (type(goc), goc, None)


def test_doc_ma_http_that_trong_chuoi_ngoai_le():
    goc = _HTTPErrorGia(429, "HTTP Error 429")
    f = t.phan_loai_loi(_DownloadErrorGia("ERROR: Unable to download API page", goc))
    assert f.category == t.RATE_LIMITED and f.http_status == 429 and f.retryable


@pytest.mark.parametrize("ma,loai", [(503, t.TRANSIENT_NETWORK), (502, t.TRANSIENT_NETWORK),
                                     (404, t.PERMANENT_UNAVAILABLE),
                                     (403, t.HTTP_FORBIDDEN), (429, t.RATE_LIMITED)])
def test_ma_http_quyet_dinh_loai(ma, loai):
    loi = RuntimeError("ERROR: lỗi bọc ngoài")
    loi.__cause__ = _HTTPErrorGia(ma, f"HTTP Error {ma}")
    assert t.phan_loai_loi(loi).category == loai


def test_403_kem_cau_bot_van_la_bot():
    loi = RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot")
    loi.__cause__ = _HTTPErrorGia(403, "HTTP Error 403")
    assert t.phan_loai_loi(loi).category == t.BOT_CHALLENGE


@pytest.mark.parametrize("loi", [TimeoutError("timed out"),
                                 ConnectionResetError(10054, "forcibly closed"),
                                 ConnectionAbortedError("aborted")])
def test_ngoai_le_mang_cua_python_la_tam_thoi(loi):
    assert t.phan_loai_loi(loi).category == t.TRANSIENT_NETWORK


def test_loi_boc_ngoai_van_doc_duoc_nguyen_nhan_trong():
    try:
        try:
            raise RuntimeError("ERROR: [youtube] x: Sign in to confirm you're not a bot")
        except RuntimeError as trong:
            raise RuntimeError("Không tải được audio. Đã thử: mặc định.") from trong
    except RuntimeError as ngoai:
        assert t.phan_loai_loi(ngoai).category == t.BOT_CHALLENGE


def test_file_cookie_hong_la_loi_cookie_va_giu_thong_bao_so_dong():
    loi = y.LoiFileCookie("File cookie «c.txt» sai định dạng Netscape ở dòng 2. Nguyên nhân…")
    f = t.phan_loai_loi(loi)
    assert f.category == t.COOKIE_INVALID_OR_EXPIRED
    assert f.auth_related and not f.retryable
    assert "dòng 2" in f.human_message_vi


def test_ket_qua_phan_loai_mang_du_truong_brief_yeu_cau():
    f = t.phan_loai_loi(RuntimeError(BOT[0]), thao_tac="metadata", video_id="dQw4w9WgXcQ",
                        lan_thu=1, toi_da=1)
    for truong in ("category", "operation", "video_id", "retryable", "auth_related",
                   "rate_limited", "human_message_vi", "technical_summary", "http_status",
                   "attempt", "max_attempts"):
        assert hasattr(f, truong), truong
    assert f.operation == "metadata" and f.video_id == "dQw4w9WgXcQ"
    assert f.attempt == 1 and f.max_attempts == 1


@pytest.mark.parametrize("tin,loai", BANG)
def test_thong_bao_tieng_viet_noi_ro_va_tom_tat_ky_thuat_gon(tin, loai):
    f = t.phan_loai_loi(RuntimeError("\x1b[0;31m" + tin))
    assert f.human_message_vi and f.human_message_vi[0].isupper()
    assert "\x1b" not in f.technical_summary
    assert "Use --cookies" not in f.technical_summary, "đuôi hướng dẫn yt-dlp phải bị cắt"
    assert len(f.technical_summary) <= 300


def test_thong_bao_cho_bot_va_429_noi_ro_tool_da_dung():
    bot = t.phan_loai_loi(RuntimeError(BOT[0])).human_message_vi
    gioi = t.phan_loai_loi(RuntimeError(GIOI_HAN_429[0])).human_message_vi
    assert "đã dừng" in bot.lower() and "xác minh" in bot.lower()
    assert "giới hạn" in gioi.lower() and "đã dừng" in gioi.lower()


def test_loi_truy_cap_mang_ket_qua_phan_loai_va_doc_lai_duoc():
    f = t.phan_loai_loi(RuntimeError(BOT[0]))
    loi = t.LoiTruyCapYouTube(f)
    assert loi.that_bai is f
    assert t.phan_loai_loi(loi) is f
    assert t.tim_loi_truy_cap(RuntimeError("bọc")) is None
    try:
        raise RuntimeError("bọc ngoài") from loi
    except RuntimeError as e:
        assert t.tim_loi_truy_cap(e) is f


# =====================================================================
#  giai_thich_loi — giữ hợp đồng cũ, nhận thêm chữ ký thật
# =====================================================================

def test_giai_thich_loi_nhan_ra_video_unavailable_cua_tier_2():
    tin = y.giai_thich_loi(VINH_VIEN[0])
    assert y.CHU_THICH["go"] in tin
    assert y.giai_thich_loi(tin) == tin, "luỹ đẳng"


def test_giai_thich_loi_tra_nguyen_thong_bao_da_phan_loai():
    loi = t.LoiTruyCapYouTube(t.phan_loai_loi(RuntimeError(BOT[0])))
    assert y.giai_thich_loi(loi) == str(loi)
    assert y.giai_thich_loi(str(loi)) == str(loi), "chuỗi đã phân loại không bị dán thêm"


def test_giai_thich_loi_che_bi_mat_trong_url():
    tin = y.giai_thich_loi(
        f"ERROR: unable to download video data: https://rr1---sn-a.googlevideo.com/"
        f"videoplayback?expire=1&sig={BI_MAT}: HTTP Error 403: Forbidden")
    assert BI_MAT not in tin and "HTTP Error 403" in tin


# =====================================================================
#  Che bí mật
# =====================================================================

# Mẫu bí mật GIẢ, ghép lúc chạy: viết nguyên văn thì máy quét bí mật — kể cả luật nội dung
# `dong_goi.ly_do_noi_dung_nhay_cam` khi áp cho mọi file — coi chính file test này là chứa
# khoá riêng / khoá JSON thật.
_PEM_DAU = "-----BEGIN " + "PRIVATE KEY-----"
_PEM_CUOI = "-----END " + "PRIVATE KEY-----"
_TRUONG_KHOA_JSON = '"private' + '_key"'

RO_RI = [
    f"Cookie: SID={BI_MAT}; HSID={BI_MAT}",
    f"cookie: {BI_MAT}",
    f"Set-Cookie: __Secure-1PSID={BI_MAT}; Path=/; Secure",
    f"Authorization: Bearer {BI_MAT}",
    f"authorization: SAPISIDHASH 1700000000_{BI_MAT}",
    f"https://rr1---sn-x.googlevideo.com/videoplayback?expire=1&sig={BI_MAT}"
    f"&lsig={BI_MAT}&ip=203.0.113.9",
    f"https://www.youtube.com/watch?v=dQw4w9WgXcQ&token={BI_MAT}",
    f"https://example.com/api?key={BI_MAT}&x=1",
    f"access_token={BI_MAT}",
    f"?token={BI_MAT}",
    f"&sig={BI_MAT}",
    f'{_TRUONG_KHOA_JSON}: "{_PEM_DAU}\\n{BI_MAT}\\n{_PEM_CUOI}\\n"',
    f"{_PEM_DAU}\n{BI_MAT}\n{_PEM_CUOI}",
    f".youtube.com\tTRUE\t/\tTRUE\t9999999999\t__Secure-1PSID\t{BI_MAT}",
    f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\t{BI_MAT}",
    f"WARNING: skipping cookie file entry due to invalid length 1: "
    f"'.youtube.com TRUE / TRUE 0 SID {BI_MAT}'",
    f"password: {BI_MAT}",
    f"LOGIN_INFO={BI_MAT}",
]


@pytest.mark.parametrize("tho", RO_RI)
def test_che_bi_mat_khong_de_lot_gia_tri(tho):
    sach = t.che_bi_mat(tho)
    assert BI_MAT not in sach
    assert t.che_bi_mat(sach) == sach, "luỹ đẳng"


def test_che_bi_mat_giu_thong_tin_chan_doan():
    giu = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ",
           "ERROR: unable to download video data: HTTP Error 403: Forbidden",
           "Không tải được audio. Đã thử: mặc định, android.",
           "[download] 12.3% of 45MB"]
    for x in giu:
        assert t.che_bi_mat(x) == x
    url = t.che_bi_mat("https://rr1---sn-x.googlevideo.com/videoplayback?itag=251&sig=abc")
    assert url.startswith("https://rr1---sn-x.googlevideo.com/videoplayback?")
    assert "abc" not in url


@pytest.mark.parametrize("tho", RO_RI)
def test_loi_truy_cap_khong_mang_bi_mat_qua_moi_duong(tho):
    f = t.phan_loai_loi(RuntimeError("ERROR: HTTP Error 403: Forbidden " + tho))
    loi = t.LoiTruyCapYouTube(f)
    for chuoi in (f.technical_summary, f.human_message_vi, str(loi), repr(f),
                  y.giai_thich_loi(loi), y.giai_thich_loi(RuntimeError(tho))):
        assert BI_MAT not in chuoi


def test_nhat_ky_che_ca_header_va_token():
    """Lớp thứ hai (stderr → file log) che được cả header/token, không chỉ dòng cookie."""
    for tho in (f"Cookie: {BI_MAT}\n", f"Authorization: Bearer {BI_MAT}\n",
                f"https://x.googlevideo.com/v?sig={BI_MAT}\n"):
        assert BI_MAT not in nhat_ky.che_bi_mat(tho)
    binh_thuong = "[download] 100% of 76.77MiB\nXONG: tải mới 12 video.\n"
    assert nhat_ky.che_bi_mat(binh_thuong) == binh_thuong


# =====================================================================
#  Cấu trúc + chẩn đoán cookie (chỉ đếm, không giá trị)
# =====================================================================

_DAU = "# Netscape HTTP Cookie File\n"


def _dong(mien, ten, gia_tri=BI_MAT, het_han="9999999999", httponly=False):
    dong = "\t".join([mien, "TRUE", "/", "TRUE", het_han, ten, gia_tri])
    return ("#HttpOnly_" + dong if httponly else dong) + "\n"


def _ghi(tmp_path, noi_dung, ten="cookies.txt"):
    p = tmp_path / ten
    p.write_text(noi_dung, encoding="utf-8")
    return str(p)


def _hop_le(tmp_path, dang_nhap=True):
    noi_dung = _DAU + _dong(".youtube.com", "PREF") + _dong(".youtube.com", "YSC", het_han="0")
    if dang_nhap:
        noi_dung += (_dong(".youtube.com", "LOGIN_INFO", httponly=True)
                     + _dong(".youtube.com", "SAPISID")
                     + _dong(".youtube.com", "__Secure-1PSID", httponly=True))
    noi_dung += _dong(".google.com", "NID") + _dong(".youtube.com", "OLD", het_han="1000")
    return _ghi(tmp_path, noi_dung)


def _khong_lo(cd):
    """Bản chẩn đoán ở MỌI dạng xuất không được mang giá trị hay tên cookie."""
    for chuoi in (repr(cd), str(cd), json.dumps(cd.thanh_dict(), ensure_ascii=False)):
        assert BI_MAT not in chuoi
        for ten in ("LOGIN_INFO", "SAPISID", "__Secure-1PSID", "PREF", "YSC", "NID"):
            assert ten not in chuoi


def test_chan_doan_khi_chua_cau_hinh():
    cd = t.chan_doan_cookie("")
    assert not cd.cau_hinh and cd.trang_thai == t.COOKIE_CHUA_CAU_HINH


def test_chan_doan_file_khong_ton_tai(tmp_path):
    cd = t.chan_doan_cookie(str(tmp_path / "khong_co.txt"))
    assert cd.cau_hinh and not cd.ton_tai and not cd.cau_truc_hop_le
    assert cd.trang_thai == t.COOKIE_KHONG_TON_TAI


def test_chan_doan_file_rong(tmp_path):
    cd = t.chan_doan_cookie(_ghi(tmp_path, ""))
    assert cd.kich_thuoc == 0 and cd.dinh_dang == "rong" and not cd.cau_truc_hop_le


def test_chan_doan_file_html_gia_danh_cookies_txt(tmp_path):
    cd = t.chan_doan_cookie(_ghi(tmp_path, "<!DOCTYPE html>\n<html><body>Sign in</body></html>"))
    assert cd.dinh_dang == "html" and not cd.cau_truc_hop_le


def test_chan_doan_file_json(tmp_path):
    cd = t.chan_doan_cookie(_ghi(tmp_path, '[{"name": "SID", "value": "%s"}]' % BI_MAT))
    assert cd.dinh_dang == "json" and not cd.cau_truc_hop_le
    _khong_lo(cd)


def test_chan_doan_file_netscape_hop_le_chi_dem(tmp_path):
    cd = t.chan_doan_cookie(_hop_le(tmp_path), bay_gio=2_000_000_000)
    assert cd.cau_truc_hop_le and cd.trang_thai == t.COOKIE_FILE_STRUCTURALLY_VALID
    assert cd.co_tieu_de and cd.dinh_dang == "netscape"
    assert cd.so_ban_ghi == 7, "dòng #HttpOnly_ là bản ghi thật (yt-dlp bóc tiền tố rồi nạp)"
    assert cd.so_ban_ghi_youtube == 6 and cd.so_ban_ghi_google == 1
    assert cd.so_het_han == 1, "cookie phiên (hạn 0) không tính là hết hạn"
    assert cd.co_cookie_dang_nhap is True
    assert cd.so_dong_hong == 0
    assert cd.phien_chap_nhan == t.COOKIE_PHIEN_CHUA_RO, "cấu trúc đúng ≠ YouTube chấp nhận"
    _khong_lo(cd)


def test_chan_doan_khong_co_cookie_dang_nhap(tmp_path):
    cd = t.chan_doan_cookie(_hop_le(tmp_path, dang_nhap=False))
    assert cd.cau_truc_hop_le and cd.co_cookie_dang_nhap is False


def test_chan_doan_dong_hong_chi_neu_so_dong(tmp_path):
    p = _ghi(tmp_path, _DAU + _dong(".youtube.com", "PREF")
             + f".youtube.com TRUE / TRUE 0 SID {BI_MAT}\n"
             + _dong(".youtube.com", "X", het_han="ngay-mai"))
    cd = t.chan_doan_cookie(p)
    assert not cd.cau_truc_hop_le
    assert cd.so_dong_hong == 2 and cd.dong_hong_dau == (3, 4)
    _khong_lo(cd)


def test_chan_doan_thieu_dong_tieu_de(tmp_path):
    cd = t.chan_doan_cookie(_ghi(tmp_path, _dong(".youtube.com", "PREF")))
    assert not cd.co_tieu_de and not cd.cau_truc_hop_le


def test_chan_doan_cookie_tu_trinh_duyet_khong_doc_gi():
    cd = t.chan_doan_cookie("", cookies_browser="chrome")
    assert cd.cau_hinh and cd.nguon == "trinh_duyet"
    assert cd.trang_thai == t.COOKIE_TU_TRINH_DUYET


def test_chan_doan_khong_ghi_file(tmp_path):
    p = _hop_le(tmp_path)
    truoc = (os.path.getmtime(p), os.path.getsize(p))
    time.sleep(0.01)
    t.chan_doan_cookie(p)
    assert (os.path.getmtime(p), os.path.getsize(p)) == truoc


# ---- cổng an toàn trước yt-dlp: siết theo đúng luật nạp của yt-dlp

def test_cong_chan_dong_httponly_sai_dinh_dang(tmp_path):
    """yt-dlp bóc ``#HttpOnly_`` rồi kiểm; dòng hỏng bị IN NGUYÊN VĂN ra stderr
    (yt_dlp/cookies.py:1362-1386). Cổng cũ coi dòng đó là chú thích nên bỏ lọt."""
    p = _ghi(tmp_path, _DAU + _dong(".youtube.com", "PREF")
             + f"#HttpOnly_.youtube.com TRUE / TRUE 0 SID {BI_MAT}\n")
    with pytest.raises(y.LoiFileCookie) as ei:
        y.kiem_tra_file_cookie(p)
    assert "dòng 3" in str(ei.value) and BI_MAT not in str(ei.value)


def test_cong_chan_han_dung_khong_phai_so(tmp_path):
    p = _ghi(tmp_path, _DAU + _dong(".youtube.com", "X", het_han="ngay-mai"))
    with pytest.raises(y.LoiFileCookie) as ei:
        y.kiem_tra_file_cookie(p)
    assert "dòng 2" in str(ei.value) and "ngay-mai" not in str(ei.value)


def test_cong_chan_file_thieu_dong_tieu_de(tmp_path):
    """`MozillaCookieJar._really_load` từ chối cả file khi dòng 1 không phải tiêu đề."""
    with pytest.raises(y.LoiFileCookie) as ei:
        y.kiem_tra_file_cookie(_ghi(tmp_path, _dong(".youtube.com", "PREF")))
    assert "tiêu đề" in str(ei.value)


def test_cong_bao_ro_file_html(tmp_path):
    with pytest.raises(y.LoiFileCookie) as ei:
        y.kiem_tra_file_cookie(_ghi(tmp_path, "<html><body>login</body></html>"))
    assert "HTML" in str(ei.value)


def test_cong_cho_qua_file_chi_co_ban_ghi_httponly(tmp_path):
    p = _ghi(tmp_path, _DAU + _dong(".youtube.com", "SID", httponly=True))
    y.kiem_tra_file_cookie(p)
    assert y.CauHinhMang(cookiefile=p).tuy_chon()["cookiefile"] == p
