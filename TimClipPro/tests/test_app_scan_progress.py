# -*- coding: utf-8 -*-
"""Smoke Streamlit: màn hình quét hiện số liệu THẬT khi batch còn chạy."""

from __future__ import annotations

import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from engine import ScanResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _van_ban(at) -> str:
    phan = []
    for nhom in (at.markdown, at.info, at.caption, at.warning, at.error,
                 at.header, at.subheader):
        phan.extend(str(i.value) for i in nhom)
    phan.extend(str(i.label) for i in at.metric)
    phan.extend(str(i.value) for i in at.metric)
    return "\n".join(phan)


def _kq(vid, matches=0):
    r = ScanResult(source_name=f"Video {vid}", source_ref=f"https://youtu.be/{vid}")
    r.source_id = vid
    r.matches = [object()] * matches
    r.so_dat_nguong = matches
    r.job_id = 1
    return r


def test_man_hinh_quet_hien_tien_do_va_bang_tung_video_khi_dang_chay(tmp_path, monkeypatch):
    import streamlit

    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception

    # Màn hình tiến độ tự gọi st.rerun; vô hiệu hoá để chụp đúng một khung hình.
    monkeypatch.setattr(streamlit, "rerun", lambda *a, **k: None)

    eng = at.session_state.eng
    urls = ["aaa", "bbb", "ccc"]

    def scan_youtube(url, progress=None, luu_lich_su=True):
        for pct, msg in ((0.05, "Đang lấy thông tin video..."),
                         (0.40, "Đang tải audio..."),
                         (0.80, "Đang so khớp vân tay... khúc 1/2")):
            if progress:
                progress(pct, msg)
            time.sleep(0.15)
        return _kq(url, matches=2)

    eng.scan_youtube = scan_youtube

    controller = at.session_state.scan_controller
    controller.start(urls, "youtube")
    at.session_state.job.update({
        "running": True, "pct": 0.0, "msg": "", "results": [], "error": "",
        "kind": "scan", "da_day_sheet": True, "scan_batch_id": "test",
    })

    khung = []
    han = time.monotonic() + 60
    while controller.running and time.monotonic() < han and len(khung) < 3:
        at.run()
        assert not at.exception
        khung.append(_van_ban(at))

    ghep = "\n".join(khung)
    assert "Đang quét video" in ghep
    assert "Hoàn tất" in ghep and "ETA" in ghep and "Đã chạy" in ghep
    assert any(x in ghep for x in ("Đang lấy thông tin video", "Đang tải audio",
                                   "Đang so khớp vân tay"))
    # Bảng từng video được vẽ -> phải có dataframe trên trang.
    assert len(at.dataframe) >= 1

    han = time.monotonic() + 60
    while controller.running and time.monotonic() < han:
        time.sleep(0.02)
    anh = controller.snapshot()
    assert anh.completed == 3 and anh.failed == 0
    assert len(controller.results()) == 3
