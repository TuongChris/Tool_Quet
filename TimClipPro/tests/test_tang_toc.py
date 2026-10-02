# -*- coding: utf-8 -*-
"""Test cấu hình tăng tốc mà không chạy ffmpeg hoặc audfprint thật."""

import wave
from types import SimpleNamespace

import pytest

import engine as engine_module
from kho_gia import ghi_kho_tu_lenh
from engine import so_nhan_nen_dung


def _wav_khuc(path) -> None:
    """Khúc WAV HỢP LỆ (1 giây im lặng). Khúc mà header không đọc được nay bị coi là cắt
    lỗi (phản biện TCP-04), nên bộ giả không còn ghi bytes rác."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(11025)
        w.writeframes(bytes(2 * 11025))


@pytest.mark.parametrize(
    ("cpu_count", "mong_doi"),
    [(None, 1), (1, 1), (2, 1), (4, 3), (16, 8), (64, 8)],
)
def test_so_nhan_kep_trong_khoang(monkeypatch, cpu_count, mong_doi):
    monkeypatch.setattr(engine_module.os, "cpu_count", lambda: cpu_count)

    assert so_nhan_nen_dung() == mong_doi


def test_audfprint_tu_dong_dung_so_nhan_hieu_luc(engine, monkeypatch):
    engine.config.ncores = 0
    monkeypatch.setattr(engine_module.os, "cpu_count", lambda: 6)

    lenh = engine._audfprint_cmd("match")

    vi_tri = lenh.index("--ncores")
    assert lenh[vi_tri + 1] == "5"


def test_dung_kho_da_nhan_dem_du_so_file(engine, tmp_path, monkeypatch):
    thu_muc = tmp_path / "clips"
    thu_muc.mkdir()
    for i in range(4):
        (thu_muc / f"clip-{i}.wav").write_bytes(b"fake audio")
    engine.add_kho("Kho đa nhân", str(thu_muc))
    engine.config.ncores = 0
    monkeypatch.setattr(engine, "require", lambda **kwargs: None)

    def run_stream(lenh, on_line=None, **kwargs):
        for i, so_file in enumerate((1, 1, 1, 1, 0, 0, 0, 0)):
            on_line(f"hash_table {i} has {so_file} files 100 hashes")
        on_line("Saved fprints for 4 files (400 hashes) to db.pklz")
        ghi_kho_tu_lenh(lenh)
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)

    ket_qua = engine.build_database(str(thu_muc), "new")

    assert ket_qua["da_xu_ly"] == 4


def test_overlap_tu_dong_theo_clip_dai_nhat(engine, monkeypatch):
    engine.config.chunk_s = 3600
    engine.config.overlap_tu_dong = True
    thong_bao = []
    monkeypatch.setattr(
        engine,
        "clip_meta",
        lambda: {
            "ngan.opus": {"duration": 600},
            "dai.opus": {"duration": 1500},
        },
    )

    overlap = engine._overlap_thuc_te(
        lambda pct, msg: thong_bao.append((pct, msg)),
        0.4,
    )

    assert overlap == 180
    assert any("Khúc gối thực tế: 180 giây" in msg for _, msg in thong_bao)


@pytest.mark.parametrize("clip_dai_nhat", [30, 1790, 1900])
def test_overlap_tu_dong_tang_den_tran_roi_giu_nguyen(
    engine,
    monkeypatch,
    clip_dai_nhat,
):
    engine.config.chunk_s = 3600
    engine.config.overlap_tu_dong = True
    monkeypatch.setattr(
        engine,
        "clip_meta",
        lambda: {"clip.opus": {"duration": clip_dai_nhat}},
    )

    mong_doi = min(180, max(120, clip_dai_nhat + 30))
    assert engine._overlap_thuc_te() == mong_doi


def test_kho_rong_dung_gia_tri_cau_hinh(engine, monkeypatch):
    engine.config.overlap_s = 450
    engine.config.overlap_tu_dong = True
    monkeypatch.setattr(engine, "clip_meta", lambda: {})

    assert engine._overlap_thuc_te() == 180


def test_overlap_tu_dong_cham_tran_thay_vi_phu_thuoc_clip_dai(engine, monkeypatch):
    engine.config.chunk_s = 300
    engine.config.overlap_tu_dong = True
    thong_bao = []
    monkeypatch.setattr(
        engine,
        "clip_meta",
        lambda: {"clip.opus": {"duration": 280}},
    )

    overlap = engine._overlap_thuc_te(
        lambda pct, msg: thong_bao.append(msg),
    )

    assert overlap == 180
    assert any("Khúc gối thực tế: 180 giây" in msg for msg in thong_bao)


def test_cut_chunks_dung_overlap_tu_dong(engine, tmp_path, monkeypatch):
    engine.config.chunk_s = 1000
    engine.config.overlap_tu_dong = True
    monkeypatch.setattr(
        engine,
        "clip_meta",
        lambda: {"clip.opus": {"duration": 270}},
    )
    monkeypatch.setattr(engine, "duration_of", lambda media: 1500)

    def ffmpeg_gia(lenh, **kwargs):
        _wav_khuc(tmp_path.joinpath(lenh[-1]))
        return SimpleNamespace(returncode=0, cancelled=False, timed_out=False,
                               stdout="", stderr="", ly_do="")

    # Mọi lời gọi FFmpeg của engine đi qua `chay_lenh_media` (có huỷ + hạn im lặng).
    monkeypatch.setattr(engine_module, "chay_lenh_media", ffmpeg_gia)

    chunks, duration = engine._cut_chunks("video.mp4")

    assert duration == 1500
    assert [engine_module.os.path.basename(path) for path in chunks] == [
        "chunk_0000000.wav",
        "chunk_0000820.wav",
    ]


def test_cut_chunks_khong_goi_ffmpeg_tai_dung_eof(engine, tmp_path, monkeypatch):
    engine.config.chunk_s = 300
    engine.config.overlap_s = 60
    engine.config.overlap_max_s = 60
    engine.config.overlap_tu_dong = False
    monkeypatch.setattr(engine, "duration_of", lambda media: 480)
    cac_moc = []

    def ffmpeg_gia(lenh, **kwargs):
        cac_moc.append(int(lenh[lenh.index("-ss") + 1]))
        _wav_khuc(tmp_path.joinpath(lenh[-1]))
        return SimpleNamespace(returncode=0, cancelled=False, timed_out=False,
                               stdout="", stderr="", ly_do="")

    # Mọi lời gọi FFmpeg của engine đi qua `chay_lenh_media` (có huỷ + hạn im lặng).
    monkeypatch.setattr(engine_module, "chay_lenh_media", ffmpeg_gia)

    chunks, _ = engine._cut_chunks("video.mp4")

    assert cac_moc == [0, 240]
    assert len(chunks) == 2


def test_match_chunks_bao_truoc_khi_chay_subprocess(engine, monkeypatch):
    su_kien = []

    def progress(pct, msg):
        su_kien.append(("progress", msg))

    def run_stream(lenh, on_line=None, **kwargs):
        su_kien.append(("subprocess", lenh))
        return 0, []

    monkeypatch.setattr(engine, "_run_stream", run_stream)

    assert engine._match_chunks(["chunk.wav"], progress) == []
    assert su_kien[0] == (
        "progress",
        "Đang nạp kho vân tay và bắt đầu so khớp...",
    )
    assert su_kien[1][0] == "subprocess"
