# -*- coding: utf-8 -*-
"""Ngày đăng chính tắc — toàn bộ test chạy offline, không gọi mạng.

Hai fixture regression lấy từ raw metadata THẬT của yt-dlp 2026.07.04, giữ đúng
các trường dẫn tới quyết định chứ không phải chỉ ghi sẵn ngày kỳ vọng.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

import pytest

from publication_date import (
    MUI_GIO_MAC_DINH,
    PublicationDateResolver,
    format_publication_date,
    ngay_tu_epoch,
    resolve_publication_date,
)

VN = "Asia/Ho_Chi_Minh"

# Raw metadata thật, rút gọn còn các trường thời gian.
# https://www.youtube.com/watch?v=Asv1kjFuX-4 — UTC 2026-07-31 20:00:34
META_ASV = {
    "id": "Asv1kjFuX-4",
    "title": '*4 HOURS 09 MINUTES* OF "BEST" CORYXKENSHIN VIDEOS TO FALL ASLEEP TO!',
    "upload_date": "20260731",
    "timestamp": 1785528034,
    "release_timestamp": None,
    "release_year": None,
    "live_status": "not_live",
    "was_live": False,
    "availability": "public",
}

# https://youtu.be/T_mKh8IUpWw — UTC 2025-06-20 18:45:39
META_TMK = {
    "id": "T_mKh8IUpWw",
    "title": "AMANDA CALLED ME OUT [Amanda The Adventurer 3]",
    "upload_date": "20250620",
    "timestamp": 1750445139,
    "release_timestamp": None,
    "release_year": None,
    "live_status": "not_live",
    "was_live": False,
    "availability": "public",
}


# ---------------------------------------------------------------------------
# Regression cho hai video người dùng đã kiểm chứng
# ---------------------------------------------------------------------------

def test_regression_asv1kjfux4_ra_dung_01_08_2026():
    kq = resolve_publication_date(META_ASV, VN)

    assert kq.date == date(2026, 8, 1)
    assert format_publication_date(kq) == "01/08/2026"
    assert kq.source_field == "timestamp"
    assert kq.confidence == "high"
    assert "khac_upload_date" in kq.warnings, "Phải ghi nhận lệch so với upload_date"
    # upload_date thô đúng theo lịch UTC nhưng không phải ngày người dùng thấy.
    assert META_ASV["upload_date"] == "20260731"


def test_regression_t_mkh8iupww_ra_dung_21_06_2025():
    kq = resolve_publication_date(META_TMK, VN)

    assert kq.date == date(2025, 6, 21)
    assert format_publication_date(kq) == "21/06/2025"
    assert kq.source_field == "timestamp"
    assert kq.confidence == "high"
    assert "khac_upload_date" in kq.warnings
    assert META_TMK["upload_date"] == "20250620"


def test_hai_video_mau_lech_dung_mot_ngay_khong_phai_hai():
    """Offset +7 giờ không thể tạo sai lệch 2 ngày. Chốt lại tính chất này."""
    for meta in (META_ASV, META_TMK):
        canonical = resolve_publication_date(meta, VN).date
        from publication_date import ngay_tu_chuoi
        upload = ngay_tu_chuoi(meta["upload_date"])
        assert (canonical - upload).days == 1


# ---------------------------------------------------------------------------
# Ma trận ngữ nghĩa
# ---------------------------------------------------------------------------

def test_case1_upload_thong_thuong_chi_co_upload_date():
    kq = resolve_publication_date({"upload_date": "20240115"}, VN)

    assert kq.date == date(2024, 1, 15)
    assert kq.source_field == "upload_date"
    assert kq.confidence == "medium"
    assert "khong_co_gio_de_quy_doi_mui_gio" in kq.warnings


def test_case2_premiere_release_timestamp_thang_upload_date():
    """Video đăng riêng tư trước, công khai sau: release mới là ngày phát hành."""
    kq = resolve_publication_date({
        "upload_date": "20240110",
        "timestamp": 1704844800,                 # 2024-01-10 00:00:00 UTC
        "release_timestamp": 1705320000,         # 2024-01-15 12:00:00 UTC
        "live_status": "was_live",
    }, VN)

    assert kq.date == date(2024, 1, 15)
    assert kq.source_field == "release_timestamp"
    assert kq.confidence == "high"
    assert "khac_upload_date" in kq.warnings


def test_case3_release_date_dung_khi_khong_co_epoch():
    kq = resolve_publication_date({
        "upload_date": "20240110",
        "release_date": "20240115",
    }, VN)

    assert kq.date == date(2024, 1, 15)
    assert kq.source_field == "release_date"
    assert "khac_upload_date" in kq.warnings


@pytest.mark.parametrize(
    "epoch, ngay_utc, ngay_vn",
    [
        (1750445139, date(2025, 6, 20), date(2025, 6, 21)),   # 18:45 UTC
        (1719792000, date(2024, 7, 1), date(2024, 7, 1)),     # 00:00 UTC
        (1719849599, date(2024, 7, 1), date(2024, 7, 1)),     # 15:59:59 UTC
        (1719853200, date(2024, 7, 1), date(2024, 7, 2)),     # 17:00:00 UTC — mốc
        (1719853199, date(2024, 7, 1), date(2024, 7, 1)),     # 16:59:59 UTC
    ],
)
def test_case4_ranh_gioi_utc_va_gio_viet_nam(epoch, ngay_utc, ngay_vn):
    """17:00 UTC là đúng 00:00 giờ VN: từ mốc đó trở đi ngày VN nhảy sang hôm sau."""
    assert ngay_tu_epoch(epoch, "UTC") == ngay_utc
    assert ngay_tu_epoch(epoch, VN) == ngay_vn


def test_case5_cung_ngay_thi_khong_canh_bao_thua():
    kq = resolve_publication_date({
        "upload_date": "20240701",
        "timestamp": 1719792000,                 # 2024-07-01 00:00 UTC -> 07:00 VN
    }, VN)

    assert kq.date == date(2024, 7, 1)
    assert kq.source_field == "timestamp"
    assert "khac_upload_date" not in kq.warnings
    assert kq.can_review is False


def test_case6_metadata_legacy_chi_co_upload_date_van_doc_duoc():
    kq = resolve_publication_date({
        "id": "abc12345678",
        "title": "Clip cũ",
        "url": "https://youtu.be/abc12345678",
        "upload_date": "20230414",
        "duration": 431.0,
    }, VN)

    assert kq.date == date(2023, 4, 14)
    assert kq.source_field == "upload_date"


def test_case7_fallback_ten_file_co_do_tin_cay_thap():
    kq = resolve_publication_date({"filename_date": "20240115"}, VN)

    assert kq.date == date(2024, 1, 15)
    assert kq.source_field == "filename"
    assert kq.confidence == "low"
    assert "suy_tu_ten_file" in kq.warnings


def test_case7b_metadata_chinh_thuc_thang_ten_file():
    """Có metadata chính thức thì tuyệt đối không lấy ngày từ tên file."""
    kq = resolve_publication_date({
        "timestamp": 1750445139,
        "filename_date": "20200101",
    }, VN)

    assert kq.date == date(2025, 6, 21)
    assert kq.source_field == "timestamp"


@pytest.mark.parametrize("xau", ["20251340", "2025-06-21", "", "00000000", "abcdefgh", None, 20250621])
def test_case8_ngay_khong_hop_le_khong_crash_va_khong_bia(xau):
    kq = resolve_publication_date({"upload_date": xau}, VN)

    assert kq.date is None
    assert kq.source_field is None
    assert kq.confidence == "none"


def test_case9_thieu_ngay_tra_none_kem_canh_bao():
    kq = resolve_publication_date({"id": "x", "title": "y"}, VN)

    assert kq.date is None
    assert "khong_co_du_lieu_ngay" in kq.warnings
    assert format_publication_date(kq) == ""


def test_case10_epoch_mili_giay_bi_tu_choi_ro_rang():
    """Không âm thầm chia 1000: hiểu sai đơn vị còn tệ hơn bỏ qua."""
    kq = resolve_publication_date({
        "timestamp": 1750445139000,
        "upload_date": "20250620",
    }, VN)

    assert kq.source_field == "upload_date"
    assert kq.date == date(2025, 6, 20)
    assert any("mili_giay" in w for w in kq.warnings)


def test_case10b_epoch_vo_ly_bi_tu_choi():
    kq = resolve_publication_date({"timestamp": 99, "upload_date": "20250620"}, VN)

    assert kq.source_field == "upload_date"
    assert any("ngoai_khoang" in w for w in kq.warnings)


def test_case11_epoch_am_hoac_bool_khong_duoc_coi_la_ngay():
    for xau in (0, -1, True, False, "1750445139", None):
        kq = resolve_publication_date({"timestamp": xau}, VN)
        assert kq.date is None, f"{xau!r} không được coi là epoch"


def test_case12_ket_qua_khong_phu_thuoc_mui_gio_cua_may(monkeypatch):
    """Chạy lại trong tiến trình con với TZ khác; kết quả canonical phải y hệt."""
    kich_ban = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from publication_date import resolve_publication_date\n"
        "kq = resolve_publication_date({'timestamp': 1750445139}, 'Asia/Ho_Chi_Minh')\n"
        "print(kq.yyyymmdd)\n"
    ) % str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    ket = []
    for tz in ("UTC", "America/Los_Angeles", "Asia/Tokyo", "Pacific/Kiritimati"):
        env = dict(os.environ)
        env["TZ"] = tz
        r = subprocess.run(
            [sys.executable, "-c", kich_ban],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
        )
        assert r.returncode == 0, r.stderr[-400:]
        ket.append(r.stdout.strip())

    assert ket == ["20250621"] * 4, ket


# ---------------------------------------------------------------------------
# Định dạng
# ---------------------------------------------------------------------------

def test_format_nhan_moi_kieu_dau_vao():
    assert format_publication_date(date(2025, 6, 21)) == "21/06/2025"
    assert format_publication_date("20250621") == "21/06/2025"
    assert format_publication_date(resolve_publication_date(META_TMK, VN)) == "21/06/2025"
    assert format_publication_date("00000000") == ""
    assert format_publication_date(None) == ""
    assert format_publication_date("linh tinh") == ""


def test_mui_gio_mac_dinh_la_viet_nam():
    assert MUI_GIO_MAC_DINH == "Asia/Ho_Chi_Minh"
    assert PublicationDateResolver().display_timezone == MUI_GIO_MAC_DINH


def test_mui_gio_khong_ton_tai_thi_lui_ve_utc_chu_khong_crash():
    kq = PublicationDateResolver("Khong/Ton_Tai").resolve({"timestamp": 1750445139})

    assert kq.date == date(2025, 6, 20)
    assert kq.source_field == "timestamp"
