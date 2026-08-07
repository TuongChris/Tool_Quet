# -*- coding: utf-8 -*-
"""Test cho phễu chẩn đoán và tiêu chí chấp nhận hai bậc.

Bối cảnh: 11 video người dùng báo "quét xong 0 đoạn" hoá ra là ÂM TÍNH ĐÚNG —
chúng chỉ chứa nhạc hiệu dùng chung của kênh chứ không chứa bản reup nào. Vấn đề
thật là hệ thống không nói được điều đó. Các test dưới khoá lại hai thứ:

  1. một kết quả 0 đoạn luôn chỉ đúng tầng đã làm mất kết quả;
  2. tiêu chí chấp nhận mới nhận được clip gốc ngắn nhưng vẫn loại nhiễu thật đã
     đo được trên dữ liệu quét thật.

Các con số dùng ở đây lấy từ log quét thật, không phải bịa (xem
docs/ZERO_MATCH_ROOT_CAUSE.md).
"""

import chan_doan_quet as cd_mod
import pytest
from chan_doan_quet import ChanDoanQuet, ghi_nhan_bi_loai
from chap_nhan_khop import BAC_PHU_CAO, BAC_TUYET_DOI, danh_gia_chap_nhan, loc_chap_nhan
from conftest import M
from engine import RE_MATCH, Config, Engine


# =====================================================================
#  Tiêu chí chấp nhận
# =====================================================================

def _cfg(**kw):
    return Config(min_hash_floor=1000, ty_le_chap_nhan=60.0,
                  min_match_chap_nhan=20.0, mat_do_toi_thieu=3.0, **kw)


def _m(hashes, ty_le, matched):
    m = M(hashes=hashes, matched=matched)
    m.ty_le = ty_le
    return m


def test_bac_tuyet_doi_giu_nguyen_hanh_vi_cu():
    kq = danh_gia_chap_nhan(_m(1000, 0.0, 60.0), _cfg())
    assert kq.chap_nhan and kq.bac == BAC_TUYET_DOI


def test_duoi_nguong_tuyet_doi_va_phu_thap_thi_loai():
    assert not danh_gia_chap_nhan(_m(999, 5.0, 60.0), _cfg())


def test_clip_goc_ngan_khop_gan_het_van_duoc_nhan():
    """§107: clip gốc chỉ có ~900 hash thì KHÔNG BAO GIỜ đạt nổi ngưỡng 1000.

    Kho Cory thật có 3/1717 clip tổng hash < 1000. Trước đây các clip đó dù bị
    reup nguyên vẹn cũng không bao giờ được báo cáo.
    """
    kq = danh_gia_chap_nhan(_m(hashes=830, ty_le=92.2, matched=55.0), _cfg())
    assert kq.chap_nhan and kq.bac == BAC_PHU_CAO


def test_nhac_hieu_dung_chung_bi_loai():
    """Số thật đo trên 11 video: 133 hash / 8,8s / phủ 0,9%, mật độ 15 hash/s.

    Mật độ cao nên chỉ có `matched_s` và `ty_le` mới chặn được ca này.
    """
    kq = danh_gia_chap_nhan(_m(hashes=133, ty_le=0.9, matched=8.8), _cfg())
    assert not kq.chap_nhan
    assert "phủ" in kq.ly_do


def test_trung_khop_thua_ngau_nhien_bi_loai():
    """Số thật đo trên qUrJv94OzJE: 309 hash trải 578,6s = 0,53 hash/s."""
    assert not danh_gia_chap_nhan(_m(hashes=309, ty_le=0.5, matched=578.6), _cfg())


def test_phu_cao_nhung_qua_ngan_thi_loai():
    assert not danh_gia_chap_nhan(_m(hashes=200, ty_le=95.0, matched=8.0), _cfg())


def test_phu_cao_du_dai_nhung_thua_hash_thi_loai():
    """Phủ cao + dài nhưng mật độ 1 hash/s là dấu hiệu bám align ngẫu nhiên."""
    assert not danh_gia_chap_nhan(_m(hashes=100, ty_le=90.0, matched=100.0), _cfg())


def test_bac_a_loai_bang_chung_qua_loang():
    """§68: vượt ngưỡng tuyệt đối chưa đủ nếu hash rải quá mỏng.

    1.200 hash trải 2.000 giây = 0,6 hash/s — chỉ là các điểm trùng rải rác bám
    cùng một align, không phải một đoạn khớp thật.
    """
    kq = danh_gia_chap_nhan(_m(hashes=1200, ty_le=6.0, matched=2000.0), _cfg())
    assert not kq.chap_nhan
    assert "loãng" in kq.ly_do and "mật độ" in kq.ly_do


def test_bac_a_bao_dung_ly_do_khi_du_hash_nhung_loang():
    """Không được báo 'thiếu hash' — người dùng sẽ đi hạ nhầm ngưỡng."""
    kq = danh_gia_chap_nhan(_m(hashes=1200, ty_le=6.0, matched=2000.0), _cfg())
    assert "1200 hash < ngưỡng tuyệt đối" not in kq.ly_do
    assert kq.ly_do.startswith("đủ 1200 hash")


def test_rao_chan_mat_do_khong_dung_toi_match_that():
    """Mật độ thấp nhất đo được trên 1.198 match thật trong lịch sử là 9,99 hash/s.

    Rào chắn 3,0 phải cách xa mức đó — nếu test này vỡ nghĩa là ai đó đã nâng
    ngưỡng vào vùng cắt mất bằng chứng thật.
    """
    thap_nhat_that = _m(hashes=11445, ty_le=50.0, matched=1145.3)   # 9,99 hash/s
    assert danh_gia_chap_nhan(thap_nhat_that, _cfg()).chap_nhan


def test_tat_rao_chan_mat_do_thi_ve_dung_hanh_vi_cu():
    cfg = _cfg()
    cfg.mat_do_bac_a = 0.0
    assert danh_gia_chap_nhan(_m(hashes=1200, ty_le=6.0, matched=2000.0), cfg)


def test_khong_cho_dat_rao_chan_vao_vung_nguy_hiem():
    """Chặn gõ nhầm: trên 9,0 hash/s là bắt đầu cắt vào match thật."""
    cfg = Config()
    cfg.mat_do_bac_a = 12.0
    with pytest.raises(ValueError, match="mat_do_bac_a"):
        cfg.validate()


def test_loc_chap_nhan_chia_dung_hai_nhom():
    ds = [_m(1500, 0.0, 60.0), _m(830, 92.2, 55.0), _m(133, 0.9, 8.8)]
    dat, loai, ly_do = loc_chap_nhan(ds, _cfg())
    assert len(dat) == 2 and len(loai) == 1
    assert all(id(m) in ly_do for m in ds)


def test_tat_bac_phu_cao_thi_ve_dung_hanh_vi_cu():
    cfg = _cfg()
    cfg.ty_le_chap_nhan = 0.0
    assert not danh_gia_chap_nhan(_m(830, 92.2, 55.0), cfg)


# =====================================================================
#  Phễu chẩn đoán — mỗi tầng mất kết quả phải có mã riêng
# =====================================================================

@pytest.mark.parametrize("dung, mong_doi", [
    (dict(so_khuc=0),
     cd_mod.KHONG_CAT_DUOC_KHUC),
    (dict(so_khuc=3, dong_co_matched=0),
     cd_mod.AUDFPRINT_KHONG_RA_MATCH),
    (dict(so_khuc=3, dong_co_matched=17, parse_duoc=0),
     cd_mod.PARSER_HONG),
    (dict(so_khuc=3, dong_co_matched=17, parse_duoc=17, qua_min_match_s=0),
     cd_mod.BANG_CHUNG_QUA_YEU),
    (dict(so_khuc=3, dong_co_matched=17, parse_duoc=17, qua_min_match_s=17,
          gop_lai=4, duoc_chap_nhan=0),
     cd_mod.KHONG_DAT_CHAP_NHAN),
    (dict(so_khuc=3, dong_co_matched=17, parse_duoc=17, qua_min_match_s=17,
          gop_lai=4, duoc_chap_nhan=2, da_chon=0),
     cd_mod.CHON_LOC_BO_HET),
])
def test_chot_dung_giai_doan_mat_ket_qua(dung, mong_doi):
    cd = ChanDoanQuet(**dung)
    assert cd.chot_giai_doan() == mong_doi
    assert cd.mat_o_dau()          # luôn có câu giải thích tiếng Việt


def test_co_ket_qua_thi_khong_bao_mat_o_dau():
    cd = ChanDoanQuet(so_khuc=2, dong_co_matched=9, parse_duoc=9,
                      qua_min_match_s=9, gop_lai=3, duoc_chap_nhan=1, da_chon=1)
    assert cd.chot_giai_doan() == ""
    assert cd.mat_o_dau() == ""


def test_phan_biet_parser_hong_voi_khong_co_match():
    """Hai ca này trước đây đều hiện ra là 'không tìm thấy clip gốc nào'."""
    khong_co = ChanDoanQuet(so_khuc=2, dong_co_matched=0)
    hong = ChanDoanQuet(so_khuc=2, dong_co_matched=42, parse_duoc=0)
    assert khong_co.chot_giai_doan() != hong.chot_giai_doan()


def test_ghi_nhan_ung_vien_manh_nhat_bi_loai():
    cd = ChanDoanQuet()
    loai = [_m(133, 0.9, 8.8), _m(830, 92.2, 55.0)]
    ghi_nhan_bi_loai(cd, loai, {"a.opus": 900}, {id(loai[1]): "thiếu 170 hash"})
    u = cd.manh_nhat_bi_loai
    assert u is not None and u.hashes == 830
    assert u.tong_hash_clip == 900
    assert u.mat_do_hash == pytest.approx(830 / 55.0, abs=0.01)
    assert "thiếu 170 hash" in u.mo_ta()


def test_dong_log_co_du_moc_quan_trong():
    cd = ChanDoanQuet(so_khuc=2, dong_co_matched=300, parse_duoc=300,
                      qua_min_hash=300, qua_min_match_s=296, gop_lai=296)
    cd.chot_giai_doan()
    dong = cd.dong_log()
    for khoa in ("chunks=", "raw_matched=", "parsed=", "merged=", "zero_stage="):
        assert khoa in dong


def test_thanh_dict_luon_kem_cau_giai_thich():
    cd = ChanDoanQuet(so_khuc=1, dong_co_matched=0)
    cd.chot_giai_doan()
    assert cd.thanh_dict()["mat_o_dau"]


# =====================================================================
#  Parser — dòng thật của audfprint phải đọc được 100%
# =====================================================================

DONG_THAT = [
    "Matched    8.3 s starting at  787.9 s in D:\\a\\chunk_0000000.wav to time  "
    "876.2 s in D:\\ClipGocSML\\00000000 - SML Movie_ Junior's Broken Leg! "
    "[VTQtuzMdHlE].opus with    67 of  8748 common hashes at rank 34",
    "Matched  786.8 s starting at 1421.0 s in D:\\a\\chunk_0003420.wav to time    "
    "1.2 s in D:\\ClipGocSML\\00000000 - SML Movie_ The Break Up! [V2LeSJqcUcg].opus "
    "with 15173 of 21044 common hashes at rank  0",
    "Matched    1.5 s starting at   33.9 s in D:\\a\\chunk_0000000.wav to time  "
    "639.2 s in D:\\ClipGocSML\\00000000 - SML Movie_ Orange Is The New Black! "
    "[YjHcwx5Ix-Y].opus with    17 of  7178 common hashes at rank 12",
]


@pytest.mark.parametrize("dong", DONG_THAT)
def test_parser_doc_duoc_dong_that_cua_audfprint(dong):
    m = RE_MATCH.search(dong)
    assert m is not None, "định dạng output audfprint đã đổi — phải sửa RE_MATCH"
    assert float(m.group(1)) > 0
    assert int(m.group(6)) > 0
    assert m.group(5).endswith(".opus")


def test_parser_doc_dung_ten_clip_co_dau_ngoac_vuong():
    m = RE_MATCH.search(DONG_THAT[0])
    assert m.group(5).endswith("[VTQtuzMdHlE].opus")
    assert int(m.group(6)) == 67


# =====================================================================
#  Đường đi nhanh Top-1
# =====================================================================

def _eng_top1(**kw):
    cfg = Config(top_n=1, top1_tim_nhanh=True, top1_khuc_toi_thieu=3, **kw)
    e = Engine.__new__(Engine)
    e.config = cfg
    e.chan_doan_quet = ChanDoanQuet()
    e.canh_bao_gop = []
    e.db_clips = lambda: []
    return e


def _tho(hash_, khop, bat_dau=100.0, clip=r"C:\kho\x.opus"):
    return {"clip": clip, "bat_dau": bat_dau, "khop": khop, "t_clip": 0.0,
            "hash": hash_, "align": bat_dau}


def test_dung_som_khi_bang_chung_rat_manh(monkeypatch):
    e = _eng_top1()
    goi = []

    def gia_match(chunks, *a, **kw):
        goi.append(list(chunks))
        return [_tho(15173, 786.8)]

    monkeypatch.setattr(e, "_match_chunks", gia_match)
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    tho = e._quet_tho(["c1", "c2", "c3"], 7200.0, None, 0.0, 1.0, "ws")
    assert len(goi) == 1 and goi[0] == ["c1"], "phải dừng sau khúc đầu"
    assert tho and e.chan_doan_quet.duong_di == "dung_som_vung_dau"


def test_khong_du_manh_thi_quet_not_phan_con_lai(monkeypatch):
    e = _eng_top1()
    goi = []

    def gia_match(chunks, *a, **kw):
        goi.append(list(chunks))
        return [_tho(120, 9.0)]

    monkeypatch.setattr(e, "_match_chunks", gia_match)
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    e._quet_tho(["c1", "c2", "c3"], 7200.0, None, 0.0, 1.0, "ws")
    assert goi == [["c1"], ["c2", "c3"]], "phải quét bù đúng một lần"
    assert e.chan_doan_quet.duong_di == "quet_bu_toan_bo"


def test_quet_bu_giu_lai_ket_qua_tho_cua_vung_dau(monkeypatch):
    """Không được vứt bằng chứng đã tìm được ở khúc đầu khi phải quét tiếp."""
    e = _eng_top1()

    def gia_match(chunks, *a, **kw):
        return [_tho(120, 9.0, bat_dau=50.0)] if chunks == ["c1"] \
            else [_tho(140, 9.5, bat_dau=5000.0)]

    monkeypatch.setattr(e, "_match_chunks", gia_match)
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    tho = e._quet_tho(["c1", "c2", "c3"], 7200.0, None, 0.0, 1.0, "ws")
    assert sorted(x["bat_dau"] for x in tho) == [50.0, 5000.0]


def test_match_manh_o_cuoi_video_van_tim_duoc(monkeypatch):
    """§72: fast pass trượt thì fallback vẫn phải thấy match nằm ở 90% video."""
    e = _eng_top1()

    def gia_match(chunks, *a, **kw):
        if chunks == ["c1"]:
            return []
        return [_tho(15173, 786.8, bat_dau=6500.0)]

    monkeypatch.setattr(e, "_match_chunks", gia_match)
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    tho = e._quet_tho(["c1", "c2", "c3"], 7200.0, None, 0.0, 1.0, "ws")
    assert [x["hash"] for x in tho] == [15173]


def test_top_n_lon_hon_1_khong_dung_duong_di_nhanh(monkeypatch):
    e = _eng_top1()
    e.config.top_n = 5
    goi = []
    monkeypatch.setattr(e, "_match_chunks",
                        lambda chunks, *a, **kw: goi.append(list(chunks)) or [])
    e._quet_tho(["c1", "c2", "c3"], 7200.0, None, 0.0, 1.0, "ws")
    assert goi == [["c1", "c2", "c3"]]
    assert e.chan_doan_quet.duong_di == "quet_toan_bo"


def test_video_it_khuc_khong_dung_duong_di_nhanh(monkeypatch):
    """Video 2 khúc thì tách làm hai lượt chỉ tổ tốn thêm một lần nạp kho."""
    e = _eng_top1()
    goi = []
    monkeypatch.setattr(e, "_match_chunks",
                        lambda chunks, *a, **kw: goi.append(list(chunks)) or [])
    e._quet_tho(["c1", "c2"], 3600.0, None, 0.0, 1.0, "ws")
    assert goi == [["c1", "c2"]]


def test_dung_som_khong_kich_hoat_voi_bang_chung_yeu(monkeypatch):
    """§108: top_n=1 nghĩa là 'nhiều nhất một kết quả', không phải 'luôn có một'."""
    e = _eng_top1()
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    assert e._du_manh_de_dung_som([_tho(40, 5.0)], 7200.0) is None


def test_dung_som_co_the_bo_qua_ung_vien_ty_le_cao_hon_o_sau(monkeypatch):
    """Khoá lại ĐÁNH ĐỔI đã biết của việc dừng sớm — không phải lỗi, là thiết kế.

    Đo thật trên n4Ca9SmTfi0: quét toàn bộ chọn clip phủ 81,2% nằm ở 01:29:28, còn
    fast Top-1 dừng ở khúc đầu và chọn clip phủ 73,2% nằm ở 00:25:18. Cả hai đều là
    bản reup thật trên 10.000 hash. Fast Top-1 cam kết trả về bằng chứng RẤT MẠNH,
    không cam kết trả về ứng viên tối ưu toàn cục theo `khoa_chat_luong`.

    Nếu test này vỡ thì hoặc cổng dừng sớm đã đổi, hoặc ai đó vô tình biến đường đi
    nhanh thành quét toàn bộ — cả hai đều cần xem lại có chủ ý hay không.
    """
    e = _eng_top1()
    monkeypatch.setattr(e, "_gan_chi_so", lambda ds, d: None)
    monkeypatch.setattr(
        e, "_match_chunks",
        lambda chunks, *a, **kw: (
            [_tho(13316, 711.0, bat_dau=1518.0, clip=r"C:\kho\som.opus")]
            if chunks == ["c1"] else
            [_tho(10436, 562.2, bat_dau=5368.0, clip=r"C:\kho\muon.opus")]
        ),
    )
    tho = e._quet_tho(["c1", "c2", "c3"], 24204.0, None, 0.0, 1.0, "ws")
    assert [x["clip"] for x in tho] == [r"C:\kho\som.opus"]
    assert e.chan_doan_quet.duong_di == "dung_som_vung_dau"

    # Tắt đường đi nhanh thì phải thấy cả hai ứng viên.
    e2 = _eng_top1()
    e2.config.top1_tim_nhanh = False
    monkeypatch.setattr(e2, "_gan_chi_so", lambda ds, d: None)
    monkeypatch.setattr(
        e2, "_match_chunks",
        lambda chunks, *a, **kw: [
            _tho(13316, 711.0, bat_dau=1518.0, clip=r"C:\kho\som.opus"),
            _tho(10436, 562.2, bat_dau=5368.0, clip=r"C:\kho\muon.opus"),
        ],
    )
    tho2 = e2._quet_tho(["c1", "c2", "c3"], 24204.0, None, 0.0, 1.0, "ws")
    assert len(tho2) == 2 and e2.chan_doan_quet.duong_di == "quet_toan_bo"
