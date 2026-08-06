# -*- coding: utf-8 -*-
"""Smoke test giao diện Streamlit."""

from streamlit.testing.v1 import AppTest


def test_giao_dien_khong_loi_render(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "ketqua"
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(out_dir))
    at = AppTest.from_file("app.py", default_timeout=120).run()
    assert not at.exception
    assert at.session_state.eng.data_dir == str(data_dir)
    assert at.session_state.eng.out_dir == str(out_dir)
    dinh_dang = next(
        radio
        for radio in at.sidebar.radio
        if radio.label == "Định dạng đẩy lên Sheets"
    )
    assert dinh_dang.value == "Ngang (khớp bảng 34 cột)"

    dinh_dang.set_value("Dọc (chi tiết, 15 cột)").run()
    assert at.session_state.sheet_dang_ngang is False
