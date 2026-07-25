# -*- coding: utf-8 -*-
"""Test các thành phần lõi: tiện ích, quản lý kho, báo cáo, đồng bộ kênh."""
import os

import pytest
from conftest import M

from channel import ChannelSync, lam_sach_ten
from engine import Engine, ScanResult, hhmmss

# ---------------------------------------------------------------- tiện ích


@pytest.mark.parametrize("giay,mong_doi", [
    (0, "00:00:00"), (59, "00:00:59"), (60, "00:01:00"),
    (3600, "01:00:00"), (7605, "02:06:45"), (-5, "00:00:00"),
])
def test_hhmmss(giay, mong_doi):
    assert hhmmss(giay) == mong_doi


def test_link_moc_tu_id():
    assert Engine.link_moc("dQw4w9WgXcQ", "", 7605) == "https://youtu.be/dQw4w9WgXcQ?t=7605"


def test_link_moc_khi_khong_co_id():
    assert Engine.link_moc("", "https://www.youtube.com/watch?v=abc", 60).endswith("&t=60")
    assert Engine.link_moc("", "D:/video.mp4", 60) == ""


@pytest.mark.parametrize("vao,cam", [
    ("Video: tập 1/2 | phần <A>?", ':/<>|?"\\*'),
    ('Tiêu đề có "nháy" và \\ gạch', ':/<>|?"\\*'),
])
def test_lam_sach_ten_bo_ky_tu_windows_cam(vao, cam):
    ra = lam_sach_ten(vao)
    assert not any(c in ra for c in cam)


def test_lam_sach_ten_giu_dau_tieng_viet():
    assert "Hướng dẫn" in lam_sach_ten("Hướng dẫn làm bánh")


def test_lam_sach_ten_cat_ngan_va_khong_rong():
    assert len(lam_sach_ten("a" * 300)) <= 80
    assert lam_sach_ten("   ...   ") == "khong_ten"


# ---------------------------------------------------------------- quản lý kho


def test_tao_va_chuyen_kho(engine):
    engine.add_kho("Ẩm thực", "/tmp/a")
    engine.add_kho("Du lịch", "/tmp/b")
    assert {k["ten"] for k in engine.list_khos()} == {"Ẩm thực", "Du lịch"}
    engine.use_kho("Ẩm thực")
    assert engine.kho_dang_dung == "Ẩm thực"


def test_moi_kho_co_file_van_tay_rieng(engine):
    engine.add_kho("A")
    db_a = engine.db_file
    engine.add_kho("B")
    assert engine.db_file != db_a


def test_khong_cho_trung_ten_kho(engine):
    engine.add_kho("A")
    with pytest.raises(RuntimeError):
        engine.add_kho("A")


def test_ten_kho_rong_bi_tu_choi(engine):
    with pytest.raises(RuntimeError):
        engine.add_kho("   ")


def test_xoa_kho_khong_dung_toi_file_goc(engine, tmp_path):
    thu_muc = tmp_path / "clip"
    thu_muc.mkdir()
    (thu_muc / "video.mp4").write_text("noi dung goc")
    engine.add_kho("A", str(thu_muc))
    engine.delete_kho("A")
    assert (thu_muc / "video.mp4").exists(), "TUYỆT ĐỐI không được xoá file gốc của người dùng"


def test_xoa_an_toan_file_khong_ton_tai(engine):
    assert engine._xoa_an_toan("/tmp/khong_he_ton_tai_12345.pklz") is True


# ---------------------------------------------------------------- báo cáo


def test_so_cot_luon_khop_header(engine):
    """Lệch số cột là hỏng CSV và hỏng Google Sheets — phải khoá chặt."""
    ok = ScanResult(source_name="v", matches=[M("a.opus", 10, 9000)])
    rong = ScanResult(source_name="v")
    loi = ScanResult(source_name="v", status="error", note="hỏng")
    for r in engine.to_rows([ok, rong, loi]):
        assert len(r) == len(Engine.HEADER)


def test_xuat_csv_co_bom_utf8(engine):
    r = ScanResult(source_name="Tiếng Việt", matches=[M("a.opus", 10, 9000)])
    f = engine.export_csv([r])
    with open(f, "rb") as fh:
        assert fh.read(3) == b"\xef\xbb\xbf", "Thiếu BOM thì Excel hiện sai tiếng Việt"


def test_luu_va_doc_lai_lich_su(engine):
    r = ScanResult(source_name="v", source_id="ABC", matches=[M("a.opus", 10, 9000)])
    jid = engine.save_job(r, "file")
    assert engine.list_jobs()[0]["id"] == jid
    assert len(engine.job_matches(jid)) == 1
    engine.delete_job(jid)
    assert engine.job_matches(jid) == []


# ---------------------------------------------------------------- đồng bộ kênh


def _tao_kho_gia(d, ids):
    for i in ids:
        (d / f"20250101 - Video {i} [{i}].opus").write_text("x")


def test_quet_id_tu_ten_file(tmp_path):
    _tao_kho_gia(tmp_path, ["aaa111", "bbb222"])
    assert set(ChannelSync(str(tmp_path)).quet_id_tren_dia()) == {"aaa111", "bbb222"}


def test_sua_archive_dung_theo_thuc_te_tren_dia(tmp_path):
    """Tình huống thật: tải đứt giữa chừng, archive lệch với đĩa."""
    _tao_kho_gia(tmp_path, ["aaa111", "bbb222", "ccc333"])
    (tmp_path / "downloaded.txt").write_text("youtube aaa111\nyoutube zzz999\n")
    cs = ChannelSync(str(tmp_path))
    r = cs.sua_archive()
    assert r["tren_dia"] == 3
    assert "zzz999" in r["ma_bi_ghi_thua"]     # có trong archive mà mất file
    assert set(cs.done_ids()) == {"aaa111", "bbb222", "ccc333"}


def test_archive_dung_dinh_dang_yt_dlp(tmp_path):
    cs = ChannelSync(str(tmp_path))
    cs._mark_done("abc123")
    assert (tmp_path / "downloaded.txt").read_text().strip() == "youtube abc123"


def test_metadata_giu_nguyen_tieng_viet(tmp_path):
    cs = ChannelSync(str(tmp_path))
    cs.save_meta({"a.opus": {"title": "Hướng dẫn làm bánh chưng"}})
    assert cs.load_meta()["a.opus"]["title"] == "Hướng dẫn làm bánh chưng"
