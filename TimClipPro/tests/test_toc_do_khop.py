# -*- coding: utf-8 -*-
"""Test bù video bị đổi tốc độ để né vân tay.

Số liệu trong file lấy từ đo thật (xem docs/DA_TOC_DO.md), không phải bịa.
"""

import chan_doan_quet
import pytest
from chan_doan_quet import ChanDoanQuet
from engine import RE_TEN_KHUC, Config, Engine
from toc_do_khop import (
    HO_RESAMPLE,
    HO_TEMPO,
    bo_loc_ffmpeg,
    giai_ma_he_so,
    ma_he_so,
    uoc_luong_toc_do,
)


def _manh(t_video: float, t_clip: float, clip: str = "goc.opus",
          khop: float = 6.0, hash_: int = 80) -> dict:
    return {"clip": clip, "bat_dau": t_video, "t_clip": t_clip,
            "khop": khop, "hash": hash_, "align": t_video - t_clip}


def _mo_phong(r: float, n: int = 20, dau: float = 30.0, buoc: float = 35.0,
              clip: str = "goc.opus") -> list:
    """Sinh mảnh khớp của một bản reup phát ở tốc độ r.

    Điểm ở giây t_o của bản gốc xuất hiện ở giây t_o/r trong video, nên
    t_clip = r * t_video.
    """
    return [
        _manh(t_video := dau + i * buoc, r * t_video, clip=clip)
        for i in range(n)
    ]


# =====================================================================
#  Ước lượng tốc độ từ độ trôi align
# =====================================================================

@pytest.mark.parametrize("r", [0.94, 0.97, 0.98, 0.995, 1.005, 1.02, 1.03, 1.05])
def test_uoc_luong_dung_ty_le(r):
    kq = uoc_luong_toc_do(_mo_phong(r))
    assert len(kq) == 1
    assert kq[0].ty_le == pytest.approx(r, abs=1e-4)


def test_he_so_bu_la_nghich_dao():
    u = uoc_luong_toc_do(_mo_phong(1.03))[0]
    assert u.he_so_bu == pytest.approx(1 / 1.03, abs=1e-5)


def test_khong_doi_toc_do_thi_khong_bao_gi():
    """Bản khớp nguyên tốc độ có align gần như hằng số — không được coi là bị đổi."""
    assert uoc_luong_toc_do(_mo_phong(1.0)) == []


def test_lech_qua_nho_bi_bo_qua():
    """Dưới ngưỡng 0,15% là dao động bình thường, không phải né tránh."""
    assert uoc_luong_toc_do(_mo_phong(1.0005)) == []


def test_lech_qua_lon_bi_bo_qua():
    assert uoc_luong_toc_do(_mo_phong(1.60), lech_toi_da=0.25) == []


def test_qua_it_manh_thi_khong_uoc_luong():
    assert uoc_luong_toc_do(_mo_phong(1.03, n=3), min_manh=4) == []


def test_manh_don_o_mot_cho_khong_du_trai_dai():
    """Mảnh dồn trong 20 giây thì độ dốc chỉ là nhiễu cục bộ được nhân lên."""
    ds = _mo_phong(1.03, n=10, buoc=2.0)
    assert uoc_luong_toc_do(ds, min_trai_dai_s=60.0) == []


def test_ben_voi_manh_nhieu_lan_vao():
    """Nhạc hiệu dùng chung tạo mảnh align ngẫu nhiên trong CÙNG một clip gốc.

    Đây chính là ca làm hồi quy bình phương tối thiểu lệch hẳn; Theil–Sen phải
    chịu được.
    """
    ds = _mo_phong(1.03, n=20)
    ds += [_manh(500.0, 12.0), _manh(505.0, 640.0), _manh(510.0, 300.0),
           _manh(515.0, 55.0), _manh(520.0, 810.0)]
    kq = uoc_luong_toc_do(ds)
    assert len(kq) == 1
    assert kq[0].ty_le == pytest.approx(1.03, abs=1e-3)
    assert kq[0].r2 < 1.0   # có điểm bị loại, tỉ lệ thẳng hàng không thể là 100%


def test_chi_toan_nhieu_thi_khong_uoc_luong_bua():
    """Align ngẫu nhiên không được sinh ra một 'tốc độ' giả."""
    ds = [_manh(30.0 + i * 40, (i * 137 % 700)) for i in range(20)]
    for u in uoc_luong_toc_do(ds):
        assert u.r2 >= 0.60   # nếu lọt thì cũng phải thực sự thẳng hàng


def test_hai_clip_cung_toc_do_thi_gop_lam_mot():
    ds = _mo_phong(1.03, clip="a.opus") + _mo_phong(1.03, clip="b.opus")
    assert len(uoc_luong_toc_do(ds)) == 1


def test_gioi_han_so_uoc_luong_tra_ve():
    ds = (_mo_phong(1.03, clip="a.opus") + _mo_phong(1.05, clip="b.opus")
          + _mo_phong(0.97, clip="c.opus") + _mo_phong(0.94, clip="d.opus"))
    assert len(uoc_luong_toc_do(ds, toi_da=2)) == 2


# =====================================================================
#  Bộ lọc ffmpeg và mã hệ số trong tên khúc
# =====================================================================

def test_bo_loc_tempo_giu_cao_do():
    assert bo_loc_ffmpeg(0.97087, HO_TEMPO).startswith("atempo=")


def test_bo_loc_resample_ep_tan_so_truoc_khi_doi():
    """Phải aresample TRƯỚC asetrate, nếu không bộ lọc thấy luồng ở 48 kHz gốc."""
    loc = bo_loc_ffmpeg(0.97087, HO_RESAMPLE)
    assert loc.index("aresample") < loc.index("asetrate")


@pytest.mark.parametrize("k", [0.9, 0.97087, 1.0, 1.03, 1.25])
def test_ma_he_so_di_ve_nguyen_ven(k):
    assert giai_ma_he_so(ma_he_so(k)) == pytest.approx(k, abs=1e-5)


def test_ten_khuc_cu_van_doc_duoc():
    """Tên khúc chưa có hậu tố hệ số phải hiểu là hệ số 1,0 (tương thích ngược)."""
    m = RE_TEN_KHUC.search("chunk_0003420.wav")
    assert int(m.group(1)) == 3420
    assert giai_ma_he_so(m.group(2)) == 1.0


def test_ten_khuc_co_he_so():
    m = RE_TEN_KHUC.search("chunk_0003420_k097087.wav")
    assert int(m.group(1)) == 3420
    assert giai_ma_he_so(m.group(2)) == pytest.approx(0.97087, abs=1e-5)


# =====================================================================
#  Quy đổi mốc thời gian về trục video gốc
# =====================================================================

def _eng():
    e = Engine.__new__(Engine)
    e.config = Config()
    e.chan_doan_quet = ChanDoanQuet()
    e.canh_bao_gop = []
    e.db_clips = lambda: []
    return e


def test_ke_hoach_uu_tien_do_troi_hon_luoi():
    e = _eng()
    ke = e._ke_hoach_toc_do(_mo_phong(1.03))
    assert ke, "phải có phương án"
    assert "độ trôi" in ke[0][2]
    assert ke[0][0] == pytest.approx(1 / 1.03, abs=1e-4)
    assert all(ho == HO_TEMPO for _, ho, _ in ke)


def test_ke_hoach_lui_ve_luoi_khi_khong_doc_duoc_do_troi():
    e = _eng()
    ke = e._ke_hoach_toc_do([])
    assert [round(k, 5) for k, _, _ in ke] == [
        round(1 / x, 5) for x in e.config.luoi_resample
    ]
    assert all(ho == HO_RESAMPLE for _, ho, _ in ke)


def test_ke_hoach_ton_trong_tran_so_luot():
    e = _eng()
    e.config.toc_do_toi_da_thu = 2
    assert len(e._ke_hoach_toc_do([])) == 2


def test_tat_thi_khong_co_ke_hoach_nao_chay():
    e = _eng()
    e.config.toc_do_toi_da_thu = 0
    assert e._ke_hoach_toc_do(_mo_phong(1.03)) == []


def test_luoi_rong_thi_khong_bia_phuong_an():
    e = _eng()
    e.config.luoi_resample = []
    e.config.luoi_tempo = []
    assert e._ke_hoach_toc_do([]) == []


def test_chan_doan_ghi_lai_da_thu_va_cach_bu():
    cd = ChanDoanQuet(so_khuc=2, dong_co_matched=50, parse_duoc=50,
                      qua_min_match_s=50, gop_lai=9, duoc_chap_nhan=0)
    cd.da_thu_toc_do = ["đo từ độ trôi: video 3.00% nhanh hơn bản gốc"]
    cd.chot_giai_doan()
    assert cd.giai_doan_mat == chan_doan_quet.KHONG_DAT_CHAP_NHAN
    assert "tempo_tried=1" in cd.dong_log()
    cd.toc_do_tim_duoc = "đo từ độ trôi"
    assert "tempo_recovered=1" in cd.dong_log()
