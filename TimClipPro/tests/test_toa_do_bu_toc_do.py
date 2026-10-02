# -*- coding: utf-8 -*-
"""Mốc thời gian khi bù tốc độ phải nằm đúng hệ tọa độ (audit TCP-05).

Ba trục khác nhau, không được trộn:
* trục KHÚC ĐÃ BIẾN ĐỔI (``t_khuc``) — audfprint đo trên đây;
* trục VIDEO ĐANG QUÉT — báo cáo, link nhảy mốc dùng trục này;
* trục CLIP GỐC (``t_clip``) — "khớp từ giây thứ mấy của clip".

Khúc ``chunk_<O>_k<k>`` được làm nhanh lên ``k`` lần, nên một điểm ở ``t_khuc`` của khúc
nằm ở ``O + k·t_khuc`` trên video. Trên trục đã hiệu chỉnh, clip gốc phát đúng tốc độ,
nên mốc ĐẦU clip gốc (``t_clip = 0``) nằm ở ``t_khuc − t_clip`` của khúc, tức
``O + k·(t_khuc − t_clip)`` trên video. Giá trị kỳ vọng dưới đây tính TRỰC TIẾP từ công
thức này, không gọi lại hàm đang được kiểm.
"""

import pytest

from engine import Engine, Match
from toc_do_khop import ma_he_so


def _eng(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.db_clips = lambda **k: [{"ten": "reference.opus", "duong_dan": "reference.opus",
                               "so_hash": 100000}]
    return e


def _ten_khuc(tmp_path, offset: int, k: float) -> str:
    duoi = "" if k == 1.0 else f"_k{ma_he_so(k)}"
    return str(tmp_path / f"chunk_{offset:07d}{duoi}.wav")


def _khop_tho(e, tmp_path, dong: list) -> list:
    """Chạy PARSER thật của `_match_chunks` trên các dòng audfprint dựng sẵn."""
    def chay(lenh, on_line=None, **kw):
        with open(lenh[lenh.index("--opfile") + 1], "w", encoding="utf-8") as f:
            for khuc, t_q, t_r, dai, so_hash in dong:
                f.write(f"Matched {dai:.1f} s starting at {t_q:.1f} s in {khuc} to time "
                        f"{t_r:.1f} s in reference.opus with {so_hash} of "
                        f"{so_hash * 2} common hashes at rank 0\n")
        return 0, []
    e._run_stream = chay
    return e._match_chunks(sorted({d[0] for d in dong}), workspace=str(tmp_path))


@pytest.mark.parametrize("k", [1.0, 0.98, 0.95, 1.03])
@pytest.mark.parametrize("offset,t_q,t_r", [(0, 700.0, 0.0), (3420, 700.0, 600.0),
                                           (7000, 1500.0, 1200.0)])
def test_moc_dau_clip_dung_cong_thuc_affine(tmp_path, k, offset, t_q, t_r):
    e = _eng(tmp_path)
    dai = 90.0
    tho = _khop_tho(e, tmp_path, [(_ten_khuc(tmp_path, offset, k), t_q, t_r, dai, 3000)])
    m = e._merge(tho)[0]

    dau_clip = offset + k * (t_q - t_r)          # mốc đầu clip gốc trên trục video
    vung_khop = offset + k * t_q                 # nơi vùng khớp bắt đầu trên trục video
    assert m.start_s == pytest.approx(max(0.0, dau_clip), abs=1e-6)
    assert m.clip_bat_dau_s == pytest.approx(max(0.0, dau_clip), abs=1e-6)
    assert m.vung_khop_s == pytest.approx(vung_khop, abs=1e-6)
    assert m.end_s == pytest.approx(vung_khop + k * dai, abs=1e-6)
    assert m.matched_s == pytest.approx(k * dai, abs=1e-6)
    if dau_clip >= 0:
        # "Khớp từ giây thứ mấy CỦA CLIP" là trục clip gốc: đúng bằng t_clip.
        assert m.clip_offset_s == pytest.approx(t_r, abs=1e-6)


def test_ca_cua_audit_3420_098_700_600(tmp_path):
    e = _eng(tmp_path)
    tho = _khop_tho(e, tmp_path, [(_ten_khuc(tmp_path, 3420, 0.98), 700.0, 600.0, 100.0,
                                   2000)])
    m = e._merge(tho)[0]
    assert m.start_s == pytest.approx(3518.0, abs=1e-6), "code cũ trả 3506 (lệch 12 s)"


def test_hai_manh_qua_ranh_gioi_khuc_gop_thanh_mot_va_dung_moc(tmp_path):
    """Cùng một lần xuất hiện cắt qua ranh giới hai khúc (k = 0,98)."""
    e = _eng(tmp_path)
    k = 0.98
    dau_clip = 2352.0                                   # mốc đầu clip trên video
    # Mảnh A ở khúc 0: tham chiếu 1000 → 1150 s.
    t_q_a = (dau_clip + k * 1000.0 - 0) / k
    # Mảnh B ở khúc 3420: tiếp tục tham chiếu 1150 → 1300 s.
    t_q_b = (dau_clip + k * 1150.0 - 3420) / k
    tho = _khop_tho(e, tmp_path, [
        (_ten_khuc(tmp_path, 0, k), t_q_a, 1000.0, 150.0, 3000),
        (_ten_khuc(tmp_path, 3420, k), t_q_b, 1150.0, 150.0, 3000),
    ])
    ket = e._merge(tho)
    assert len(ket) == 1, "hai mảnh của cùng một lần xuất hiện phải gộp làm một"
    m = ket[0]
    assert m.start_s == pytest.approx(dau_clip, abs=0.2)
    assert m.clip_offset_s == pytest.approx(1000.0, abs=0.2)
    assert m.end_s == pytest.approx(dau_clip + k * 1300.0, abs=0.2)


def test_khong_gop_manh_khac_phep_bien_doi(tmp_path):
    """Mảnh của lượt thường (k=1) và lượt đã bù (k≠1) không cùng trục khúc."""
    e = _eng(tmp_path)
    tho = _khop_tho(e, tmp_path, [
        (_ten_khuc(tmp_path, 0, 1.0), 500.0, 100.0, 30.0, 40),
        (_ten_khuc(tmp_path, 0, 0.98), 510.0, 100.0, 120.0, 3000),
    ])
    he_so = sorted(round(x["he_so"], 5) for x in tho)
    assert he_so == [0.98, 1.0]
    assert len(e._merge(tho)) == 2


def test_duong_k_bang_1_cho_ket_qua_y_het_cong_thuc_cu(tmp_path):
    """Đường không bù tốc độ không được đổi một bit nào (kể cả ca clip bắt đầu trước
    đầu video, bị kẹp về 0)."""
    e = _eng(tmp_path)
    dong = [(_ten_khuc(tmp_path, 3420, 1.0), 40.0, 3500.0, 60.0, 900),
            (_ten_khuc(tmp_path, 0, 1.0), 300.0, 20.0, 80.0, 1200)]
    tho = _khop_tho(e, tmp_path, dong)
    ket = sorted(e._merge(tho), key=lambda m: m.vung_khop_s)

    def cu(offset, t_q, t_r, dai, so_hash):
        bat_dau = offset + t_q
        dau = max(0.0, bat_dau - t_r)
        return Match(clip="reference.opus", start_s=dau, end_s=bat_dau + dai,
                     matched_s=dai, clip_offset_s=bat_dau - dau, hashes=so_hash,
                     confidence="", clip_bat_dau_s=dau, vung_khop_s=bat_dau)

    ky_vong = sorted([cu(0, 300.0, 20.0, 80.0, 1200), cu(3420, 40.0, 3500.0, 60.0, 900)],
                     key=lambda m: m.vung_khop_s)
    for m, mk in zip(ket, ky_vong):
        for truong in ("start_s", "end_s", "matched_s", "clip_offset_s",
                       "clip_bat_dau_s", "vung_khop_s", "hashes"):
            assert getattr(m, truong) == pytest.approx(getattr(mk, truong)), truong
