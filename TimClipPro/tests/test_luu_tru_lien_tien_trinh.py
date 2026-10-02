# -*- coding: utf-8 -*-
"""Ghi JSON an toàn GIỮA CÁC PROCESS (audit TCP-03).

Ba lỗi khác nhau, mỗi lỗi một test:

* hai writer dùng chung một file tạm → writer A báo "ok" nhưng file chứa dữ liệu
  của B, còn B nhận FileNotFoundError;
* đọc-sửa-ghi không cùng một khoá → mất cập nhật (entry của một bên biến mất);
* phục hồi/sao lưu không cùng giao thức → bản sao tốt bị thay bằng file hỏng.

Lịch xen kẽ được điều khiển bằng ``multiprocessing.Event`` (start method ``spawn``
như Windows), không dựa vào ``sleep`` ngẫu nhiên.
"""

import json
import multiprocessing
import os

import pytest

import luu_tru

CHO_S = 30


def _writer_dung_o_replace(path, nhan, dang_thu, da_san_sang, cho_phep, ket_qua):
    """Ghi JSON nhưng dừng ngay trước os.replace cho tới khi được phép."""
    import luu_tru as lt

    goc = lt.os.replace

    def replace_cho(src, dst):
        if os.path.abspath(str(dst)) == os.path.abspath(path):
            da_san_sang.set()
            if not cho_phep.wait(CHO_S):
                raise TimeoutError("điều phối test thất bại")
        return goc(src, dst)

    lt.os.replace = replace_cho
    dang_thu.set()
    try:
        lt.ghi_json_an_toan(path, {"writer": nhan})
        ket_qua.put((nhan, "ok"))
    except Exception as e:  # noqa: BLE001
        ket_qua.put((nhan, type(e).__name__))


# B đã vào hàm ghi mà trong ngần này giây vẫn chưa chạm tới replace thì coi là đang
# bị khoá chặn đúng như mong muốn. Mã KHÔNG khoá chạm tới đó trong vài mili giây.
CUA_SO_LOAI_TRU_S = 3.0


def test_hai_writer_khong_dung_chung_file_tam_va_khong_ai_nhan_ket_qua_cua_ai(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    path = str(tmp_path / "clips_meta.json")
    luu_tru.ghi_json_an_toan(path, {"writer": "cu"})
    ev = {k: ctx.Event() for k in ("a_thu", "a_toi", "a_di", "b_thu", "b_toi", "b_di")}
    ket_qua = ctx.Queue()
    a = ctx.Process(target=_writer_dung_o_replace,
                    args=(path, "A", ev["a_thu"], ev["a_toi"], ev["a_di"], ket_qua))
    b = ctx.Process(target=_writer_dung_o_replace,
                    args=(path, "B", ev["b_thu"], ev["b_toi"], ev["b_di"], ket_qua))
    try:
        a.start()
        assert ev["a_toi"].wait(CHO_S), "A không tới được bước replace"
        b.start()
        assert ev["b_thu"].wait(CHO_S), "B không khởi động được"
        # A đang ở giữa giao dịch. B KHÔNG được chạm tới replace lúc này: nếu chạm
        # được nghĩa là hai writer đang cùng ghi một file (lỗi của audit).
        b_chen_vao = ev["b_toi"].wait(CUA_SO_LOAI_TRU_S)
        ev["a_di"].set()
        assert ev["b_toi"].wait(CHO_S), "B không bao giờ ghi được"
        ev["b_di"].set()
        nhan = dict(ket_qua.get(timeout=CHO_S) for _ in range(2))
    finally:
        for k in ("a_di", "b_di"):
            ev[k].set()
        for p in (a, b):
            p.join(CHO_S)
            if p.is_alive():
                p.kill()
    assert not b_chen_vao, "B chen vào giữa giao dịch của A"
    assert nhan == {"A": "ok", "B": "ok"}
    # B vào sau A nên bản cuối là của B — và đó là đúng nội dung B đã ghi.
    assert json.loads(open(path, encoding="utf-8").read()) == {"writer": "B"}
    assert not list(tmp_path.glob("clips_meta.json*.tmp")), "sót file tạm"


def _them_entry(path, ten, vao_giao_dich, cho_phep, ket_qua):
    import luu_tru as lt

    def sua(du_lieu):
        vao_giao_dich.set()
        if not cho_phep.wait(CHO_S):
            raise TimeoutError("điều phối test thất bại")
        du_lieu[ten] = {"id": ten}

    try:
        lt.cap_nhat_json(path, sua, mac_dinh={})
        ket_qua.put((ten, "ok"))
    except Exception as e:  # noqa: BLE001
        ket_qua.put((ten, type(e).__name__))


def _them_entry_ngay(path, ten, dang_thu, ket_qua):
    import luu_tru as lt

    dang_thu.set()
    try:
        lt.cap_nhat_json(path, lambda d: d.__setitem__(ten, {"id": ten}), mac_dinh={})
        ket_qua.put((ten, "ok"))
    except Exception as e:  # noqa: BLE001
        ket_qua.put((ten, type(e).__name__))


def test_doc_sua_ghi_hai_process_khong_mat_entry_nao(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    path = str(tmp_path / "clips_meta.json")
    luu_tru.ghi_json_an_toan(path, {"co_san": {"id": "co_san"}})
    a_trong, a_duoc_di, b_dang_thu = ctx.Event(), ctx.Event(), ctx.Event()
    ket_qua = ctx.Queue()
    a = ctx.Process(target=_them_entry, args=(path, "a", a_trong, a_duoc_di, ket_qua))
    b = ctx.Process(target=_them_entry_ngay, args=(path, "b", b_dang_thu, ket_qua))
    try:
        a.start()
        assert a_trong.wait(CHO_S), "A không vào được giao dịch"
        b.start()
        assert b_dang_thu.wait(CHO_S)
        a_duoc_di.set()
        nhan = dict(ket_qua.get(timeout=CHO_S) for _ in range(2))
    finally:
        a_duoc_di.set()
        for p in (a, b):
            p.join(CHO_S)
            if p.is_alive():
                p.kill()
    assert nhan == {"a": "ok", "b": "ok"}
    du_lieu = json.loads(open(path, encoding="utf-8").read())
    assert set(du_lieu) == {"co_san", "a", "b"}, "mất cập nhật của một bên"


def _giu_khoa_toi_khi_duoc_tha(path, da_giu, tha):
    import luu_tru as lt

    with lt.khoa_json(path):
        da_giu.set()
        tha.wait(CHO_S)


def test_khoa_bi_giu_qua_han_thi_bao_loi_ro_va_khong_dung_vao_du_lieu(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    path = str(tmp_path / "khos.json")
    luu_tru.ghi_json_an_toan(path, {"dang_dung": "A"})
    da_giu, tha = ctx.Event(), ctx.Event()
    p = ctx.Process(target=_giu_khoa_toi_khi_duoc_tha, args=(path, da_giu, tha))
    try:
        p.start()
        assert da_giu.wait(CHO_S)
        with pytest.raises(luu_tru.LoiKhoaDuLieu) as loi:
            luu_tru.cap_nhat_json(path, lambda d: d.update(dang_dung="B"), han_cho_s=0.3)
        assert "PID" in str(loi.value), "phải nêu ai đang giữ khoá"
    finally:
        tha.set()
        p.join(CHO_S)
        if p.is_alive():
            p.kill()
    assert json.loads(open(path, encoding="utf-8").read()) == {"dang_dung": "A"}
    # Khoá đã được thả thì giao dịch kế tiếp chạy bình thường.
    luu_tru.cap_nhat_json(path, lambda d: d.update(dang_dung="B"))
    assert json.loads(open(path, encoding="utf-8").read()) == {"dang_dung": "B"}


def test_file_tam_cua_writer_da_chet_duoc_don_o_lan_ghi_sau(tmp_path):
    path = tmp_path / "khos.json"
    luu_tru.ghi_json_an_toan(str(path), {"lan": 1})
    # Giả lập process chết giữa chừng: để lại file tạm kiểu cũ lẫn kiểu mới.
    (tmp_path / "khos.json.tmp").write_text('{"lan": 9', encoding="utf-8")
    (tmp_path / "khos.json.1234.abcd1234.tmp").write_text("{", encoding="utf-8")

    luu_tru.ghi_json_an_toan(str(path), {"lan": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"lan": 2}
    assert not list(tmp_path.glob("khos.json*.tmp"))


def test_ban_sao_tot_khong_bi_thay_bang_file_chinh_hong(tmp_path):
    path = tmp_path / "clips_meta.json"
    luu_tru.ghi_json_an_toan(str(path), {"lan": 1})
    luu_tru.ghi_json_an_toan(str(path), {"lan": 2})   # .bak = lan 1
    path.write_text("{hỏng giữa chừng", encoding="utf-8")

    # Ghi trực tiếp (không đọc trước) không được lấy file hỏng làm bản sao.
    luu_tru.ghi_json_an_toan(str(path), {"lan": 3})

    bak = json.loads((tmp_path / "clips_meta.json.bak").read_text(encoding="utf-8"))
    assert bak == {"lan": 1}
    assert json.loads(path.read_text(encoding="utf-8")) == {"lan": 3}


def test_cap_nhat_khi_file_chinh_hong_thi_phuc_hoi_tu_ban_sao_roi_moi_sua(tmp_path):
    path = tmp_path / "clips_meta.json"
    luu_tru.ghi_json_an_toan(str(path), {"a": 1})
    luu_tru.ghi_json_an_toan(str(path), {"a": 1, "b": 2})   # .bak = {"a": 1}
    path.write_text("{hỏng", encoding="utf-8")

    luu_tru.cap_nhat_json(str(path), lambda d: d.__setitem__("c", 3), mac_dinh={})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "c": 3}
    assert list(tmp_path.glob("clips_meta.json.hong.*")), "file hỏng phải được giữ lại"


def test_cap_nhat_tra_ve_gia_tri_cua_ham_sua_va_khong_ghi_khi_ham_loi(tmp_path):
    path = tmp_path / "khos.json"
    luu_tru.ghi_json_an_toan(str(path), {"x": 1})
    truoc = path.read_bytes()

    def sua_loi(d):
        d["x"] = 2
        raise ValueError("dừng giữa chừng")

    with pytest.raises(ValueError):
        luu_tru.cap_nhat_json(str(path), sua_loi)
    assert path.read_bytes() == truoc
    assert luu_tru.cap_nhat_json(str(path), lambda d: d["x"] + 10) == 11


def test_khoa_vao_lai_duoc_trong_cung_thread(tmp_path):
    path = str(tmp_path / "a.json")
    with luu_tru.khoa_json(path):
        with luu_tru.khoa_json(path):
            luu_tru.ghi_json_an_toan(path, {"ok": True})
        assert luu_tru.doc_json_an_toan(path) == {"ok": True}


def test_khong_sinh_file_khoa_cho_tung_ban_ghi(tmp_path):
    """Bản ghi chẩn đoán có tên duy nhất: không được đẻ ra một file khoá mỗi bản."""
    for i in range(5):
        luu_tru.ghi_json_an_toan(str(tmp_path / f"ban_ghi_{i}.json"), {"i": i})
    khac_json = [p.name for p in tmp_path.iterdir()
                 if not p.name.endswith(".json")]
    assert len(khac_json) <= 1, khac_json
