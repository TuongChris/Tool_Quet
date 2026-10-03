# -*- coding: utf-8 -*-
"""Nhãn vùng Đầu/Giữa/Cuối phải theo thời lượng VIDEO thật (CLAUDE.md mục 12–13).

Bất biến: hễ `ScanResult.duration_s` được đổi từ độ dài FILE đang xử lý sang độ dài VIDEO
thật, mọi `Match.vung` tính từ nó phải được dán lại theo độ dài mới. Có đúng ba chỗ như vậy:
tải một phần (test trong `test_quet_tang_dan.py`), âm thanh YouTube ngắn hơn video thật, và
file tải về thiếu đuôi (cả hai trong `_xu_ly_tai_thieu`).

Ranh giới 1/3–2/3 khoá bằng giá trị viết tay — không dùng chính hàm đang test để tính kỳ vọng.
Luật hiện hành: p < 1/3 → «Đầu»; p < 2/3 → «Giữa»; còn lại «Cuối» (điểm ranh giới thuộc vùng
SAU).

Đường YouTube chạy THẬT (`scan_youtube`, `_xu_ly_tai_thieu`, báo cáo 16 cột, giao diện); chỉ
giả ở ranh giới tải/quét file như `test_phan_bien_vong_hai.py`. `scan_media` giả trả đúng thứ
bản thật trả cho một FILE: `duration_s` là độ dài file, và nhãn vùng do CHÍNH `_gan_chi_so`
dán theo độ dài file đó (`_scan_media` gọi `_gan_chi_so(tat_ca, tong)`, `tong` = độ dài file).
"""

import os
from pathlib import Path

import pytest

from conftest import M
from engine import Engine, Match, ScanResult

_B = "B [bbbbbbbbbbb].opus"
_ID = "abcdefghijk"


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


def _engine_yt(tmp_path, dai_video, **cfg):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.db_clips = lambda **k: [{"ten": _B, "duong_dan": _B, "so_hash": 20000}]
    for ten, gia_tri in cfg.items():
        setattr(e.config, ten, gia_tri)
    e.youtube_info = lambda url: {"title": "Video", "id": _ID, "channel": "",
                                  "channel_id": "", "channel_url": "", "upload_date": "",
                                  "duration": float(dai_video)}
    return e


def _quet_file_gia(e, do_dai, dat=(), loai=()):
    """`scan_media` giả: kết quả của FILE `path` dài `do_dai[path]` giây, đã phủ trọn file.

    `dat` / `loai`: giây bắt đầu của các đoạn đạt chuẩn / bị loại của clip B."""
    def quet(path, **k):
        dai = do_dai[path]
        r = ScanResult(source_name="Video", duration_s=dai, vung_da_khop=[(0.0, dai)])
        r.matches = [Match(clip=_B, start_s=s, end_s=s + 60, matched_s=60.0,
                           clip_offset_s=0.0, hashes=900, confidence="Cao") for s in dat]
        r.matches_loai = [Match(clip=_B, start_s=s, end_s=s + 9, matched_s=9.0,
                                clip_offset_s=0.0, hashes=30, confidence="Thấp")
                          for s in loai]
        e._gan_chi_so([*r.matches, *r.matches_loai], dai)
        return r
    return quet


def _yt_file_ngan(tmp_path, cac_lan_tai, dat=(), loai=()):
    """Video 3000 s tải TRỌN (không tải một phần); lần tải thứ i ra một file MỚI dài
    `cac_lan_tai[i]` giây — ngắn hơn video thì đi vào `_xu_ly_tai_thieu`."""
    e = _engine_yt(tmp_path, 3000, quet_tang_dan=False, keep_downloads=True, top_n=1)
    os.makedirs(e.dl_dir, exist_ok=True)
    do_dai, lan_tai = {}, []

    def tai(url, vid, progress=None, gioi_han_giay=None):
        tep = os.path.join(e.dl_dir, f"{vid}.webm")
        do_dai[tep] = float(cac_lan_tai[len(lan_tai)])
        lan_tai.append(gioi_han_giay)
        Path(tep).write_bytes(b"x" * 64)
        return tep

    e.download_audio = tai
    e.duration_of = lambda p: do_dai.get(p)
    e.scan_media = _quet_file_gia(e, do_dai, dat, loai)
    return e, lan_tai


def test_file_thieu_duoi_dan_nhan_theo_video_that(tmp_path):
    """Video 3000 s, file tải về chỉ 1500 s, đoạn khớp ở giây 700: theo video là «Đầu»
    (700/3000), theo file là «Giữa» (700/1500). Đã có bằng chứng nên không tải lại; phần
    đuôi thành vùng lỗi và `duration_s` đổi về 3000 s. Đoạn bị loại ở giây 1400 cũng phải
    theo video: «Giữa» (1400/3000), không phải «Cuối» (1400/1500)."""
    e, lan_tai = _yt_file_ngan(tmp_path, [1500], dat=[700.0], loai=[1400.0])
    kq = e.scan_youtube(f"https://youtu.be/{_ID}", luu_lich_su=False)
    assert len(lan_tai) == 1 and kq.status == "ok", kq.note
    assert kq.ly_do_pham_vi == "tai_thieu" and kq.duration_s == 3000.0
    assert [m.vung for m in kq.matches] == ["Đầu"]
    assert [m.vung for m in kq.matches_loai] == ["Giữa"]
    assert _vung_bao_cao(e, kq) == "Đầu"


def test_am_thanh_ngan_hon_dan_nhan_ca_doan_bi_loai(tmp_path):
    """Không đoạn nào đạt chuẩn nên tải lại MỘT lần; bản tải lại ngắn ĐÚNG như cũ nên nhận là
    âm thanh YouTube ngắn hơn video thật — `duration_s` đổi về 3000 s. Đoạn bị loại cũng mang
    nhãn vùng (`_gan_chi_so` dán cho MỌI ứng viên) — phải theo video thật."""
    e, lan_tai = _yt_file_ngan(tmp_path, [1500, 1500], loai=[700.0])
    kq = e.scan_youtube(f"https://youtu.be/{_ID}", luu_lich_su=False)
    assert len(lan_tai) == 2 and kq.status == "ok", kq.note
    assert kq.ly_do_pham_vi == "am_thanh_ngan_hon" and kq.duration_s == 3000.0
    assert not kq.matches
    assert [m.vung for m in kq.matches_loai] == ["Đầu"]


def test_bang_ket_qua_giao_dien_hien_nhan_vung_theo_video_that(tmp_path, monkeypatch):
    """AppTest: kết quả của đường tải một phần (chỉ tải 720 s đầu của video 3000 s, năm đoạn
    ở 10–600 s) hiện trên bảng kết quả với cột «Vùng» theo video thật — đều là «Đầu». Theo
    file 720 s thì 300/450/600 s là Giữa/Giữa/Cuối."""
    from streamlit.testing.v1 import AppTest

    e = _engine_yt(tmp_path / "quet", 3000, quet_tang_dan=True, tai_mot_phan=True,
                   quet_tang_dan_tu_gio=0.5, quet_tang_dan_buoc_gio=0.2, top_n=5)
    do_dai, lan_tai = {}, []

    def tai(url, vid, progress=None, gioi_han_giay=None):
        lan_tai.append(gioi_han_giay)
        tep = str(tmp_path / f"{vid}__p720.webm")
        do_dai[tep] = 720.0
        return tep

    e.download_audio = tai
    e.scan_media = _quet_file_gia(e, do_dai, dat=[10.0, 150.0, 300.0, 450.0, 600.0])
    kq = e.scan_youtube(f"https://youtu.be/{_ID}", luu_lich_su=False)
    assert lan_tai == [720.0], "đủ 5/5 đoạn trong 720 s đầu thì không tải nốt"
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
