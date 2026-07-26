# -*- coding: utf-8 -*-
"""Smoke test giao diện Streamlit."""

from streamlit.testing.v1 import AppTest


def test_giao_dien_khong_loi_render():
    at = AppTest.from_file("app.py", default_timeout=120).run()
    assert not at.exception
    dinh_dang = next(
        radio
        for radio in at.sidebar.radio
        if radio.label == "Định dạng đẩy lên Sheets"
    )
    assert dinh_dang.value == "Ngang (khớp bảng 34 cột)"

    dinh_dang.set_value("Dọc (chi tiết, 15 cột)").run()
    assert at.session_state.sheet_dang_ngang is False
