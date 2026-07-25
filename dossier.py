# -*- coding: utf-8 -*-
"""Mô hình dữ liệu và hàm dựng hồ sơ vi phạm."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import engine


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


def dung_ho_so(kq: engine.ScanResult, meta: dict | None = None) -> HoSo:
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
                link_moc=engine.Engine.link_moc(
                    kq.source_id, kq.source_ref, m.start_s
                ),
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
        thoi_luong_hhmmss=engine.hhmmss(kq.duration_s),
        ngay_lap=datetime.now().strftime("%Y-%m-%d"),
        tong_giay_vi_pham=tong_giay_vi_pham,
        ty_le_video=ty_le_video,
        muc=cac_muc,
    )


def render_markdown(ho_so: HoSo) -> str:
    """Trả về nội dung Markdown hoàn chỉnh của hồ sơ. Không ghi file."""
    def hien_thi(gia_tri: str) -> str:
        return gia_tri if gia_tri and gia_tri.strip() else "—"

    cac_dong = [
        "# Hồ sơ khiếu nại bản quyền",
        "",
        "## Thông tin chung",
        f"- **Tiêu đề video vi phạm:** {ho_so.tieu_de_vi_pham}",
        f"- **Link video vi phạm:** {ho_so.link_vi_pham}",
        f"- **Thời lượng:** {ho_so.thoi_luong_hhmmss}",
        f"- **Ngày lập:** {ho_so.ngay_lap}",
        f"- **Tổng số đoạn vi phạm:** {len(ho_so.muc)}",
        f"- **Tổng thời gian vi phạm:** {engine.hhmmss(ho_so.tong_giay_vi_pham)}",
        f"- **Tỷ lệ video bị chiếm:** {ho_so.ty_le_video}%",
        "",
    ]

    if not ho_so.muc:
        cac_dong.append("*Không phát hiện đoạn vi phạm nào.*")
        return "\n".join(cac_dong)

    for so_thu_tu, muc in enumerate(ho_so.muc, start=1):
        cac_dong.extend([
            f"## Đoạn {so_thu_tu}",
            f"- **Khoảng thời gian:** {hien_thi(muc.tu_hhmmss)} – "
            f"{hien_thi(muc.den_hhmmss)}",
            f"- **Link nhảy tới mốc:** {hien_thi(muc.link_moc)}",
            f"- **Tên clip gốc:** {hien_thi(muc.ten_clip_goc)}",
            f"- **Tiêu đề video gốc:** {hien_thi(muc.tieu_de_goc)}",
            f"- **Link video gốc:** {hien_thi(muc.link_goc)}",
            f"- **Độ dài đoạn:** {muc.do_dai_giay} giây",
            f"- **Tỷ lệ khớp:** {muc.ty_le}%",
            f"- **Số hash:** {muc.hashes}",
            "",
        ])

    cac_dong.append(
        "*Ghi chú: Bằng chứng được sinh tự động bằng đối chiếu vân tay âm thanh.*"
    )
    return "\n".join(cac_dong)
