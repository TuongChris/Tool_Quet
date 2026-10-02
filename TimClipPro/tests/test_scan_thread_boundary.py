# -*- coding: utf-8 -*-
"""Thread nền tuyệt đối không chạm Streamlit.

Root cause của «missing ScriptRunContext» + `KeyError: sheet_link`: callback chạy
trong scan worker đọc `st.session_state`. Thread nền không có ScriptRunContext nên
Streamlit trả về một SessionState rỗng — key *có* tồn tại ở main thread vẫn báo thiếu.
Vì vậy khởi tạo thêm key KHÔNG phải cách sửa; phải cắt hẳn phụ thuộc.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import pytest

from engine import ScanResult
from scan_jobs import ScanJobController, ScanLaunchConfig
from sheet_delivery import SheetDelivery, SheetDeliveryWorker

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Guard cấu trúc
# ---------------------------------------------------------------------------

def _chi_lay_code(duong_dan: Path) -> str:
    """Bỏ bình luận và chuỗi, chỉ giữ code thật.

    Cần thiết vì chính các module này có docstring GIẢI THÍCH vì sao không được
    chạm `st.session_state`; tìm chuỗi thô sẽ bắt nhầm phần giải thích đó.
    """
    import io
    import tokenize

    giu = []
    with open(duong_dan, "rb") as fh:
        for tok in tokenize.tokenize(io.BytesIO(fh.read()).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            giu.append(tok.string)
    return " ".join(giu)


@pytest.mark.parametrize("ten_file", ["scan_jobs.py", "sheet_delivery.py", "scan_ui.py",
                                      "common_original.py", "common_original_jobs.py"])
def test_module_chay_o_thread_nen_khong_cham_streamlit(ten_file):
    code = _chi_lay_code(REPO / ten_file)
    assert not re.search(r"\bimport streamlit\b", code), ten_file
    assert not re.search(r"\bst\s*\.\s*session_state\b", code), ten_file
    assert not re.search(r"\bst\s*\.\s*(write|error|warning|success|rerun)\b", code), ten_file


def test_engine_khong_import_streamlit():
    assert "import streamlit" not in _chi_lay_code(REPO / "engine.py")


def test_guard_bat_duoc_vi_pham_that(tmp_path):
    """Guard phải thực sự bắt được, không phải luôn xanh."""
    xau = tmp_path / "xau.py"
    xau.write_text(
        "import streamlit as st\n"
        "def f():\n"
        "    return st.session_state.sheet_link\n",
        encoding="utf-8",
    )
    code = _chi_lay_code(xau)
    assert re.search(r"\bimport streamlit\b", code)
    assert re.search(r"\bst\s*\.\s*session_state\b", code)


# ---------------------------------------------------------------------------
# Snapshot cấu hình
# ---------------------------------------------------------------------------

def test_config_bat_bien_va_chuan_hoa_sheet_id():
    cfg = ScanLaunchConfig(
        auto_sheet=True,
        sheet_link="https://docs.google.com/spreadsheets/d/ABC123xyz/edit#gid=0",
        dang_ngang=True,
    )

    assert cfg.sheet_id == "ABC123xyz"
    with pytest.raises(Exception):
        cfg.auto_sheet = False       # frozen dataclass


def test_config_rong_khong_no():
    cfg = ScanLaunchConfig()
    assert cfg.sheet_id == ""
    assert cfg.auto_sheet is False


# ---------------------------------------------------------------------------
# Worker không chạm Streamlit
# ---------------------------------------------------------------------------

def _kq(vid, matches=1):
    r = ScanResult(source_name=f"V{vid}", source_ref=f"https://youtu.be/{vid}")
    r.source_id = vid
    r.matches = [object()] * matches
    r.job_id = 1
    return r


def _gia_lap(engine, monkeypatch, urls, cham=0.0):
    def scan_youtube(url, progress=None, luu_lich_su=True):
        if progress:
            progress(0.5, "Đang so khớp vân tay... khúc 1/2")
        if cham:
            time.sleep(cham)
        return _kq(url)
    monkeypatch.setattr(engine, "scan_youtube", scan_youtube)


def test_callback_chay_o_thread_khac_main_va_khong_doc_session_state(engine, monkeypatch):
    """Chạy callback thật; nếu nó chạm st.session_state thì test phải đỏ."""
    import streamlit as st

    urls = ["a", "b"]
    _gia_lap(engine, monkeypatch, urls)

    vi_pham = []
    main_thread = threading.current_thread().name

    class SessionStateCam:
        def __getattr__(self, ten):
            vi_pham.append(ten)
            raise AssertionError(f"Thread nền đọc st.session_state.{ten}")

        def __getitem__(self, ten):
            vi_pham.append(ten)
            raise AssertionError(f"Thread nền đọc st.session_state[{ten!r}]")

    monkeypatch.setattr(st, "session_state", SessionStateCam())

    # Đúng cách app.py làm: chụp cấu hình TRƯỚC, ở main thread.
    cfg = ScanLaunchConfig(auto_sheet=True, sheet_link="sheet123", dang_ngang=True)
    da_xep = []
    thread_callback = []

    def sau_moi_video(index, tong, ket_qua):
        thread_callback.append(threading.current_thread().name)
        da_xep.append(SheetDelivery(
            delivery_key=f"k{index}", source_id=ket_qua.source_id,
            source_name=ket_qua.source_name, header=["A"], rows=[["1"]],
            sheet_link=cfg.sheet_link,
        ))

    controller = ScanJobController(engine)
    controller.start(urls, "youtube", on_result=sau_moi_video)
    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        time.sleep(0.01)

    assert not vi_pham, f"Thread nền đã chạm session state: {vi_pham}"
    assert len(da_xep) == 2
    assert all(t != main_thread for t in thread_callback), "Callback phải ở thread nền"
    assert all(d.sheet_link == "sheet123" for d in da_xep)


def test_sheet_worker_nhan_sheet_link_tu_cong_viec_khong_hoi_lai_ui():
    """sender nhận sheet_link kèm việc nên chạy được ở thread giao hàng."""
    nhan = []
    worker = SheetDeliveryWorker(
        sender=lambda sheet_link, header, rows: nhan.append(sheet_link) or len(rows)
    )
    worker.start()
    worker.enqueue(SheetDelivery(
        delivery_key="k", source_id="v", source_name="V",
        header=["A"], rows=[["1"]], sheet_link="sheet-abc",
    ))
    han = time.monotonic() + 15
    while worker.con_viec and time.monotonic() < han:
        time.sleep(0.01)
    worker.stop()

    assert nhan == ["sheet-abc"]


def test_callback_no_tung_van_giu_ket_qua_va_chay_tiep(engine, monkeypatch):
    """Giao hàng lỗi là chuyện của giao hàng — không được biến scan thành failed."""
    urls = ["a", "b", "c"]
    _gia_lap(engine, monkeypatch, urls)

    def callback_hong(index, tong, ket_qua):
        raise RuntimeError("Sheets sập")

    controller = ScanJobController(engine)
    controller.start(urls, "youtube", on_result=callback_hong)
    han = time.monotonic() + 30
    while controller.running and time.monotonic() < han:
        time.sleep(0.01)

    anh = controller.snapshot()
    assert anh.completed == 3, "Callback lỗi không được làm video thành failed"
    assert anh.failed == 0
    assert len(controller.results()) == 3
