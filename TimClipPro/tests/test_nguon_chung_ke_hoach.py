# -*- coding: utf-8 -*-
"""Bộ lập kế hoạch thuần của chế độ «một video gốc chung cho cả lô».

Ngoài các ca định danh, có một MÔ PHỎNG 2.000 thế giới ngẫu nhiên (seed cố định): mỗi video
chứa một tập video gốc ở vị trí ngẫu nhiên; lượt quét giả dừng sớm đúng như engine (chỉ khi
mục tiêu đạt), có lỗi và quét-dở tiêm vào. Các tính chất phải giữ ở MỌI thế giới:

* TÌM THẤY  ⇒ video gốc đó thật sự có ở mọi video (không dương tính giả);
* KHÔNG TÌM THẤY ⇒ thật sự không có video gốc chung (không âm tính giả);
* không có lỗi tiêm vào ⇒ luôn có kết luận dứt khoát, và có nguồn chung thì phải TÌM THẤY;
* mỗi video bị quét tối đa 2 lượt.
"""

import random

import pytest

import common_original as co
from engine import Config, Match

KHO = "k"


def M(clip, start=0.0, hashes=6000, matched=300.0, ty_le=50.0):
    return Match(clip=clip, start_s=start, end_s=start + matched, matched_s=matched,
                 clip_offset_s=0.0, hashes=hashes, confidence="x", ty_le=ty_le,
                 clip_bat_dau_s=start, vung_khop_s=start)


def video(i, thoi_luong=None):
    return co.VideoTrongLo(thu_tu=i, nguon=f"v{i}", ma=f"v{i}", thoi_luong=thoi_luong)


def lo(*videos):
    tt = co.TrangThaiLo(kho_id=KHO, videos=list(videos), cfg=Config())
    tt.thu_tu_xu_ly = co.chon_thu_tu_xu_ly(tt.videos)
    return tt


def luot(*ms, tron=True, hop_le=True, muc_tieu="collect"):
    return co.LuotQuet(muc_tieu=muc_tieu, hop_le=hop_le, tron=tron and hop_le,
                       ung_vien=tuple(ms) if hop_le else ())


def ghi(tt, b, lq):
    """Ghi một lượt như bộ điều phối làm (kể cả chốt video mốc)."""
    co.ghi_luot(tt, b, lq)


# ---------------------------------------------------------------------------
#  Thứ tự và video mốc
# ---------------------------------------------------------------------------

def test_thu_tu_xu_ly_ngan_truoc_chua_biet_thoi_luong_sau_hoa_theo_thu_tu_nhap():
    vids = [video(1, 7200), video(2, None), video(3, 3600), video(4, 3600), video(5, None)]
    assert co.chon_thu_tu_xu_ly(vids) == [2, 3, 0, 1, 4]


def test_buoc_dau_tien_la_thu_thap_tron_video_ngan_nhat():
    tt = lo(video(1, 7200), video(2, 3600), video(3, 9000))
    b = co.buoc_tiep(tt)
    assert (b.video, b.muc_tieu, b.pha) == (1, "collect", "moc")


def test_moc_loi_thi_lay_video_ke_tiep_lam_moc():
    tt = lo(video(1, 7200), video(2, 3600))
    ghi(tt, co.buoc_tiep(tt), luot(hop_le=False))
    b = co.buoc_tiep(tt)
    assert (b.video, b.muc_tieu) == (0, "collect")


def test_pha_nhanh_xac_minh_ung_vien_dau_bang_cua_moc():
    tt = lo(video(1, 3600), video(2, 7200), video(3, 9000))
    ghi(tt, co.buoc_tiep(tt), luot(M("A", hashes=9000, matched=600), M("B", hashes=1500,
                                                                      matched=60)))
    assert tt.moc == 0 and tt.muc_tieu_nhanh == co.khoa_goc(KHO, "A")
    b = co.buoc_tiep(tt)
    assert (b.video, b.muc_tieu, b.pha) == (1, "verify", "nhanh")
    assert b.nhom_can_du == (co.khoa_goc(KHO, "A"),) and b.nhom_du_mot == ()


def test_video_cuoi_cua_pha_nhanh_co_nhom_xac_nhan_ngay():
    tt = lo(video(1, 3600), video(2, 7200), video(3, 9000))
    ghi(tt, co.buoc_tiep(tt), luot(M("A"), M("B", hashes=1500)))
    ghi(tt, co.buoc_tiep(tt), luot(M("A"), M("B"), tron=False, muc_tieu="verify"))
    b = co.buoc_tiep(tt)
    assert b.video == 2
    assert set(b.nhom_du_mot) == {co.khoa_goc(KHO, "A"), co.khoa_goc(KHO, "B")}


def test_dich_vang_mat_du_thi_chuyen_bo_sung_nham_dung_phan_chua_ro():
    tt = lo(video(1, 3600), video(2, 7200), video(3, 9000))
    ghi(tt, co.buoc_tiep(tt), luot(M("A"), M("B", hashes=1500), M("C", hashes=1400)))
    # Video 2: thấy A sớm, dừng (chưa rõ B, C).
    ghi(tt, co.buoc_tiep(tt), luot(M("A"), tron=False, muc_tieu="verify"))
    # Video 3: quét TRỌN mà không có A, có B và C → A bị loại.
    ghi(tt, co.buoc_tiep(tt), luot(M("B"), M("C"), muc_tieu="verify"))
    assert co.tap_kha_di(tt) == {co.khoa_goc(KHO, "B"), co.khoa_goc(KHO, "C")}
    b = co.buoc_tiep(tt)
    assert (b.video, b.muc_tieu, b.pha) == (1, "verify", "bo_sung")
    assert set(b.nhom_can_du) == {co.khoa_goc(KHO, "B"), co.khoa_goc(KHO, "C")}
    assert set(b.nhom_du_mot) == {co.khoa_goc(KHO, "B"), co.khoa_goc(KHO, "C")}


def test_moi_video_toi_da_hai_luot():
    tt = lo(video(1, 3600), video(2, 7200))
    ghi(tt, co.buoc_tiep(tt), luot(M("A")))
    ghi(tt, co.buoc_tiep(tt), luot(hop_le=False, muc_tieu="verify"))
    ghi(tt, co.buoc_tiep(tt), luot(hop_le=False, muc_tieu="verify"))
    assert len(tt.videos[1].luot) == 2
    assert co.buoc_tiep(tt) is None
    assert co.ket_luan(tt).trang_thai == co.CHUA_KET_LUAN


def test_buoc_quet_doi_ra_muc_tieu_engine_theo_ten_clip():
    b = co.BuocQuet(video=0, muc_tieu="verify", nhom_can_du=(co.khoa_goc(KHO, "A"),),
                    nhom_du_mot=(co.khoa_goc(KHO, "B"),))
    mt = b.objective()
    assert mt.mode == "verify"
    assert mt.nhom_can_du == (frozenset({"A"}),) and mt.nhom_du_mot == (frozenset({"B"}),)
    assert co.BuocQuet(video=0, muc_tieu="collect").objective().mode == "collect"


# ---------------------------------------------------------------------------
#  dieu_phoi: vòng lặp thuần, có huỷ và dừng hẳn
# ---------------------------------------------------------------------------

def test_dieu_phoi_dung_khi_bi_huy_khong_mo_luot_moi():
    tt = lo(video(1, 3600), video(2, 7200), video(3, 9000))
    goi = []

    def quet(b):
        goi.append(b.video)
        return luot(M("A"), muc_tieu=b.muc_tieu)

    kl = co.dieu_phoi(tt, quet, da_huy=lambda: len(goi) >= 1)
    assert goi == [0]
    assert kl.trang_thai == co.DA_HUY


def test_dieu_phoi_dung_han_khi_lo_khong_con_nhat_quan():
    tt = lo(video(1, 3600), video(2, 7200))

    def quet(b):
        raise co.DungLo("Kho vân tay đã đổi trong lúc quét lô.")

    kl = co.dieu_phoi(tt, quet)
    assert kl.trang_thai == co.CHUA_KET_LUAN and "Kho vân tay đã đổi" in kl.ly_do


def test_dieu_phoi_goi_sau_moi_luot():
    tt = lo(video(1, 3600), video(2, 7200))
    da_goi = []
    kl = co.dieu_phoi(tt, lambda b: luot(M("A"), muc_tieu=b.muc_tieu),
                      sau_moi_luot=lambda b, lq: da_goi.append((b.video, b.muc_tieu)))
    assert kl.trang_thai == co.TIM_THAY
    assert da_goi == [(0, "collect"), (1, "verify")]


# ---------------------------------------------------------------------------
#  Mô phỏng 2.000 thế giới
# ---------------------------------------------------------------------------

def _mo_phong(seed: int):
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    clips = [f"c{i}" for i in range(rng.randint(1, 7))]
    the_gioi = [{c: rng.random() for c in clips if rng.random() < 0.55} for _ in range(n)]
    if rng.random() < 0.5:
        chung = rng.choice(clips)
        for tg in the_gioi:
            tg.setdefault(chung, rng.random())
    co_loi = rng.random() < 0.35
    tt = lo(*[video(i + 1, rng.choice([None, rng.uniform(1, 30)])) for i in range(n)])

    def quet(b):
        hien = the_gioi[b.video]
        if co_loi and rng.random() < 0.15:
            return luot(hop_le=False, muc_tieu=b.muc_tieu)
        dung = 1.0
        if b.muc_tieu == "verify":
            can = [k.clip for k in b.nhom_can_du]
            mot = [k.clip for k in b.nhom_du_mot]
            ung = []
            if can and all(c in hien for c in can):
                ung.append(max(hien[c] for c in can))
            ung += [hien[c] for c in mot if c in hien]
            dung = min(ung) if ung else 1.0
        tron = dung >= 1.0
        if co_loi and rng.random() < 0.15:          # quét dở vì vùng lỗi
            dung, tron = min(dung, rng.random()), False
        thay = [M(c, start=p * 1000) for c, p in sorted(hien.items()) if p <= dung]
        return luot(*thay, tron=tron, muc_tieu=b.muc_tieu)

    kl = co.dieu_phoi(tt, quet)
    that_su_chung = set.intersection(*[set(tg) for tg in the_gioi])
    return kl, tt, that_su_chung, co_loi


@pytest.mark.parametrize("khoi", range(20))
def test_mo_phong_dung_va_du_tren_2000_the_gioi(khoi):
    for seed in range(khoi * 100, khoi * 100 + 100):
        kl, tt, that_su_chung, co_loi = _mo_phong(seed)
        if kl.trang_thai == co.TIM_THAY:
            assert kl.goc.clip in that_su_chung, f"seed {seed}: dương tính giả"
        if kl.trang_thai == co.KHONG_TIM_THAY:
            assert not that_su_chung, f"seed {seed}: âm tính giả"
        if not co_loi:
            assert kl.trang_thai in (co.TIM_THAY, co.KHONG_TIM_THAY), f"seed {seed}"
            assert (kl.trang_thai == co.TIM_THAY) == bool(that_su_chung), f"seed {seed}"
        assert all(len(v.luot) <= 2 for v in tt.videos), f"seed {seed}: quá 2 lượt"


# ---------------------------------------------------------------------------
#  Tên trùng trong kho: khoá không phân biệt được bản ghi không điều khiển kế hoạch
# ---------------------------------------------------------------------------

def test_ung_vien_trung_ten_khong_lam_dich_nhanh_va_khong_xac_nhan_ngay():
    tt = lo(video(1, 3600), video(2, 7200), video(3, 9000))
    tt.ten_trung = {"T": 2}
    ghi(tt, co.buoc_tiep(tt), luot(M("T", hashes=20000, matched=900),
                                   M("A", hashes=9000, matched=600)))
    assert tt.muc_tieu_nhanh == co.khoa_goc(KHO, "A"), "khoá trùng tên không được làm đích"
    ghi(tt, co.buoc_tiep(tt), luot(M("T"), M("A"), tron=False, muc_tieu="verify"))
    b = co.buoc_tiep(tt)
    assert b.video == 2
    assert co.khoa_goc(KHO, "T") not in b.nhom_du_mot + b.nhom_can_du


def test_chi_con_ung_vien_trung_ten_thi_dung_lap_ke_hoach_va_chua_ket_luan():
    tt = lo(video(1, 3600), video(2, 7200))
    tt.ten_trung = {"T": 2}
    ghi(tt, co.buoc_tiep(tt), luot(M("T"), M("A")))
    ghi(tt, co.buoc_tiep(tt), luot(M("T"), muc_tieu="verify"))     # trọn, không có A
    assert co.buoc_tiep(tt) is None
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.CHUA_KET_LUAN and "trùng tên" in kl.ly_do


def _mo_phong_ten_trung(seed: int):
    """Như ``_mo_phong`` nhưng một vài tên clip ứng với HAI video gốc khác nhau trong kho.

    Máy quét chỉ thấy TÊN (basename) — đúng như engine — còn sự thật tính theo bản ghi.
    """
    rng = random.Random(seed)
    n = rng.randint(2, 5)
    so_ten = rng.randint(1, 5)
    goc = [(f"c{i}", 0) for i in range(so_ten)]                 # (tên clip, bản ghi)
    trung = rng.sample(range(so_ten), k=rng.randint(1, min(2, so_ten)))
    goc += [(f"c{i}", 1) for i in trung]
    ten_trung = {f"c{i}": 2 for i in trung}
    the_gioi = [{g: rng.random() for g in goc if rng.random() < 0.55} for _ in range(n)]
    if rng.random() < 0.6:
        chung = rng.choice(goc)
        for tg in the_gioi:
            tg.setdefault(chung, rng.random())
    co_loi = rng.random() < 0.35
    tt = lo(*[video(i + 1, rng.choice([None, rng.uniform(1, 30)])) for i in range(n)])
    tt.ten_trung = dict(ten_trung)

    def quet(b):
        hien: dict = {}
        for (ten, _), p in the_gioi[b.video].items():
            hien[ten] = min(p, hien.get(ten, 1.0))
        if co_loi and rng.random() < 0.15:
            return luot(hop_le=False, muc_tieu=b.muc_tieu)
        dung = 1.0
        if b.muc_tieu == "verify":
            can = [k.clip for k in b.nhom_can_du]
            mot = [k.clip for k in b.nhom_du_mot]
            ung = []
            if can and all(c in hien for c in can):
                ung.append(max(hien[c] for c in can))
            ung += [hien[c] for c in mot if c in hien]
            dung = min(ung) if ung else 1.0
        tron = dung >= 1.0
        if co_loi and rng.random() < 0.15:
            dung, tron = min(dung, rng.random()), False
        thay = [M(c, start=p * 1000) for c, p in sorted(hien.items()) if p <= dung]
        return luot(*thay, tron=tron, muc_tieu=b.muc_tieu)

    kl = co.dieu_phoi(tt, quet)
    that_su_chung = set.intersection(*[set(tg) for tg in the_gioi])
    return kl, tt, that_su_chung, ten_trung, co_loi


@pytest.mark.parametrize("khoi", range(10))
def test_mo_phong_ten_trung_khong_tao_nguon_chung_gia(khoi):
    for seed in range(khoi * 100, khoi * 100 + 100):
        kl, tt, chung, ten_trung, co_loi = _mo_phong_ten_trung(seed)
        chung_ro = {ten for ten, _ in chung if ten not in ten_trung}
        if kl.trang_thai == co.TIM_THAY:
            assert kl.goc.clip not in ten_trung, f"seed {seed}: xác nhận một tên trùng"
            assert kl.goc.clip in chung_ro, f"seed {seed}: dương tính giả"
        if kl.trang_thai == co.KHONG_TIM_THAY:
            assert not chung, f"seed {seed}: âm tính giả"
        if not co_loi:
            assert (kl.trang_thai == co.TIM_THAY) == bool(chung_ro), f"seed {seed}"
            if chung and not chung_ro:
                assert kl.trang_thai == co.CHUA_KET_LUAN, f"seed {seed}"
        assert all(len(v.luot) <= 2 for v in tt.videos), f"seed {seed}: quá 2 lượt"
