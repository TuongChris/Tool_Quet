# -*- coding: utf-8 -*-
"""Vòng phản biện 3 — phạm vi quét (reviewer A): dòng stdout xen nhau của nhiều worker
audfprint, lớp phòng thủ theo nội dung khúc, độ dài luồng tiếng, dọn bản tải một phần."""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import engine as engine_module
from engine import Engine, ScanResult

can_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="cần ffmpeg/ffprobe trong PATH")
SR = 11025
VID = "abcdefghijk"


def _ghi_wav_11k(path, giay: float, bien_do: float = 0.0) -> None:
    """WAV mono 11025 Hz; `bien_do` = 0 → im lặng tuyệt đối, > 0 → sóng sin có tiếng."""
    n = int(giay * SR)
    if bien_do:
        t = np.arange(n) / SR
        mau = (np.sin(2 * np.pi * 440 * t) * bien_do * 32767).astype(np.int16)
    else:
        mau = np.zeros(n, dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(mau.tobytes())


def _eng_gia(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.chunk_s = 100
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    e.config.top_n = 1
    e._overlap_thuc_te = lambda *a, **k: 0
    e.db_clips = lambda **k: [{"ten": "goc.opus", "duong_dan": "goc.opus",
                               "so_hash": 20000}]
    return e


def _ffmpeg_cat_gia(bien_do: float = 0.0):
    def chay(lenh, **kw):
        bat_dau = int(float(lenh[lenh.index("-ss") + 1]))
        _ghi_wav_11k(lenh[-1], min(100.0, 300.0 - bat_dau), bien_do)
        return SimpleNamespace(returncode=0, stdout="", stderr="", cancelled=False,
                               timed_out=False, ly_do="")
    return chay


def _audfprint_xen(dong_stdout, khong_hash=()):
    """audfprint giả: in nguyên văn các dòng `dong_stdout(khúc theo mốc)` rồi ghi opfile."""
    def chay(lenh, on_line=None, **kw):
        ds = [p for p in Path(lenh[lenh.index("--list") + 1])
              .read_text(encoding="utf-8").splitlines() if p]
        theo_moc = {int(os.path.basename(p)[6:13]): p for p in ds}
        for dong in dong_stdout(theo_moc):
            on_line(dong)
        with open(lenh[lenh.index("--opfile") + 1], "w", encoding="utf-8") as f:
            for moc, p in theo_moc.items():
                if moc in khong_hash:
                    f.write(f"NOMATCH {p} 0.0 sec 0 raw hashes\n")
                else:
                    f.write(f"NOMATCH {p} 99.9 sec 812 raw hashes\n")
        return 0, []
    return chay


def _media(tmp_path):
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")
    return str(media)


# ---------------------------------------------------------------------------
#  V3-A1 — dòng stdout của nhiều worker audfprint XEN nhau (ncores > 1)
# ---------------------------------------------------------------------------

def test_hai_loi_doc_xen_tren_cung_mot_dong_stdout_deu_bi_bat(tmp_path, monkeypatch):
    """Mẫu A: `…Error reading <100> …Error reading <200> skippingskipping` — khúc thứ hai
    từng bị bỏ sót (chỉ đọc tên khúc ĐẦU TIÊN của dòng)."""
    e = _eng_gia(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat_gia())
    e._run_stream = _audfprint_xen(lambda k: [
        f"wavfile2peaks: Error reading {k[100]} wavfile2peaks: Error reading {k[200]} "
        "skippingskipping"], khong_hash=(100, 200))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 300.0)], (kq.status, kq.vung_loi)


def test_loi_doc_chen_giua_dong_cua_khuc_khac_khong_gan_nham(tmp_path, monkeypatch):
    """Mẫu B: `Analyzed  <0> of wavfile2peaks: Error reading <100> skipping` — lỗi là của
    khúc 100, không phải khúc 0."""
    e = _eng_gia(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat_gia())
    e._run_stream = _audfprint_xen(lambda k: [
        f"Analyzed  {k[0]} of wavfile2peaks: Error reading {k[100]} skipping"],
        khong_hash=(100,))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 200.0)], (kq.status, kq.vung_loi)


def test_khuc_co_tieng_ro_ma_0_hash_la_chua_phan_tich(tmp_path, monkeypatch):
    """Lớp phòng thủ thứ hai theo NỘI DUNG: dòng lỗi lạc mất, WAV vẫn đọc được (lỗi tạm thời
    lúc audfprint đọc), nhưng khúc có tiếng rõ thì không thể ra 0 hash nếu đã được phân
    tích (audfprint chuẩn hoá phổ theo đỉnh của chính khúc)."""
    e = _eng_gia(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat_gia(bien_do=0.5))
    e._run_stream = _audfprint_xen(lambda k: [], khong_hash=(100,))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 200.0)], (kq.status, kq.vung_loi)


def test_khuc_gan_im_lang_0_hash_van_la_am_tinh(tmp_path, monkeypatch):
    """Tiếng rất nhỏ (−70 dBFS, ví dụ nhiễu nền của video bị tắt tiếng): không được thành
    lỗi vĩnh viễn — về mặt so khớp đó vẫn là im lặng."""
    e = _eng_gia(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media",
                        _ffmpeg_cat_gia(bien_do=10 ** (-70 / 20)))
    e._run_stream = _audfprint_xen(lambda k: [], khong_hash=(100,))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "ok" and kq.quet_day_du, (kq.status, kq.vung_loi)


def test_tien_do_khop_dem_ca_dong_analyzed_khong_co_so_thu_tu(tmp_path, monkeypatch):
    """ncores > 1: audfprint in `Analyzed  <khúc> of …` không có `#N` — tiến độ phải chạy."""
    e = _eng_gia(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat_gia())
    e._run_stream = _audfprint_xen(lambda k: [
        f"Analyzed  {p} of 99.900 s to 812 hashes" for p in k.values()])
    tin = []

    e.scan_media(_media(tmp_path), progress=lambda pct, msg: tin.append(msg))

    assert any("so khớp vân tay... khúc 3/3" in m for m in tin), [
        m for m in tin if "so khớp" in m]


# ---------------------------------------------------------------------------
#  V3-A2 / A-P3 — độ dài luồng tiếng: nhiều luồng tiếng; luồng bắt đầu trễ
# ---------------------------------------------------------------------------

def _ffmpeg(*tham_so) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    *map(str, tham_so)], check=True)


@can_ffmpeg
def test_nhieu_luong_tieng_khong_lay_luong_dau_lam_het_am_thanh(tmp_path):
    """a:0 (mono 60 s) kết thúc sớm nhưng a:1 (stereo) còn tiếng tới hết: phần sau giây 60
    KHÔNG phải "không có tiếng"."""
    media = tmp_path / "hai_luong.mkv"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:r=5:d=200",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
            "-f", "lavfi", "-i", "sine=frequency=660:duration=200",
            "-map", "0:v", "-map", "1:a", "-map", "2:a",
            "-c:v", "mpeg4", "-q:v", "31", "-c:a", "aac", "-b:a", "32k",
            "-ac:a:1", "2", media)
    e = _eng_gia(tmp_path)
    e._match_chunks = lambda chunks, *a, **k: []

    assert Engine.do_dai_am_thanh(str(media)) is None
    kq = e.scan_media(str(media))
    assert not (kq.status == "ok" and kq.quet_day_du), (kq.status, kq.vung_da_khop)


@can_ffmpeg
def test_luong_tieng_bat_dau_tre_tinh_den_moc_ket_thuc_that(tmp_path):
    media = tmp_path / "tre.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:r=5:d=200",
            "-itsoffset", "30", "-f", "lavfi", "-i", "sine=frequency=440:duration=150",
            "-c:v", "mpeg4", "-q:v", "31", "-c:a", "aac", "-b:a", "32k", media)

    assert Engine.do_dai_am_thanh(str(media)) == pytest.approx(180.0, abs=1.0)


# ---------------------------------------------------------------------------
#  V3-A3 — bản tải MỘT PHẦN cũng phải được dọn khi không giữ đệm
# ---------------------------------------------------------------------------

def test_ban_tai_mot_phan_duoc_don_khi_khong_giu_dem(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.keep_downloads = False
    e.config.quet_tang_dan = True
    e.config.tai_mot_phan = True
    e.config.quet_tang_dan_tu_gio = 10
    e.config.quet_tang_dan_buoc_gio = 3
    e.config.top_n = 1
    tong = 40 * 3600.0
    e.youtube_info = lambda url: {"title": "V", "id": VID, "channel": "", "channel_id": "",
                                  "channel_url": "", "upload_date": "", "duration": tong}

    def tai(url, vid, progress=None, gioi_han_giay=None):
        ten = f"{vid}__p{int(gioi_han_giay)}.wav" if gioi_han_giay else f"{vid}.wav"
        tep = Path(e.dl_dir) / ten
        tep.write_bytes(b"x")
        return str(tep)

    def quet(path, **kw):
        dai = 3 * 3600.0 if "__p" in path else tong
        return ScanResult(source_name="V", duration_s=dai, vung_da_khop=[(0.0, dai)])

    e.download_audio = tai
    e.scan_media = quet

    e.scan_youtube(f"https://youtu.be/{VID}")

    assert os.listdir(e.dl_dir) == [], os.listdir(e.dl_dir)


# ---------------------------------------------------------------------------
#  V3-A-P1 — "âm thanh ngắn thật" mang lý do riêng để còn rà lại về sau
# ---------------------------------------------------------------------------

def test_am_thanh_ngan_that_ghi_ly_do_rieng_vao_lich_su(tmp_path):
    import lich_su

    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.quet_tang_dan = False
    e.config.keep_downloads = True
    e.youtube_info = lambda url: {"title": "V", "id": VID, "channel": "", "channel_id": "",
                                  "channel_url": "", "upload_date": "", "duration": 600.0}

    def tai(url, vid, progress=None, gioi_han_giay=None):
        tep = Path(e.dl_dir) / f"{vid}.webm"
        tep.write_bytes(b"x")
        return str(tep)

    e.download_audio = tai
    e.duration_of = lambda p: 580.0
    e.scan_media = lambda path, **kw: ScanResult(source_name="V", duration_s=580.0,
                                                 vung_da_khop=[(0.0, 580.0)])

    kq = e.scan_youtube(f"https://youtu.be/{VID}")

    assert kq.status == "ok" and kq.quet_day_du and kq.ly_do_pham_vi == "am_thanh_ngan_hon"
    hang = e.list_jobs()[0]
    assert "ngắn hơn" in lich_su.mo_ta_pham_vi(hang), lich_su.mo_ta_pham_vi(hang)


# ---------------------------------------------------------------------------
#  V3 kiểm lại (reviewer A) — lệch DC hằng số; lý do "ngắn thật" không đè "lỗi khúc"
# ---------------------------------------------------------------------------

def test_khuc_lech_dc_hang_so_0_hash_van_la_am_tinh(tmp_path, monkeypatch):
    """PCM hằng số khác 0 (DC −45 dBFS — "im lặng" bị lệch DC của file lossless): phổ không
    đổi nên audfprint ra 0 hash. Không có tiếng nào để so khớp → không được thành lỗi."""
    e = _eng_gia(tmp_path)
    e.duration_of = lambda p: 300.0

    def cat_dc(lenh, **kw):
        bat_dau = int(float(lenh[lenh.index("-ss") + 1]))
        n = int(min(100.0, 300.0 - bat_dau) * SR)
        with wave.open(lenh[-1], "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(np.full(n, 184, dtype=np.int16).tobytes())   # ≈ −45 dBFS
        return SimpleNamespace(returncode=0, stdout="", stderr="", cancelled=False,
                               timed_out=False, ly_do="")

    monkeypatch.setattr(engine_module, "chay_lenh_media", cat_dc)
    e._run_stream = _audfprint_xen(lambda k: [], khong_hash=(100,))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "ok" and kq.quet_day_du, (kq.status, kq.vung_loi)


def test_am_thanh_ngan_that_khong_de_ly_do_loi_khuc(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.quet_tang_dan = False
    e.config.keep_downloads = True
    e.youtube_info = lambda url: {"title": "V", "id": VID, "channel": "", "channel_id": "",
                                  "channel_url": "", "upload_date": "", "duration": 600.0}

    def tai(url, vid, progress=None, gioi_han_giay=None):
        tep = Path(e.dl_dir) / f"{vid}.webm"
        tep.write_bytes(b"x")
        return str(tep)

    def quet(path, **kw):
        kq = ScanResult(source_name="V", duration_s=580.0, status="error",
                        vung_da_khop=[(0.0, 200.0), (250.0, 580.0)],
                        vung_loi=[(200.0, 250.0)])
        kq.ly_do_pham_vi = "loi_khuc"
        return kq

    e.download_audio = tai
    e.duration_of = lambda p: 580.0
    e.scan_media = quet

    kq = e.scan_youtube(f"https://youtu.be/{VID}")

    assert kq.status == "error" and kq.ly_do_pham_vi == "loi_khuc", (kq.status,
                                                                      kq.ly_do_pham_vi)
