# -*- coding: utf-8 -*-
"""Nguồn metadata chuẩn và định danh clip (audit TCP-09, TCP-12).

TCP-09 — chính sách: ``clips_meta.json`` trong thư mục kho là NGUỒN CHUẨN (đồng bộ kênh
và các công cụ sửa ngày/thời lượng đều ghi vào đó). Snapshot ``data/metadata`` chỉ bù
trường còn thiếu và thay thế khi thư mục kho không truy cập được. Bản cũ ưu tiên
snapshot, nên một lần sửa đã ghi thành công vào ``clips_meta.json`` không bao giờ tới
được báo cáo — kể cả khi làm mới snapshot, vì lượt làm mới lại đọc qua resolver ưu
tiên snapshot cũ.

TCP-12 — mã video chỉ lấy theo NGỮ PHÁP TÊN FILE của bộ tải
(``<ngày> - <tiêu đề> [<ID>].<đuôi>``): ngoặc vuông 11 ký tự nằm trong tiêu đề hay
trong tên thư mục không phải là mã video. Mâu thuẫn định danh THẬT vẫn là ambiguous.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pytest

import kiem_ngay_dang
from bang_ngang import HEADER_NGANG
from clip_metadata import ClipMetadataResolver, extract_youtube_id, source_from_mapping
from engine import Engine, Match, ScanResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VID = "abcdefghijk"
TEN = f"20260101 - SML Movie_ Jeffy [{VID}].opus"


def _meta(video_id=VID, title="SML Movie: Jeffy", upload_date="20260101", **them) -> dict:
    return {"id": video_id, "title": title, "url": f"https://youtu.be/{video_id}",
            "upload_date": upload_date, **them}


def _ghi(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _eng(tmp_path, monkeypatch, thu_muc: Path, clips: list) -> Engine:
    data = tmp_path / "data"
    _ghi(data / "khos.json", {"dang_dung": "SML", "danh_sach": [
        {"ten": "SML", "thu_muc": str(thu_muc), "db": "kho_sml.pklz"}]})
    e = Engine(root=str(PROJECT_ROOT), data_dir=str(data), out_dir=str(tmp_path / "out"))
    monkeypatch.setattr(e, "db_clips", lambda bo_cache=False: [dict(c) for c in clips])
    # Chỉ để thoả điều kiện "file kho tồn tại" của lượt làm mới snapshot; db_clips đã giả.
    Path(e.db_file).write_bytes(b"marker-test-khong-phai-kho-van-tay")
    return e


def _hang_ngang(e: Engine, clip: str) -> dict:
    kq = ScanResult(source_name="Video vi phạm", source_ref="https://youtu.be/XXXXXXXXXXX",
                    source_id="XXXXXXXXXXX", duration_s=3600.0, matches=[Match(
                        clip=clip, start_s=60.0, end_s=180.0, matched_s=120.0,
                        clip_offset_s=0.0, hashes=9000, confidence="Rất chắc chắn")])
    return dict(zip(HEADER_NGANG, e.to_rows_ngang([kq])[0]))


# ---------------------------------------------------------------------------
#  TCP-09 — sửa ở clips_meta.json phải tới được báo cáo
# ---------------------------------------------------------------------------

def test_sua_ngay_dang_bang_cong_cu_that_toi_duoc_bao_cao_du_co_snapshot_cu(
        tmp_path, monkeypatch, capsys):
    kho = tmp_path / "Kho SML"
    # yt-dlp ghi `upload_date` theo UTC: 20:00 UTC ngày 01/01 là 03:00 ngày 02/01 ở VN.
    ts = int(datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc).timestamp())
    _ghi(kho / "clips_meta.json", {TEN: _meta(timestamp=ts, duration=125.0)})
    e = _eng(tmp_path, monkeypatch, kho, [{"ten": TEN, "duong_dan": str(kho / TEN)}])
    assert e.khoi_phuc_metadata_offline(dry_run=False).errors == ()
    assert _hang_ngang(e, TEN)["Ngày đăng video gốc 1"] == "01/01/2026"

    sua = kiem_ngay_dang.repair(str(kho), "Asia/Ho_Chi_Minh", dung_mang=False,
                                apply=True, gioi_han=0)
    assert sua["da_doi"] == 1

    hang = _hang_ngang(e, TEN)          # không ép xoá cache: chữ ký file phải đủ
    assert hang["Ngày đăng video gốc 1"] == "02/01/2026", \
        "bản sửa đã ghi vào clips_meta.json phải tới được báo cáo"
    assert any("lệch" in cb and "clips_meta.json" in cb for cb in e.canh_bao_metadata), \
        e.canh_bao_metadata


def test_lam_moi_snapshot_sau_khi_sua_thi_snapshot_hoi_tu_ve_nguon_chuan(
        tmp_path, monkeypatch):
    kho = tmp_path / "Kho SML"
    _ghi(kho / "clips_meta.json", {TEN: _meta(title="Tiêu đề cũ", duration=125.0)})
    e = _eng(tmp_path, monkeypatch, kho, [{"ten": TEN, "duong_dan": str(kho / TEN)}])
    e.khoi_phuc_metadata_offline(dry_run=False)
    _ghi(kho / "clips_meta.json", {TEN: _meta(title="Tiêu đề đã sửa", duration=125.0)})

    lam_moi = e.khoi_phuc_metadata_offline(dry_run=False)

    assert lam_moi.errors == () and lam_moi.updated == 1
    snap = json.loads(Path(e._metadata_snapshot_path()).read_text(encoding="utf-8"))
    assert snap["clips"][TEN]["title"] == "Tiêu đề đã sửa"
    assert _hang_ngang(e, TEN)["Tên video gốc 1"] == "Tiêu đề đã sửa"
    assert not any("lệch" in cb for cb in e.canh_bao_metadata)


def test_thu_muc_kho_offline_thi_van_dung_snapshot(tmp_path, monkeypatch):
    kho = tmp_path / "Kho SML"
    _ghi(kho / "clips_meta.json", {TEN: _meta(duration=125.0)})
    e = _eng(tmp_path, monkeypatch, kho, [{"ten": TEN, "duong_dan": str(kho / TEN)}])
    e.khoi_phuc_metadata_offline(dry_run=False)
    (kho / "clips_meta.json").rename(kho / "da_di_vang.json")   # ổ mạng/USB rút ra

    r = e.clip_metadata_resolver().resolve(TEN)

    assert r.status == "complete" and r.source_kind == "snapshot"
    assert r.title == "SML Movie: Jeffy" and r.upload_date == "20260101"


def test_nguon_chuan_thieu_truong_thi_snapshot_bu_vao(tmp_path, monkeypatch):
    kho = tmp_path / "Kho SML"
    e = _eng(tmp_path, monkeypatch, kho, [{"ten": TEN, "duong_dan": str(kho / TEN)}])
    _ghi(Path(e._metadata_snapshot_path()), {
        "schema_version": 1, "warehouse": "SML",
        "clips": {TEN: {**_meta(duration=125.0), "resolution_method": "video_id"}}})
    _ghi(kho / "clips_meta.json", {TEN: _meta(title="Tiêu đề mới")})   # chưa có duration

    r = e.clip_metadata_resolver().resolve(TEN)

    assert r.title == "Tiêu đề mới"
    assert r.duration == pytest.approx(125.0)
    assert r.status == "complete"


def test_mau_thuan_dinh_danh_that_giua_hai_nguon_van_ambiguous(tmp_path, monkeypatch):
    kho = tmp_path / "Kho SML"
    e = _eng(tmp_path, monkeypatch, kho, [{"ten": TEN, "duong_dan": str(kho / TEN)}])
    _ghi(Path(e._metadata_snapshot_path()), {
        "schema_version": 1, "warehouse": "SML",
        "clips": {TEN: {**_meta(video_id="BBBBBBBBBBB"), "resolution_method": "exact"}}})
    _ghi(kho / "clips_meta.json", {TEN: _meta()})

    r = e.clip_metadata_resolver().resolve(TEN)

    assert r.status == "ambiguous" and r.url == ""


def test_hai_muc_khac_khoa_cung_ma_video_khac_noi_dung_van_ambiguous():
    nguon = source_from_mapping({
        f"20260101 - Bản A [{VID}].opus": _meta(title="A"),
        f"20260101 - Bản B [{VID}].opus": _meta(title="B"),
    }, kind="live", priority=0)

    r = ClipMetadataResolver([nguon]).resolve(f"00000000 - Tên khác [{VID}].opus")

    assert r.status == "ambiguous"


# ---------------------------------------------------------------------------
#  TCP-12 — mã video theo ngữ pháp tên file của bộ tải
# ---------------------------------------------------------------------------

TEN_NGOAC = f"20260101 - Title [HELLOWORLD1] [{VID}].opus"


def test_ngoac_vuong_11_ky_tu_trong_tieu_de_khong_pha_dinh_danh():
    nguon = source_from_mapping({TEN_NGOAC: _meta(title="Title [HELLOWORLD1]",
                                                  duration=60.0)}, kind="live")

    r = ClipMetadataResolver([nguon]).resolve(TEN_NGOAC)

    assert r.status == "complete", r.warnings
    assert r.video_id == VID and r.url == f"https://youtu.be/{VID}"
    assert extract_youtube_id(TEN_NGOAC) == VID


def test_ngoac_vuong_trong_ten_thu_muc_khong_phai_ma_video():
    nguon = source_from_mapping({TEN: _meta(duration=60.0)}, kind="live")
    duong_dan = rf"D:\Kho\[SML-Channel]\audio\{TEN}"

    r = ClipMetadataResolver([nguon], windows_semantics=True).resolve(TEN, duong_dan)

    assert r.status == "complete" and r.video_id == VID


def test_metadata_nhan_ma_trong_tieu_de_la_ma_video_thi_van_ambiguous():
    """Đối chứng âm: hậu tố tên file nói ``abcdefghijk`` mà metadata nói mã khác."""
    nguon = source_from_mapping({TEN_NGOAC: _meta(video_id="HELLOWORLD1")}, kind="live")

    r = ClipMetadataResolver([nguon]).resolve(TEN_NGOAC)

    assert r.status == "ambiguous" and r.url == ""


def test_ten_va_duong_dan_mang_hai_ma_khac_nhau_van_ambiguous():
    nguon = source_from_mapping({TEN: _meta()}, kind="live")
    r = ClipMetadataResolver([nguon]).resolve(
        TEN, r"D:\Kho\20260101 - SML Movie_ Jeffy [BBBBBBBBBBB].opus")
    assert r.status == "ambiguous"


@pytest.mark.parametrize("bien_the", [
    lambda s: unicodedata.normalize("NFD", s),                 # macOS/HFS+ hay ghi NFD
    lambda s: s[:-5] + ".OPUS",                                # hoa/thường theo Windows
    lambda s: s + " .",                                        # Windows tự cắt " ."
])
def test_ten_tuong_duong_tren_windows_van_ra_dung_clip(bien_the):
    goc = f"20260101 - Café Don't  Stop [{VID}].opus"         # nháy đơn, hai dấu cách
    nguon = source_from_mapping({goc: _meta(title="Café Don't  Stop", duration=60.0)},
                                kind="live")

    r = ClipMetadataResolver([nguon], windows_semantics=True).resolve(bien_the(goc))

    assert r.status == "complete" and r.video_id == VID
    assert r.title == "Café Don't  Stop"
