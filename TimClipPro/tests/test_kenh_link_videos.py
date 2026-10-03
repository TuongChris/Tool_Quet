# -*- coding: utf-8 -*-
"""Link kênh `/channel/UC…` phải trỏ tới tab Videos, như link `@tên` đã làm.

Tier 2 (03/10/2026): `list_channel` với `/channel/UC…` thiếu `/videos` trả về các TAB của kênh
(Videos/Shorts/Live) mang id = id KÊNH thay vì danh sách video. yt-dlp giả, không mạng.
"""

import pytest
import yt_dlp

from channel import ChannelSync
from ytdlp_gia import YdlKichBan

KENH = "https://www.youtube.com/channel/UC" + "z" * 22
_DS = {"_type": "playlist", "id": "UCkenh", "entries": [
    {"id": "vid00000001", "title": "Video", "url": "https://www.youtube.com/watch?v=vid00000001"}]}


@pytest.mark.parametrize("vao,ra", [
    (KENH, KENH + "/videos"),
    (KENH + "/", KENH + "/videos"),
    (KENH + "/videos", KENH + "/videos"),
    ("https://www.youtube.com/@kenh", "https://www.youtube.com/@kenh/videos"),
    ("https://www.youtube.com/playlist?list=PLabc", "https://www.youtube.com/playlist?list=PLabc"),
])
def test_link_kenh_duoc_tro_toi_tab_videos(monkeypatch, vao, ra):
    ydl = YdlKichBan(liet_ke=lambda _p, _u: _DS)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", ydl)
    assert [v.id for v in ChannelSync.list_channel(vao)] == ["vid00000001"]
    assert ydl.goi[0][1] == ra
