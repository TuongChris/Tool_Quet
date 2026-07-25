# -*- coding: utf-8 -*-
"""Mô hình dữ liệu và hàm dựng hồ sơ vi phạm."""

from dataclasses import dataclass, field
from datetime import datetime

from engine import Engine, ScanResult, hhmmss


@dataclass
class MucViPham:
    """Một đoạn nội dung gốc xuất hiện trong video vi phạm."""

    ten_clip_goc: str
    tieu_de_goc: str
    link_goc: str
    tu_hhmmss: str
    den_hhmmss: str
    link_moc: str
    do_dai_giay: int
    ty_le: float
    hashes: int


@dataclass
class HoSo:
    """Hồ sơ tổng hợp cho một kết quả quét."""

    tieu_de_vi_pham: str
    link_vi_pham: str
    thoi_luong_hhmmss: str
    ngay_lap: str
    tong_giay_vi_pham: int
    ty_le_video: float
    muc: list = field(default_factory=list)


def dung_ho_so(kq: ScanResult, meta: dict | None = None) -> HoSo:
    """Dựng HoSo từ một ScanResult. Hàm thuần — không đọc/ghi file."""
    if meta is None:
        meta = {}

    cac_muc = []
    if kq.status == "ok":
        for m in kq.matches:
            thong_tin = meta.get(m.clip, {})
            cac_muc.append(MucViPham(
                ten_clip_goc=m.clip,
                tieu_de_goc=thong_tin.get("title", ""),
                link_goc=thong_tin.get("url", ""),
                tu_hhmmss=m.start_hhmmss,
                den_hhmmss=m.end_hhmmss,
                link_moc=Engine.link_moc(kq.source_id, kq.source_ref, m.start_s),
                do_dai_giay=round(m.matched_s),
                ty_le=m.ty_le,
                hashes=m.hashes,
            ))

    tong_giay_vi_pham = sum(muc.do_dai_giay for muc in cac_muc)
    ty_le_video = (
        round(100 * tong_giay_vi_pham / kq.duration_s, 1)
        if kq.duration_s > 0
        else 0.0
    )

    return HoSo(
        tieu_de_vi_pham=kq.source_name,
        link_vi_pham=kq.source_ref,
        thoi_luong_hhmmss=hhmmss(kq.duration_s),
        ngay_lap=datetime.now().strftime("%Y-%m-%d"),
        tong_giay_vi_pham=tong_giay_vi_pham,
        ty_le_video=ty_le_video,
        muc=cac_muc,
    )
