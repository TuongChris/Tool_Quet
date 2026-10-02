# -*- coding: utf-8 -*-
"""Bấm Dừng thì CẢ batch dừng, không chỉ video đang chạy (audit TCP-13).

Dùng ``Engine.scan_iter`` và ``ScanJobController`` THẬT; chỉ thay phần mạng/khớp
bằng hàm giả. Cờ huỷ thuộc về job: chỉ được xoá MỘT lần lúc bắt đầu job.
"""

import threading

import pytest

from engine import Cancelled, Engine, ScanResult
from scan_jobs import ScanJobController


@pytest.fixture
def eng(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    return e


def _info_gia(e, goi, huy_o=1, cach="trong_ham"):
    def info(url):
        goi.append({"url": url, "co_huy_luc_vao": e.cancel_event.is_set()})
        if len(goi) == huy_o:
            e.cancel()
            raise Cancelled()
        raise RuntimeError("lỗi giả lập, không gọi mạng")
    return info


def test_huy_o_video_dau_thi_video_sau_khong_chay(eng):
    goi = []
    eng.youtube_info = _info_gia(eng, goi)

    ket = list(eng.scan_iter(["https://youtu.be/aaaaaaaaaaa",
                              "https://youtu.be/bbbbbbbbbbb",
                              "https://youtu.be/ccccccccccc"]))

    assert len(goi) == 1, f"video sau vẫn chạy sau khi đã huỷ: {goi}"
    assert len(ket) == 1
    assert ket[0].status == "error" and "hủy" in ket[0].note.lower()


def test_huy_trong_callback_sau_video_thi_dung_o_ranh_gioi(eng):
    goi = []

    def info(url):
        goi.append(url)
        raise RuntimeError("lỗi giả lập")

    eng.youtube_info = info

    def on_video(i, tong, kq):
        if i == 1:
            eng.cancel()

    ket = list(eng.scan_iter(["u1", "u2", "u3"], on_video=on_video))

    assert goi == ["u1"]
    assert len(ket) == 1


def test_huy_trong_luc_khop_file_cua_batch_file(eng, tmp_path):
    for ten in ("a.wav", "b.wav"):
        (tmp_path / ten).write_bytes(b"x")
    da_khop = []

    def khop(chunks, *a, **k):
        da_khop.append(chunks)
        eng.cancel()
        raise Cancelled()

    eng.duration_of = lambda p: 100.0
    eng._cut_chunks = lambda path, *a, **k: ([str(tmp_path / "chunk_0000000.wav")], 100.0)
    eng._match_chunks = khop

    ket = list(eng.scan_iter([str(tmp_path / "a.wav"), str(tmp_path / "b.wav")],
                             source_type="file"))

    assert len(da_khop) == 1, "file thứ hai vẫn được khớp sau khi huỷ"
    assert len(ket) == 1 and ket[0].status == "error"


def test_quet_don_moi_van_xoa_co_huy_cu(eng):
    """Batch trước bị huỷ không được làm lượt quét đơn SAU đó tự huỷ."""
    eng.cancel()
    goi = []

    def info(url):
        goi.append(eng.cancel_event.is_set())
        raise RuntimeError("lỗi giả lập")

    eng.youtube_info = info
    kq = eng.scan_youtube("u1")

    assert goi == [False]
    assert kq.status == "error" and "giả lập" in kq.note


def test_controller_huy_giu_ket_qua_da_xong_va_khong_chay_tiep(eng):
    da_vao = threading.Event()
    cho_huy = threading.Event()
    goi = []

    def info(url):
        goi.append(url)
        if len(goi) == 1:
            return {"id": "aaaaaaaaaaa", "title": "Video 1", "duration": 10,
                    "channel": "", "channel_id": "", "channel_url": "",
                    "upload_date": ""}
        raise RuntimeError("lỗi giả lập")

    def tai(url, video_id, progress=None, gioi_han_giay=None):
        da_vao.set()
        cho_huy.wait(10)
        raise Cancelled()

    eng.youtube_info = info
    eng.download_audio = tai
    ctl = ScanJobController(eng)
    ctl.start(["u1", "u2", "u3"])
    assert da_vao.wait(10)
    ctl.cancel()
    cho_huy.set()
    ctl._thread.join(20)

    assert not ctl.running
    assert goi == ["u1"], f"batch vẫn chạy tiếp sau khi Dừng: {goi}"
    anh = ctl.snapshot()
    assert [v.scan_status for v in anh.videos][1:] == ["queued", "queued"]
    assert len(ctl.results()) == 1 and isinstance(ctl.results()[0], ScanResult)
