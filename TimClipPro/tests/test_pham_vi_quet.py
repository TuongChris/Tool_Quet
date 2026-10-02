# -*- coding: utf-8 -*-
"""Kết quả quét phải nói thật về PHẠM VI đã thực sự so khớp (audit TCP-04, TCP-06).

* Một khúc không cắt/giải mã/khớp được thì vùng đó CHƯA được kiểm: không được báo
  "quét xong, không có clip" như thể đã kiểm cả video.
* Dừng sớm vì đã đủ bằng chứng là hợp lệ, nhưng không được ghi là đã quét toàn bộ.
* Phạm vi phải tới được lịch sử và báo cáo mà KHÔNG thêm cột (ngang 34, dọc 16).

Khúc WAV trong test là WAV thật (stdlib ``wave``), FFmpeg được thay ở đúng điểm gọi
chung ``engine.chay_lenh_media``.
"""

import os
import wave
from types import SimpleNamespace

import pytest

import bang_ngang
import engine as engine_module
from engine import Engine, ScanResult, hop_khoang, tong_do_dai, tru_khoang

SR = 11025


def _ghi_wav(path, giay: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"\x00\x00" * int(giay * SR))


def _eng(tmp_path, chunk_s=100):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.chunk_s = chunk_s
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    e.config.top_n = 1
    e._overlap_thuc_te = lambda *a, **k: 0
    e.db_clips = lambda **k: [{"ten": "goc.opus", "duong_dan": "goc.opus",
                               "so_hash": 20000}]
    return e


def _ffmpeg_gia(tong: float, chunk_s: float, loi=(), cut_ngan=None, loi_lan_dau=()):
    """Giả FFmpeg cắt khúc: ghi WAV thật dài đúng phần được yêu cầu."""
    da_thu = {}

    def chay(lenh, **kw):
        bat_dau = int(float(lenh[lenh.index("-ss") + 1]))
        da_thu[bat_dau] = da_thu.get(bat_dau, 0) + 1
        if bat_dau in loi or (bat_dau in loi_lan_dau and da_thu[bat_dau] == 1):
            return SimpleNamespace(returncode=1, stdout="", stderr="lỗi giải mã giả",
                                   cancelled=False, timed_out=False, ly_do="")
        dai = min(chunk_s, tong - bat_dau)
        if cut_ngan and bat_dau in cut_ngan:
            dai = cut_ngan[bat_dau]
        _ghi_wav(lenh[-1], dai)
        return SimpleNamespace(returncode=0, stdout="", stderr="",
                               cancelled=False, timed_out=False, ly_do="")
    chay.da_thu = da_thu
    return chay


def _manh(bat_dau, khop=60.0, so_hash=9000):
    return {"clip": "goc.opus", "bat_dau": bat_dau, "khop": khop, "t_clip": 0.0,
            "hash": so_hash, "align": bat_dau}


# ---------------------------------------------------------------------------
#  Hàm thuần: hợp / trừ khoảng
# ---------------------------------------------------------------------------

def test_hop_khoang_gop_chong_lap_va_giu_khoang_trong():
    assert hop_khoang([(0, 100), (50, 160), (200, 300), (300, 310)]) == [
        (0, 160), (200, 310)]
    assert tong_do_dai([(0, 100), (50, 160), (200, 300)]) == 260


def test_tru_khoang_chi_con_phan_chua_duoc_phu():
    assert tru_khoang([(100, 400)], [(0, 160), (300, 500)]) == [(160, 300)]
    assert tru_khoang([(0, 10)], [(0, 10)]) == []


# ---------------------------------------------------------------------------
#  TCP-04 — khúc lỗi không được biến mất khỏi trách nhiệm quét
# ---------------------------------------------------------------------------

def test_khuc_giua_loi_va_khong_co_bang_chung_thi_khong_ket_luan_am_tinh(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100, loi={100}))
    e._match_chunks = lambda chunks, *a, **k: []
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error", "vùng chưa kiểm không được báo là quét xong, 0 kết quả"
    assert "00:01:40" in kq.note and "00:03:20" in kq.note
    assert kq.vung_loi == [(100.0, 200.0)]
    assert e.list_jobs()[0]["status"] == "error"


def test_khuc_loi_nhung_co_bang_chung_thi_giu_ket_qua_va_ghi_ro_chua_tron(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100, loi={100}))
    e._match_chunks = lambda chunks, *a, **k: [_manh(5.0, khop=90.0)] if any(
        "chunk_0000000" in c for c in chunks) else []
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "ok" and len(kq.matches) == 1
    assert not kq.quet_day_du and kq.quet_mot_phan
    assert kq.ly_do_pham_vi == "loi_khuc"
    assert kq.vung_loi == [(100.0, 200.0)]
    assert "00:01:40" in kq.note


def test_khuc_bi_cat_ngan_duoc_tinh_phan_thieu_la_vung_loi(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media",
                        _ffmpeg_gia(300, 100, cut_ngan={100: 40.0}))
    e._match_chunks = lambda chunks, *a, **k: []
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error"
    assert kq.vung_loi == [(140.0, 200.0)]


def test_loi_tam_thoi_duoc_thu_lai_mot_lan_roi_quet_tron(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    ffmpeg = _ffmpeg_gia(300, 100, loi_lan_dau={100})
    monkeypatch.setattr(engine_module, "chay_lenh_media", ffmpeg)
    e._match_chunks = lambda chunks, *a, **k: []
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert ffmpeg.da_thu[100] == 2
    assert kq.status == "ok" and kq.quet_day_du and not kq.vung_loi


def test_khuc_vang_mat_trong_output_audfprint_bi_tinh_la_chua_khop(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 200.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(200, 100))

    def run_stream(lenh, on_line=None, **kw):
        ds = open(lenh[lenh.index("--list") + 1], encoding="utf-8").read().split("\n")
        op = lenh[lenh.index("--opfile") + 1]
        # audfprint chỉ báo khúc ĐẦU (khúc sau lỗi đọc và bị bỏ qua lặng lẽ).
        with open(op, "w", encoding="utf-8") as f:
            f.write(f"NOMATCH {ds[0]} 100.0 sec 5000 raw hashes\n")
        return 0, []

    e._run_stream = run_stream
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error"
    assert kq.vung_loi == [(100.0, 200.0)]


def test_quet_tron_khong_co_ket_qua_thi_la_am_tinh_day_du(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100))
    e._match_chunks = lambda chunks, *a, **k: []
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "ok" and not kq.matches
    assert kq.quet_day_du and not kq.quet_mot_phan
    assert kq.vung_da_khop == [(0.0, 300.0)]
    assert "QUÉT MỘT PHẦN" not in " ".join(str(o) for o in e.to_rows([kq])[0])


def test_huy_giua_quet_ghi_ly_do_huy(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100))

    def khop(chunks, *a, **k):
        e.cancel()
        raise engine_module.Cancelled()

    e._match_chunks = khop
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error" and kq.ly_do_pham_vi == "huy"


# ---------------------------------------------------------------------------
#  TCP-06 — dừng sớm hợp lệ nhưng phải ghi đúng phạm vi
# ---------------------------------------------------------------------------

def _eng_top1(tmp_path):
    e = _eng(tmp_path, chunk_s=3600)
    e.config.top1_tim_nhanh = True
    e.config.top1_khuc_toi_thieu = 3
    e.duration_of = lambda p: 14400.0
    e._cut_chunks = lambda *a, **k: (
        [str(tmp_path / f"chunk_{n:07d}.wav") for n in (0, 3600, 7200, 10800)], 14400.0)
    da_hoi = []

    def khop(chunks, *a, **k):
        da_hoi.extend(chunks)
        return [_manh(10.0, khop=200.0, so_hash=9000)]

    e._match_chunks = khop
    return e, da_hoi


def test_top1_dung_som_khong_duoc_ghi_la_da_quet_toan_video(tmp_path):
    e, da_hoi = _eng_top1(tmp_path)
    media = tmp_path / "q.wav"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert len(da_hoi) == 1, "điều kiện test: chỉ khúc đầu được khớp"
    assert kq.status == "ok" and len(kq.matches) == 1
    assert kq.vung_da_khop == [(0.0, 3600.0)]
    assert kq.pham_vi_quet_s == 3600.0
    assert kq.quet_mot_phan and not kq.quet_day_du
    assert kq.ly_do_pham_vi == "dung_som" and kq.dat_muc_tieu
    assert "dừng sớm" in kq.note.lower()
    assert "dừng sớm" in e.list_jobs()[0]["note"].lower()


def test_bao_cao_ngang_va_doc_mang_pham_vi_ma_khong_them_cot(tmp_path):
    e, _ = _eng_top1(tmp_path)
    media = tmp_path / "q.wav"
    media.write_bytes(b"x")
    kq = e.scan_media(str(media))
    kq.source_name = "Video vi phạm"

    ngang = bang_ngang.dung_dong_ngang(kq)
    assert len(ngang) == len(bang_ngang.HEADER_NGANG) == 34
    assert ngang[5].startswith("Video vi phạm") and "QUÉT MỘT PHẦN" in ngang[5]

    doc = e.to_rows([kq])
    assert all(len(dong) == len(Engine.HEADER) == 16 for dong in doc)
    assert "QUÉT MỘT PHẦN" in doc[0][1]


def test_ho_so_markdown_ghi_ro_chua_quet_tron(tmp_path):
    import dossier

    e, _ = _eng_top1(tmp_path)
    media = tmp_path / "q.wav"
    media.write_bytes(b"x")
    kq = e.scan_media(str(media))
    md = dossier.render_markdown(dossier.dung_ho_so(kq))
    assert "CHƯA QUÉT TRỌN" in md and "01:00:00/04:00:00" in md

    tron = ScanResult(source_name="Trọn", status="ok", duration_s=600.0)
    tron.vung_da_khop = [(0.0, 600.0)]
    assert "CHƯA QUÉT TRỌN" not in dossier.render_markdown(dossier.dung_ho_so(tron))


def test_ket_qua_cu_khong_co_thong_tin_pham_vi_khong_bi_gan_nhan(tmp_path):
    """ScanResult dựng tay/kiểu cũ (không biết phạm vi) không bị gắn nhãn 'một phần'."""
    kq = ScanResult(source_name="Cũ", status="ok", duration_s=500.0)
    assert not kq.quet_mot_phan
    assert "QUÉT MỘT PHẦN" not in bang_ngang.dung_dong_ngang(kq)[5]


@pytest.mark.parametrize("ly_do", ["dung_som", "gioi_han_tai", "loi_khuc"])
def test_mo_ta_pham_vi_noi_ro_tung_ly_do(ly_do):
    kq = ScanResult(source_name="V", status="ok", duration_s=7200.0)
    kq.vung_da_khop = [(0.0, 3600.0)]
    kq.vung_loi = [(3600.0, 4000.0)] if ly_do == "loi_khuc" else []
    kq.ly_do_pham_vi = ly_do
    mo_ta = engine_module.mo_ta_pham_vi(kq)
    assert "01:00:00" in mo_ta and "02:00:00" in mo_ta
    assert os.linesep not in mo_ta
