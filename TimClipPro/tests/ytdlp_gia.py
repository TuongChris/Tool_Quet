# -*- coding: utf-8 -*-
"""yt-dlp GIẢ theo kịch bản cho test truy cập YouTube — không mạng, đếm TỪNG lần gọi.

``monkeypatch.setattr(yt_dlp, "YoutubeDL", YdlKichBan(...))``. Mỗi lần mở một phiên yt-dlp
được ghi vào ``goi`` là ``(loai, ma, client)`` với ``loai`` ∈ {"info", "tai", "liet_ke"} — đúng
đơn vị "request" mà brief yêu cầu đếm. Chuỗi lỗi theo khuôn câu yt-dlp 2026.08.19.
"""

import os
import re

BOT = ("ERROR: [youtube] {id}: Sign in to confirm you're not a bot. Use --cookies-from-browser "
       "or --cookies for the authentication.")
AUTH = ("ERROR: [youtube] {id}: Sign in to confirm your age. This video may be inappropriate "
        "for some users.")
GO = "ERROR: [youtube] {id}: Video unavailable"
R429 = "ERROR: [youtube] {id}: Unable to download API page: HTTP Error 429: Too Many Requests"
C403 = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
TAM = "ERROR: [youtube] {id}: Unable to download API page: The read operation timed out"

_RE_MA = re.compile(r"(?:youtu\.be/|[?&]v=|/shorts/)([A-Za-z0-9_-]{6,20})")


def ma_video(url: str) -> str:
    m = _RE_MA.search(url or "")
    return m.group(1) if m else (url or "").rstrip("/").rsplit("/", 1)[-1]


def info_mau(ma: str, dai: float = 600.0) -> dict:
    return {"id": ma, "title": f"Video {ma}", "duration": dai, "uploader": "Kênh thử",
            "channel": "Kênh thử", "channel_id": "UCthu", "upload_date": "20260101",
            "channel_url": "https://www.youtube.com/channel/UCthu",
            "webpage_url": f"https://www.youtube.com/watch?v={ma}"}


class YdlKichBan:
    """Hành vi theo mã video: ``info``/``tai`` là dict ``ma -> lỗi (str) | dict | None | hàm``.

    Khoá ``"*"`` là mặc định. Lỗi dạng chuỗi được ``format(id=ma)`` rồi ném ``RuntimeError``.
    ``liet_ke``: ``hàm(phiên, url) -> dict | None`` cho lượt liệt kê kênh (``ignoreerrors``).
    """

    def __init__(self, info=None, tai=None, liet_ke=None):
        self.info = dict(info or {})
        self.tai = dict(tai or {})
        self.liet_ke = liet_ke
        self.goi: list = []
        self.opts: list = []

    def __call__(self, opts):
        self.opts.append(dict(opts))
        return _PhienYdl(self, dict(opts))

    def dem(self, loai: str) -> int:
        return sum(1 for g in self.goi if g[0] == loai)


class _PhienYdl:
    def __init__(self, cha, opts):
        self.cha, self.opts = cha, opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def client(self) -> str:
        args = (self.opts.get("extractor_args") or {}).get("youtube", {})
        return (args.get("player_client") or [""])[0]

    def _hanh_vi(self, bang, ma, mac_dinh):
        x = bang.get(ma, bang.get("*", mac_dinh))
        if callable(x):
            x = x(self, ma)
        if isinstance(x, str):
            raise RuntimeError(x.format(id=ma))
        if isinstance(x, BaseException):
            raise x
        return x

    def _ghi_file(self, ma):
        mau = self.opts.get("outtmpl")
        if isinstance(mau, dict):
            mau = mau.get("default")
        if not mau:
            return
        duong_dan = mau.replace("%(id)s", ma).replace("%(ext)s", "webm")
        os.makedirs(os.path.dirname(duong_dan) or ".", exist_ok=True)
        with open(duong_dan, "wb") as f:
            f.write(b"audio gia " + ma.encode())

    def extract_info(self, url, download=False):
        if self.opts.get("ignoreerrors"):
            self.cha.goi.append(("liet_ke", url, self.client))
            return self.cha.liet_ke(self, url) if callable(self.cha.liet_ke) else self.cha.liet_ke
        ma = ma_video(url)
        if download:
            self.cha.goi.append(("tai", ma, self.client))
            self._hanh_vi(self.cha.tai, ma, None)
            self._ghi_file(ma)
            return info_mau(ma)
        self.cha.goi.append(("info", ma, self.client))
        return self._hanh_vi(self.cha.info, ma, lambda _p, m: info_mau(m))

    def download(self, urls):
        ma = ma_video(urls[0])
        self.cha.goi.append(("tai", ma, self.client))
        self._hanh_vi(self.cha.tai, ma, None)
        self._ghi_file(ma)
        return 0
