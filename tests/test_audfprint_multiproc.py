# -*- coding: utf-8 -*-
"""Regression cho bản vá nhánh đa nhân của audfprint.

Ba tính chất phải giữ:

1. Cả ba điểm vá đều được gắn — quên một cái là mất event hoặc quay lại nguy cơ treo.
2. Tiến trình cha KHÔNG giữ đầu ghi pipe: worker chết phải thành lỗi rõ ràng,
   không phải treo vĩnh viễn (bản vendored treo mãi mãi trong tình huống này).
3. Nhiều tiến trình con cùng ghi stdout không được làm mất/ghép dòng event.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import audfprint_progress_runner as runner

REPO = Path(__file__).resolve().parents[1]


def test_cai_dat_day_du_ba_diem_va():
    class Analyzer:
        def ingest(self, hashtable, filename):
            return 1.0, 1

    class AudfprintGia:
        make_ht_from_list = "goc"
        multiproc_add = "goc"

    class AnalyzeGia:
        pass

    AnalyzeGia.Analyzer = Analyzer
    goc_ingest = Analyzer.ingest

    runner.cai_dat_instrumentation(AudfprintGia, AnalyzeGia)

    assert AudfprintGia.make_ht_from_list is runner.instrumented_make_ht_from_list
    assert AudfprintGia.multiproc_add is runner.instrumented_multiproc_add
    assert AnalyzeGia.Analyzer.ingest is not goc_ingest


class _HashTabGia:
    """Đủ thuộc tính mà instrumented_multiproc_add cần, ghi lại các lần merge."""

    hashbits = 4
    depth = 2
    maxtimebits = 4

    def __init__(self):
        self.da_merge = []

    def merge(self, khac):
        self.da_merge.append(khac)


def worker_chet_ngay(*args, **kwargs):
    """Worker chết mà KHÔNG gửi gì qua pipe. Phải ở cấp module vì Windows dùng spawn."""
    raise SystemExit(3)


def test_worker_chet_khong_gui_gi_thi_bao_loi_chu_khong_treo(monkeypatch):
    """Bản vendored giữ tx[ix] mở nên recv() chờ mãi mãi. Bản này phải raise."""
    monkeypatch.setattr(runner, "_worker_ghi_hash_table", worker_chet_ngay)
    monkeypatch.setattr(runner, "CHO_WORKER_S", 20.0)

    bat_dau = time.monotonic()
    with pytest.raises(RuntimeError, match="không trả kết quả|không phản hồi"):
        runner.instrumented_multiproc_add(
            analyzer=None,
            hash_tab=_HashTabGia(),
            filename_iter=["a.wav", "b.wav"],
            report=lambda msgs: None,
            ncores=2,
        )
    assert time.monotonic() - bat_dau < 20.0, "Phải phát hiện worker chết ngay, không chờ hết timeout."


def test_khong_con_file_tam_sau_khi_that_bai(monkeypatch, tmp_path):
    truoc = set(Path(runner.tempfile.gettempdir()).glob("timclip_ht_*"))
    monkeypatch.setattr(runner, "_worker_ghi_hash_table", worker_chet_ngay)
    monkeypatch.setattr(runner, "CHO_WORKER_S", 20.0)
    with pytest.raises(RuntimeError):
        runner.instrumented_multiproc_add(
            analyzer=None,
            hash_tab=_HashTabGia(),
            filename_iter=["a.wav"],
            report=lambda msgs: None,
            ncores=1,
        )
    sau = set(Path(runner.tempfile.gettempdir()).glob("timclip_ht_*"))
    assert sau <= truoc, "Thư mục tạm của hash table phải được dọn kể cả khi lỗi."


KICH_BAN_GHI_CHUNG = """
import multiprocessing, os, sys
sys.path.insert(0, r"{repo}")
import audfprint_progress_runner as runner

def phat(chi_so):
    for lan in range(40):
        runner._emit("clip_started", file="clip_%d_%d.opus" % (chi_so, lan),
                     phase="fingerprinting", process_pid=os.getpid())

if __name__ == "__main__":
    ps = [multiprocessing.Process(target=phat, args=(i,)) for i in range(8)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
"""


def test_tam_tien_trinh_con_ghi_chung_stdout_khong_mat_hay_ghep_dong(tmp_path):
    """8 worker × 40 event = 320 dòng; tất cả phải nguyên vẹn và parse được JSON."""
    script = tmp_path / "ghi_chung.py"
    script.write_text(KICH_BAN_GHI_CHUNG.format(repo=str(REPO)), encoding="utf-8")

    ket_qua = subprocess.run(
        [sys.executable, "-u", str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180,
    )
    assert ket_qua.returncode == 0, ket_qua.stderr[-500:]

    dong = [d for d in ket_qua.stdout.splitlines() if d.strip()]
    assert len(dong) == 8 * 40, f"Mất hoặc ghép dòng: nhận {len(dong)}/320"
    for d in dong:
        assert d.startswith(runner.PREFIX), f"Dòng bị ghép: {d[:120]!r}"
        payload = json.loads(d[len(runner.PREFIX):])
        assert payload["event"] == "clip_started"
        assert payload["file"].startswith("clip_")
