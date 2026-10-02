# -*- coding: utf-8 -*-
"""FFmpeg/FFprobe treo hoặc bị huỷ giữa chừng không được giữ job vô hạn (audit TCP-15).

Thay FFmpeg thật bằng một process Python treo, nhưng vẫn chạy qua ĐÚNG helper của
dự án với ĐÚNG ngân sách mà Engine/kênh truyền vào — nên test đo được cả việc
Engine có truyền cờ huỷ/hạn chờ hay không.
"""

import sys
import threading
import time

import pytest

import channel
import engine as engine_module
import process_runner
from engine import Cancelled, Engine

LENH_TREO = [sys.executable, "-c", "import time; time.sleep(120)"]


def _helper_that_nhung_lenh_treo(ghi_nhan: list):
    """Gọi helper THẬT với lệnh treo; giữ nguyên mọi tham số ngân sách của caller."""
    def chay(lenh, **kw):
        ghi_nhan.append((list(lenh), dict(kw)))
        kw = dict(kw)
        kw["them_co_tien_do"] = False
        return process_runner.chay_lenh_media(LENH_TREO, **kw)
    return chay


@pytest.fixture
def eng(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.config.chunk_s = 600
    e.config.overlap_s = 60
    e.config.overlap_max_s = 60
    e.config.overlap_tu_dong = False
    return e


def test_cat_khuc_bi_huy_khi_ffmpeg_dang_treo(eng, tmp_path, monkeypatch):
    goi = []
    monkeypatch.setattr(engine_module, "chay_lenh_media", _helper_that_nhung_lenh_treo(goi))
    monkeypatch.setattr(eng, "duration_of", lambda p: 1200.0)
    threading.Timer(0.5, eng.cancel_event.set).start()

    bat_dau = time.monotonic()
    with pytest.raises(Cancelled):
        eng._cut_chunks("phim.mp4", workspace=str(tmp_path))
    assert time.monotonic() - bat_dau < 20
    assert goi and goi[0][1].get("cancel_event") is eng.cancel_event


def test_cat_khuc_co_han_im_lang_theo_tien_do_thay_vi_han_chot_tong(eng, tmp_path, monkeypatch):
    goi = []

    def ghi_lai(lenh, **kw):
        goi.append(kw)
        with open(lenh[-1], "wb") as f:
            f.write(b"x" * 4096)
        return process_runner.KetQuaLenh(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(engine_module, "chay_lenh_media", ghi_lai)
    monkeypatch.setattr(eng, "duration_of", lambda p: 1200.0)

    eng._cut_chunks("phim.mp4", workspace=str(tmp_path))

    assert goi and all(kw.get("theo_doi_tien_do") for kw in goi)
    assert all(kw.get("im_lang_toi_da_s") for kw in goi)
    assert all(kw.get("tran_tong_s") is None for kw in goi), "không dùng hạn chót tổng"


def test_ffprobe_treo_khong_giu_job_vo_han(monkeypatch):
    goi = []
    monkeypatch.setattr(engine_module, "chay_lenh_media", _helper_that_nhung_lenh_treo(goi))
    monkeypatch.setattr(engine_module, "TRAN_FFPROBE_S", 1.0)

    bat_dau = time.monotonic()
    assert Engine.duration_of("video.mp4") is None
    assert time.monotonic() - bat_dau < 20
    assert goi and goi[0][1].get("tran_tong_s")


def test_nen_audio_kenh_co_huy_va_han_im_lang(tmp_path, monkeypatch):
    goi = []
    monkeypatch.setattr(channel, "chay_lenh_media", _helper_that_nhung_lenh_treo(goi))
    cs = channel.ChannelSync(str(tmp_path / "kho"))
    v = channel.VideoInfo("abcdefghijk", "Video", "20260101", 100.0,
                          "https://youtu.be/abcdefghijk")

    def tai(url, rieng):
        import os
        os.makedirs(cs.tmp_dir, exist_ok=True)
        with open(os.path.join(cs.tmp_dir, "abcdefghijk.webm"), "wb") as f:
            f.write(b"x" * 4096)
        return {}

    cs._tai_thu_tung_client = tai
    huy = threading.Event()
    threading.Timer(0.5, huy.set).start()

    bat_dau = time.monotonic()
    with pytest.raises(Exception) as loi:
        cs._tai_va_nen(v, cancel_event=huy)
    assert time.monotonic() - bat_dau < 20
    assert "huỷ" in str(loi.value).lower() or "hủy" in str(loi.value).lower()
    kw = goi[0][1]
    assert kw.get("cancel_event") is huy
    assert kw.get("theo_doi_tien_do") and kw.get("im_lang_toi_da_s")
