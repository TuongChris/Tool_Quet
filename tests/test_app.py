# -*- coding: utf-8 -*-
"""Smoke test giao diện Streamlit."""

from streamlit.testing.v1 import AppTest


def test_giao_dien_khong_loi_render():
    at = AppTest.from_file("app.py", default_timeout=120).run()
    assert not at.exception
