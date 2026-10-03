# -*- coding: utf-8 -*-
"""Mọi exporter phải cho ra CÙNG một ngày đăng, và không tự parse ngày riêng."""

from __future__ import annotations

import re
from pathlib import Path

import bang_ngang
import engine as engine_module
from engine import Match, ScanResult
from publication_date import format_publication_date, resolve_publication_date

REPO = Path(__file__).resolve().parents[1]
VN = "Asia/Ho_Chi_Minh"

# Raw metadata thật của https://youtu.be/T_mKh8IUpWw (UTC 2025-06-20 18:45:39).
META_VI_PHAM = {"id": "T_mKh8IUpWw", "upload_date": "20250620", "timestamp": 1750445139}
# Video gốc phát hành 2026-07-31 20:00:34 UTC -> 01/08/2026 giờ VN.
META_GOC = {"id": "Asv1kjFuX-4", "upload_date": "20260731", "timestamp": 1785528034}


def _kho_gia(tmp_path):
    folder = tmp_path / "kho"
    folder.mkdir()
    ten = "20260801 - Clip gốc [Asv1kjFuX-4].opus"
    (folder / ten).write_bytes(b"opus")
    ngay_goc = resolve_publication_date(META_GOC, VN)
    (folder / "clips_meta.json").write_text(
        __import__("json").dumps({ten: {
            "id": "Asv1kjFuX-4",
            "title": "Clip gốc",
            "url": "https://youtu.be/Asv1kjFuX-4",
            "publication_date": ngay_goc.yyyymmdd,
            "publication_date_source": ngay_goc.source_field,
            "upload_date": "20260731",
            "duration": 600.0,
        }}, ensure_ascii=False),
        encoding="utf-8",
    )
    return folder, ten


def test_publication_date_is_identical_across_exporters(engine, tmp_path, monkeypatch):
    folder, ten_clip = _kho_gia(tmp_path)
    engine.kho_dang_dung = "KhoTest"
    engine.kho_thu_muc = str(folder)
    engine._metadata_cache_key = None
    engine._metadata_resolver_cache = None
    monkeypatch.setattr(
        engine, "db_clips",
        lambda bo_cache=False: [
            {"ten": ten_clip, "duong_dan": str(folder / ten_clip), "so_hash": 100}
        ],
    )

    ngay_vi_pham = resolve_publication_date(META_VI_PHAM, VN)
    kq = ScanResult(
        source_name="Video vi phạm",
        source_ref="https://youtu.be/T_mKh8IUpWw",
        source_id="T_mKh8IUpWw",
        duration_s=3600.0,
        matches=[Match(clip=ten_clip, start_s=10.0, end_s=310.0, matched_s=300.0,
                       clip_offset_s=0.0, hashes=500, confidence="cao", ty_le=40.0)],
        upload_date=ngay_vi_pham.yyyymmdd,
        so_dat_nguong=1,
    )

    resolver = engine.clip_metadata_resolver(bo_cache=True)
    header = bang_ngang.HEADER_NGANG

    dong = bang_ngang.dung_dong_ngang(kq, resolver=resolver)
    dong_sheets = engine.to_rows_ngang([kq])[0]          # Google Sheets dùng đúng hàm này

    ngay_vi_pham_mong_doi = "21/06/2025"
    ngay_goc_mong_doi = "01/08/2026"

    assert dong[header.index("Ngày đăng video vi phạm")] == ngay_vi_pham_mong_doi
    assert dong[header.index("Ngày đăng video gốc 1")] == ngay_goc_mong_doi

    # CSV ngang và Sheets là cùng một dòng dữ liệu -> không thể lệch nhau.
    assert dong_sheets[header.index("Ngày đăng video vi phạm")] == ngay_vi_pham_mong_doi
    assert dong_sheets[header.index("Ngày đăng video gốc 1")] == ngay_goc_mong_doi

    # Và đều bằng đúng kết quả của hàm format dùng chung.
    assert format_publication_date(kq.upload_date) == ngay_vi_pham_mong_doi
    assert format_publication_date(resolver.resolve(ten_clip).upload_date) == ngay_goc_mong_doi


def test_khong_module_nao_tu_dinh_dang_ngay_rieng():
    """Chỉ publication_date.py được phép chứa format DD/MM/YYYY."""
    mau = re.compile(r"%d/%m/%Y")
    pham_loi = []
    for path in REPO.glob("*.py"):
        if path.name == "publication_date.py":
            continue
        if mau.search(path.read_text(encoding="utf-8")):
            pham_loi.append(path.name)
    assert not pham_loi, (
        f"Các module sau tự định dạng ngày thay vì dùng "
        f"publication_date.format_publication_date: {pham_loi}"
    )


# Dùng epoch cho việc KHÁC ngày đăng thì được phép; liệt kê tường minh để mỗi
# lần thêm mới đều phải cân nhắc chứ không lọt âm thầm.
CHO_PHEP_EPOCH = {
    # app.py: hiển thị đồng hồ của màn hình tiến độ ("Cập nhật gần nhất HH:MM:SS").
    # Đây là giờ treo tường của máy đang chạy, đúng ngữ nghĩa, không phải ngày đăng.
    "app.py",
    # truy_cap_youtube.py: thời điểm SỬA FILE cookie trên máy này (chẩn đoán cookie cũ hay
    # mới) — giờ treo tường của máy, không phải ngày đăng video.
    "truy_cap_youtube.py",
}
CHO_PHEP_TIMEDELTA_DAYS = {
    # nhat_ky.py: cửa sổ giữ log N ngày, không liên quan ngày đăng video.
    "nhat_ky.py",
}


def test_khong_module_nao_tu_doi_epoch_sang_ngay_dang():
    """fromtimestamp/utcfromtimestamp chỉ publication_date.py được dùng cho ngày đăng."""
    mau = re.compile(r"\b(utc)?fromtimestamp\s*\(")
    pham_loi = [
        p.name for p in REPO.glob("*.py")
        if p.name != "publication_date.py"
        and p.name not in CHO_PHEP_EPOCH
        and mau.search(p.read_text(encoding="utf-8"))
    ]
    assert not pham_loi, (
        f"Các module sau tự quy đổi epoch, dễ lệch múi giờ: {pham_loi}"
    )


def test_khong_co_hotfix_cong_tru_ngay_dang():
    """Không được có timedelta(days=...) để 'sửa' ngày đăng ở bất kỳ đâu."""
    mau = re.compile(r"timedelta\s*\(\s*days\s*=")
    pham_loi = [
        p.name for p in REPO.glob("*.py")
        if p.name not in CHO_PHEP_TIMEDELTA_DAYS
        and mau.search(p.read_text(encoding="utf-8"))
    ]
    assert not pham_loi, f"Phát hiện cộng/trừ ngày thủ công: {pham_loi}"


def test_exporter_khong_goi_mang_khi_dinh_dang(monkeypatch):
    """Sau khi metadata đã normalize, exporter không được hỏi lại YouTube."""
    import yt_dlp

    def cam(*args, **kwargs):
        raise AssertionError("Exporter không được gọi mạng")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", cam)
    monkeypatch.setattr(engine_module.Engine, "youtube_info", cam)

    kq = ScanResult(
        source_name="X", source_ref="https://youtu.be/T_mKh8IUpWw",
        source_id="T_mKh8IUpWw", duration_s=60.0, matches=[],
        upload_date="20250621", so_dat_nguong=0,
    )
    dong = bang_ngang.dung_dong_ngang(kq)
    assert dong[bang_ngang.HEADER_NGANG.index("Ngày đăng video vi phạm")] == "21/06/2025"
