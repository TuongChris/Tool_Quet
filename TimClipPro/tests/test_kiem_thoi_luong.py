# -*- coding: utf-8 -*-
"""Test công cụ bổ sung `duration_media` cho metadata clip gốc.

Không gọi ffprobe thật: thay `do_dai_media` bằng bảng tra để test chạy trong mili
giây và kiểm được đúng phần logic quyết định ghi hay không ghi.
"""

import json

import kiem_thoi_luong as ktl
import pytest


def _kho(tmp_path, meta: dict, tao_file=True):
    d = tmp_path / "kho"
    d.mkdir(exist_ok=True)
    (d / "clips_meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                       encoding="utf-8")
    if tao_file:
        for ten in meta:
            (d / ten).write_bytes(b"gia")
    return d


def _do(monkeypatch, bang: dict):
    monkeypatch.setattr(ktl, "do_dai_media",
                        lambda p: bang.get(__import__("os").path.basename(p)))


def _doc(d):
    return json.loads((d / "clips_meta.json").read_text(encoding="utf-8"))


META = {
    "a.opus": {"id": "a", "duration": 676},          # chưa có duration_media
    "b.opus": {"id": "b", "duration": 100,
               "duration_media": 99.5},              # đã có
}
DO_DUOC = {"a.opus": 675.858, "b.opus": 98.2}


# =====================================================================
#  Mặc định: chỉ bổ sung mục còn thiếu
# =====================================================================

def test_mac_dinh_khong_ghi_gi(tmp_path, monkeypatch, capsys):
    d = _kho(tmp_path, META)
    _do(monkeypatch, DO_DUOC)
    tk = ktl.kiem_mot_kho("k", str(d), sua=False, that_su=False, gioi_han=0)
    assert tk["da_ghi"] == 0
    assert _doc(d) == META, "chế độ kiểm tra không được đụng vào file"


def test_bo_sung_muc_con_thieu_va_bo_qua_muc_da_co(tmp_path, monkeypatch):
    d = _kho(tmp_path, META)
    _do(monkeypatch, DO_DUOC)
    tk = ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=0)
    assert tk["do_duoc"] == 1 and tk["da_ghi"] == 1
    sau = _doc(d)
    assert sau["a.opus"]["duration_media"] == pytest.approx(675.858)
    assert sau["b.opus"]["duration_media"] == 99.5, "mục đã có phải giữ nguyên"


def test_chay_lai_khong_ghi_them(tmp_path, monkeypatch):
    """Idempotent: lần hai không còn gì để ghi."""
    d = _kho(tmp_path, META)
    _do(monkeypatch, DO_DUOC)
    ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=0)
    tk = ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=0)
    assert tk["da_ghi"] == 0 and tk["do_duoc"] == 0


# =====================================================================
#  --ghi-de: đo lại cả mục đã có
# =====================================================================

def test_ghi_de_do_lai_va_cap_nhat_muc_da_co(tmp_path, monkeypatch):
    d = _kho(tmp_path, META)
    _do(monkeypatch, DO_DUOC)
    tk = ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=0,
                          ghi_de=True)
    assert tk["do_lai"] == 1, "phải đếm được số mục đo lại"
    assert tk["do_duoc"] == 2 and tk["da_ghi"] == 2
    sau = _doc(d)
    assert sau["b.opus"]["duration_media"] == pytest.approx(98.2), "phải ghi đè"
    assert sau["b.opus"]["duration"] == 100, "không được đụng `duration` gốc"


def test_ghi_de_xem_truoc_van_khong_ghi(tmp_path, monkeypatch):
    """`--ghi-de` không có `--sua` chỉ để xem trước, tuyệt đối không ghi."""
    d = _kho(tmp_path, META)
    _do(monkeypatch, DO_DUOC)
    tk = ktl.kiem_mot_kho("k", str(d), sua=False, that_su=False, gioi_han=0,
                          ghi_de=True)
    assert tk["do_duoc"] == 2 and tk["da_ghi"] == 0
    assert _doc(d) == META


def test_ghi_de_so_voi_gia_tri_dang_hien_thi(tmp_path, monkeypatch):
    """Ở chế độ ghi đè phải so với `duration_media` cũ, không phải `duration`.

    b.opus: duration=100 (01:40), duration_media cũ=99.5 (01:39), đo lại=98.2
    (01:38). Cái đang hiển thị là 01:39 nên đây LÀ một thay đổi; nếu so nhầm với
    `duration` thì cũng ra "đổi" nhưng vì lý do sai.
    """
    d = _kho(tmp_path, {"b.opus": META["b.opus"]})
    _do(monkeypatch, {"b.opus": 99.9})   # 01:39 — cùng hiển thị với 99.5
    tk = ktl.kiem_mot_kho("k", str(d), sua=False, that_su=False, gioi_han=0,
                          ghi_de=True)
    assert tk["doi_hien_thi"] == 0, "99,5 và 99,9 cùng hiện 00:01:39"


# =====================================================================
#  Biên
# =====================================================================

def test_thieu_file_thi_dem_rieng_khong_ghi(tmp_path, monkeypatch):
    d = _kho(tmp_path, META, tao_file=False)
    _do(monkeypatch, DO_DUOC)
    tk = ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=0)
    assert tk["thieu_file"] == 1 and tk["da_ghi"] == 0


def test_do_that_bai_thi_bo_qua(tmp_path, monkeypatch):
    d = _kho(tmp_path, META)
    _do(monkeypatch, {})     # ffprobe luôn trả None
    tk = ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=0)
    assert tk["da_ghi"] == 0
    assert _doc(d) == META


def test_gioi_han_chan_so_luong_do(tmp_path, monkeypatch):
    meta = {f"c{i}.opus": {"id": str(i), "duration": 100} for i in range(5)}
    d = _kho(tmp_path, meta)
    _do(monkeypatch, {f"c{i}.opus": 99.1 for i in range(5)})
    tk = ktl.kiem_mot_kho("k", str(d), sua=True, that_su=True, gioi_han=2)
    assert tk["do_duoc"] == 2 and tk["da_ghi"] == 2


def test_khong_co_clips_meta_thi_khong_no(tmp_path):
    (tmp_path / "trong").mkdir()
    assert ktl.kiem_mot_kho("k", str(tmp_path / "trong"), False, False, 0) == {}
