# -*- coding: utf-8 -*-
"""Fixture dùng chung cho toàn bộ test. Sinh audio giả lập, không cần file thật."""
import os
import sys
import wave

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ghi_wav(path, sig, sr=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(sig, -1, 1) * 32000).astype(np.int16).tobytes())


def _giai_dieu(dur_s, seed, sr=22050):
    """Chuỗi nốt ngẫu nhiên -> nhiều điểm mốc phổ, giống nhạc thật."""
    rng = np.random.default_rng(seed)
    n = int(dur_s / 0.4) + 1
    freqs = rng.uniform(200, 4000, n)
    t = np.arange(int(0.4 * sr)) / sr
    env = np.hanning(len(t))
    sig = np.concatenate([np.sin(2 * np.pi * f * t) * env for f in freqs])[: int(dur_s * sr)]
    return (sig + 0.02 * rng.standard_normal(len(sig))) * 0.7


@pytest.fixture(scope="session")
def bo_clip(tmp_path_factory):
    """4 clip gốc 30 giây + 1 video dài 6 phút chứa 3 clip ở vị trí đã biết."""
    d = tmp_path_factory.mktemp("kho")
    sr = 22050
    clips = []
    for i in range(4):
        c = _giai_dieu(30, seed=500 + i, sr=sr)
        clips.append(c)
        _ghi_wav(d / f"clip_{i}.wav", c, sr)

    dai = _giai_dieu(360, seed=777, sr=sr)
    vi_tri = {0: 30, 1: 160, 2: 300}          # clip index -> giây bắt đầu
    for idx, giay in vi_tri.items():
        i0 = int(giay * sr)
        dai[i0:i0 + len(clips[idx])] = clips[idx]
    vp = tmp_path_factory.mktemp("nguon") / "vi_pham.wav"
    _ghi_wav(vp, dai, sr)
    return {"kho": str(d), "vi_pham": str(vp), "vi_tri": vi_tri, "thoi_luong": 360.0}


@pytest.fixture()
def engine(tmp_path):
    """Engine sạch, dữ liệu ghi vào thư mục tạm — không đụng data/ thật."""
    from engine import Engine
    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Engine(
        root=goc,
        data_dir=str(tmp_path / "data"),
        out_dir=str(tmp_path / "ketqua"),
    )


def M(clip="a.opus", start=0.0, hashes=1000, matched=60.0, offset=0.0):
    """Tạo nhanh một Match giả để test thuần logic (không cần audio)."""
    from engine import Match
    return Match(clip=clip, start_s=start, end_s=start + matched, matched_s=matched,
                 clip_offset_s=offset, hashes=hashes, confidence="x")
