# -*- coding: utf-8 -*-
"""TCP-05 trên AUDIO THẬT: video bị tăng tốc 2% để né vân tay, đoạn bị chèn bắt đầu từ
giữa clip gốc. Mốc đầu clip và "khớp từ giây thứ" phải đúng hệ tọa độ.

Dựng dữ liệu (FFmpeg thật, audfprint thật):
* clip gốc 600 s;
* video vi phạm 900 s nền khác hẳn, chèn đoạn clip[300 s → 600 s] đã ``atempo=1.02``
  (nhanh hơn 2%, giữ cao độ) tại mốc P = 400 s — vắt qua ranh giới khúc 480 s.

Ngưỡng chấp nhận để MẶC ĐỊNH của sản phẩm: lệch 2% làm lượt quét thường chỉ còn vài
mảnh vụn dưới ngưỡng, nên kết quả buộc phải đến từ lượt BÙ TỐC ĐỘ — đúng đường TCP-05.

Kỳ vọng tính TRỰC TIẾP từ cách dựng (không gọi hàm đang kiểm):
* trên video, đầu clip gốc (t_clip = 0) ở P − 300/1,02 ≈ 105,88 s;
* "khớp từ giây thứ" (trục clip) = 300 + (vùng_khớp − P)·1,02.
Code cũ trừ thẳng t_clip nên báo sớm hơn khoảng (1 − 1/1,02)·300 ≈ 5,9 s.

Dung sai 1 s: bước thời gian audfprint là 256/11025 ≈ 23 ms; hệ số đọc từ độ trôi sai
≤ 0,05% (docs/DA_TOC_DO.md §2), tức ≤ 0,15 s ở t_clip = 300 s. 1 s rộng hơn hẳn hai
nguồn đó nhưng hẹp hơn nhiều so với lỗi 5,9 s cần bắt.
"""

import shutil
import subprocess
import wave

import numpy as np
import pytest

from conftest import _ghi_wav, _giai_dieu

SR = 22050
TOC_DO = 1.02          # video phát nhanh hơn bản gốc 2%
P = 400.0              # mốc chèn trên video
CAT_DAU = 300.0        # đoạn chèn bắt đầu từ giây thứ 300 của clip gốc


def _doc_wav(path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        du_lieu = w.readframes(w.getnframes())
    return np.frombuffer(du_lieu, dtype=np.int16).astype(np.float64) / 32000.0


@pytest.mark.slow
def test_moc_dau_clip_dung_khi_video_bi_tang_toc(engine, tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("cần ffmpeg trong PATH")
    kho = tmp_path / "kho"
    kho.mkdir()
    clip = _giai_dieu(600, seed=9101, sr=SR)
    _ghi_wav(kho / "ref.wav", clip, SR)

    doan = tmp_path / "doan.wav"
    _ghi_wav(doan, clip[int(CAT_DAU * SR):], SR)
    doan_nhanh = tmp_path / "doan_nhanh.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(doan),
                    "-filter:a", f"atempo={TOC_DO}", "-ar", str(SR), "-ac", "1",
                    str(doan_nhanh)], check=True)
    chen = _doc_wav(doan_nhanh)

    nen = _giai_dieu(900, seed=9102, sr=SR)
    i0 = int(P * SR)
    nen[i0:i0 + len(chen)] = chen[: len(nen) - i0]
    video = tmp_path / "vi_pham.wav"
    _ghi_wav(video, nen, SR)

    engine.config.chunk_s = 300
    engine.config.overlap_s = 60
    engine.config.top_n = 1
    engine.config.quet_da_toc_do = True
    engine.add_kho("Test", str(kho))
    engine.build_database(str(kho), "new")

    kq = engine.scan_media(str(video))

    assert kq.status == "ok", kq.note
    assert kq.chan_doan and kq.chan_doan.toc_do_tim_duoc, \
        "điều kiện test: kết quả phải đến từ lượt BÙ TỐC ĐỘ"
    m = next(m for m in kq.matches if m.clip == "ref.wav")
    dau_clip = P - CAT_DAU / TOC_DO
    assert m.start_s == pytest.approx(dau_clip, abs=1.0)
    assert m.clip_bat_dau_s == pytest.approx(dau_clip, abs=1.0)
    assert m.vung_khop_s >= P - 1.0
    assert m.clip_offset_s == pytest.approx(
        CAT_DAU + (m.vung_khop_s - P) * TOC_DO, abs=1.0)
