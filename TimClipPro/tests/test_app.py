# -*- coding: utf-8 -*-
"""Smoke test giao diện Streamlit."""

import json
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
    # Tab «Danh sách video trong kho» chỉ vẽ nút khi đã có ít nhất một kho.
    kho_dir = tmp_path / "kho_gia"
    kho_dir.mkdir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "khos.json").write_text(json.dumps({
        "dang_dung": "KhoTest",
        "danh_sach": [{"ten": "KhoTest", "thu_muc": str(kho_dir),
                       "db": "kho_test.pklz"}],
    }, ensure_ascii=False), encoding="utf-8")
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
    # Tab mới. Các assert cũ ở trên chính là thứ bắt được ca đổi số tab làm rơi
    # mất một khối cũ — đừng bỏ chúng đi.
    assert "📋 Xem danh sách video trong kho" in button_labels
    assert any(sb.label == "Chọn kho muốn liệt kê" for sb in at.selectbox)
    dinh_dang = next(
        radio
        for radio in at.sidebar.radio
        if radio.label == "Định dạng đẩy lên Sheets"
    )
    assert dinh_dang.value == "Ngang (khớp bảng 34 cột)"

    dinh_dang.set_value("Dọc (chi tiết, 15 cột)").run()
    assert at.session_state.sheet_dang_ngang is False


def _du_lieu_hai_kho(tmp_path, monkeypatch):
    """Hai kho thật trên đĩa, mỗi kho một video có tên khác nhau rõ rệt."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))

    danh_sach = []
    for ten, vid, title in (("KhoA", "aaaaaaaaaaa", "Video của kho A"),
                            ("KhoB", "bbbbbbbbbbb", "Video của kho B")):
        thu_muc = tmp_path / ten
        thu_muc.mkdir()
        ten_file = f"20250115 - {title} [{vid}].opus"
        (thu_muc / ten_file).write_bytes(b"")
        (thu_muc / "clips_meta.json").write_text(json.dumps({ten_file: {
            "id": vid, "title": title, "url": f"https://youtu.be/{vid}",
            "upload_date": "20250115", "duration": 60,
        }}, ensure_ascii=False), encoding="utf-8")
        danh_sach.append({"ten": ten, "thu_muc": str(thu_muc),
                          "db": f"kho_{ten.lower()}.pklz"})

    (data_dir / "khos.json").write_text(
        json.dumps({"dang_dung": "KhoA", "danh_sach": danh_sach},
                   ensure_ascii=False), encoding="utf-8")
    return data_dir


def test_tab_danh_sach_quet_duoc_va_lay_dung_ten_video(tmp_path, monkeypatch):
    _du_lieu_hai_kho(tmp_path, monkeypatch)
    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()

    nut = next(b for b in at.button if b.label == "📋 Xem danh sách video trong kho")
    at = nut.click().run()

    assert not at.exception
    kq = at.session_state.dsv_ket_qua
    assert kq.so_video == 1
    assert kq.dong[0].ten_video == "Video của kho A"
    assert kq.dong[0].chinh_xac is True
    assert at.session_state.dsv_kho_da_quet == "KhoA"
    assert any("📤 Đẩy 1 video lên Google Sheets (ghi đè)" == b.label for b in at.button)


def test_doi_kho_sau_khi_quet_thi_khong_hien_danh_sach_kho_cu(tmp_path, monkeypatch):
    """Bẫy nguy hiểm nhất: hiện danh sách kho A dưới nhãn kho B rồi đẩy nhầm."""
    _du_lieu_hai_kho(tmp_path, monkeypatch)
    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    at = next(b for b in at.button
              if b.label == "📋 Xem danh sách video trong kho").click().run()
    assert at.session_state.dsv_kho_da_quet == "KhoA"

    chon = next(sb for sb in at.selectbox if sb.label == "Chọn kho muốn liệt kê")
    at = chon.set_value("KhoB").run()

    assert not at.exception
    # Kết quả cũ vẫn nằm trong session nhưng KHÔNG được vẽ, và nút đẩy phải biến mất.
    assert at.session_state.dsv_kho_da_quet == "KhoA"
    assert not any("Đẩy" in b.label for b in at.button)
    assert not any("Video của kho A" in str(getattr(el, "value", ""))
                   for el in list(at.success) + list(at.info))
    # Trang tính đích phải đổi theo kho đang chọn, không kẹt ở kho cũ.
    assert any("DanhSachVideo_KhoB" in c.value for c in at.caption)


def test_kho_mat_thu_muc_thi_bao_loi_tieng_viet_khong_sap_app(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    (data_dir / "khos.json").write_text(json.dumps({
        "dang_dung": "KhoMat",
        "danh_sach": [{"ten": "KhoMat", "thu_muc": str(tmp_path / "khong_co"),
                       "db": "kho_mat.pklz"}],
    }, ensure_ascii=False), encoding="utf-8")

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    at = next(b for b in at.button
              if b.label == "📋 Xem danh sách video trong kho").click().run()

    assert not at.exception
    assert any("KhoMat" in e.value and "thư mục" in e.value for e in at.error)
    assert "dsv_ket_qua" not in at.session_state


def test_kho_khong_co_metadata_thi_giao_dien_hien_canh_bao(tmp_path, monkeypatch):
    """Không có chốt này thì xoá `for cb in kq.canh_bao: st.warning(cb)` vẫn xanh,
    và người dùng nhận cả kho tên đã bị làm sạch mà tưởng là tên thật."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    kho = tmp_path / "KhoChepTay"
    kho.mkdir()
    # Chép tay file vào kho, KHÔNG có clips_meta.json.
    (kho / "20250115 - SML Movie_ The World Cup! [gRZah-YY0FM].opus").write_bytes(b"")
    (data_dir / "khos.json").write_text(json.dumps({
        "dang_dung": "KhoChepTay",
        "danh_sach": [{"ten": "KhoChepTay", "thu_muc": str(kho),
                       "db": "kho_chep_tay.pklz"}],
    }, ensure_ascii=False), encoding="utf-8")

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    at = next(b for b in at.button
              if b.label == "📋 Xem danh sách video trong kho").click().run()

    assert not at.exception
    assert any("clips_meta.json" in w.value for w in at.warning)
    assert at.session_state.dsv_ket_qua.so_chinh_xac == 0


def test_dropdown_mo_san_dung_kho_dang_dung_o_thanh_ben(tmp_path, monkeypatch):
    """Không có `index`, Streamlit lấy phần tử số 0 — người dùng quét kho này rồi
    đẩy đè lên trang tính của kho kia, không hoàn tác được."""
    data_dir = _du_lieu_hai_kho(tmp_path, monkeypatch)
    # KhoB đứng SAU trong danh sách nhưng đang là kho dùng.
    d = json.loads((data_dir / "khos.json").read_text(encoding="utf-8"))
    d["dang_dung"] = "KhoB"
    (data_dir / "khos.json").write_text(json.dumps(d, ensure_ascii=False),
                                        encoding="utf-8")

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    chon = next(sb for sb in at.selectbox if sb.label == "Chọn kho muốn liệt kê")
    assert chon.value == "KhoB"


def test_kho_chua_gan_thu_muc_luu_duoc_ngay_trong_tab(tmp_path, monkeypatch):
    """`update_kho` chỉ được gọi từ `build_database`, nên không có ô này thì cách
    duy nhất để gán thư mục là chạy tạo vân tay hàng giờ."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    kho = tmp_path / "KhoThat"
    kho.mkdir()
    (kho / "20250115 - A [aaaaaaaaaaa].opus").write_bytes(b"")
    (data_dir / "khos.json").write_text(json.dumps({
        "dang_dung": "ChuaGan",
        "danh_sach": [{"ten": "ChuaGan", "thu_muc": "", "db": "kho_x.pklz"}],
    }, ensure_ascii=False), encoding="utf-8")

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    o = next(t for t in at.text_input if "Đường dẫn thư mục audio" in t.label)
    at = o.set_value(str(kho)).run()
    at = next(b for b in at.button if b.label == "💾 Lưu thư mục cho kho này").click().run()

    assert not at.exception
    ghi = json.loads((data_dir / "khos.json").read_text(encoding="utf-8"))
    assert ghi["danh_sach"][0]["thu_muc"] == str(kho)


def test_luu_thu_muc_gan_dung_kho_dang_chon_khong_phai_kho_dang_dung(tmp_path, monkeypatch):
    """Dropdown ở tab này độc lập với kho đang dùng ở thanh bên."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    kho_moi = tmp_path / "ThuMucMoi"
    kho_moi.mkdir()
    kho_a = tmp_path / "KhoA"
    kho_a.mkdir()
    (data_dir / "khos.json").write_text(json.dumps({
        "dang_dung": "KhoA",
        "danh_sach": [
            {"ten": "KhoA", "thu_muc": str(kho_a), "db": "kho_a.pklz"},
            {"ten": "KhoB", "thu_muc": "", "db": "kho_b.pklz"},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    chon = next(sb for sb in at.selectbox if sb.label == "Chọn kho muốn liệt kê")
    at = chon.set_value("KhoB").run()
    o = next(t for t in at.text_input if "Đường dẫn thư mục audio" in t.label)
    at = o.set_value(str(kho_moi)).run()
    at = next(b for b in at.button if b.label == "💾 Lưu thư mục cho kho này").click().run()

    ghi = {k["ten"]: k["thu_muc"]
           for k in json.loads((data_dir / "khos.json").read_text(encoding="utf-8"))["danh_sach"]}
    assert ghi["KhoB"] == str(kho_moi)
    assert ghi["KhoA"] == str(kho_a), "KHÔNG được gán nhầm sang kho đang dùng"


def test_doi_kho_giai_thich_thay_vi_de_man_hinh_trong(tmp_path, monkeypatch):
    _du_lieu_hai_kho(tmp_path, monkeypatch)
    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    at = next(b for b in at.button
              if b.label == "📋 Xem danh sách video trong kho").click().run()
    chon = next(sb for sb in at.selectbox if sb.label == "Chọn kho muốn liệt kê")
    at = chon.set_value("KhoB").run()

    assert any("vừa đổi sang kho «KhoB»" in i.value for i in at.info)
    assert any("vẫn còn" in i.value for i in at.info)
