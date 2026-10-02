# -*- coding: utf-8 -*-
"""Các writer của ``clips_meta.json``/``khos.json`` không được làm mất cập nhật của
nhau (audit TCP-03, mức người dùng thật: đồng bộ kênh, vá metadata, sửa ngày đăng,
sửa thời lượng, thiết lập máy phụ, sổ đăng ký kho).

Mỗi test cho một writer khác chen vào GIỮA lúc writer đang làm việc (sau khi nó đã
đọc dữ liệu) rồi kiểm cả hai thay đổi đều còn.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import channel
from channel import ChannelSync, VideoInfo


def _doc(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _chen_ngoai(path, ten, entry):
    """Một process khác ghi thêm entry (mô phỏng bằng đúng API giao dịch)."""
    from luu_tru import cap_nhat_json
    cap_nhat_json(str(path), lambda d: d.__setitem__(ten, entry), mac_dinh={})


def test_sync_khong_xoa_entry_do_writer_khac_them_giua_chung(tmp_path):
    kho = tmp_path / "kho"
    cs = ChannelSync(str(kho))
    meta_path = kho / "clips_meta.json"
    meta_path.write_text(json.dumps({"cu.opus": {"id": "aaaaaaaaaaa"}}), encoding="utf-8")
    v = VideoInfo("bbbbbbbbbbb", "Video moi", "20260101", 100.0,
                  "https://youtu.be/bbbbbbbbbbb")
    cs.list_channel = lambda *a, **k: [v]

    def tai_va_nen(video):
        # Trong lúc sync đang tải, kiem_ngay_dang/va_metadata ở process khác ghi vào.
        _chen_ngoai(meta_path, "ngoai.opus", {"id": "ccccccccccc"})
        dich = kho / cs._ten_file(video)
        dich.write_bytes(b"x" * 4096)
        return str(dich), video

    cs._tai_va_nen = tai_va_nen
    with patch.object(channel, "do_dai_media", lambda p: 100.0):
        kq = cs.sync(v.url)

    assert kq["moi"] == 1
    meta = _doc(meta_path)
    assert "ngoai.opus" in meta, "sync ghi đè mất entry của writer khác"
    assert "cu.opus" in meta
    assert any(e.get("id") == "bbbbbbbbbbb" for e in meta.values())


def test_va_metadata_chi_gop_truong_minh_doi(tmp_path):
    kho = tmp_path / "kho"
    cs = ChannelSync(str(kho))
    meta_path = kho / "clips_meta.json"
    meta_path.write_text(json.dumps({
        "20260101 - A [aaaaaaaaaaa].opus": {"id": "aaaaaaaaaaa", "title": "A",
                                            "upload_date": "", "duration": None},
    }), encoding="utf-8")

    def fetcher(video_id):
        _chen_ngoai(meta_path, "ngoai.opus", {"id": "ccccccccccc", "title": "Ngoai"})
        return {"upload_date": "20260102", "duration": 99.0, "title": "A"}

    kq = cs.va_metadata(fetcher=fetcher)

    assert kq["da_va"] == 1
    meta = _doc(meta_path)
    assert meta["ngoai.opus"]["title"] == "Ngoai"
    assert meta["20260101 - A [aaaaaaaaaaa].opus"]["upload_date"] == "20260102"


def test_kiem_ngay_dang_apply_khong_xoa_entry_moi(tmp_path):
    import kiem_ngay_dang

    kho = tmp_path / "kho"
    kho.mkdir()
    meta_path = kho / "clips_meta.json"
    meta_path.write_text(json.dumps({
        "a.opus": {"id": "aaaaaaaaaaa", "upload_date": "20260101",
                   "timestamp": 1767312000},
    }), encoding="utf-8")

    goc_resolve = kiem_ngay_dang.resolve_publication_date

    def resolve_va_chen(*a, **k):
        _chen_ngoai(meta_path, "ngoai.opus", {"id": "ccccccccccc"})
        return goc_resolve(*a, **k)

    with patch.object(kiem_ngay_dang, "resolve_publication_date", resolve_va_chen):
        kiem_ngay_dang.repair(str(kho), "Asia/Ho_Chi_Minh", dung_mang=False,
                              apply=True, gioi_han=0)

    meta = _doc(meta_path)
    assert "ngoai.opus" in meta
    assert meta["a.opus"].get("publication_date")


def test_kiem_thoi_luong_sua_that_khong_xoa_entry_moi(tmp_path):
    import kiem_thoi_luong

    kho = tmp_path / "kho"
    kho.mkdir()
    (kho / "a.opus").write_bytes(b"x")
    meta_path = kho / "clips_meta.json"
    meta_path.write_text(json.dumps({"a.opus": {"id": "aaaaaaaaaaa", "duration": 10}}),
                         encoding="utf-8")

    def do_va_chen(path):
        _chen_ngoai(meta_path, "ngoai.opus", {"id": "ccccccccccc"})
        return 9.5

    with patch.object(kiem_thoi_luong, "do_dai_media", do_va_chen):
        kiem_thoi_luong.kiem_mot_kho("A", str(kho), sua=True, that_su=True, gioi_han=0)

    meta = _doc(meta_path)
    assert "ngoai.opus" in meta
    assert meta["a.opus"]["duration_media"] == 9.5


def test_thiet_lap_may_phu_khong_xoa_kho_them_giua_chung(tmp_path):
    import thiet_lap_may_phu

    goc = tmp_path / "may_phu"
    (goc / "data").mkdir(parents=True)
    (goc / "kho_meta" / "A").mkdir(parents=True)
    khos = goc / "data" / "khos.json"
    khos.write_text(json.dumps({"dang_dung": "A", "danh_sach": [
        {"ten": "A", "thu_muc": "", "db": "kho_a.pklz"}]}), encoding="utf-8")

    goc_isdir = os.path.isdir

    def isdir_va_chen(p):
        if str(p).endswith(os.path.join("kho_meta", "A")):
            _chen_ngoai(khos, "ghi_chu", "writer khac")
        return goc_isdir(p)

    with patch.object(thiet_lap_may_phu.os.path, "isdir", isdir_va_chen):
        thiet_lap_may_phu.sua_duong_dan_kho(str(goc))

    d = _doc(khos)
    assert d.get("ghi_chu") == "writer khac"
    assert d["danh_sach"][0]["thu_muc"].endswith(os.path.join("kho_meta", "A"))
