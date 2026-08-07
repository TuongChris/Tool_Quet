# -*- coding: utf-8 -*-
"""Chạy app.py thật qua AppTest và khẳng định terminal KHÔNG còn hai lỗi cũ.

Đây là test tái hiện sát nhất với triệu chứng người dùng thấy:
    pyarrow.lib.ArrowInvalid: Could not convert '—' with type str...
    Thread 'scan-xxxxxxxx': missing ScriptRunContext!
    KeyError: st.session_state has no key "sheet_link"
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pyarrow as pa
from streamlit.testing.v1 import AppTest

from engine import ScanResult
from scan_ui import build_scan_status_dataframe

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _kq(vid, matches=0):
    r = ScanResult(source_name=f"Video {vid}", source_ref=f"https://youtu.be/{vid}")
    r.source_id = vid
    r.matches = [object()] * matches
    r.so_dat_nguong = matches
    r.job_id = 1
    return r


def test_quet_batch_khong_sinh_canh_bao_arrow_hay_scriptruncontext(
    tmp_path, monkeypatch, caplog
):
    import streamlit

    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception

    # sheet_link PHẢI có sẵn ngay từ lần render đầu (cau_hinh.GIA_TRI_GIAO_DIEN_MAC_DINH).
    assert "sheet_link" in at.session_state
    assert "sheet_auto" in at.session_state
    assert "sheet_dang_ngang" in at.session_state

    monkeypatch.setattr(streamlit, "rerun", lambda *a, **k: None)

    eng = at.session_state.eng
    # Bật auto Sheets để đi đúng đường đã gây lỗi, nhưng chặn mọi lần gửi thật.
    at.session_state.sheet_auto = True
    at.session_state.sheet_link = "https://docs.google.com/spreadsheets/d/ABC/edit"
    da_gui = []
    at.session_state.scan_sheet_worker.sender = (
        lambda sheet_link, header, rows: da_gui.append(sheet_link) or len(rows)
    )

    urls = ["aaa", "bbb", "ccc"]

    def scan_youtube(url, progress=None, luu_lich_su=True):
        if progress:
            progress(0.5, "Đang so khớp vân tay... khúc 1/2")
        time.sleep(0.12)
        return _kq(url, matches=2 if url != "bbb" else 0)

    eng.scan_youtube = scan_youtube
    eng.to_rows_ngang = lambda ket: [["x"] * 34]

    controller = at.session_state.scan_controller
    cfg_worker = at.session_state.scan_sheet_worker
    cfg_worker.start()

    from scan_jobs import ScanLaunchConfig
    from sheet_delivery import SheetDelivery, khoa_giao_hang

    cfg = ScanLaunchConfig(auto_sheet=True, sheet_link=at.session_state.sheet_link,
                           dang_ngang=True)

    def sau_moi_video(index, tong, ket_qua):
        rows = eng.to_rows_ngang([ket_qua])
        khoa = khoa_giao_hang(cfg.sheet_id, "", "ngang", ket_qua.job_id,
                              ket_qua.source_id, rows)
        cfg_worker.enqueue(SheetDelivery(
            delivery_key=khoa, source_id=ket_qua.source_id,
            source_name=ket_qua.source_name, header=["h"] * 34, rows=rows,
            sheet_link=cfg.sheet_link,
        ))
        controller.ghi_nhan_giao_hang(index, khoa)

    with caplog.at_level(logging.WARNING):
        controller.start(urls, "youtube", on_result=sau_moi_video)
        at.session_state.job.update({
            "running": True, "pct": 0.0, "msg": "", "results": [], "error": "",
            "kind": "scan", "da_day_sheet": True, "scan_batch_id": "test",
        })

        so_lan_ve = 0
        han = time.monotonic() + 60
        while controller.running and time.monotonic() < han and so_lan_ve < 4:
            at.run()
            assert not at.exception
            so_lan_ve += 1

        han = time.monotonic() + 60
        while controller.running and time.monotonic() < han:
            time.sleep(0.02)

    ban_ghi = "\n".join(r.getMessage() for r in caplog.records)

    # AppTest ở bare mode tự sinh cảnh báo cho 'MainThread' — đó là artefact của
    # harness, không phải lỗi. Lỗi thật là cảnh báo mang tên THREAD NỀN, ví dụ
    # "Thread 'scan-2924d458': missing ScriptRunContext!".
    thieu_ctx_o_worker = [
        dong for dong in ban_ghi.splitlines()
        if "missing ScriptRunContext" in dong and "MainThread" not in dong
    ]
    assert not thieu_ctx_o_worker, thieu_ctx_o_worker
    assert "on_video_callback_failed" not in ban_ghi, (
        "Callback vẫn hỏng — thread nền còn chạm Streamlit"
    )
    assert "ArrowInvalid" not in ban_ghi
    assert "Serialization of dataframe to Arrow table was unsuccessful" not in ban_ghi

    anh = controller.snapshot()
    assert anh.completed == 3 and anh.failed == 0
    # Bảng hiển thị cuối cùng vẫn chuyển Arrow thẳng được.
    pa.Table.from_pandas(
        build_scan_status_dataframe(anh.videos, cfg_worker.snapshot())
    )
    assert da_gui and all(s == cfg.sheet_link for s in da_gui)
    cfg_worker.stop()
