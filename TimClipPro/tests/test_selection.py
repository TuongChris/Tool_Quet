# -*- coding: utf-8 -*-
"""Test thuật toán chọn lọc kết quả (_chon_loc) — thuần logic, chạy trong mili giây."""
from conftest import M

from engine import Config, Engine

DUR = 3 * 3600.0   # video vi phạm 3 tiếng


def _eng(**kw):
    cfg = Config(top_n=5, min_hash_floor=1000, min_hash_strong=5000, **kw)
    e = Engine.__new__(Engine)          # không cần khởi tạo đầy đủ cho test thuần logic
    e.config = cfg
    return e


def test_loai_bo_ket_qua_duoi_nguong():
    e = _eng()
    ds = [M("a", 100, 9000), M("b", 200, 500), M("c", 300, 999)]
    chon, loai = e._chon_loc(ds, DUR)
    assert [m.clip for m in chon] == ["a"]
    assert len(loai) == 2


def test_phan_bo_deu_khi_ket_qua_manh_don_o_dau_video():
    """Bẫy kinh điển: 5 kết quả mạnh nhất đều nằm ở đầu video."""
    e = _eng()
    ds = [M(f"dau{i}", 100 + i * 200, 9000 - i) for i in range(5)]
    ds += [M(f"giua{i}", 5000 + i * 500, 6000 - i) for i in range(3)]
    ds += [M(f"cuoi{i}", 9000 + i * 500, 5500 - i) for i in range(3)]
    chon, _ = e._chon_loc(ds, DUR)
    assert len(chon) == 5
    # Phải trải ra cả 3 phần ba của video, không dồn vào đầu
    phan = {int(m.start_s / DUR * 3) for m in chon}
    assert phan == {0, 1, 2}


def test_ket_qua_tra_ve_theo_thu_tu_thoi_gian():
    e = _eng()
    ds = [M("a", 9000, 6000), M("b", 100, 8000), M("c", 5000, 7000)]
    chon, _ = e._chon_loc(ds, DUR)
    assert [m.start_s for m in chon] == sorted(m.start_s for m in chon)


def test_uu_tien_clip_khac_nhau():
    e = _eng()
    ds = [M("trung", i * 1800, 9000 - i) for i in range(6)]
    ds += [M("khac", 5000, 5200)]
    chon, _ = e._chon_loc(ds, DUR)
    assert "khac" in [m.clip for m in chon]


def test_khong_vuot_qua_top_n():
    e = _eng()
    ds = [M(f"c{i}", i * 600, 6000) for i in range(30)]
    chon, _ = e._chon_loc(ds, DUR)
    assert len(chon) == 5


def test_it_ket_qua_hon_top_n_van_tra_ve_du():
    e = _eng()
    ds = [M("a", 100, 8000), M("b", 5000, 7000)]
    chon, loai = e._chon_loc(ds, DUR)
    assert len(chon) == 2 and loai == []


def test_tat_ca_bi_loai_thi_tra_ve_rong_nhung_giu_danh_sach_loai():
    """Lưới an toàn: giao diện cần matches_loai để cảnh báo ngưỡng quá cao."""
    e = _eng()
    ds = [M(f"c{i}", i * 100, 300) for i in range(8)]
    chon, loai = e._chon_loc(ds, DUR)
    assert chon == [] and len(loai) == 8


def test_khong_biet_thoi_luong_van_chay():
    e = _eng()
    chon, _ = e._chon_loc([M("a", 10, 8000), M("b", 20, 7000)], 0)
    assert len(chon) == 2


def test_tat_phan_bo_deu_thi_lay_theo_hash():
    e = _eng(phan_bo_deu=False)
    e.config.top_n = 3
    ds = [M(f"c{i}", i * 100, 9000 - i * 100) for i in range(8)]
    chon, _ = e._chon_loc(ds, DUR)
    assert [m.hashes for m in chon] == [9000, 8900, 8800]


def test_danh_sach_rong():
    e = _eng()
    assert e._chon_loc([], DUR) == ([], [])
