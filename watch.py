# -*- coding: utf-8 -*-
"""Mô hình dữ liệu và lưu trữ danh sách nguồn YouTube cần theo dõi."""

from dataclasses import asdict, dataclass, field
import json
import os
import re
from typing import Any


@dataclass
class MucTheoDoi:
    loai: str
    url: str
    ghi_chu: str = ""
    bat: bool = True


@dataclass
class WatchList:
    muc: list = field(default_factory=list)
    kho: str = ""
    gioi_han_moi_lan: int = 20


@dataclass
class UngVien:
    video_id: str
    url: str
    tieu_de: str = ""
    nguon: str = ""


_MAU_ID_YOUTUBE = (
    re.compile(
        r"^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{6,20})(?=$|[?&#/])",
        re.IGNORECASE,
    ),
    re.compile(
        r"^https?://(?:www\.)?youtube\.com/watch\?"
        r"(?:[^&#]+&)*v=([A-Za-z0-9_-]{6,20})(?=$|[&#])",
        re.IGNORECASE,
    ),
    re.compile(
        r"^https?://(?:www\.)?youtube\.com/shorts/"
        r"([A-Za-z0-9_-]{6,20})(?=$|[?&#/])",
        re.IGNORECASE,
    ),
)


def lay_id_youtube(url: str) -> str:
    """Tách ID video từ URL YouTube. Trả về "" nếu không nhận dạng được."""
    for mau in _MAU_ID_YOUTUBE:
        ket_qua = mau.search(url.strip())
        if ket_qua:
            return ket_qua.group(1)
    return ""


def doc_watchlist(path: str) -> WatchList:
    """Đọc watchlist.json. File không tồn tại hoặc hỏng -> trả WatchList rỗng."""
    if not os.path.isfile(path):
        return WatchList()

    try:
        with open(path, encoding="utf-8") as f:
            du_lieu = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return WatchList()

    if not isinstance(du_lieu, dict):
        return WatchList()

    du_lieu_muc = du_lieu.get("muc", [])
    if not isinstance(du_lieu_muc, list):
        du_lieu_muc = []

    cac_muc = []
    for muc in du_lieu_muc:
        if not isinstance(muc, dict):
            continue
        loai = muc.get("loai")
        url = muc.get("url")
        if loai not in {"kenh", "link"} or not isinstance(url, str) or not url.strip():
            continue
        ghi_chu = muc.get("ghi_chu", "")
        bat = muc.get("bat", True)
        cac_muc.append(MucTheoDoi(
            loai=loai,
            url=url,
            ghi_chu=ghi_chu if isinstance(ghi_chu, str) else "",
            bat=bat if isinstance(bat, bool) else True,
        ))

    kho = du_lieu.get("kho", "")
    gioi_han = du_lieu.get("gioi_han_moi_lan", 20)
    return WatchList(
        muc=cac_muc,
        kho=kho if isinstance(kho, str) else "",
        gioi_han_moi_lan=(
            gioi_han
            if isinstance(gioi_han, int) and not isinstance(gioi_han, bool)
            else 20
        ),
    )


def ghi_watchlist(wl: WatchList, path: str) -> None:
    """Ghi watchlist.json, encoding utf-8, ensure_ascii=False, indent=2."""
    du_lieu = {
        "muc": [asdict(muc) for muc in wl.muc],
        "kho": wl.kho,
        "gioi_han_moi_lan": wl.gioi_han_moi_lan,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(du_lieu, f, ensure_ascii=False, indent=2)


def id_da_quet(engine: Any, chi_thanh_cong: bool = True) -> set:
    """Trả về set các video_id đã quét, đọc từ lịch sử SQLite."""
    ket_qua = set()
    for job in engine.list_jobs(limit=100000):
        if chi_thanh_cong and job.get("status") != "ok":
            continue
        video_id = job.get("source_id")
        if video_id:
            ket_qua.add(video_id)
    return ket_qua


def loc_can_quet(ung_vien: list, da_quet: set, gioi_han: int = 0) -> list:
    """Lọc ra các ứng viên CHƯA quét. Hàm thuần — không chạm engine, không I/O."""
    ket_qua = []
    da_gap = set()
    for muc in ung_vien:
        video_id = muc.video_id
        if not video_id or video_id in da_quet or video_id in da_gap:
            continue
        da_gap.add(video_id)
        ket_qua.append(muc)
        if gioi_han > 0 and len(ket_qua) >= gioi_han:
            break
    return ket_qua
