# -*- coding: utf-8 -*-
"""Lớp dùng chung cho MỌI lượt gọi yt-dlp trong dự án.

Lý do module này tồn tại: dự án có **hai đường gọi yt-dlp** — quét video dài
(`engine.py`) và đồng bộ kênh (`channel.py`). Trong đúng một ngày, cùng một loại
lỗi bị vá lệch ba lần:

* 18/08 sáng — HTTP 403 ở khâu tải: chỉ `engine.py` được thêm đường lui player client.
* 18/08 trưa — đồng bộ kênh vẫn 403 vì `channel.py` bị bỏ sót.
* 18/08 chiều — lỗi yt-dlp lên giao diện còn nguyên escape ANSI, vì `engine.py`
  không dùng hàm dọn màu mà `channel.py` đã có.

Từ nay mọi tuỳ chọn yt-dlp đi qua :class:`CauHinhMang` nên không còn chỗ nào lệch.
Module này KHÔNG import `engine` hay `channel` để tránh vòng import.

Về bảo mật: chỉ giữ **đường dẫn** file cookie, không bao giờ giữ hay ghi log nội
dung cookie — `cau_hinh.lay_tu_config()` serialize toàn bộ trường Config ra
`data/cau_hinh.json` mà không có danh sách trắng, nên trường nào chứa cookie sẽ bị
ghi thẳng ra đĩa dạng thô.
"""

from __future__ import annotations

import io
import os
import re
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

# Thứ tự "player client" thử khi tải. YouTube chặn từng client một cách ĐỘC LẬP và
# đổi theo thời gian, nên phải có đường lui thay vì khoá cứng một cái. Chuỗi rỗng
# nghĩa là để yt-dlp tự chọn.
#
# Client MẶC ĐỊNH đứng đầu vì chỉ nó có format CHỈ-TIẾNG. `android` không trả format
# audio-only nên `ba` rơi xuống `b` và tải CẢ VIDEO — đo 2026-08-19 trên video 121
# tiếng: `android` chọn format 18 (360p) nặng 31,27 GB, client mặc định chọn 249 chỉ
# 2,75 GB. Chênh hơn 11 lần.
#
# NHƯNG đo cùng ngày: client mặc định vẫn bị HTTP 403 ở khâu TẢI (trích xuất thì chạy
# — đó là lý do bẫy này khó thấy: kiểm bằng tải thử 10 KB sẽ báo "OK" nhầm, phải tải
# ĐẦY ĐỦ mới lộ). Thử hết mweb, android_vr, web_creator, web_embedded, tv_simply,
# android_music, web_music: client nào có audio-only cũng 403; chỉ `android` tải được.
#
# Vì vậy thứ tự này là "thứ tự MONG MUỐN", không phải thứ tự sẽ chạy. `NhoClientTotNhat`
# nhớ client thật sự tải được để không phải trả giá 403 cho từng video, nhưng vẫn dò
# lại định kỳ để tự lấy lại khoản tiết kiệm 11 lần ngay khi YouTube mở lại.
PLAYER_CLIENTS_MAC_DINH = ["", "android", "tv", "ios", "web_safari"]

# Danh sách dự phòng cho :func:`client_khong_ho_tro_cookie` khi không đọc được bảng
# thật của yt-dlp. Đo trên yt-dlp 2026.07.04.
CLIENT_KHONG_COOKIE_DU_PHONG = frozenset({"android", "android_vr", "ios", "tv_simply"})

# yt-dlp tô màu thông báo lỗi bằng escape ANSI. Giao diện Streamlit không hiểu chúng
# nên người dùng thấy rác kiểu "[0;31mERROR:[0m". Vẫn dọn ở đây dù đã đặt `no_color`
# vì lỗi có thể tới từ tiến trình con hoặc từ bản ghi cũ trong lịch sử.
RE_MA_MAU = re.compile(r"\x1b?\[[0-9;]*m")

# Đuôi hướng dẫn của yt-dlp ("Use --cookies-from-browser ... See https://...") dài
# gần 300 ký tự và vô nghĩa với người dùng không phải lập trình viên; câu tiếng Việt
# bên dưới đã nói đủ ý. Cắt từ chỗ đầu tiên trong các mốc này trở đi.
MOC_CAT_HUONG_DAN = (" Use --cookies", " See  https://", " See https://")

CHU_THICH = {
    "cookie_chet": ("Cookie YouTube đã hết hiệu lực nên YouTube không trả về âm thanh "
                    "nữa (chỉ còn ảnh thu nhỏ). Cookie chết còn tệ hơn không có cookie. "
                    "Cách xử lý: vào tab «Cấu hình» → «🔐 Kết nối YouTube» và XOÁ TRỐNG "
                    "ô đường dẫn cookie, hoặc xuất lại file cookie mới."),
    "bot": ("YouTube đang nghi máy bạn là bot và chặn ở mức ĐỊA CHỈ MẠNG, không phải "
            "do link hỏng. Đổi cách tải không cứu được. Cách xử lý: nghỉ vài tiếng "
            "cho hết hạn chặn, giảm nhịp quét, hoặc nạp cookie tài khoản YouTube "
            "trong tab «Cấu hình»."),
    "tuoi": ("Video bị giới hạn độ tuổi: YouTube bắt đăng nhập mới cho tải. "
             "Đây KHÔNG phải lỗi tool; cần nạp cookie tài khoản mới tải được."),
    "go": "Video đã bị gỡ hoặc để riêng tư trên YouTube.",
}


def go_ma_mau(s: Any) -> str:
    """Bỏ escape ANSI khỏi thông báo lỗi trước khi đưa lên giao diện."""
    return RE_MA_MAU.sub("", str(s)).strip()


def giai_thich_loi(loi: Any, co_cookie: bool = False) -> str:
    """Diễn giải lỗi yt-dlp thành câu tiếng Việt nói rõ ai phải làm gì.

    Người dùng không phải lập trình viên: cần phân biệt ngay "tool hỏng" với
    "YouTube không cho tải" để khỏi ngồi chờ sửa nhầm chỗ.

    Hàm này **luỹ đẳng**: gọi lại trên chuỗi đã diễn giải không nhân đôi chú thích.
    Cần vậy vì lỗi đi qua nhiều lớp (helper gói lại rồi báo cáo ghi ra) — bản đầu đã
    dán chú thích hai lần vào cùng một dòng.
    """
    tin = go_ma_mau(loi)
    for moc in MOC_CAT_HUONG_DAN:
        vi_tri = tin.find(moc)
        if vi_tri > 0:
            tin = tin[:vi_tri].rstrip()
    thap = tin.lower()

    def dan(khoa: str) -> str:
        chu = CHU_THICH[khoa]
        return tin if chu in tin else f"{tin} | {chu}"

    # Bot-check phải xét TRƯỚC giới hạn độ tuổi: cả hai câu của YouTube đều bắt đầu
    # bằng "Sign in to confirm...", nhưng chỉ bot-check mới là chặn theo địa chỉ mạng
    # và mới cần lời khuyên nghỉ/giảm nhịp.
    # Chỉ quy cho cookie khi PHIÊN CÓ cookie: cùng câu lỗi đó, không cookie thì lại
    # nghĩa là video thật sự không còn định dạng nào (bị gỡ, DRM...). Đoán bừa sẽ đẩy
    # người dùng đi sửa nhầm chỗ.
    if co_cookie and la_dau_hieu_cookie_chet(tin):
        return dan("cookie_chet")
    if "not a bot" in thap:
        return dan("bot")
    if "confirm your age" in thap or "age-restricted" in thap:
        return dan("tuoi")
    if "video is not available" in thap or "private video" in thap or "removed" in thap:
        return dan("go")
    return tin


def client_khong_ho_tro_cookie() -> frozenset:
    """Các player client bị yt-dlp LOẠI khi phiên có cookie đăng nhập.

    Đọc thẳng bảng ``INNERTUBE_CLIENTS`` của yt-dlp để tự cập nhật theo phiên bản;
    yt-dlp đổi đường dẫn nội bộ thì rơi về danh sách dự phòng đã đo.
    Xem ``yt_dlp/extractor/youtube/_video.py``: client thiếu ``SUPPORTS_COOKIES``
    bị gỡ khỏi danh sách yêu cầu kèm cảnh báo, tức đường lui của ta sẽ mất lượt.
    """
    try:
        from yt_dlp.extractor.youtube._base import INNERTUBE_CLIENTS

        return frozenset(
            ten for ten, mo_ta in INNERTUBE_CLIENTS.items()
            if not mo_ta.get("SUPPORTS_COOKIES")
        )
    except Exception:  # noqa: BLE001 — bảng nội bộ của yt-dlp có thể đổi chỗ
        return CLIENT_KHONG_COOKIE_DU_PHONG


def sap_xep_player_clients(clients: list, co_cookie: bool) -> list:
    """Sắp lại thứ tự thử client cho phù hợp với việc có cookie hay không.

    Khi phiên có cookie, yt-dlp tự gỡ các client không hỗ trợ cookie (``android``,
    ``ios``...). Nếu vẫn để chúng đứng đầu thì mỗi video mất vài lượt thử vô ích, và
    tệ hơn là chúng che mất chính lợi ích của cookie. Nên đẩy chúng xuống cuối, giữ
    nguyên thứ tự tương đối để cấu hình của người dùng vẫn còn ý nghĩa.

    Vẫn giữ nhóm không hỗ trợ ở CUỐI chứ không xoá hẳn: nếu cookie sai hoặc hết hạn
    thì yt-dlp không coi là "đã đăng nhập" nên chúng vẫn là đường lui hợp lệ.
    """
    ds = list(clients or [""])
    if not co_cookie:
        return ds
    loai = client_khong_ho_tro_cookie()
    hop_le = [c for c in ds if c not in loai]
    khong = [c for c in ds if c in loai]
    return (hop_le or [""]) + khong


TRINH_DUYET_HO_TRO = ("brave", "chrome", "chromium", "edge", "opera",
                      "vivaldi", "whale", "firefox", "safari")


def phan_tich_cookies_browser(chuoi: str) -> Optional[tuple]:
    """Chuyển ``"chrome"`` / ``"edge:Profile 1"`` thành tuple cho yt-dlp.

    yt-dlp nhận ``cookiesfrombrowser`` là tuple 4 phần tử
    ``(trình duyệt, profile, keyring, container)`` — **khác** thứ tự của chuỗi trên
    dòng lệnh ``BROWSER[+KEYRING][:PROFILE][::CONTAINER]``, nên không thể truyền
    thẳng chuỗi người dùng gõ. Trả ``None`` khi rỗng để bên gọi biết là chưa cấu hình.
    """
    chuoi = (chuoi or "").strip()
    if not chuoi:
        return None
    trinh_duyet, _, profile = chuoi.partition(":")
    trinh_duyet = trinh_duyet.strip().lower()
    if not trinh_duyet:
        return None
    return (trinh_duyet, profile.strip() or None, None, None)


class LoiFileCookie(ValueError):
    """File cookie sai định dạng. Thông báo CHỈ nêu số dòng, không bao giờ nêu nội dung."""


# Cache kết quả kiểm tra theo (đường dẫn, mtime, kích thước): mỗi video là một lượt
# dựng tuỳ chọn, không đọc lại file cookie hàng trăm lần.
_CACHE_COOKIE: dict = {}


def kiem_tra_file_cookie(duong_dan: str) -> None:
    """Kiểm định dạng Netscape TRƯỚC khi đưa file cho yt-dlp. Sai thì ném lỗi.

    **Đây là một rào chắn bảo mật, không phải tiện ích.** ``YoutubeDLCookieJar.load()``
    của yt-dlp gặp dòng sai định dạng thì gọi ``write_string()`` in NGUYÊN VĂN dòng đó
    ra ``sys.stderr`` — kèm cả giá trị ``__Secure-1PSID``, thứ đủ để chiếm tài khoản.
    Cờ ``quiet``/``no_warnings``/``no_color`` KHÔNG chặn được vì ``write_string`` ghi
    thẳng stderr chứ không đi qua logger. Mà ``nhat_ky.mo_nhat_ky()`` lại đấu stderr
    vào ``ketqua/giamsat_*.log`` — file giữ 30 ngày, nằm chung thư mục với CSV mà người
    dùng hay nén gửi đi khi nhờ hỗ trợ.

    Lỗi hay gặp nhất: mở cookies.txt bằng Notepad rồi lưu lại, TAB biến thành dấu cách.

    Ném :class:`LoiFileCookie` chỉ nêu SỐ DÒNG. Không bao giờ đưa nội dung dòng vào
    thông báo, log hay ngoại lệ — nó sẽ đi đúng vào chỗ ta đang bịt.
    """
    duong_dan = (duong_dan or "").strip()
    if not duong_dan:
        return
    try:
        khoa = (duong_dan, os.path.getmtime(duong_dan), os.path.getsize(duong_dan))
    except OSError as e:
        raise LoiFileCookie(
            f"Không đọc được file cookie «{os.path.basename(duong_dan)}»: {e.strerror}."
        ) from None
    if _CACHE_COOKIE.get(khoa):
        return

    try:
        noi_dung = io.open(duong_dan, encoding="utf-8", errors="replace").read()
    except OSError as e:
        raise LoiFileCookie(
            f"Không đọc được file cookie «{os.path.basename(duong_dan)}»: {e.strerror}."
        ) from None

    dong_hong = []
    co_ban_ghi = False
    for so, dong in enumerate(noi_dung.splitlines(), start=1):
        tho = dong.strip()
        if not tho or tho.startswith("#"):
            continue
        # Netscape: đúng 7 trường phân tách bằng TAB. yt-dlp chấp nhận cả tiền tố
        # "#HttpOnly_" ở cột đầu, nhưng số trường thì không đổi.
        if len(dong.rstrip("\n").split("\t")) != 7:
            dong_hong.append(so)
        else:
            co_ban_ghi = True

    if dong_hong:
        vi_du = ", ".join(str(x) for x in dong_hong[:5])
        them = f" (và {len(dong_hong) - 5} dòng nữa)" if len(dong_hong) > 5 else ""
        raise LoiFileCookie(
            f"File cookie «{os.path.basename(duong_dan)}» sai định dạng Netscape ở "
            f"dòng {vi_du}{them}. Nguyên nhân hay gặp: mở bằng Notepad rồi lưu lại làm "
            "TAB biến thành dấu cách. Hãy xuất lại bằng tiện ích trình duyệt, đừng sửa tay."
        )
    if not co_ban_ghi:
        raise LoiFileCookie(
            f"File cookie «{os.path.basename(duong_dan)}» không có bản ghi cookie nào."
        )
    _CACHE_COOKIE[khoa] = True


@dataclass(frozen=True)
class CauHinhMang:
    """Mọi tham số mạng/xác thực dùng chung cho các lượt gọi yt-dlp.

    Bất biến để chia sẻ tự do giữa các luồng nền của Streamlit.
    """

    network_timeout_s: int = 30
    cookiefile: str = ""          # ĐƯỜNG DẪN tới cookies.txt — không bao giờ là nội dung
    cookies_browser: str = ""     # "chrome" hoặc "edge:Tên Profile"
    sleep_requests_s: float = 1.0
    sleep_min_s: float = 0.0
    sleep_max_s: float = 0.0

    @classmethod
    def tu_config(cls, cfg: Any) -> "CauHinhMang":
        """Dựng từ ``engine.Config``.

        Dùng ``getattr`` có mặc định để module này không phụ thuộc vào việc Config đã
        có đủ trường hay chưa (cấu hình cũ của người dùng, hoặc test dựng Config giả).
        """
        return cls(
            network_timeout_s=int(getattr(cfg, "network_timeout_s", 30)),
            cookiefile=str(getattr(cfg, "ytdlp_cookiefile", "") or ""),
            cookies_browser=str(getattr(cfg, "ytdlp_cookies_browser", "") or ""),
            sleep_requests_s=float(getattr(cfg, "ytdlp_sleep_requests_s", 1.0) or 0.0),
            sleep_min_s=float(getattr(cfg, "ytdlp_sleep_min_s", 0.0) or 0.0),
            sleep_max_s=float(getattr(cfg, "ytdlp_sleep_max_s", 0.0) or 0.0),
        )

    @classmethod
    def tu_file_cau_hinh(cls, data_dir: str) -> "CauHinhMang":
        """Đọc thẳng ``data/cau_hinh.json``, KHÔNG cần dựng ``Engine``.

        Dành cho các lệnh nhẹ (ví dụ ``cli.py vameta``) vốn cố tình không khởi tạo
        Engine — dựng Engine sẽ nạp kho vân tay và giành khoá liên tiến trình, quá đắt
        cho một lệnh chỉ vá metadata. Nhưng chúng vẫn gọi mạng, nên vẫn phải mang theo
        cookie và nhịp tải người dùng đã đặt.

        Đọc lỗi hay thiếu file thì trả về mặc định: thiếu cấu hình không được làm hỏng
        lệnh, chỉ mất phần tuỳ chỉnh.
        """
        import json

        mac_dinh = cls()
        try:
            with io.open(os.path.join(data_dir, "cau_hinh.json"), encoding="utf-8") as f:
                du_lieu = json.load(f)
            if not isinstance(du_lieu, dict):
                return mac_dinh
        except Exception:  # noqa: BLE001 — chưa có cấu hình là chuyện bình thường
            return mac_dinh

        def so(khoa: str, san: float) -> float:
            gia_tri = du_lieu.get(khoa, san)
            return float(gia_tri) if isinstance(gia_tri, (int, float)) else san

        def chu(khoa: str) -> str:
            gia_tri = du_lieu.get(khoa, "")
            return gia_tri if isinstance(gia_tri, str) else ""

        return cls(
            network_timeout_s=int(so("network_timeout_s", mac_dinh.network_timeout_s)),
            cookiefile=chu("ytdlp_cookiefile"),
            cookies_browser=chu("ytdlp_cookies_browser"),
            sleep_requests_s=so("ytdlp_sleep_requests_s", mac_dinh.sleep_requests_s),
            sleep_min_s=so("ytdlp_sleep_min_s", mac_dinh.sleep_min_s),
            sleep_max_s=so("ytdlp_sleep_max_s", mac_dinh.sleep_max_s),
        )

    @property
    def co_cookie(self) -> bool:
        return bool(self.cookiefile.strip() or self.cookies_browser.strip())

    def bo_cookie(self) -> "CauHinhMang":
        """Bản sao đã gỡ cookie, giữ nguyên timeout và nhịp tải.

        Dùng cho đường lui khi cookie hết hạn — xem :func:`chay_kem_duong_lui_cookie`.
        """
        return replace(self, cookiefile="", cookies_browser="")

    def player_clients(self, clients: list) -> list:
        return sap_xep_player_clients(clients, self.co_cookie)

    def tuy_chon(self, **them: Any) -> dict:
        """Dict tuỳ chọn yt-dlp: phần dùng chung + phần riêng của nơi gọi.

        ``no_color`` để yt-dlp không nhét escape ANSI vào thông báo lỗi ngay từ đầu —
        chữa tận gốc thay vì chỉ dọn lúc hiển thị.
        """
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "socket_timeout": self.network_timeout_s,
        }
        if self.sleep_requests_s > 0:
            # Khoá DUY NHẤT giãn nhịp ở khâu TRÍCH XUẤT — đúng chỗ bot-check đánh.
            # `sleep_interval`/`max_sleep_interval` chỉ có tác dụng ở khâu tải.
            opts["sleep_interval_requests"] = self.sleep_requests_s
        if self.sleep_min_s > 0 or self.sleep_max_s > 0:
            # Xét cả hai chứ không chỉ min: giao diện mô tả đây là "nghỉ ngẫu nhiên
            # trong khoảng", nên người dùng đặt mỗi ô tối đa vẫn phải có tác dụng.
            opts["sleep_interval"] = self.sleep_min_s
            opts["max_sleep_interval"] = max(self.sleep_max_s, self.sleep_min_s)
        if self.cookiefile.strip():
            # Kiểm TRƯỚC khi giao cho yt-dlp: xem kiem_tra_file_cookie() để biết vì sao
            # đây là rào chắn bảo mật chứ không phải kiểm tra cho đẹp.
            kiem_tra_file_cookie(self.cookiefile)
            opts["cookiefile"] = self.cookiefile.strip()
        tu_trinh_duyet = phan_tich_cookies_browser(self.cookies_browser)
        if tu_trinh_duyet:
            opts["cookiesfrombrowser"] = tu_trinh_duyet
        opts.update(them)
        return opts


# Dấu hiệu cookie đã hết hiệu lực. Đo thật 18/08/2026 trên 8 link + 2 video đối chứng:
# gửi cookie CHẾT đi thì YouTube trả phản hồi CHỈ CÒN storyboard — 4 format ảnh thu
# nhỏ, không âm thanh, không hình. So sánh cùng lúc, cùng máy:
#     không cookie : 24 format, có 139/249/140/251 (audio-only)  -> 8/8 link chạy
#     có cookie    :  4 format, toàn storyboard                  -> 0/8 link chạy
# Tool xin `bestaudio`, không có gì để chọn, nên yt-dlp báo "Requested format is not
# available" — câu chữ chẳng liên quan gì tới nguyên nhân thật, khiến người dùng đi
# tìm nhầm phía link. Cookie chết còn TỆ HƠN không có cookie, nên phải tự lùi về.
DAU_HIEU_COOKIE_CHET = (
    "requested format is not available",
    "no video formats found",
    "no formats found",
)


def la_dau_hieu_cookie_chet(loi: Any) -> bool:
    """Lỗi này có mang dấu hiệu đặc trưng của cookie hết hạn không?"""
    thap = go_ma_mau(loi).lower()
    return any(d in thap for d in DAU_HIEU_COOKIE_CHET)


def chay_kem_duong_lui_cookie(
    cau_hinh: "CauHinhMang",
    chay: Callable[["CauHinhMang"], Any],
    khi_bo_cookie: Optional[Callable[[BaseException], None]] = None,
) -> Any:
    """Chạy ``chay(cau_hinh)``; cookie chết thì tự chạy lại KHÔNG cookie.

    Vì sao phải tự lùi thay vì chỉ báo lỗi: cookie YouTube hết hiệu lực rất thường
    xuyên (xoay vòng phiên, đăng xuất, đổi mạng) và **hạn ghi trong file không phản
    ánh điều đó** — file vẫn "còn 400 ngày" trong khi phiên đã chết. Nếu không lùi,
    một cookie chết làm hỏng TOÀN BỘ việc quét cho tới khi người dùng tự đoán ra.

    Chỉ lùi khi có cookie và lỗi đúng dấu hiệu; mọi lỗi khác ném nguyên ra ngoài để
    không che mất nguyên nhân thật.

    ``khi_bo_cookie``: gọi khi quyết định lùi, để bên trên ghi log/cảnh báo.
    """
    try:
        return chay(cau_hinh)
    except Exception as e:  # noqa: BLE001 — phân loại rồi mới quyết định
        if not cau_hinh.co_cookie or not la_dau_hieu_cookie_chet(e):
            raise
        if khi_bo_cookie:
            khi_bo_cookie(e)
        try:
            return chay(cau_hinh.bo_cookie())
        except Exception:  # noqa: BLE001
            # Bỏ cookie vẫn hỏng => cookie không phải nguyên nhân. Ném lỗi GỐC để
            # người dùng thấy đúng vấn đề thật của video, không bị dẫn sai hướng.
            raise e from None


class NhoClientTotNhat:
    """Nhớ player client vừa TẢI ĐƯỢC, để khỏi trả giá thử-và-hỏng cho từng video.

    Bài toán: thứ tự mong muốn đặt client rẻ (có audio-only) lên đầu, nhưng client rẻ
    lại đang bị YouTube chặn ở khâu tải. Nếu cứ theo thứ tự mong muốn thì MỖI video mất
    một lượt 403 vô ích — đồng bộ một kênh 758 video là mất hàng chục phút.

    Giải pháp: sau lần đầu, đưa client đã tải được lên đầu. Nhưng KHÔNG khoá vĩnh viễn —
    hết ``song_giay`` thì quên đi để dò lại thứ tự mong muốn, nhờ đó tự lấy lại khoản
    tiết kiệm băng thông ngay khi YouTube mở lại client rẻ, không cần ai sửa cấu hình.

    An toàn theo thiết kế: đây chỉ là gợi ý THỨ TỰ. Đường lui vẫn thử đủ mọi client,
    nên nhớ nhầm thì chỉ chậm hơn một chút chứ không bao giờ làm hỏng việc tải.
    """

    def __init__(self, song_giay: float = 1800.0):
        self.song_giay = song_giay
        self._client: Optional[str] = None
        self._luc: float = 0.0

    def _con_han(self) -> bool:
        return self._client is not None and (time.monotonic() - self._luc) < self.song_giay

    def sap_xep(self, clients: list) -> list:
        """Đưa client đã biết là tải được lên đầu, giữ nguyên thứ tự còn lại."""
        ds = list(clients or [""])
        if not self._con_han() or self._client not in ds:
            return ds
        return [self._client] + [c for c in ds if c != self._client]

    def ghi_nhan(self, client: str) -> None:
        self._client = client
        self._luc = time.monotonic()

    def quen(self) -> None:
        self._client = None


def thu_tung_client(
    clients: list,
    chay: Callable[[dict], Any],
    opts: dict,
    khi_that_bai: Optional[Callable[[str, BaseException], None]] = None,
    bo_qua: tuple = (),
    truoc_khi_thu_lai: Optional[Callable[[], None]] = None,
    khi_thanh_cong: Optional[Callable[[str, list], None]] = None,
    bo_nho: Optional["NhoClientTotNhat"] = None,
) -> Any:
    """Chạy ``chay(opts)`` lần lượt với từng player client cho tới khi có cái được.

    YouTube chặn từng client một cách độc lập, và khâu trích metadata thường vẫn chạy
    trong khi khâu TẢI đã bị chặn — nên lỗi hiện ra là ``HTTP Error 403: Forbidden``
    *sau khi* tool đã lấy được tiêu đề video, rất dễ tưởng là hỏng link.

    ``bo_qua``: các lớp ngoại lệ KHÔNG được kích hoạt đường lui (ví dụ ``Cancelled``) —
    huỷ là ý người dùng, không được lặng lẽ thử tiếp cho hết danh sách.

    ``truoc_khi_thu_lai``: dọn dẹp trước khi đổi sang client khác. BẮT BUỘC có khi bên
    gọi bật ``continuedl``: mỗi client trả một format khác nhau, mà yt-dlp thấy file
    ``.part`` cũ thì nối tiếp byte của luồng mới vào — ra file audio hỏng mà không báo
    lỗi gì. Dọn ở đây chứ không tắt ``continuedl``, để việc nối tiếp sau khi đứt mạng
    giữa hai lần chạy vẫn dùng được.

    ``khi_thanh_cong(ten_client, da_thu)``: để bên gọi ghi log client nào CỨU được —
    thông tin quan trọng nhất khi YouTube đổi chính sách chặn.
    """
    loi_cuoi: Optional[BaseException] = None
    da_thu: list = []
    if bo_nho is not None:
        clients = bo_nho.sap_xep(clients)
    for client in (clients or [""]):
        rieng = dict(opts)
        if client:
            rieng["extractor_args"] = {"youtube": {"player_client": [client]}}
        if da_thu and truoc_khi_thu_lai:
            truoc_khi_thu_lai()
        try:
            ket_qua = chay(rieng)
        except bo_qua:
            raise
        except Exception as e:  # noqa: BLE001 — còn client khác thì thử tiếp
            loi_cuoi = e
            ten = client or "mặc định"
            da_thu.append(ten)
            if khi_that_bai:
                khi_that_bai(ten, e)
        else:
            if bo_nho is not None:
                bo_nho.ghi_nhan(client)
            if khi_thanh_cong:
                khi_thanh_cong(client or "mặc định", list(da_thu))
            return ket_qua
    raise RuntimeError(
        "Không tải được audio. Đã thử: " + ", ".join(da_thu)
        + ". Lỗi cuối: " + go_ma_mau(loi_cuoi)
    ) from loi_cuoi
