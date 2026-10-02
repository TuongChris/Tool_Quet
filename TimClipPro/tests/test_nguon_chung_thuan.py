# -*- coding: utf-8 -*-
"""Phần THUẦN của chế độ «một video gốc chung cho cả lô»: định danh, bằng chứng, kết luận.

Không I/O, không engine thật — mỗi lượt quét được rút gọn thành ``LuotQuet``.
"""

import csv
import io

import pytest

import common_original as co
from engine import Config, Match, ScanResult

KHO = "kho1"
DD = ("kho1", "r1:100", "v1:abc")       # định danh lô: (kho_id, kho_phien_ban, chinh_sach)
A, B, C, D = "A [aaaaaaaaaaa].opus", "B [bbbbbbbbbbb].opus", "C [ccccccccccc].opus", \
    "D [ddddddddddd].opus"


def M(clip, start=0.0, hashes=6000, matched=300.0, ty_le=50.0):
    return Match(clip=clip, start_s=start, end_s=start + matched, matched_s=matched,
                 clip_offset_s=0.0, hashes=hashes, confidence="x", ty_le=ty_le,
                 clip_bat_dau_s=start, vung_khop_s=start)


def luot(*ms, tron=True, hop_le=True, muc_tieu="collect", thoi_luong=3600.0, cham_tran=0,
         bu=False):
    return co.LuotQuet(muc_tieu=muc_tieu, hop_le=hop_le, tron=tron and hop_le,
                       ung_vien=tuple(ms) if hop_le else (), thoi_luong=thoi_luong,
                       so_khuc_cham_tran=cham_tran, thu_bu_toc_do=bu)


def video(i, *luots, thoi_luong=3600.0, ma=None):
    v = co.VideoTrongLo(thu_tu=i, nguon=f"https://youtu.be/vid{i:08d}",
                        ma=ma or f"vid{i:08d}", tieu_de=f"Video {i}", kenh="Kênh X",
                        thoi_luong=thoi_luong)
    v.luot.extend(luots)
    return v


def lo(*videos, cfg=None):
    return co.TrangThaiLo(kho_id=KHO, videos=list(videos), cfg=cfg or Config())


def k(clip, kho=KHO):
    return co.khoa_goc(kho, clip)


# ---------------------------------------------------------------------------
#  Ca bắt buộc của Plan: Top-1 mỗi video là nguồn KHÁC nhau
# ---------------------------------------------------------------------------

def test_top1_moi_video_khac_nhau_van_tim_ra_nguon_chung():
    v1 = video(1, luot(M(A, 100, hashes=2000, matched=100), M(B, 900, hashes=9000, matched=600)))
    v2 = video(2, luot(M(A, 50, hashes=2000, matched=100), M(C, 700, hashes=9000, matched=600)))
    v3 = video(3, luot(M(A, 300, hashes=2000, matched=100), M(D, 20, hashes=9000, matched=600)))
    tt = lo(v1, v2, v3)

    # Giao các Top-1 thì rỗng — đúng cái bẫy mà chế độ này sinh ra để tránh.
    top1 = [max(v.luot[0].ung_vien, key=lambda m: m.hashes).clip for v in tt.videos]
    assert top1 == [B, C, D]

    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.TIM_THAY
    assert kl.goc == k(A) and kl.so_co_mat == kl.tong == 3


# ---------------------------------------------------------------------------
#  Trạng thái từng cặp (video, video gốc)
# ---------------------------------------------------------------------------

def test_luot_mot_phan_khong_bao_gio_la_vang_mat_du():
    v = video(1, luot(M(B), tron=False))
    assert v.trang_thai(k(A), KHO) == co.CHUA_RO


def test_luot_tron_khong_co_thi_la_vang_mat_du():
    v = video(1, luot(M(B), tron=True))
    assert v.trang_thai(k(A), KHO) == co.VANG_MAT_DU


def test_chua_quet_va_chi_co_luot_loi():
    assert video(1).trang_thai(k(A), KHO) == co.CHUA_QUET
    assert video(2, luot(hop_le=False)).trang_thai(k(A), KHO) == co.LOI_QUET


def _kq(status="ok", dat=(), phien_ban="r1:100", day_du=True):
    kq = ScanResult(source_name="v", status=status, duration_s=600.0,
                    kho_id="kho1", kho_phien_ban=phien_ban, chinh_sach="v1:abc",
                    vung_da_khop=[(0.0, 600.0)] if day_du else [(0.0, 200.0)])
    kq.ung_vien_dat = list(dat)
    return kq


def test_luot_loi_khong_cho_bang_chung_du_co_ung_vien():
    lq = co.luot_tu_ket_qua(_kq(status="error", dat=[M(A)]), "verify", DD)
    assert not lq.hop_le and not lq.tron and lq.ung_vien == ()


def test_luot_khac_kho_hoac_chinh_sach_khong_hop_le():
    lq = co.luot_tu_ket_qua(_kq(dat=[M(A)], phien_ban="r2:999"), "verify", DD)
    assert not lq.hop_le and lq.ung_vien == ()
    assert "Kho" in lq.ly_do or "kho" in lq.ly_do


def test_luot_hop_le_giu_dung_ung_vien_dat_va_do_tron():
    lq = co.luot_tu_ket_qua(_kq(dat=[M(A)], day_du=False), "verify", DD)
    assert lq.hop_le and not lq.tron and [m.clip for m in lq.ung_vien] == [A]
    assert co.luot_tu_ket_qua(_kq(dat=[M(A)]), "collect", DD).tron


def test_luot_khong_hop_le_bi_bo_qua_ke_ca_khi_mang_ung_vien():
    """Lớp phòng thủ thứ hai: lượt không hợp lệ không bao giờ cho bằng chứng."""
    v = video(1, co.LuotQuet(muc_tieu="verify", hop_le=False, tron=False,
                             ung_vien=(M(A),)))
    assert v.ung_vien(KHO) == {}
    assert v.trang_thai(k(A), KHO) == co.LOI_QUET


def test_co_mat_thang_vang_mat_du_va_ghi_mau_thuan():
    v = video(1, luot(M(A), tron=False), luot(M(B), tron=True))
    assert v.trang_thai(k(A), KHO) == co.CO_MAT
    assert co.mau_thuan(v, KHO) == {k(A)}


# ---------------------------------------------------------------------------
#  Định danh
# ---------------------------------------------------------------------------

def test_khoa_theo_kho_va_ten_file_khong_gop_theo_ma_trong_ngoac():
    assert k("X [Compilation].mp3") != k("Y [Compilation].mp3")
    assert k(A, "kho1") != k(A, "kho2")
    assert k("D:/Kho/con/a.opus") == k("a.opus")
    assert k(A).clip == A


def test_ung_vien_gom_theo_khoa_qua_moi_luot_hop_le():
    v = video(1, luot(M(A, 10), tron=False), luot(M(A, 500), M(B)), luot(M(C), hop_le=False))
    uv = v.ung_vien(KHO)
    assert set(uv) == {k(A), k(B)}
    assert len(uv[k(A)]) == 2


# ---------------------------------------------------------------------------
#  Xếp hạng và đại diện
# ---------------------------------------------------------------------------

def test_xep_hang_moc_de_bang_chung_dai_manh_len_truoc_doan_ngan_phu_cao():
    intro = M("Intro [iiiiiiiiiii].opus", 0, hashes=1200, matched=25.0, ty_le=95.0)
    chinh = M(A, 3000, hashes=9000, matched=600.0, ty_le=45.0)
    v = video(1, luot(intro, chinh))
    assert co.xep_hang_ung_vien(v, KHO, Config()) == [k(A), k(intro.clip)]


def test_dai_dien_chat_luong_truoc_vi_tri_chi_pha_hoa_gan_bang():
    cfg = Config()
    gan = M(A, 600, hashes=9000, matched=600.0, ty_le=50.0)
    xa = M(A, 30000, hashes=9100, matched=605.0, ty_le=50.2)
    v = video(1, luot(xa, gan), thoi_luong=36000.0)
    assert co.dai_dien(v, k(A), cfg) is gan, "gần bằng nhau thì đoạn dễ tua tới thắng"
    manh = M(A, 30000, hashes=20000, matched=900.0, ty_le=90.0)
    v2 = video(2, luot(manh, gan), thoi_luong=36000.0)
    assert co.dai_dien(v2, k(A), cfg) is manh, "mạnh hơn hẳn thì vị trí không cứu được"
    # Cả hai đều qua sàn bằng chứng (≥70% hash và thời lượng), chỉ khác chất lượng chuẩn
    # hoá rõ rệt: đoạn muộn hơn nhưng phủ vân tay cao hơn hẳn phải thắng.
    som_yeu = M(A, 600, hashes=8000, matched=600.0, ty_le=40.0)
    muon_tot = M(A, 30000, hashes=9000, matched=620.0, ty_le=60.0)
    v3 = video(3, luot(som_yeu, muon_tot), thoi_luong=36000.0)
    assert co.dai_dien(v3, k(A), cfg) is muon_tot


def test_hai_nguon_chung_chon_nguon_chat_luong_hon_khong_theo_vi_tri():
    vids = []
    for i in range(1, 4):
        vids.append(video(i, luot(
            M(A, 30000, hashes=9000, matched=600.0, ty_le=60.0),
            M(B, 10, hashes=1500, matched=60.0, ty_le=70.0))))
    kl = co.ket_luan(lo(*vids))
    assert kl.trang_thai == co.TIM_THAY
    assert kl.goc == k(A) and kl.goc_khac == (k(B),)


# ---------------------------------------------------------------------------
#  Kết luận cả lô
# ---------------------------------------------------------------------------

def test_khong_tim_thay_kem_ung_vien_tot_nhat_nhung_khong_phai_tim_thay():
    tt = lo(video(1, luot(M(A), M(B))), video(2, luot(M(A))), video(3, luot(M(B), M(C))))
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.KHONG_TIM_THAY
    assert kl.goc is None
    assert kl.tot_nhat in (k(A), k(B)) and kl.so_co_mat == 2 and kl.tong == 3


def test_con_video_loi_da_het_luot_thi_chua_ket_luan():
    v3 = video(3, luot(hop_le=False), luot(hop_le=False))
    tt = lo(video(1, luot(M(A))), video(2, luot(M(A))), v3)
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.CHUA_KET_LUAN
    assert kl.tot_nhat == k(A) and kl.so_co_mat == 2


def test_con_buoc_quet_thi_dang_tim_va_huy_thi_da_huy():
    tt = lo(video(1, luot(M(A))), video(2, luot(M(A))), video(3))
    assert co.ket_luan(tt).trang_thai == co.DANG_TIM
    assert co.ket_luan(tt, da_huy=True).trang_thai == co.DA_HUY


def test_tim_thay_van_la_tim_thay_du_bi_huy_sau_do():
    tt = lo(video(1, luot(M(A))), video(2, luot(M(A), tron=False)))
    assert co.ket_luan(tt, da_huy=True).trang_thai == co.TIM_THAY


def test_moc_quet_tron_khong_co_ung_vien_thi_khong_tim_thay_ngay():
    tt = lo(video(1, luot()), video(2), video(3))
    assert co.ket_luan(tt).trang_thai == co.KHONG_TIM_THAY


# ---------------------------------------------------------------------------
#  Cờ cảnh báo
# ---------------------------------------------------------------------------

def test_canh_bao_ten_trung_trong_kho():
    tt = lo(video(1, luot(M(A))), video(2, luot(M(A))))
    cb = co.canh_bao_goc(tt, k(A), dem_ten={A: 2})
    assert any("2 bản ghi" in x for x in cb)


def test_canh_bao_chi_dat_nho_phu_van_tay_cao():
    ngan = dict(hashes=300, matched=25.0, ty_le=95.0)   # bậc B: phủ cao, dưới sàn hash
    tt = lo(video(1, luot(M(A, **ngan))), video(2, luot(M(A, **ngan))))
    assert any("phủ vân tay cao" in x for x in co.canh_bao_goc(tt, k(A), dem_ten={}))
    tt2 = lo(video(1, luot(M(A))), video(2, luot(M(A, **ngan))))
    assert not any("phủ vân tay cao" in x for x in co.canh_bao_goc(tt2, k(A), dem_ten={}))


def test_canh_bao_link_co_the_chinh_la_video_goc():
    tt = lo(video(1, luot(M(A)), ma="aaaaaaaaaaa"), video(2, luot(M(A))))
    assert any("chính là video gốc" in x for x in co.canh_bao_goc(tt, k(A), dem_ten={}))
    tt2 = lo(video(1, luot(M(A)), ma="AAAAAAAAAAA"), video(2, luot(M(A))))
    assert not any("chính là video gốc" in x for x in co.canh_bao_goc(tt2, k(A), dem_ten={})), \
        "mã YouTube phân biệt hoa thường"


def test_khong_tim_thay_co_khuc_cham_tran_thi_ghi_luu_y():
    tt = lo(video(1, luot(M(A), cham_tran=2)), video(2, luot(M(B))))
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.KHONG_TIM_THAY
    assert "chạm trần" in kl.ly_do


# ---------------------------------------------------------------------------
#  Báo cáo CSV
# ---------------------------------------------------------------------------

def test_bao_cao_mot_dong_dai_dien_moi_video_va_an_toan_bang_tinh():
    v1 = video(1, luot(M(A, 125.0)))
    v1.tieu_de = "=HYPERLINK(\"x\")"
    tt = lo(v1, video(2, luot(M(A, 3600.0))))
    kl = co.ket_luan(tt)
    kql = co.dung_ket_qua_lo(tt, kl, ma_lo="lo1", kho_ten="Kho SML",
                             thong_tin_goc={"title": "Tên gốc", "url": "https://youtu.be/aaaaaaaaaaa",
                                            "upload_date": "20250101", "duration": 600.0},
                             dem_ten={})
    rows = co.dong_bao_cao(kql)
    assert len(rows) == 2 and all(len(r) == len(co.HEADER_NGUON_CHUNG) for r in rows)
    cot = {ten: i for i, ten in enumerate(co.HEADER_NGUON_CHUNG)}
    assert rows[0][cot["Video vi phạm"]].startswith("'="), "chặn công thức bảng tính"
    assert rows[0][cot["🔗 Nhảy tới đúng mốc vi phạm"]] == "https://youtu.be/vid00000001?t=125"
    assert rows[1][cot["Clip bắt đầu từ"]] == "01:00:00"
    assert rows[0][cot["Trạng thái trên video này"]] == "Có mặt"
    f = io.StringIO()
    csv.writer(f).writerows([co.HEADER_NGUON_CHUNG, *rows])
    assert "Tên gốc" in f.getvalue()


def test_bao_cao_khong_tim_thay_van_ghi_ro_khong_phai_nguon_chung():
    tt = lo(video(1, luot(M(A), M(B))), video(2, luot(M(A))), video(3, luot(M(B))))
    kl = co.ket_luan(tt)
    kql = co.dung_ket_qua_lo(tt, kl, ma_lo="lo2", kho_ten="K", thong_tin_goc={}, dem_ten={})
    rows = co.dong_bao_cao(kql)
    cot = {ten: i for i, ten in enumerate(co.HEADER_NGUON_CHUNG)}
    assert len(rows) == 3
    # «Không TÌM THẤY», không phải «không CÓ»: phương pháp có giới hạn (trần max_matches,
    # luật bù tốc độ) nên kết luận âm không được nói như một chứng minh tuyệt đối.
    assert all(r[cot["Kết luận"]].startswith("Không tìm thấy video gốc chung") for r in rows)
    assert not any("Không có video gốc chung" in r[cot["Kết luận"]] for r in rows)


@pytest.mark.parametrize("ten", ["Đoạn khớp (giây)", "Số hash khớp", "Tỷ lệ vân tay khớp (%)"])
def test_cot_so_nam_trong_header(ten):
    assert ten in co.COT_SO_NGUON_CHUNG and ten in co.HEADER_NGUON_CHUNG


# ---------------------------------------------------------------------------
#  Tên trùng trong kho: nhiều bản ghi vân tay cùng một basename
# ---------------------------------------------------------------------------
#
# `_merge` chỉ giữ basename của tên audfprint trả về (engine.py, `ten_clip`), nên
# «dir1/same.opus» (nội dung A) và «dir2/same.opus» (nội dung B) đều ra Match.clip
# "same.opus". Hai video khớp HAI bản ghi khác nhau trông y hệt một nguồn chung.

TRUNG = "same.opus"


def lo_trung(*videos, ten_trung=None):
    tt = lo(*videos)
    tt.ten_trung = dict(ten_trung or {TRUNG: 2})
    return tt


def test_dem_ten_kho_dem_theo_basename_cua_moi_ban_ghi():
    ds = [{"ten": TRUNG, "duong_dan": "D:/Kho1/same.opus"},
          {"ten": TRUNG, "duong_dan": "D:/Kho2/same.opus"},
          {"ten": A, "duong_dan": "D:/Kho1/" + A},
          {"duong_dan": "D:/Kho1/x.opus"}]
    assert co.dem_ten_kho(ds) == {TRUNG: 2, A: 1, "x.opus": 1}


def test_ten_trung_trong_kho_khong_bao_gio_la_TIM_THAY():
    tt = lo_trung(video(1, luot(M(TRUNG, 100))), video(2, luot(M(TRUNG, 900))))
    # Đối chứng: không biết tên trùng thì đây chính là dương tính giả.
    assert co.ket_luan(lo(*tt.videos)).trang_thai == co.TIM_THAY

    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.CHUA_KET_LUAN
    assert kl.goc is None and kl.tot_nhat == k(TRUNG) and kl.so_co_mat == 2
    assert "trùng tên" in kl.ly_do and "2 bản ghi" in kl.ly_do


def test_ten_trung_khong_che_mat_nguon_chung_ro_rang_va_duoc_neu_ra():
    tt = lo_trung(video(1, luot(M(TRUNG, 100, hashes=20000), M(A, 2000))),
                  video(2, luot(M(TRUNG, 50, hashes=20000), M(A, 3000))))
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.TIM_THAY and kl.goc == k(A)
    assert k(TRUNG) not in kl.goc_khac
    kql = co.dung_ket_qua_lo(tt, kl, ma_lo="l", kho_ten="K", thong_tin_goc={},
                             dem_ten={TRUNG: 2, A: 1})
    assert any(TRUNG in x and "không tính" in x for x in kql.canh_bao)


# ---------------------------------------------------------------------------
#  «Không tìm thấy» không phải chứng minh tuyệt đối
# ---------------------------------------------------------------------------

def _cot():
    return {ten: i for i, ten in enumerate(co.HEADER_NGUON_CHUNG)}


def test_khong_tim_thay_sach_thi_khong_co_gioi_han():
    tt = lo(video(1, luot(M(A), bu=True)), video(2, luot(M(B), bu=True)))
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.KHONG_TIM_THAY and kl.gioi_han == ()


def test_khong_tim_thay_co_khuc_cham_tran_thi_mang_gioi_han_toi_tan_csv():
    tt = lo(video(1, luot(M(A), cham_tran=3, bu=True)), video(2, luot(M(B), bu=True)))
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.KHONG_TIM_THAY
    assert any("3 khúc" in x and "max_matches" in x for x in kl.gioi_han)
    assert "chưa loại trừ tuyệt đối" in kl.ly_do
    kql = co.dung_ket_qua_lo(tt, kl, ma_lo="l", kho_ten="K", thong_tin_goc={}, dem_ten={})
    assert kql.gioi_han == kl.gioi_han
    rows = co.dong_bao_cao(kql)
    assert all("max_matches" in r[_cot()["Ghi chú"]] for r in rows)
    assert all("chưa loại trừ tuyệt đối" in r[_cot()["Kết luận"]] for r in rows)


def test_khong_tim_thay_luot_tron_khong_thu_bu_toc_do_thi_neu_gioi_han():
    tt = lo(video(1, luot(M(A))), video(2, luot(M(B), bu=True)))
    assert any("bù tốc độ" in x and "1/2" in x for x in co.ket_luan(tt).gioi_han)
    cfg = Config()
    cfg.quet_da_toc_do = False
    tt2 = lo(video(1, luot(M(A))), video(2, luot(M(B))), cfg=cfg)
    assert any("đang tắt" in x for x in co.ket_luan(tt2).gioi_han)


def test_tim_thay_khong_mang_gioi_han_cua_ket_luan_am():
    tt = lo(video(1, luot(M(A), cham_tran=5)), video(2, luot(M(A))))
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.TIM_THAY and kl.gioi_han == ()


def test_luot_ghi_lai_co_thu_bu_toc_do_hay_khong():
    from chan_doan_quet import ChanDoanQuet
    kq = _kq(dat=[M(A)])
    kq.chan_doan = ChanDoanQuet()
    kq.chan_doan.da_thu_toc_do = ["đo từ độ trôi: video nhanh 2,0%"]
    assert co.luot_tu_ket_qua(kq, "collect", DD).thu_bu_toc_do
    kq.chan_doan.da_thu_toc_do = []
    assert not co.luot_tu_ket_qua(kq, "collect", DD).thu_bu_toc_do


def test_ten_trang_thai_va_nhan_khong_tim_thay_khong_noi_tuyet_doi():
    assert co.TEN_TRANG_THAI_LO[co.KHONG_TIM_THAY] == "Không tìm thấy video gốc chung"
