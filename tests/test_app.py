# -*- coding: utf-8 -*-
"""Smoke test giao diện Streamlit."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

# AppTest giải đường dẫn tương đối theo file gọi nó (tests/), không theo CWD.
# Dùng đường dẫn tuyệt đối để test chạy đúng dù pytest được gọi từ thư mục nào.
APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def test_giao_dien_khong_loi_render(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "ketqua"
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(out_dir))
    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception
    assert at.session_state.eng.data_dir == str(data_dir)
    assert at.session_state.eng.out_dir == str(out_dir)
    assert at.session_state.fingerprint_controller.engine is at.session_state.eng
    button_labels = {button.label for button in at.button}
    assert "🔍 Kiểm tra metadata báo cáo" in button_labels
    assert "🧪 Xem trước khôi phục offline" in button_labels
    assert "🛠️ Khôi phục metadata offline" in button_labels
    assert "Bắt đầu vá metadata thiếu" in button_labels
    dinh_dang = next(
        radio
        for radio in at.sidebar.radio
        if radio.label == "Định dạng đẩy lên Sheets"
    )
    assert dinh_dang.value == "Ngang (khớp bảng 34 cột)"

    dinh_dang.set_value("Dọc (chi tiết, 15 cột)").run()
    assert at.session_state.sheet_dang_ngang is False
