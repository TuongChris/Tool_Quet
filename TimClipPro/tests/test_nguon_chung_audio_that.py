# -*- coding: utf-8 -*-
"""Chế độ «một video gốc chung cho cả lô» trên audio THẬT (audfprint + FFmpeg). Chậm.

Dữ liệu tổng hợp, mốc đã biết:

    f1 (360 s, mốc)  : B @30 (60 s) · C @150 (40 s) · 22 s đầu của A @270
    f2 (960 s)       : B @20 (60 s) · E @400 (40 s) · 22 s đầu của A @700
    f3 (960 s)       : C @60 (40 s) · F @400 (40 s) · 22 s đầu của A @800

A có mặt ở cả ba nhưng luôn là đoạn NGẮN nhất — chế độ «mỗi video tự chọn» (Top-1) không
bao giờ chọn A. Chế độ nguồn chung phải ra A, với đúng mốc ở từng video.
"""

import time

import numpy as np
import pytest

import common_original as co
from common_original_jobs import CommonOriginalJobController
from conftest import _ghi_wav, _giai_dieu

SR = 22050
CLIP = {"A": (45, 901), "B": (60, 902), "C": (40, 903), "E": (40, 905), "F": (40, 906)}
TEN = {k: f"{k}_goc.wav" for k in CLIP}


def _dung_kho(thu_muc):
    am = {}
    for k, (dai, seed) in CLIP.items():
        am[k] = _giai_dieu(dai, seed=seed, sr=SR)
        _ghi_wav(thu_muc / TEN[k], am[k], SR)
    return am


def _video(duong, dai_s, seed, chen, am):
    nen = _giai_dieu(dai_s, seed=seed, sr=SR) * 0.6
    for k, giay, cat_s in chen:
        doan = am[k][: int(cat_s * SR)] if cat_s else am[k]
        i0 = int(giay * SR)
        nen[i0:i0 + len(doan)] = doan
    _ghi_wav(duong, np.clip(nen, -1, 1), SR)
    return str(duong)


@pytest.fixture()
def lo_that(engine, tmp_path):
    kho = tmp_path / "kho"
    kho.mkdir()
    am = _dung_kho(kho)
    nguon = tmp_path / "nguon"
    nguon.mkdir()
    f = {
        "f1": _video(nguon / "f1.wav", 360, 11, [("B", 30, 0), ("C", 150, 0),
                                                ("A", 270, 22)], am),
        "f2": _video(nguon / "f2.wav", 960, 12, [("B", 20, 0), ("E", 400, 0),
                                                ("A", 700, 22)], am),
        "f3": _video(nguon / "f3.wav", 960, 13, [("C", 60, 0), ("F", 400, 0),
                                                ("A", 800, 22)], am),
        "f4": _video(nguon / "f4.wav", 960, 14, [("C", 60, 0), ("F", 400, 0)], am),
    }
    c = engine.config
    c.chunk_s, c.overlap_s, c.min_hash_floor, c.top_n = 300, 60, 50, 1
    c.quet_da_toc_do = False
    engine.add_kho("Kho thử nguồn chung", str(kho))
    r = engine.build_database(str(kho), "new")
    assert r["da_xu_ly"] == len(CLIP)
    return engine, f


def _chay(engine, files):
    ctl = CommonOriginalJobController(engine)
    ctl.start(files, "file")
    han = time.monotonic() + 600
    while ctl.running and time.monotonic() < han:
        time.sleep(0.2)
    assert not ctl.running and not ctl.error, ctl.error
    return ctl.result


@pytest.mark.slow
def test_nguon_chung_khong_phai_top1_cua_video_nao_van_duoc_tim_ra(lo_that):
    engine, f = lo_that
    # Điều kiện tiên quyết: chế độ cũ (Top-1) không bao giờ chọn A.
    for ten in ("f1", "f2", "f3"):
        kq = engine.scan_media(f[ten], luu_lich_su=False)
        assert kq.status == "ok" and kq.matches
        assert kq.matches[0].clip != TEN["A"], f"{ten}: Top-1 cũ đã là A — kịch bản vô hiệu"

    kql = _chay(engine, [f["f1"], f["f2"], f["f3"]])
    assert kql.trang_thai == co.TIM_THAY, kql.ly_do
    assert kql.goc.clip == TEN["A"]
    moc = {"f1.wav": 270, "f2.wav": 700, "f3.wav": 800}
    for v in kql.videos:
        ten = v.nguon.replace("\\", "/").rsplit("/", 1)[-1]
        assert v.trang_thai == co.CO_MAT
        assert abs(v.dai_dien.clip_bat_dau_s - moc[ten]) < 5, f"{ten} lệch mốc"
    so = {v.nguon.replace("\\", "/").rsplit("/", 1)[-1]: v.so_luot for v in kql.videos}
    assert so == {"f1.wav": 1, "f2.wav": 2, "f3.wav": 1}, so
    assert kql.so_lieu["luot_toi_da_moi_video"] <= 2


@pytest.mark.slow
def test_khong_co_nguon_chung_thi_khong_bao_nham(lo_that):
    engine, f = lo_that
    kql = _chay(engine, [f["f1"], f["f2"], f["f4"]])
    assert kql.trang_thai == co.KHONG_TIM_THAY, kql.ly_do
    assert not kql.la_nguon_chung and kql.so_co_mat == 2
    assert kql.so_lieu["luot_toi_da_moi_video"] <= 2
