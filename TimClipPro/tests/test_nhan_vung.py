# -*- coding: utf-8 -*-
"""Nhãn vùng Đầu/Giữa/Cuối phải theo thời lượng VIDEO thật (CLAUDE.md mục 12–13).

Bất biến: hễ `ScanResult.duration_s` được đổi từ độ dài FILE đang xử lý sang độ dài VIDEO
thật, mọi `Match.vung` tính từ nó phải được dán lại theo độ dài mới. Có đúng ba chỗ như vậy:
tải một phần (test trong `test_quet_tang_dan.py`), âm thanh YouTube ngắn hơn video thật, và
file tải về thiếu đuôi (cả hai trong `_xu_ly_tai_thieu`).

Ranh giới 1/3–2/3 khoá bằng giá trị viết tay — không dùng chính hàm đang test để tính kỳ vọng.
Luật hiện hành: p < 1/3 → «Đầu»; p < 2/3 → «Giữa»; còn lại «Cuối» (điểm ranh giới thuộc vùng
SAU).
"""

import pytest

from conftest import M
from engine import Engine, ScanObjective
from golden_quet import Dat, KichBan, chay

_B = "B [bbbbbbbbbbb].opus"


@pytest.mark.parametrize("start, nhan", [
    (0.0, "Đầu"),
    (299.999, "Đầu"),
    (300.0, "Giữa"),
    (599.999, "Giữa"),
    (600.0, "Cuối"),
    (899.0, "Cuối"),
])
def test_ranh_gioi_mot_phan_ba_va_hai_phan_ba(start, nhan):
    assert Engine._nhan_vung(start, 900.0) == nhan


@pytest.mark.parametrize("dai", [0.0, -10.0])
def test_thoi_luong_khong_hop_le_thi_khong_dan_nhan(dai):
    assert Engine._nhan_vung(100.0, dai) == ""


def test_gan_chi_so_dung_dung_ranh_gioi_do(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    ds = [M(start=s) for s in (299.999, 300.0, 599.999, 600.0)]
    e._gan_chi_so(ds, 900.0)
    assert [m.vung for m in ds] == ["Đầu", "Giữa", "Giữa", "Cuối"]


def _vung_bao_cao(e, kq) -> str:
    return e.to_rows([kq])[0][Engine.HEADER.index("Vùng")]


def test_file_thieu_duoi_dan_nhan_theo_video_that(tmp_path, monkeypatch):
    """Video 3000 s, file tải về chỉ 1500 s, đoạn khớp ở giây 700: theo video là «Đầu»
    (700/3000), theo file là «Giữa» (700/1500). Đã có bằng chứng nên không tải lại; phần
    đuôi thành vùng lỗi và `duration_s` đổi về 3000 s."""
    kb = KichBan("thieu_duoi", "youtube", 3000,
                 {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
                 (Dat(_B, 700, 120),), tai=(1500, 1500))
    kq, e, *_ = chay(kb, tmp_path, monkeypatch)
    assert kq.ly_do_pham_vi == "tai_thieu" and kq.duration_s == 3000.0
    assert [m.vung for m in kq.matches] == ["Đầu"]
    assert _vung_bao_cao(e, kq) == "Đầu"


def test_am_thanh_ngan_hon_dan_nhan_theo_video_that(tmp_path, monkeypatch):
    """Lượt thu thập luôn tải lại file ngắn; bản tải lại ngắn ĐÚNG như cũ nên nhận là âm
    thanh YouTube ngắn hơn video thật — `duration_s` đổi về 3000 s, nhãn phải theo đó."""
    kb = KichBan("am_thanh_ngan", "youtube", 3000,
                 {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
                 (Dat(_B, 700, 120),), tai=(1500, 1500))
    kq, e, *_ = chay(kb, tmp_path, monkeypatch, muc_tieu=ScanObjective("collect"))
    assert kq.ly_do_pham_vi == "am_thanh_ngan_hon" and kq.duration_s == 3000.0
    assert [m.vung for m in kq.matches] == ["Đầu"]
    assert _vung_bao_cao(e, kq) == "Đầu"


def test_bang_ket_qua_giao_dien_hien_nhan_vung_theo_video_that(tmp_path, monkeypatch):
    """AppTest: kết quả THẬT của engine (chỉ tải 720 s đầu của video 3000 s, năm đoạn ở
    10–600 s) hiện trên bảng kết quả với cột «Vùng» theo video thật — đều là «Đầu»."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from golden_quet import KICH_BAN

    kb = next(k for k in KICH_BAN if k.ten == "yt_top5_nam_doan_ba_clip_trong_phan_tai_dau")
    kq, *_ = chay(kb, tmp_path / "quet", monkeypatch, luu_lich_su=False)
    assert kq.quet_mot_phan and kq.duration_s == 3000.0 and len(kq.matches) == 5

    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))
    app = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app), default_timeout=120).run()
    assert not at.exception
    at.session_state.job.update({"running": False, "kind": "scan", "results": [kq],
                                 "error": "", "da_day_sheet": True})
    at.run()
    assert not at.exception
    bang = next(d.value for d in at.dataframe if "Vùng" in d.value.columns)
    assert list(bang["Vùng"]) == ["Đầu"] * 5


def test_am_thanh_ngan_hon_che_do_cu_dan_nhan_ca_doan_bi_loai(tmp_path, monkeypatch):
    """Chế độ cũ: không đoạn nào đạt chuẩn nên tải lại; bản tải lại ngắn như cũ. Đoạn bị
    loại cũng mang nhãn vùng (`_gan_chi_so` dán cho MỌI ứng viên) — phải theo video thật."""
    kb = KichBan("am_thanh_ngan_cu", "youtube", 3000,
                 {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
                 (Dat(_B, 700, 30),), tai=(1500, 1500))
    kq, *_ = chay(kb, tmp_path, monkeypatch)
    assert kq.ly_do_pham_vi == "am_thanh_ngan_hon" and kq.duration_s == 3000.0
    ung_vien = [*kq.matches, *kq.matches_loai]
    assert ung_vien and all(m.vung == "Đầu" for m in ung_vien)
