# -*- coding: utf-8 -*-
"""Chọn kết quả đại diện: chất lượng trước, dễ kiểm tra chỉ để phá hoà.

Thứ tự giá trị không được đảo:
    đúng đắn kỹ thuật → chất lượng bằng chứng → rõ ràng/liên tục
    → thuận tiện kiểm tra → phá hoà tất định
"""

from __future__ import annotations

import random

import pytest

from engine import Config, Match, chi_phi_kiem_tra, chon_dai_dien

GIO = 3600.0


def M(clip, start, hashes, matched=600.0):
    return Match(
        clip=clip, start_s=start, end_s=start + matched, matched_s=matched,
        clip_offset_s=0.0, hashes=hashes, confidence="x",
    )


def _khoa(manh_tu: int = 5000):
    """Khoá chất lượng giống hệt `uu_tien` thật của engine."""
    return lambda m: (m.hashes >= manh_tu, True, m.hashes)


def chon(ung_vien, duration, dung_sai=0.03, manh_tu=5000):
    return chon_dai_dien(ung_vien, duration, dung_sai, _khoa(manh_tu))


# ---------------------------------------------------------------------------
# Nguyên tắc số 1: chất lượng luôn thắng vị trí
# ---------------------------------------------------------------------------

def test_case1_match_manh_o_cuoi_thang_match_yeu_o_dau():
    """Không được để đoạn yếu đầu video vượt đoạn mạnh hơn hẳn ở cuối."""
    yeu_dau = M("a.opus", start=0.05 * GIO, hashes=7000)
    manh_cuoi = M("b.opus", start=0.90 * GIO, hashes=10000)

    assert chon([yeu_dau, manh_cuoi], GIO) is manh_cuoi


def test_case1b_chenh_lech_lon_thi_vi_tri_khong_co_y_nghia():
    som = M("a.opus", start=0.0, hashes=5100)
    sau = M("b.opus", start=0.95 * GIO, hashes=20000)

    assert chon([som, sau], GIO) is sau


def test_bac_bang_chung_manh_khong_bi_dung_sai_pha():
    """Ứng viên dưới ngưỡng 'mạnh' không được coi là ngang bằng ứng viên trên."""
    duoi_nguong = M("a.opus", start=0.0, hashes=4990)          # < 5000
    tren_nguong = M("b.opus", start=0.95 * GIO, hashes=5010)   # >= 5000

    assert chon([duoi_nguong, tren_nguong], GIO) is tren_nguong


# ---------------------------------------------------------------------------
# Nguyên tắc số 2: gần tương đương thì ưu tiên dễ kiểm tra
# ---------------------------------------------------------------------------

def test_case2_gan_tuong_duong_thi_chon_doan_som_hon():
    sau = M("a.opus", start=0.85 * GIO, hashes=10000)
    som = M("b.opus", start=0.10 * GIO, hashes=9800)     # kém 2%, trong dung sai

    assert chon([sau, som], GIO) is som


def test_case5_compilation_8_tieng_chon_doan_dau():
    tam_gio = 8 * GIO
    som = M("a.opus", start=20 * 60, hashes=9900)          # 00:20
    sau = M("b.opus", start=6.5 * GIO, hashes=10000)       # 06:30

    assert chon([sau, som], tam_gio) is som


def test_case4_moi_thu_bang_nhau_thi_chon_doan_som_hon():
    a = M("a.opus", start=0.12 * GIO, hashes=8000)
    b = M("b.opus", start=0.78 * GIO, hashes=8000)

    assert chon([b, a], GIO) is a


def test_khong_co_nguong_cung_50_phan_tram():
    """Đoạn ở 55% vẫn thắng đoạn ở 60% nếu ngang bằng — không có vách 50%."""
    a = M("a.opus", start=0.55 * GIO, hashes=8000)
    b = M("b.opus", start=0.60 * GIO, hashes=8000)

    assert chon([b, a], GIO) is a


# ---------------------------------------------------------------------------
# Thời lượng phải được bảo vệ
# ---------------------------------------------------------------------------

def test_case3_doan_ngan_o_dau_khong_duoc_thang_doan_dai_ro_rang():
    """20 giây không thể coi là tương đương 15 phút dù số hash xấp xỉ."""
    ngan_som = M("a.opus", start=0.02 * GIO, hashes=9900, matched=20.0)
    dai_giua = M("b.opus", start=0.22 * GIO, hashes=10000, matched=900.0)

    assert chon([ngan_som, dai_giua], GIO) is dai_giua


def test_thoi_luong_chenh_it_thi_van_coi_la_ngang_bang():
    sau = M("a.opus", start=0.80 * GIO, hashes=10000, matched=900.0)
    som = M("b.opus", start=0.10 * GIO, hashes=9800, matched=890.0)

    assert chon([sau, som], GIO) is som


# ---------------------------------------------------------------------------
# Dữ liệu thiếu / không hợp lệ
# ---------------------------------------------------------------------------

def test_case6_khong_biet_thoi_luong_video_van_chay_va_uu_tien_giay_tuyet_doi():
    som = M("a.opus", start=120.0, hashes=9900)
    sau = M("b.opus", start=9000.0, hashes=10000)

    assert chon([sau, som], 0.0) is som          # duration = 0
    assert chon([sau, som], None) is som         # duration = None


def test_case7_start_am_khong_lam_no():
    xau = M("a.opus", start=-50.0, hashes=9900)
    tot = M("b.opus", start=0.50 * GIO, hashes=10000)

    assert chon([xau, tot], GIO) in (xau, tot)
    assert chi_phi_kiem_tra(xau, GIO)[0] >= 0.0


def test_mot_ung_vien_duy_nhat_thi_tra_ve_luon():
    chi_mot = M("a.opus", start=0.99 * GIO, hashes=1200)
    assert chon([chi_mot], GIO) is chi_mot


def test_danh_sach_rong_bao_loi_ro_rang():
    with pytest.raises(ValueError, match="Không có ứng viên"):
        chon([], GIO)


def test_dung_sai_bang_khong_thi_thuan_chat_luong():
    sau = M("a.opus", start=0.90 * GIO, hashes=10000)
    som = M("b.opus", start=0.05 * GIO, hashes=9999)

    assert chon([sau, som], GIO, dung_sai=0.0) is sau


# ---------------------------------------------------------------------------
# Tính tất định
# ---------------------------------------------------------------------------

def test_case10_ket_qua_khong_doi_du_dao_thu_tu_dau_vao():
    ds = [
        M("a.opus", start=0.80 * GIO, hashes=10000),
        M("b.opus", start=0.10 * GIO, hashes=9800),
        M("c.opus", start=0.50 * GIO, hashes=9850),
        M("d.opus", start=0.30 * GIO, hashes=4000),
    ]
    mong_doi = chon(list(ds), GIO)

    rng = random.Random(12345)
    for _ in range(50):
        xao = list(ds)
        rng.shuffle(xao)
        assert chon(xao, GIO) is mong_doi


def test_hoa_hoan_toan_thi_pha_hoa_theo_ten_clip():
    a = M("a.opus", start=0.30 * GIO, hashes=8000)
    b = M("b.opus", start=0.30 * GIO, hashes=8000)

    assert chon([b, a], GIO) is a
    assert chon([a, b], GIO) is a


# ---------------------------------------------------------------------------
# Chi phí kiểm tra
# ---------------------------------------------------------------------------

def test_chi_phi_dung_ca_ty_le_lan_giay_tuyet_doi():
    """45% của video 12 tiếng vẫn là hơn 5 tiếng tua — tỉ lệ một mình chưa đủ."""
    ngan = M("a.opus", start=0.45 * GIO, hashes=1)
    dai = M("b.opus", start=0.45 * 12 * GIO, hashes=1)

    assert chi_phi_kiem_tra(ngan, GIO)[0] == pytest.approx(
        chi_phi_kiem_tra(dai, 12 * GIO)[0]
    )
    # Cùng tỉ lệ thì giây tuyệt đối phá hoà: video ngắn tua nhanh hơn.
    assert chi_phi_kiem_tra(ngan, GIO) < chi_phi_kiem_tra(dai, 12 * GIO)


def test_chi_phi_khong_vuot_khoang_0_1():
    qua_xa = M("a.opus", start=10 * GIO, hashes=1)
    assert 0.0 <= chi_phi_kiem_tra(qua_xa, GIO)[0] <= 1.0


# ---------------------------------------------------------------------------
# Tích hợp với _chon_loc thật
# ---------------------------------------------------------------------------

def test_top_n_1_tra_ve_dung_mot_ket_qua(engine):
    engine.config = Config(top_n=1, min_hash_floor=1000)
    ds = [
        M("a.opus", start=0.80 * GIO, hashes=10000),
        M("b.opus", start=0.10 * GIO, hashes=9800),
        M("c.opus", start=0.40 * GIO, hashes=3000),
    ]

    chon_ds, loai = engine._chon_loc(ds, GIO)

    assert len(chon_ds) == 1
    assert len(loai) == 2


def test_top_n_1_uu_tien_doan_som_khi_ngang_bang(engine):
    engine.config = Config(top_n=1, min_hash_floor=1000)
    sau = M("a.opus", start=0.80 * GIO, hashes=10000)
    som = M("b.opus", start=0.10 * GIO, hashes=9800)

    chon_ds, _ = engine._chon_loc([sau, som], GIO)

    assert chon_ds[0] is som


def test_top_n_1_giu_doan_manh_o_cuoi_khi_vuot_troi(engine):
    engine.config = Config(top_n=1, min_hash_floor=1000)
    yeu_som = M("a.opus", start=0.05 * GIO, hashes=6000)
    manh_sau = M("b.opus", start=0.90 * GIO, hashes=15000)

    chon_ds, _ = engine._chon_loc([yeu_som, manh_sau], GIO)

    assert chon_ds[0] is manh_sau


def test_top_n_lon_van_giu_phan_bo_deu(engine):
    """Chính sách mới không được phá việc trải bằng chứng khắp video."""
    engine.config = Config(top_n=3, min_hash_floor=1000, phan_bo_deu=True)
    ds = [
        M("a.opus", start=0.05 * GIO, hashes=9000),
        M("b.opus", start=0.10 * GIO, hashes=9500),
        M("c.opus", start=0.45 * GIO, hashes=8000),
        M("d.opus", start=0.85 * GIO, hashes=8500),
    ]

    chon_ds, _ = engine._chon_loc(ds, GIO)

    assert len(chon_ds) == 3
    vung = {int(m.start_s / (GIO / 3)) for m in chon_ds}
    assert vung == {0, 1, 2}, "Mỗi vùng thời gian phải có đúng một đại diện"


def test_ket_qua_van_duoc_sap_theo_thoi_gian(engine):
    engine.config = Config(top_n=3, min_hash_floor=1000)
    ds = [
        M("a.opus", start=0.80 * GIO, hashes=9000),
        M("b.opus", start=0.10 * GIO, hashes=9500),
        M("c.opus", start=0.45 * GIO, hashes=8000),
    ]

    chon_ds, _ = engine._chon_loc(ds, GIO)

    assert [m.start_s for m in chon_ds] == sorted(m.start_s for m in chon_ds)


def test_duoi_nguong_van_bi_loai_nhu_cu(engine):
    engine.config = Config(top_n=5, min_hash_floor=1000)
    # `matched` phải để mật độ hash ở mức thực tế (đo trên 1.198 match thật:
    # thấp nhất 9,99 hash/s, trung vị 16,8). Mặc định 600 giây cho ~1.000 hash là
    # 1,7 hash/s — loãng hơn thực tế 6 lần, và test sẽ đo nhầm rào chắn mật độ
    # thay vì đo đúng ngưỡng hash tuyệt đối mà nó muốn kiểm.
    ds = [M("a.opus", start=0.1 * GIO, hashes=999, matched=60.0),
          M("b.opus", start=0.2 * GIO, hashes=1001, matched=60.0)]

    chon_ds, loai = engine._chon_loc(ds, GIO)

    assert [m.clip for m in chon_ds] == ["b.opus"]
    assert [m.clip for m in loai] == ["a.opus"]


def test_khong_co_ung_vien_dat_nguong_thi_khong_bia_ket_qua(engine):
    engine.config = Config(top_n=1, min_hash_floor=1000)
    chon_ds, loai = engine._chon_loc([M("a.opus", start=0.0, hashes=10)], GIO)

    assert chon_ds == []
    assert len(loai) == 1


# ---------------------------------------------------------------------------
# Khoá chất lượng ty_le + sàn bằng chứng
# ---------------------------------------------------------------------------

def _voi_ty_le(m, ty_le):
    m.ty_le = ty_le
    return m


def test_ty_le_la_khoa_chat_luong_mac_dinh(engine):
    """Clip ngắn bị copy gần trọn thắng clip dài bị copy một phần, khi bằng chứng tương đương."""
    engine.config = Config(top_n=1, min_hash_floor=1000)
    it_ty_le = _voi_ty_le(M("a.opus", start=0.1 * GIO, hashes=12000, matched=800.0), 20.0)
    nhieu_ty_le = _voi_ty_le(M("b.opus", start=0.5 * GIO, hashes=11000, matched=760.0), 75.0)

    chon_ds, _ = engine._chon_loc([it_ty_le, nhieu_ty_le], GIO)

    assert chon_ds[0] is nhieu_ty_le


def test_san_chan_ung_vien_co_bang_chung_sup_do(engine):
    """Ca thật job 316: 22,8 phút/36.939 hash không được thay bằng 9,4 phút/13.129 hash."""
    engine.config = Config(top_n=1, min_hash_floor=1000, san_bang_chung=0.70)
    manh = _voi_ty_le(M("a.opus", start=0.5 * GIO, hashes=36939, matched=1368.0), 17.3)
    ty_le_cao = _voi_ty_le(M("b.opus", start=0.2 * GIO, hashes=13129, matched=562.0), 27.5)

    chon_ds, _ = engine._chon_loc([manh, ty_le_cao], GIO)

    assert chon_ds[0] is manh, "Sàn bằng chứng phải chặn ca đánh đổi nặng"


def test_bo_san_thi_ty_le_thang_luon(engine):
    """Chứng minh chính cái sàn tạo ra khác biệt, không phải thứ khác."""
    engine.config = Config(top_n=1, min_hash_floor=1000, san_bang_chung=0.0)
    manh = _voi_ty_le(M("a.opus", start=0.5 * GIO, hashes=36939, matched=1368.0), 17.3)
    ty_le_cao = _voi_ty_le(M("b.opus", start=0.2 * GIO, hashes=13129, matched=562.0), 27.5)

    chon_ds, _ = engine._chon_loc([manh, ty_le_cao], GIO)

    assert chon_ds[0] is ty_le_cao


def test_san_cho_qua_khi_bang_chung_van_con_nguyen(engine):
    """Ca thật job 315: hash chỉ kém 6% mà ty_le tăng 9,7 -> 48,6 thì phải đổi."""
    engine.config = Config(top_n=1, min_hash_floor=1000, san_bang_chung=0.70)
    ty_le_thap = _voi_ty_le(M("a.opus", start=0.5 * GIO, hashes=37451, matched=1430.0), 9.7)
    ty_le_cao = _voi_ty_le(M("b.opus", start=0.6 * GIO, hashes=35303, matched=1235.0), 48.6)

    chon_ds, _ = engine._chon_loc([ty_le_thap, ty_le_cao], GIO)

    assert chon_ds[0] is ty_le_cao


def test_lui_ve_hashes_khi_chua_tinh_ty_le(engine):
    """_gan_chi_so chưa chạy -> mọi ty_le = 0 -> không được xếp hạng tuỳ tiện."""
    engine.config = Config(top_n=1, min_hash_floor=1000)
    yeu = M("a.opus", start=0.1 * GIO, hashes=6000)      # ty_le mặc định 0.0
    manh = M("b.opus", start=0.5 * GIO, hashes=20000)

    chon_ds, _ = engine._chon_loc([yeu, manh], GIO)

    assert chon_ds[0] is manh


def test_dat_khoa_ve_hashes_khoi_phuc_hanh_vi_cu(engine):
    engine.config = Config(top_n=1, min_hash_floor=1000, khoa_chat_luong="hashes",
                           dung_sai_gan_bang=0.0)
    nhieu_hash = _voi_ty_le(M("a.opus", start=0.5 * GIO, hashes=20000, matched=900.0), 10.0)
    nhieu_ty_le = _voi_ty_le(M("b.opus", start=0.2 * GIO, hashes=19000, matched=880.0), 90.0)

    chon_ds, _ = engine._chon_loc([nhieu_hash, nhieu_ty_le], GIO)

    assert chon_ds[0] is nhieu_hash


def test_loc_du_bang_chung_khong_bao_gio_tra_rong():
    from engine import loc_du_bang_chung

    ds = [M("a.opus", start=0.0, hashes=100, matched=10.0),
          M("b.opus", start=0.0, hashes=100000, matched=5000.0)]

    giu = loc_du_bang_chung(ds, san=0.99)

    assert len(giu) >= 1
    assert giu[0].clip == "b.opus"


def test_config_tu_choi_khoa_va_san_vo_ly():
    with pytest.raises(ValueError, match="khoa_chat_luong"):
        Config(khoa_chat_luong="linh_tinh").validate()
    with pytest.raises(ValueError, match="san_bang_chung"):
        Config(san_bang_chung=1.5).validate()
    with pytest.raises(ValueError, match="san_bang_chung"):
        Config(san_bang_chung=-0.1).validate()


def test_config_tu_choi_dung_sai_vo_ly():
    with pytest.raises(ValueError, match="dung_sai_gan_bang"):
        Config(dung_sai_gan_bang=0.9).validate()
    with pytest.raises(ValueError, match="dung_sai_gan_bang"):
        Config(dung_sai_gan_bang=-0.1).validate()
