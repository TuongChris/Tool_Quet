# -*- coding: utf-8 -*-
"""Chính sách truy cập YouTube dùng chung — NƠI DUY NHẤT hiểu một lỗi yt-dlp nghĩa là gì.

Vì sao có module này (đo trên source d67ce31, xem docs/YOUTUBE_ACCESS_RELIABILITY.md):

* Lỗi chỉ được diễn giải bằng vài phép so chuỗi trong ``ytdlp_chung.giai_thich_loi`` — không
  nhận ra cả chữ ký THẬT ``Video unavailable`` của Job 43/130 ở Tier 2, không có loại 429/403
  hay lỗi mạng tạm thời, và không vòng lặp nào biết khi nào phải DỪNG.
* Khi YouTube đòi xác minh không phải bot (chặn theo địa chỉ mạng — CLAUDE.md mục 6c), mọi vòng
  lặp vẫn chạy tiếp hết lô; mỗi video còn thử đủ 5 player client. Một lần bị chặn thành hàng
  chục request nữa, đúng thứ làm bị chặn nặng hơn.

Module này THUẦN: không import engine/channel/streamlit, không gọi mạng. Nó không dựng tuỳ chọn
yt-dlp — việc đó vẫn chỉ ``ytdlp_chung.CauHinhMang`` làm (CLAUDE.md quy tắc 5).

Đây KHÔNG phải công cụ vượt chặn: không CAPTCHA, không đổi proxy/dấu vân tay, không tự lấy cookie.
YouTube từ chối thì chẩn đoán, giảm request và dừng an toàn.
"""

from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Optional

LOGGER = logging.getLogger("youtube.truy_cap")

# =====================================================================
#  Loại lỗi
# =====================================================================

PERMANENT_UNAVAILABLE = "PERMANENT_UNAVAILABLE"     # gỡ, riêng tư, sai mã, không tồn tại
AUTH_REQUIRED = "AUTH_REQUIRED"                     # giới hạn tuổi, hội viên, cần đăng nhập
BOT_CHALLENGE = "BOT_CHALLENGE"                     # "confirm you're not a bot", captcha
RATE_LIMITED = "RATE_LIMITED"                       # HTTP 429, phiên bị giới hạn tốc độ
HTTP_FORBIDDEN = "HTTP_FORBIDDEN"                   # 403 chưa đủ bằng chứng là bot/cookie
TRANSIENT_NETWORK = "TRANSIENT_NETWORK"             # hết giờ, đứt kết nối, DNS, 5xx
COOKIE_INVALID_OR_EXPIRED = "COOKIE_INVALID_OR_EXPIRED"
FORMAT_OR_EXTRACTOR_ERROR = "FORMAT_OR_EXTRACTOR_ERROR"
PARTIAL_OR_CORRUPT_DOWNLOAD = "PARTIAL_OR_CORRUPT_DOWNLOAD"
INVALID_INPUT = "INVALID_INPUT"                     # link không phải video / danh sách là TAB
UNKNOWN_YOUTUBE_ERROR = "UNKNOWN_YOUTUBE_ERROR"
BLOCKED_BY_BREAKER = "BLOCKED_BY_BREAKER"           # chưa gửi request: cầu dao đã mở

CAC_LOAI = (PERMANENT_UNAVAILABLE, AUTH_REQUIRED, BOT_CHALLENGE, RATE_LIMITED, HTTP_FORBIDDEN,
            TRANSIENT_NETWORK, COOKIE_INVALID_OR_EXPIRED, FORMAT_OR_EXTRACTOR_ERROR,
            PARTIAL_OR_CORRUPT_DOWNLOAD, INVALID_INPUT, UNKNOWN_YOUTUBE_ERROR,
            BLOCKED_BY_BREAKER)

# Lỗi do PHÍA TRUY CẬP (YouTube từ chối, mạng, cookie) — khác lỗi của chính video.
LOAI_TRUY_CAP = frozenset({AUTH_REQUIRED, BOT_CHALLENGE, RATE_LIMITED, HTTP_FORBIDDEN,
                           TRANSIENT_NETWORK, COOKIE_INVALID_OR_EXPIRED, BLOCKED_BY_BREAKER})

# =====================================================================
#  Văn bản lỗi yt-dlp
# =====================================================================

# yt-dlp tô màu thông báo lỗi bằng escape ANSI; vẫn dọn dù đã đặt `no_color` vì lỗi có thể tới từ
# tiến trình con hoặc từ bản ghi cũ trong lịch sử.
RE_MA_MAU = re.compile(r"\x1b?\[[0-9;]*m")

# Đuôi hướng dẫn của yt-dlp ("Use --cookies-from-browser ... See https://...") dài gần 300 ký tự
# và vô nghĩa với người dùng không phải lập trình viên. Cắt từ chỗ đầu tiên trong các mốc này.
MOC_CAT_HUONG_DAN = (" Use --cookies", " See  https://", " See https://")

# Chuỗi đánh dấu thông báo ĐÃ phân loại — để diễn giải lại không dán thêm chú thích lần nữa.
DAU_CHI_TIET = "Chi tiết kỹ thuật:"


def go_ma_mau(s: Any) -> str:
    """Bỏ escape ANSI khỏi thông báo lỗi trước khi đưa lên giao diện."""
    return RE_MA_MAU.sub("", str(s)).strip()


def cat_huong_dan(tin: str) -> str:
    """Cắt đuôi hướng dẫn dài của yt-dlp, giữ phần nói lỗi gì."""
    for moc in MOC_CAT_HUONG_DAN:
        vi_tri = tin.find(moc)
        if vi_tri > 0:
            tin = tin[:vi_tri].rstrip()
    return tin


# Luật xếp theo THỨ TỰ ƯU TIÊN; mỗi luật là các cụm chữ thường đặc trưng đã gặp trong source
# yt-dlp 2026.08.19 hoặc trong lỗi thật. Không có luật kiểu `"sign" in loi`: câu riêng tư của
# YouTube có "Sign in if you've been granted access", câu tuổi cũng bắt đầu bằng "Sign in".
_BOT = ("not a bot", "not a robot", "captcha", "your ip is likely being blocked",
        "unusual traffic", "automated queries")
_GIOI_HAN = ("http error 429", "too many requests", "rate-limited", "rate limited",
             "ratelimit", "try again later")
_COOKIE = ("file cookie", "does not look like a netscape format cookies file",
           "cookies are no longer valid", "netscape formatted, not json")
_DANG_NHAP = ("confirm your age", "age-restricted", "age restricted",
              "inappropriate for some users", "members-only", "members only",
              "join this channel", "channel's members", "login details are needed",
              "login required", "requires payment")
_VINH_VIEN = ("video unavailable", "this video is unavailable", "video is not available",
              "private video", "this video is private", "has been removed", "been terminated",
              "no longer available", "does not exist", "available in your country",
              "geo restrict", "geo-restrict", "incomplete youtube id", "removed by the uploader",
              "copyright claim", "http error 404", "http error 410")
_DAU_VAO = ("unsupported url", "is not a valid url", "không phải một video",
            "trả về các tab")
_CAM = ("http error 403", "403: forbidden", "403 forbidden")
_MANG = ("timed out", "timeout", "connection reset", "connection aborted", "connection refused",
         "remote end closed", "temporary failure in name resolution", "getaddrinfo failed",
         "name or service not known", "nodename nor servname", "network is unreachable",
         "no route to host", "incomplete data received", "internal server error",
         "bad gateway", "service unavailable", "gateway time", "eof occurred in violation",
         "unexpected_eof", "broken pipe", "max retries exceeded", "errno 11001",
         "winerror 10054", "winerror 10060", "winerror 10061", "forcibly closed",
         "http error 500", "http error 502", "http error 503", "http error 504")
_LOP_MANG = frozenset({"TimeoutError", "timeout", "ConnectionError", "ConnectionResetError",
                       "ConnectionAbortedError", "ConnectionRefusedError", "BrokenPipeError",
                       "TransportError", "IncompleteRead", "RemoteDisconnected", "URLError",
                       "SSLError", "ProxyError", "ReadTimeoutError"})
_DINH_DANG = ("requested format is not available", "no video formats found", "no formats found",
              "page needs to be reloaded", "n challenge", "nsig extraction failed",
              "signature extraction failed", "unable to extract",
              "failed to extract any player response", "drm protected",
              "precondition check failed", "http error 400")
_TAI_HONG = ("không thấy file sau khi tải", "did not get any data blocks",
             "downloaded file is empty", "content too short", "contenttooshort",
             "downloaded file is corrupted", "file is empty")

THONG_BAO = {
    PERMANENT_UNAVAILABLE: (
        "Video không còn xem được trên YouTube (đã gỡ, để riêng tư, sai mã hoặc bị chặn ở khu "
        "vực này). Đây không phải lỗi tool; video này chưa được quét."),
    AUTH_REQUIRED: (
        "YouTube yêu cầu đăng nhập mới xem được video này (giới hạn độ tuổi hoặc chỉ dành cho "
        "hội viên). Cần cookie tài khoản hợp lệ ở «🔐 Kết nối YouTube»; video này chưa được quét."),
    BOT_CHALLENGE: (
        "YouTube yêu cầu xác minh không phải bot cho địa chỉ mạng này. Tool đã dừng yêu cầu mới "
        "tới YouTube để tránh lặp lỗi xác minh. Nghỉ vài tiếng, giảm nhịp, hoặc nạp cookie tài "
        "khoản ở «🔐 Kết nối YouTube» rồi chạy lại."),
    RATE_LIMITED: (
        "YouTube đang giới hạn số yêu cầu; Tool đã dừng yêu cầu mới để tránh làm tình trạng "
        "nặng hơn. Chờ khoảng một tiếng rồi chạy lại."),
    HTTP_FORBIDDEN: (
        "YouTube từ chối tải (HTTP 403) với mọi cách tải đã thử. Chưa đủ bằng chứng là do cookie "
        "hay do bị nghi là bot; video này chưa được quét."),
    TRANSIENT_NETWORK: (
        "Lỗi mạng tạm thời (hết thời gian chờ, mất kết nối hoặc máy chủ YouTube lỗi). Đã thử lại "
        "có giới hạn; video này chưa được quét — hãy chạy lại sau."),
    COOKIE_INVALID_OR_EXPIRED: (
        "Cookie cấu hình không được YouTube chấp nhận hoặc không dùng được — kiểm tra lại ở "
        "«🔐 Kết nối YouTube» (xuất lại file cookie, hoặc xoá trống ô cookie)."),
    FORMAT_OR_EXTRACTOR_ERROR: (
        "YouTube không trả định dạng âm thanh dùng được cho video này, hoặc yt-dlp không đọc được "
        "trang video. Video này chưa được quét."),
    PARTIAL_OR_CORRUPT_DOWNLOAD: (
        "Tải về không trọn vẹn (file rỗng hoặc hỏng). Video này chưa được quét đầy đủ."),
    INVALID_INPUT: (
        "Link này không phải một video YouTube (có thể là kênh hoặc danh sách phát). Hãy dùng "
        "link video, hoặc đưa kênh vào mục theo dõi kênh."),
    UNKNOWN_YOUTUBE_ERROR: (
        "YouTube trả lỗi chưa phân loại được. Video này chưa được quét."),
    BLOCKED_BY_BREAKER: (
        "Chưa quét — Tool đã dừng yêu cầu mới tới YouTube để tránh lặp lỗi."),
}


@dataclass(frozen=True)
class YoutubeAccessFailure:
    """Một thao tác YouTube thất bại, đã phân loại. Không bao giờ mang cookie/header/token."""

    category: str
    operation: str = ""
    video_id: str = ""
    retryable: bool = False
    auth_related: bool = False
    rate_limited: bool = False
    human_message_vi: str = ""
    technical_summary: str = ""       # đã che bí mật, đã bỏ màu, ≤ 300 ký tự
    http_status: Optional[int] = None
    attempt: int = 1
    max_attempts: int = 1

    @property
    def la_loi_truy_cap(self) -> bool:
        """Lỗi phía truy cập (YouTube từ chối, mạng, cookie) chứ không phải của chính video."""
        return self.category in LOAI_TRUY_CAP

    def thanh_dict(self) -> dict:
        return asdict(self)


class LoiTruyCapYouTube(RuntimeError):
    """Ngoại lệ mang kết quả phân loại. ``str()`` = câu tiếng Việt + tóm tắt kỹ thuật đã che."""

    def __init__(self, that_bai: YoutubeAccessFailure):
        self.that_bai = that_bai
        # Phiên đã ghi lỗi này vào cầu dao — để tầng điều phối không ghi lại lần hai.
        self.phien = None
        tin = that_bai.human_message_vi
        if that_bai.technical_summary:
            tin = f"{tin} — {DAU_CHI_TIET} {that_bai.technical_summary}"
        super().__init__(tin)


def _chuoi_ngoai_le(loi: BaseException) -> list:
    """Lỗi và các nguyên nhân của nó: ``exc_info`` (DownloadError), ``cause`` (ExtractorError),
    ``__cause__``/``__context__``. Tối đa 8 phần tử, không lặp."""
    ra: list = []
    hang = [loi]
    while hang and len(ra) < 8:
        x = hang.pop(0)
        if not isinstance(x, BaseException) or any(x is y for y in ra):
            continue
        ra.append(x)
        ei = getattr(x, "exc_info", None)
        if isinstance(ei, tuple) and len(ei) > 1:
            hang.append(ei[1])
        for ten in ("cause", "__cause__", "__context__"):
            hang.append(getattr(x, ten, None))
    return ra


def tim_loi_truy_cap(loi: Any) -> Optional[YoutubeAccessFailure]:
    """Kết quả phân loại nằm đâu đó trong chuỗi ngoại lệ (hoặc ``None``)."""
    if not isinstance(loi, BaseException):
        return None
    for x in _chuoi_ngoai_le(loi):
        if isinstance(x, LoiTruyCapYouTube):
            return x.that_bai
    return None


_RE_MA_KENH = re.compile(r"UC[A-Za-z0-9_-]{22}")
_RE_MA_TRONG_URL = re.compile(r"(?:youtu\.be/|[?&]v=|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
_RE_URL_TAB = re.compile(r"/(?:channel/[^/?#]+|@[^/?#]+|c/[^/?#]+|user/[^/?#]+)"
                         r"(?:/(?:videos|shorts|streams|live|playlists|featured|community|"
                         r"podcasts|releases|store))?/?(?:[?#]|$)|/playlist\?")


def la_muc_khong_phai_video(muc: Any) -> bool:
    """Mục trong danh sách kênh mà KHÔNG phải một video: tab của kênh, playlist con.

    Đúng triệu chứng Tier 2: link ``/channel/UC…`` thiếu ``/videos`` làm yt-dlp trả các TAB
    (Videos/Shorts/Live) mang id = id KÊNH. Nhận theo ba dấu hiệu độc lập: ``ie_key`` của
    yt-dlp là ``YoutubeTab``, id có dạng mã kênh ``UC`` + 22 ký tự, hoặc url trỏ tới kênh/tab/
    playlist thay vì một video.
    """
    if not isinstance(muc, dict):
        return False
    if muc.get("ie_key") == "YoutubeTab":
        return True
    if _RE_MA_KENH.fullmatch(str(muc.get("id") or "")):
        return True
    return bool(_RE_URL_TAB.search(str(muc.get("url") or "")))


def ma_tu_url(url: Any) -> str:
    """Mã video trong link (chỉ để ghi số đo/log); rỗng nếu không thấy."""
    m = _RE_MA_TRONG_URL.search(str(url or ""))
    return m.group(1) if m else ""


def _ma_http(chuoi: list) -> Optional[int]:
    for x in chuoi:
        for ten in ("status", "code"):
            ma = getattr(x, ten, None)
            if isinstance(ma, int) and not isinstance(ma, bool) and 100 <= ma <= 599:
                return ma
    return None


def _co(thap: str, cum: tuple) -> bool:
    return any(c in thap for c in cum)


def _xac_dinh_loai(thap: str, ma: Optional[int], lop: set) -> str:
    if _co(thap, _BOT):
        return BOT_CHALLENGE
    if ma == 429 or _co(thap, _GIOI_HAN):
        return RATE_LIMITED
    if "LoiFileCookie" in lop or _co(thap, _COOKIE):
        return COOKIE_INVALID_OR_EXPIRED
    if _co(thap, _DANG_NHAP):
        return AUTH_REQUIRED
    if "GeoRestrictedError" in lop or ma in (404, 410) or _co(thap, _VINH_VIEN):
        return PERMANENT_UNAVAILABLE
    if "UnsupportedError" in lop or _co(thap, _DAU_VAO):
        return INVALID_INPUT
    if ma == 403 or _co(thap, _CAM):
        return HTTP_FORBIDDEN
    if (ma is not None and 500 <= ma <= 599) or lop & _LOP_MANG or _co(thap, _MANG):
        return TRANSIENT_NETWORK
    if ma == 400 or _co(thap, _DINH_DANG):
        return FORMAT_OR_EXTRACTOR_ERROR
    if _co(thap, _TAI_HONG):
        return PARTIAL_OR_CORRUPT_DOWNLOAD
    return UNKNOWN_YOUTUBE_ERROR


def tom_tat_ky_thuat(tin: Any, toi_da: int = 300) -> str:
    """Dòng kỹ thuật an toàn để lưu: bỏ màu, cắt đuôi hướng dẫn, che bí mật, giới hạn độ dài."""
    gon = che_bi_mat(cat_huong_dan(go_ma_mau(tin)))
    gon = " ".join(gon.split())
    return gon if len(gon) <= toi_da else gon[: toi_da - 1] + "…"


def phan_loai_loi(loi: Any, *, thao_tac: str = "", video_id: str = "", lan_thu: int = 1,
                  toi_da: int = 1) -> YoutubeAccessFailure:
    """Phân loại MỘT lỗi của thao tác YouTube. Không suy đoán mạnh hơn bằng chứng.

    403 không tự thành "cookie hỏng"; ``Video unavailable`` không thành bot; chỉ HTTP 429 thật
    (không phải câu "phiên bị giới hạn tới một tiếng") mới được thử lại.
    """
    da_co = tim_loi_truy_cap(loi)
    if da_co is not None:
        return da_co
    chuoi = _chuoi_ngoai_le(loi) if isinstance(loi, BaseException) else []
    cac_cau = [str(x) for x in chuoi] if chuoi else [str(loi)]
    thap = go_ma_mau(" | ".join(dict.fromkeys(c for c in cac_cau if c))).lower()
    ma = _ma_http(chuoi)
    lop = {type(x).__name__ for x in chuoi}
    loai = _xac_dinh_loai(thap, ma, lop)

    thu_lai = loai == TRANSIENT_NETWORK or (
        loai == RATE_LIMITED and (ma == 429 or "429" in thap or "too many requests" in thap))
    thong_bao = THONG_BAO[loai]
    if loai == COOKIE_INVALID_OR_EXPIRED and "LoiFileCookie" in lop:
        # Thông báo của cổng cookie chỉ nêu SỐ DÒNG, không nêu nội dung — an toàn để hiện.
        goc = next(x for x in chuoi if type(x).__name__ == "LoiFileCookie")
        thong_bao = f"Cookie cấu hình không dùng được: {go_ma_mau(goc)}"
    tom_tat = tom_tat_ky_thuat(next((c for c in cac_cau if c), ""))
    return YoutubeAccessFailure(
        category=loai, operation=thao_tac, video_id=str(video_id or ""), retryable=thu_lai,
        auth_related=loai in (AUTH_REQUIRED, BOT_CHALLENGE, COOKIE_INVALID_OR_EXPIRED),
        rate_limited=loai == RATE_LIMITED, human_message_vi=thong_bao,
        technical_summary=tom_tat, http_status=ma, attempt=int(lan_thu), max_attempts=int(toi_da))


# =====================================================================
#  Che bí mật
# =====================================================================

AN = "[đã ẩn]"
_KHONG_LAI = r"(?!\[đã ẩn)"           # giá trị đã che thì thôi — giữ luỹ đẳng

_RE_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
                     re.S)
_RE_DONG_CANH_BAO_COOKIE = re.compile(
    r"(?im)^.*(?:skipping cookie file entry|failed to parse cookie).*$")
_RE_DONG_NETSCAPE = re.compile(
    r"(?m)^(?:#HttpOnly_)?[^\t\r\n]+\t(?:TRUE|FALSE)\t[^\t\r\n]*\t(?:TRUE|FALSE)\t[^\t\r\n]*"
    r"\t[^\t\r\n]*\t[^\r\n]*$")
_RE_DONG_COOKIE_DAU_CACH = re.compile(
    r"(?m)^\s*(?:#HttpOnly_)?\.?[A-Za-z0-9.-]+ +(?:TRUE|FALSE) +\S+ +(?:TRUE|FALSE) +\d+ +\S+ +\S+.*$")
_RE_HEADER = re.compile(
    r"(?i)\b((?:set-)?cookie|authorization|proxy-authorization|x-goog-api-key|x-goog-authuser|"
    r"x-youtube-identity-token)(\s*[\"']?\s*:\s*[\"']?\s*)" + _KHONG_LAI + r"([^\r\n\"']+)")
_RE_BEARER = re.compile(r"(?i)\b(bearer|sapisidhash)(\s+)" + _KHONG_LAI + r"([^\s\"',;]+)")
_RE_QUERY = re.compile(
    r"([?&](?!(?:v|list|index|t)=)[A-Za-z0-9_.%-]+=)" + _KHONG_LAI + r"([^&#\s'\"<>]+)")
_RE_KHOA_GIA_TRI = re.compile(
    r"(?i)\b(access_token|refresh_token|id_token|token|api[_-]?key|key|sig|lsig|signature|pot|"
    r"password|passwd|pwd|client_secret|secret|private_key_id|private_key)"
    r"([\"']?\s*[:=]\s*[\"']?)" + _KHONG_LAI + r"([^\s\"'&,;)}\]]+)")
_TEN_COOKIE_DANG_NHAP = (r"__Secure-[0-9A-Za-z_-]+|__Host-[0-9A-Za-z_-]+|SAPISID|APISID|HSID|"
                         r"SSID|SIDCC|SID|LOGIN_INFO|VISITOR_INFO1_LIVE|"
                         r"VISITOR_PRIVACY_METADATA|YSC|PREF|NID|CONSENT|SOCS")
_RE_COOKIE_BANG = re.compile(r"\b(" + _TEN_COOKIE_DANG_NHAP + r")(\s*=\s*)" + _KHONG_LAI
                             + r"([^\s;,'\"]+)")
_RE_COOKIE_CACH = re.compile(r"\b(" + _TEN_COOKIE_DANG_NHAP + r")(\s+)" + _KHONG_LAI
                             + r"([A-Za-z0-9_\-./+=%]{8,})")


def che_bi_mat(van_ban: Any) -> str:
    """Che cookie, header xác thực, token và tham số URL nhạy cảm. Luỹ đẳng.

    Chỉ dùng cho văn bản LỖI/CHẨN ĐOÁN trước khi lưu, ghi log hay hiện lên giao diện. Giữ
    host, đường dẫn, mã video (``v=``) và thông điệp lỗi — những thứ cần để chẩn đoán.
    """
    s = str(van_ban)
    if not s:
        return s
    s = _RE_PEM.sub("[đã ẩn: khoá riêng]", s)
    s = _RE_DONG_CANH_BAO_COOKIE.sub("[đã ẩn: dòng này chứa nội dung cookie]", s)
    s = _RE_DONG_NETSCAPE.sub("[đã ẩn: dòng cookie]", s)
    s = _RE_DONG_COOKIE_DAU_CACH.sub("[đã ẩn: dòng cookie]", s)
    s = _RE_HEADER.sub(lambda m: m.group(1) + ": " + AN, s)
    s = _RE_BEARER.sub(lambda m: m.group(1) + m.group(2) + AN, s)
    s = _RE_QUERY.sub(lambda m: m.group(1) + AN, s)
    s = _RE_KHOA_GIA_TRI.sub(lambda m: m.group(1) + m.group(2) + AN, s)
    s = _RE_COOKIE_BANG.sub(lambda m: m.group(1) + m.group(2) + AN, s)
    s = _RE_COOKIE_CACH.sub(lambda m: m.group(1) + m.group(2) + AN, s)
    return s


# =====================================================================
#  Cấu trúc + chẩn đoán cookie
# =====================================================================

# Đúng luật nạp của yt-dlp: `MozillaCookieJar._really_load` đòi dòng 1 là tiêu đề này
# (http.cookiejar.NETSCAPE_MAGIC_RGX); `YoutubeDLCookieJar.load` bóc tiền tố `#HttpOnly_`, đòi
# đúng 7 trường TAB và hạn dùng là số (yt_dlp/cookies.py:1362-1374).
RE_TIEU_DE_NETSCAPE = re.compile(r"#( Netscape)? HTTP Cookie File")
TIEN_TO_HTTPONLY = "#HttpOnly_"
_RE_HAN_DUNG = re.compile(r"[0-9]+(?:\.[0-9]+)?")

COOKIE_CHUA_CAU_HINH = "CHUA_CAU_HINH"
COOKIE_TU_TRINH_DUYET = "TU_TRINH_DUYET"
COOKIE_KHONG_TON_TAI = "KHONG_TON_TAI"
COOKIE_KHONG_DOC_DUOC = "KHONG_DOC_DUOC"
COOKIE_SAI_CAU_TRUC = "SAI_CAU_TRUC"
COOKIE_FILE_STRUCTURALLY_VALID = "COOKIE_FILE_STRUCTURALLY_VALID"

COOKIE_PHIEN_CHUA_RO = "CHUA_RO"         # chỉ một request thật mới trả lời được
COOKIE_SESSION_ACCEPTED_BY_YOUTUBE = "COOKIE_SESSION_ACCEPTED_BY_YOUTUBE"
COOKIE_PHIEN_BI_TU_CHOI = "BI_TU_CHOI"

# Cùng luật với yt-dlp `_has_auth_cookies` (_base.py:810-815): có LOGIN_INFO VÀ một trong ba SAPISID.
_COOKIE_SAPISID = frozenset({"SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID"})


@dataclass(frozen=True)
class CauTrucCookie:
    """Kết quả đọc cấu trúc. ``ban_ghi`` chỉ sống trong bộ nhớ, KHÔNG bao giờ được xuất ra."""

    dinh_dang: str                    # netscape | html | json | rong | khong_ro
    co_tieu_de: bool
    dong_hong: tuple                  # số dòng (từ 1), không nội dung
    ban_ghi: tuple = ()               # (miền, tên, hạn) — nội bộ

    @property
    def so_ban_ghi(self) -> int:
        return len(self.ban_ghi)


def doc_cau_truc_cookie(noi_dung: str) -> CauTrucCookie:
    """Đọc cấu trúc file cookie Netscape theo đúng luật yt-dlp dùng khi nạp."""
    cac_dong = noi_dung.splitlines()
    dau = next((d.strip() for d in cac_dong if d.strip()), "")
    if not dau:
        return CauTrucCookie("rong", False, ())
    if dau.startswith("<"):
        return CauTrucCookie("html", False, ())
    if dau[0] in "[{":
        return CauTrucCookie("json", False, ())
    co_tieu_de = bool(RE_TIEU_DE_NETSCAPE.match(cac_dong[0]))
    hong, ban_ghi = [], []
    for so, dong in enumerate(cac_dong, start=1):
        tho = dong[len(TIEN_TO_HTTPONLY):] if dong.startswith(TIEN_TO_HTTPONLY) else dong
        if tho.startswith("#") or not tho.strip():
            continue
        truong = tho.split("\t")
        if len(truong) != 7 or (truong[4] and not _RE_HAN_DUNG.fullmatch(truong[4])):
            hong.append(so)
            continue
        ban_ghi.append((truong[0], truong[5], truong[4]))
    dinh_dang = "netscape" if (ban_ghi or co_tieu_de) else "khong_ro"
    return CauTrucCookie(dinh_dang, co_tieu_de, tuple(hong), tuple(ban_ghi))


@dataclass(frozen=True)
class ChanDoanCookie:
    """Chẩn đoán cookie AN TOÀN: chỉ metadata và số đếm — không giá trị, không tên cookie.

    ``cau_truc_hop_le`` (COOKIE_FILE_STRUCTURALLY_VALID) KHÁC việc YouTube có chấp nhận phiên
    hay không (``phien_chap_nhan``) — cái sau chỉ một request thật mới trả lời được.
    """

    cau_hinh: bool = False
    nguon: str = ""                    # "file" | "trinh_duyet" | ""
    ten_file: str = ""                 # chỉ tên, không đường dẫn
    ton_tai: bool = False
    doc_duoc: bool = False
    kich_thuoc: int = 0
    sua_luc: str = ""
    dinh_dang: str = ""
    co_tieu_de: bool = False
    so_ban_ghi: int = 0
    so_dong_hong: int = 0
    dong_hong_dau: tuple = ()
    so_ban_ghi_youtube: int = 0
    so_ban_ghi_google: int = 0
    so_het_han: int = 0
    co_cookie_dang_nhap: bool = False
    cau_truc_hop_le: bool = False
    trang_thai: str = COOKIE_CHUA_CAU_HINH
    phien_chap_nhan: str = COOKIE_PHIEN_CHUA_RO

    def thanh_dict(self) -> dict:
        return asdict(self)


def _thuoc_mien(mien: str, goc: str) -> bool:
    mien = mien.lower().lstrip(".")
    return mien == goc or mien.endswith("." + goc)


def chan_doan_cookie(duong_dan: str, *, cookies_browser: str = "",
                     bay_gio: Optional[float] = None) -> ChanDoanCookie:
    """Chẩn đoán cookie đã CẤU HÌNH. Chỉ đọc file; không ghi, không gọi mạng, không đọc trình
    duyệt. Cookie lấy từ trình duyệt do người dùng tự cấu hình: chỉ ghi nhận, không mở profile."""
    duong_dan = (duong_dan or "").strip()
    if not duong_dan:
        if (cookies_browser or "").strip():
            return ChanDoanCookie(cau_hinh=True, nguon="trinh_duyet",
                                  trang_thai=COOKIE_TU_TRINH_DUYET)
        return ChanDoanCookie()
    ten = os.path.basename(duong_dan)
    try:
        st = os.stat(duong_dan)
    except OSError:
        return ChanDoanCookie(cau_hinh=True, nguon="file", ten_file=ten,
                              trang_thai=COOKIE_KHONG_TON_TAI)
    co_ban = dict(cau_hinh=True, nguon="file", ten_file=ten, ton_tai=True,
                  kich_thuoc=int(st.st_size),
                  sua_luc=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"))
    try:
        with io.open(duong_dan, encoding="utf-8", errors="replace") as f:
            noi_dung = f.read()
    except OSError:
        return ChanDoanCookie(**co_ban, trang_thai=COOKIE_KHONG_DOC_DUOC)
    ct = doc_cau_truc_cookie(noi_dung)
    bay_gio = time.time() if bay_gio is None else float(bay_gio)
    ten_youtube = {ten_c for mien, ten_c, _ in ct.ban_ghi if _thuoc_mien(mien, "youtube.com")}
    het_han = 0
    for _mien, _ten, han in ct.ban_ghi:
        try:
            so = float(han or 0)
        except ValueError:
            continue
        if 0 < so < bay_gio:
            het_han += 1
    hop_le = (ct.dinh_dang == "netscape" and ct.co_tieu_de and not ct.dong_hong
              and ct.so_ban_ghi > 0)
    return ChanDoanCookie(
        **co_ban, doc_duoc=True, dinh_dang=ct.dinh_dang, co_tieu_de=ct.co_tieu_de,
        so_ban_ghi=ct.so_ban_ghi, so_dong_hong=len(ct.dong_hong),
        dong_hong_dau=tuple(ct.dong_hong[:5]),
        so_ban_ghi_youtube=sum(1 for m, _, _ in ct.ban_ghi if _thuoc_mien(m, "youtube.com")),
        so_ban_ghi_google=sum(1 for m, _, _ in ct.ban_ghi if _thuoc_mien(m, "google.com")),
        so_het_han=het_han,
        co_cookie_dang_nhap="LOGIN_INFO" in ten_youtube and bool(ten_youtube & _COOKIE_SAPISID),
        cau_truc_hop_le=hop_le,
        trang_thai=COOKIE_FILE_STRUCTURALLY_VALID if hop_le else COOKIE_SAI_CAU_TRUC)


# =====================================================================
#  Ngân sách thử lại — MỘT bảng cho mọi thao tác
# =====================================================================

# Trần nghỉ giữa các lần thử lại NỘI BỘ của yt-dlp (`retry_sleep_functions`). Mặc định yt-dlp
# thử lại NGAY (không nghỉ) tới 10 lần khi 5xx/đứt kết nối — dồn dập đúng lúc máy chủ đang quá
# tải. Trần thấp để nút Dừng vẫn có tác dụng sau vài giây (yt-dlp tự ngủ, không huỷ được).
TRAN_NGHI_NOI_BO_S = 5.0


def _nghi_noi_bo(n: Any = 0) -> float:
    """Nghỉ tăng dần 1, 2, 4, 5, 5… giây giữa các lần yt-dlp tự thử lại khi tải (http/fragment)."""
    return min(TRAN_NGHI_NOI_BO_S, float(2 ** min(8, max(0, int(n or 0)))))


def _nghi_trich_xuat(n: Any = 0) -> float:
    """Nghỉ 2, 4, 5 giây giữa các lần yt-dlp tự thử lại request API khi trích xuất."""
    return min(TRAN_NGHI_NOI_BO_S, 2.0 * (max(0, int(n or 0)) + 1))


@dataclass(frozen=True)
class NganSach:
    """Ngân sách thử lại của MỘT loại thao tác.

    ``cho_tam_thoi``/``cho_429``: độ trễ (giây) trước từng lần thử lại NGOÀI — số phần tử là số
    lần thử lại tối đa. ``yt_dlp_*``: số lần yt-dlp tự thử lại BÊN TRONG một lượt (``None`` = để
    mặc định của yt-dlp). yt-dlp không tự thử lại 403/429 ở khâu trích xuất (`_extract_response`),
    nên hai tầng không nhân nhau trên lỗi bị chặn.
    """

    cho_tam_thoi: tuple = ()
    cho_429: tuple = ()
    yt_dlp_retries: Optional[int] = None
    yt_dlp_fragment_retries: Optional[int] = None
    yt_dlp_extractor_retries: int = 3

    def tuy_chon_yt_dlp(self) -> dict:
        opts: dict = {
            "extractor_retries": self.yt_dlp_extractor_retries,
            "retry_sleep_functions": {"http": _nghi_noi_bo, "fragment": _nghi_noi_bo,
                                      "extractor": _nghi_trich_xuat},
        }
        if self.yt_dlp_retries is not None:
            opts["retries"] = self.yt_dlp_retries
        if self.yt_dlp_fragment_retries is not None:
            opts["fragment_retries"] = self.yt_dlp_fragment_retries
        return opts


NGAN_SACH = {
    # Lấy thông tin / liệt kê: một lần thử lại khi mạng chập chờn, một lần sau 30 s khi HTTP 429.
    "metadata": NganSach(cho_tam_thoi=(3.0,), cho_429=(30.0,)),
    "listing": NganSach(cho_tam_thoi=(3.0,), cho_429=(30.0,)),
    # Tải: KHÔNG có vòng thử lại ngoài. Đường lui player client + yt-dlp tự nối tiếp (`retries`)
    # đã đủ; vòng ngoài sẽ chạy lại từ đầu trên file `.part` của client khác (engine.py
    # `don_file_do_dang`). Giữ 10/10 như trước, chỉ thêm nghỉ có trần.
    "download": NganSach(yt_dlp_retries=10, yt_dlp_fragment_retries=10),
}

# Số lỗi LIÊN TIẾP (không xen thành công) để mở cầu dao. Không có trong bảng = không bao giờ mở:
# video bị gỡ / không phải video / tải hỏng là chuyện của từng video, truy cập vẫn bình thường.
NGUONG_MO = {
    BOT_CHALLENGE: 1,                 # chặn theo địa chỉ mạng (CLAUDE.md 6c): request sau đều hỏng
    RATE_LIMITED: 1,                  # đã thử lại có nghỉ; tiếp tục chỉ làm nặng thêm
    COOKIE_INVALID_OR_EXPIRED: 1,     # cấu hình hỏng: mọi thao tác sẽ hỏng y hệt
    AUTH_REQUIRED: 3,                 # một video giới hạn tuổi là bình thường; ba liên tiếp thì không
    HTTP_FORBIDDEN: 3,                # "403 lặp lại"
    TRANSIENT_NETWORK: 3,             # mạng sập: dừng thay vì đốt cả lô
    FORMAT_OR_EXTRACTOR_ERROR: 5,     # yt-dlp/YouTube hỏng hàng loạt
    UNKNOWN_YOUTUBE_ERROR: 5,
}

# Lỗi mà đổi player client KHÔNG cứu được — dừng đường lui client ngay (CLAUDE.md 6c: bot-check
# đánh ở khâu trích xuất cho MỌI client). 403/định dạng thì vẫn đổi client như mục 6.
DUNG_DOI_CLIENT = frozenset({BOT_CHALLENGE, AUTH_REQUIRED, RATE_LIMITED, PERMANENT_UNAVAILABLE,
                             COOKIE_INVALID_OR_EXPIRED, INVALID_INPUT})

_LY_DO_DUNG = {
    BOT_CHALLENGE: ("xác minh", "YouTube yêu cầu xác minh không phải bot cho địa chỉ mạng này. "
                    "Nghỉ vài tiếng, giảm nhịp, hoặc nạp cookie tài khoản ở «🔐 Kết nối YouTube» "
                    "rồi chạy lại."),
    RATE_LIMITED: ("giới hạn", "YouTube đang giới hạn số yêu cầu. Chờ khoảng một tiếng rồi chạy "
                   "lại."),
    COOKIE_INVALID_OR_EXPIRED: ("cookie", ""),
    AUTH_REQUIRED: ("đăng nhập", "YouTube liên tục yêu cầu đăng nhập. Kiểm tra cookie ở "
                    "«🔐 Kết nối YouTube» rồi chạy lại."),
    HTTP_FORBIDDEN: ("403", "YouTube liên tục từ chối tải (HTTP 403). Chưa đủ bằng chứng là do "
                     "cookie hay do bị nghi là bot; hãy chạy lại sau."),
    TRANSIENT_NETWORK: ("mạng", "Mạng liên tục lỗi. Kiểm tra kết nối rồi chạy lại."),
    FORMAT_OR_EXTRACTOR_ERROR: ("trích xuất", "YouTube/yt-dlp lỗi hàng loạt; có thể yt-dlp cần "
                                "cập nhật."),
    UNKNOWN_YOUTUBE_ERROR: ("lặp", "YouTube liên tục trả lỗi chưa phân loại được."),
}

TRUONG_SO_DO = ("youtube_operations", "metadata_requests", "download_attempts",
                "listing_requests", "retries", "auth_failures", "bot_challenges", "rate_limited",
                "http_403", "transient", "permanent_unavailable", "format_errors",
                "cookie_invalid", "other_failures", "cookie_fallbacks",
                "cookie_rejected_warnings", "client_fallbacks", "skipped_by_breaker")
_DEM_THEO_LOAI = {AUTH_REQUIRED: "auth_failures", BOT_CHALLENGE: "bot_challenges",
                  RATE_LIMITED: "rate_limited", HTTP_FORBIDDEN: "http_403",
                  TRANSIENT_NETWORK: "transient", PERMANENT_UNAVAILABLE: "permanent_unavailable",
                  FORMAT_OR_EXTRACTOR_ERROR: "format_errors",
                  COOKIE_INVALID_OR_EXPIRED: "cookie_invalid"}
_DEM_YEU_CAU = {"metadata": "metadata_requests", "download": "download_attempts",
                "listing": "listing_requests"}


class DaHuyTruyCap(Exception):
    """Người dùng bấm Dừng trong lúc phiên đang nghỉ chờ thử lại (bên gọi không đưa lớp huỷ)."""


def cho_huy_duoc(giay: float, cancel_event: Any = None) -> bool:
    """Nghỉ tối đa ``giay`` giây; ``True`` nếu bị huỷ giữa chừng.

    ``cancel_event``: ``threading.Event`` (dùng ``wait`` — thoát ngay khi được set) hoặc đối tượng
    chỉ có ``is_set()`` như ``channel._CoHuyTuHam`` (hỏi lại mỗi 0,2 giây).
    """
    if cancel_event is not None and cancel_event.is_set():
        return True
    if giay <= 0:
        return False
    cho = getattr(cancel_event, "wait", None)
    if callable(cho):
        return bool(cho(giay))
    het = time.monotonic() + giay
    while True:
        con = het - time.monotonic()
        if con <= 0:
            return False
        time.sleep(min(0.2, con))
        if cancel_event is not None and cancel_event.is_set():
            return True


class PhienYouTube:
    """MỘT lượt chạy (một batch, một lượt Watch, một lô nguồn chung, một lượt đồng bộ kênh).

    Gồm: cầu dao (đóng/mở — không tự nửa mở: mở là dừng hẳn lượt này, người dùng chạy lại sau
    khi sửa cookie/mạng), bộ chạy thử lại hữu hạn và huỷ được, và số đo request. Mọi thao tác
    mạng của lượt chạy hỏi phiên TRƯỚC khi gửi request; mở rồi thì không gửi gì nữa.
    """

    def __init__(self, *, nguong: Optional[dict] = None, ngan_sach: Optional[dict] = None,
                 ham_cho: Optional[Callable] = None):
        self._lock = threading.RLock()
        self.nguong = dict(NGUONG_MO if nguong is None else nguong)
        self.ngan_sach = dict(NGAN_SACH if ngan_sach is None else ngan_sach)
        self._cho = ham_cho or cho_huy_duoc
        self._mo_boi: Optional[YoutubeAccessFailure] = None
        self._so_lan_mo = 0
        self._lien_tiep: dict = {}
        self._so = {k: 0 for k in TRUONG_SO_DO}
        self._su_kien: list = []
        self.cookie_bi_tu_choi = False
        self.bat_dau = time.time()

    # ---------- trạng thái ----------

    @property
    def mo(self) -> bool:
        with self._lock:
            return self._mo_boi is not None

    @property
    def ly_do(self) -> Optional[YoutubeAccessFailure]:
        with self._lock:
            return self._mo_boi

    def thong_bao_dung(self) -> str:
        """Câu cho người dùng khi cầu dao đã mở; rỗng khi chưa mở."""
        f = self.ly_do
        if f is None:
            return ""
        chu_de, chi_tiet = _LY_DO_DUNG.get(f.category, ("lặp", f.human_message_vi))
        if not chi_tiet:
            chi_tiet = f.human_message_vi
        them = f" (gặp {self._so_lan_mo} lần liên tiếp)" if self._so_lan_mo > 1 else ""
        return (f"Đã dừng yêu cầu mới tới YouTube để tránh lặp lỗi {chu_de}{them}: {chi_tiet} "
                "Kết quả đã có vẫn được giữ; các video chưa quét KHÔNG được tính là đã quét.")

    def that_bai_bo_qua(self, video_id: str = "", thao_tac: str = "") -> YoutubeAccessFailure:
        """Kết quả cho việc KHÔNG được làm vì cầu dao đã mở (chưa gửi request nào)."""
        return YoutubeAccessFailure(
            category=BLOCKED_BY_BREAKER, operation=thao_tac, video_id=str(video_id or ""),
            human_message_vi="Chưa quét — " + (self.thong_bao_dung()
                                              or THONG_BAO[BLOCKED_BY_BREAKER]),
            technical_summary="", attempt=0, max_attempts=0)

    # ---------- ghi nhận ----------

    def bo_qua(self, video_id: str = "", thao_tac: str = "") -> YoutubeAccessFailure:
        """Đếm một việc bị bỏ qua vì cầu dao đã mở; trả kết quả "chưa quét" tương ứng."""
        with self._lock:
            self._so["skipped_by_breaker"] += 1
        return self.that_bai_bo_qua(video_id, thao_tac)

    def kiem_truoc(self, thao_tac: str = "", video_id: str = "") -> None:
        """Ném ``LoiTruyCapYouTube(BLOCKED_BY_BREAKER)`` nếu cầu dao đã mở — KHÔNG gửi request."""
        if not self.mo:
            return
        loi = LoiTruyCapYouTube(self.bo_qua(video_id, thao_tac))
        loi.phien = self
        raise loi

    def dem_yeu_cau(self, thao_tac: str) -> None:
        """Mỗi lần thật sự mở một phiên yt-dlp (kể cả lượt đổi client / bỏ cookie)."""
        ten = _DEM_YEU_CAU.get(thao_tac)
        if ten:
            with self._lock:
                self._so[ten] += 1

    def ghi_lui_cookie(self, loi: Any = None) -> None:
        """Có cookie thì hỏng, bỏ cookie thì thử lại: dấu hiệu YouTube không chấp nhận cookie."""
        with self._lock:
            self._so["cookie_fallbacks"] += 1
            self.cookie_bi_tu_choi = True

    def ghi_cookie_khong_hop_le(self) -> None:
        """yt-dlp báo "cookies are no longer valid": YouTube đã thu hồi phiên đăng nhập."""
        with self._lock:
            self._so["cookie_rejected_warnings"] += 1
            self.cookie_bi_tu_choi = True

    def ghi_doi_client(self) -> None:
        """Một lượt player client thất bại (đường lui sẽ thử client khác nếu còn)."""
        with self._lock:
            self._so["client_fallbacks"] += 1

    def ghi_thanh_cong(self, thao_tac: str = "") -> None:
        with self._lock:
            self._lien_tiep.clear()

    def ghi_loi(self, loi: Any, thao_tac: str = "", video_id: str = "") -> YoutubeAccessFailure:
        """Phân loại + ghi một lỗi xảy ra NGOÀI ``chay`` (tầng điều phối). Lỗi phiên này đã ghi
        thì trả lại kết quả cũ, không đếm hai lần."""
        if isinstance(loi, BaseException):
            for x in _chuoi_ngoai_le(loi):
                if isinstance(x, LoiTruyCapYouTube) and x.phien is self:
                    return x.that_bai
        f = phan_loai_loi(loi, thao_tac=thao_tac, video_id=video_id)
        if f.category != BLOCKED_BY_BREAKER:
            self._ghi_that_bai(f)
        return f

    def _ghi_that_bai(self, f: YoutubeAccessFailure) -> None:
        with self._lock:
            self._so[_DEM_THEO_LOAI.get(f.category, "other_failures")] += 1
            so = self._lien_tiep.get(f.category, 0) + 1
            self._lien_tiep[f.category] = so
            nguong = self.nguong.get(f.category)
            if self._mo_boi is None and nguong is not None and so >= nguong:
                self._mo_boi = f
                self._so_lan_mo = so
                self._su_kien.append({"t": round(time.time(), 3), "category": f.category,
                                      "operation": f.operation, "video_id": f.video_id,
                                      "lien_tiep": so})
                LOGGER.warning("event=youtube.breaker.open category=%s operation=%s video=%s "
                               "consecutive=%d detail=%s", f.category, f.operation, f.video_id,
                               so, f.technical_summary[:160])

    def nen_dung_doi_client(self, loi: Any) -> bool:
        """Cho ``ytdlp_chung.thu_tung_client(dung_ngay=…)``: đổi client có vô ích không?"""
        return phan_loai_loi(loi).category in DUNG_DOI_CLIENT

    # ---------- chạy một thao tác ----------

    def chay(self, thao_tac: str, ham: Callable[[], Any], *, video_id: str = "",
             cancel_event: Any = None, loi_huy: Optional[type] = None,
             toi_da_lan: Optional[int] = None, bo_qua: tuple = ()) -> Any:
        """Chạy ``ham()`` theo ngân sách của ``thao_tac``; trả kết quả hoặc ném
        ``LoiTruyCapYouTube`` đã phân loại (và đã ghi vào cầu dao).

        Chỉ thử lại lỗi mạng tạm thời và HTTP 429, mỗi lần nghỉ theo bảng và huỷ được: bấm Dừng
        trong lúc nghỉ thì ném ``loi_huy`` ngay. ``bo_qua`` (ví dụ ``Cancelled``) đi thẳng ra
        ngoài, không bị coi là lỗi YouTube.
        """
        self.kiem_truoc(thao_tac, video_id)
        ns = self.ngan_sach.get(thao_tac) or NganSach()
        tran = 1 + len(ns.cho_tam_thoi) + len(ns.cho_429)
        if toi_da_lan is not None:
            tran = max(1, min(tran, int(toi_da_lan)))
        with self._lock:
            self._so["youtube_operations"] += 1
        lan = tam = gioi = 0
        while True:
            lan += 1
            try:
                ket_qua = ham()
            except bo_qua:
                raise
            except Exception as e:  # noqa: BLE001 — phân loại rồi mới quyết định
                da_co = tim_loi_truy_cap(e)
                if da_co is not None and da_co.category == BLOCKED_BY_BREAKER:
                    raise
                f = phan_loai_loi(e, thao_tac=thao_tac, video_id=video_id, lan_thu=lan,
                                  toi_da=tran)
                cho = None
                if f.retryable and lan < tran:
                    if f.category == TRANSIENT_NETWORK and tam < len(ns.cho_tam_thoi):
                        cho, tam = ns.cho_tam_thoi[tam], tam + 1
                    elif f.category == RATE_LIMITED and gioi < len(ns.cho_429):
                        cho, gioi = ns.cho_429[gioi], gioi + 1
                if cho is not None:
                    with self._lock:
                        self._so["retries"] += 1
                    LOGGER.info("event=youtube.retry operation=%s video=%s category=%s "
                                "attempt=%d wait_s=%.1f", thao_tac, video_id, f.category, lan, cho)
                    if self._cho(cho, cancel_event):
                        raise (loi_huy or DaHuyTruyCap)() from None
                    continue
                self._ghi_that_bai(f)
                loi = LoiTruyCapYouTube(f)
                loi.phien = self
                raise loi from e
            else:
                self.ghi_thanh_cong(thao_tac)
                return ket_qua

    # ---------- số đo ----------

    def tom_tat(self) -> dict:
        """Số đo của lượt chạy — để thấy khuếch đại request. Không chứa bí mật."""
        with self._lock:
            so = dict(self._so)
            so["breaker_events"] = [dict(x) for x in self._su_kien]
            so["breaker_open"] = self._mo_boi is not None
            so["breaker_category"] = self._mo_boi.category if self._mo_boi else ""
            so["cookie_rejected"] = self.cookie_bi_tu_choi
            so["elapsed_s"] = round(time.time() - self.bat_dau, 3)
        return so
