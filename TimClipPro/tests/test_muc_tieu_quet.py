# -*- coding: utf-8 -*-
"""Mục tiêu của một lượt quét — nền của chế độ «một video gốc chung cho cả lô».

Ba câu hỏi phải trả lời được bằng test:
1. Ứng viên ĐẠT CHUẨN trước khi cắt Top-N có được lộ ra đúng, không phá báo cáo/lịch sử?
2. Ở chế độ xác minh, thấy một nguồn KHÁC (dù rất mạnh) có bao giờ làm dừng quét không?
3. Chưa thấy đích thì có tải nốt / tải lại / bù tốc độ đủ trước khi coi là vắng mặt không?

Thế giới bên ngoài (FFmpeg, audfprint, yt-dlp) là bản giả ở ranh giới tiến trình trong
``golden_quet.py``; mọi quyết định của engine chạy thật.
"""

import dataclasses

import pytest

from chap_nhan_khop import loc_chap_nhan
from engine import ScanObjective, ScanResult
from golden_quet import KICH_BAN, Dat, KichBan, chay

_A = "A [aaaaaaaaaaa].opus"
_B = "B [bbbbbbbbbbb].opus"
_C = "C [ccccccccccc].opus"


def _m(clip):
    from conftest import M
    return M(clip=clip, hashes=2000)


# ---------------------------------------------------------------------------
#  ScanObjective — hàm thuần
# ---------------------------------------------------------------------------

def test_thu_thap_khong_bao_gio_dat_de_khong_bao_gio_dung_som():
    mt = ScanObjective("collect")
    assert not mt.da_dat([_m(_A), _m(_B), _m(_C)])


def test_xac_minh_chi_dat_khi_MOI_nhom_dich_co_mat():
    mt = ScanObjective("verify", nhom_can_du=({_A}, {_C}))
    assert not mt.da_dat([_m(_B)]), "nguồn khác không bao giờ làm đạt"
    assert not mt.da_dat([_m(_A), _m(_B)])
    assert mt.da_dat([_m(_C), _m(_A)])


def test_xac_minh_mot_nhom_xac_nhan_ngay_la_du():
    mt = ScanObjective("verify", nhom_can_du=({_A}, {_C}), nhom_du_mot=({_B},))
    assert mt.da_dat([_m(_B)])
    assert not mt.da_dat([])


def test_nhom_dich_la_tap_ten_clip_cua_mot_video_goc():
    mt = ScanObjective("verify", nhom_can_du=({_A, "A ban sao.opus"},))
    assert mt.da_dat([_m("A ban sao.opus")])
    assert mt.nhom_can_du == (frozenset({_A, "A ban sao.opus"}),)


@pytest.mark.parametrize("kw", [
    {"mode": "legacy"},
    {"mode": "verify"},
    {"mode": "verify", "nhom_can_du": (set(),)},
    {"mode": "verify", "nhom_du_mot": (frozenset(),)},
])
def test_muc_tieu_vo_nghia_bi_tu_choi(kw):
    with pytest.raises(ValueError):
        ScanObjective(**kw)


# ---------------------------------------------------------------------------
#  ung_vien_dat — ứng viên đạt chuẩn TRƯỚC Top-N, chỉ sống trong bộ nhớ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kb", KICH_BAN, ids=[k.ten for k in KICH_BAN])
def test_ung_vien_dat_dung_bang_tap_dat_chuan_truoc_top_n(kb, tmp_path, monkeypatch):
    kq, e, _, _ = chay(kb, tmp_path, monkeypatch)
    assert len(kq.ung_vien_dat) == kq.so_dat_nguong
    id_dat = {id(m) for m in kq.ung_vien_dat}
    assert {id(m) for m in kq.matches} <= id_dat
    # Đúng bằng phần đạt chuẩn của mọi ứng viên đã gộp (matches + matches_loai).
    dat, _, _ = loc_chap_nhan(list(kq.matches) + list(kq.matches_loai), e.config)
    assert {id(m) for m in dat} == id_dat


def test_ung_vien_dat_giu_ca_ung_vien_dat_chuan_khong_duoc_chon(tmp_path, monkeypatch):
    """Top-1 là B nhưng A cũng đạt chuẩn: A phải nằm trong ung_vien_dat."""
    kb = KichBan("ab", "file", 600, {"top_n": 1, "quet_da_toc_do": False,
                                      "top1_tim_nhanh": False},
                 (Dat(_B, 10, 180, mat_do=30.0), Dat(_A, 300, 100)))
    kq, *_ = chay(kb, tmp_path, monkeypatch)
    assert [m.clip for m in kq.matches] == [_B]
    assert sorted(m.clip for m in kq.ung_vien_dat) == [_A, _B]


def test_ung_vien_dat_khong_vao_repr_va_khong_doi_so_sanh_bang():
    a = ScanResult(source_name="x")
    b = dataclasses.replace(a, ung_vien_dat=[_m(_A)])
    assert a == b
    assert "ung_vien_dat" not in repr(b)


def test_ung_vien_dat_khong_vao_lich_su_va_bao_cao(tmp_path, monkeypatch):
    kb = KichBan("ab2", "file", 600, {"top_n": 1, "quet_da_toc_do": False,
                                       "top1_tim_nhanh": False},
                 (Dat(_B, 10, 180, mat_do=30.0), Dat(_A, 300, 100)))
    kq, e, _, _ = chay(kb, tmp_path, monkeypatch)
    with e._db() as c:
        cot = [r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()]
        so_dong = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    assert not any("ung_vien" in x for x in cot)
    assert so_dong == len(kq.matches) == 1
    assert len(e.to_rows([kq])) == 1


# ---------------------------------------------------------------------------
#  Chế độ XÁC MINH trên đường quét file (điểm 1–5)
# ---------------------------------------------------------------------------

def _xm(*clip):
    return ScanObjective("verify", nhom_can_du=tuple({c} for c in clip))


def _khop(mt):
    """Chuỗi lần gọi audfprint: (hậu tố, số khúc)."""
    return [(x[1], len(x[2])) for x in mt.nhat_ky if x[0] == "khop"]


def _cat_max(mt):
    return max(int(x[1]) for x in mt.nhat_ky if x[0] == "cat")


def _clip_dat(kq):
    return sorted({m.clip for m in kq.ung_vien_dat})


def test_xac_minh_khong_dung_vi_nguon_KHAC_rat_manh_o_khuc_dau(tmp_path, monkeypatch):
    """Đường nhanh cũ dừng ở B (≥5000 hash). Xác minh A thì phải quét tiếp tới A."""
    kb = KichBan("xm1", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 10, 180, mat_do=30.0), Dat(_A, 450, 100)))
    _, _, mt_cu, _ = chay(kb, tmp_path / "cu", monkeypatch)
    assert _khop(mt_cu) == [("_uu_tien", 1)], "đối chứng: chế độ cũ dừng ở khúc đầu"

    kq, _, mt, _ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_A))
    assert _khop(mt) == [("_uu_tien", 1), ("_con_lai", 4)]
    assert _A in _clip_dat(kq)
    assert kq.quet_day_du


def test_xac_minh_dung_som_ngay_khi_thay_dich_du_chi_dat_chuan(tmp_path, monkeypatch):
    """Cổng của xác minh là ĐẠT CHUẨN, không phải cổng ≥5000 hash của Top-1."""
    kb = KichBan("xm2", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_A, 10, 60), Dat(_B, 300, 200)))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A))
    assert _khop(mt) == [("_uu_tien", 1)]
    assert _clip_dat(kq) == [_A]
    assert kq.ly_do_pham_vi == "dung_som" and not kq.quet_day_du
    assert kq.chan_doan.duong_di == "dung_som_thay_dich"
    assert "video gốc cần xác minh" in kq.note


def test_xac_minh_quet_tang_dan_khong_dung_o_B_ma_dung_sau_doan_co_A(tmp_path, monkeypatch):
    kb = KichBan("xm3", "file", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300), Dat(_A, 1600, 200)))
    _, _, mt_cu, _ = chay(kb, tmp_path / "cu", monkeypatch)
    assert _cat_max(mt_cu) < 720, "đối chứng: chế độ cũ dừng ngay đoạn đầu vì đã có B"

    kq, _, mt, _ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_A))
    assert 1440 <= _cat_max(mt) < 2160, "dừng ở đoạn 3 (có A), không quét đoạn 4"
    assert _clip_dat(kq) == [_A, _B]
    # Đoạn 1 có B (đạt chuẩn) nhưng vẫn quét trọn; ở đoạn 3 khúc đầu (1540–1740) đã có A
    # nên dừng ngay sau khúc đó.
    assert _khop(mt) == [("_uu_tien", 1), ("_con_lai", 5), ("_uu_tien", 1),
                         ("_con_lai", 4), ("_uu_tien", 1)]
    assert kq.ly_do_pham_vi == "dung_som" and kq.vung_da_khop == [(0.0, 1740.0)]


def test_xac_minh_khong_thay_dich_thi_quet_tron_va_bao_trung_thuc(tmp_path, monkeypatch):
    kb = KichBan("xm4", "file", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300),))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A))
    assert kq.quet_day_du and kq.status == "ok"
    assert _clip_dat(kq) == [_B]
    assert _cat_max(mt) == 2940


def test_xac_minh_khuc_loi_thi_khong_phai_vang_mat(tmp_path, monkeypatch):
    kb = KichBan("xm5", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 10, 60),), loi_cat=frozenset({280}))
    kq, *_ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A))
    assert not kq.quet_day_du and kq.vung_loi


def test_xac_minh_bu_toc_do_khi_chi_thieu_dich(tmp_path, monkeypatch):
    """B đạt chuẩn ở tốc độ thường; A chỉ khớp sau khi bù tốc độ. Cũ: không bù vì đã có B."""
    kb = KichBan("xm6", "file", 600, {"top_n": 1},
                 (Dat(_B, 10, 60), Dat(_A, 300, 250, toc_do=1.02, troi=True)))
    kq_cu, *_ = chay(kb, tmp_path / "cu", monkeypatch)
    assert _clip_dat(kq_cu) == [_B], "đối chứng: chế độ cũ không tìm A"

    kq, *_ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_A))
    assert _clip_dat(kq) == [_A, _B]
    assert kq.chan_doan.toc_do_tim_duoc


def test_xac_minh_vong_bu_khong_dung_vi_nguon_khac_ma_dung_khi_thay_dich(tmp_path, monkeypatch):
    """Lưới bù: lượt 1 thấy C (đổi tốc độ 0,96), lượt 3 mới thấy A (1,02).

    Cũ dừng ngay ở C; xác minh A phải chạy tiếp tới lượt 3 rồi DỪNG (không chạy lượt 4).
    """
    kb = KichBan("xm7", "file", 600, {"top_n": 1},
                 (Dat(_C, 50, 200, toc_do=0.96), Dat(_A, 300, 250, toc_do=1.02)))
    kq_cu, *_ = chay(kb, tmp_path / "cu", monkeypatch)
    assert len(kq_cu.chan_doan.da_thu_toc_do) == 1 and _clip_dat(kq_cu) == [_C]

    kq, *_ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_A))
    assert len(kq.chan_doan.da_thu_toc_do) == 3
    assert _clip_dat(kq) == [_A, _C]


def test_xac_minh_luot_bu_hong_khi_chua_thay_dich_la_vung_chua_kiem(tmp_path, monkeypatch):
    kb = KichBan("xm8", "file", 600, {"top_n": 1},
                 (Dat(_B, 10, 60),), loi_bien_doi=frozenset({140}))
    kq, *_ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A))
    assert kq.status == "ok" and _clip_dat(kq) == [_B]
    assert kq.vung_loi == [(200.0, 280.0)] and not kq.quet_day_du


def test_xac_minh_nhieu_nhom_chi_dung_khi_du_ca_nhom(tmp_path, monkeypatch):
    kb = KichBan("xm9", "file", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_A, 100, 100), Dat(_C, 1600, 100)))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A, _C))
    assert 1440 <= _cat_max(mt) < 2160
    assert _clip_dat(kq) == [_A, _C]


def test_xac_minh_mot_nhom_xac_nhan_ngay_thi_dung_som(tmp_path, monkeypatch):
    kb = KichBan("xm10", "file", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 100, 100), Dat(_A, 1600, 100)))
    muc_tieu = ScanObjective("verify", nhom_can_du=({_A}, {_C}), nhom_du_mot=({_B},))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=muc_tieu)
    assert _cat_max(mt) < 720
    assert _clip_dat(kq) == [_B]


def test_xac_minh_khong_tinh_ung_vien_tu_khop(tmp_path, monkeypatch):
    """File đang quét trùng tên clip trong kho: khớp với chính nó không phải bằng chứng."""
    kb = KichBan("xm11", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 10, 180, mat_do=30.0), Dat(_A, 450, 100)), ten_file=_B)
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch,
                        muc_tieu=ScanObjective("verify", nhom_can_du=({_B},)))
    assert _khop(mt) == [("_uu_tien", 1), ("_con_lai", 4)]
    assert _clip_dat(kq) == [_A]


# ---------------------------------------------------------------------------
#  Chế độ THU THẬP (video mốc)
# ---------------------------------------------------------------------------

def test_thu_thap_khong_dung_som_va_ra_dung_tap_cua_luot_quet_tron_cu(tmp_path, monkeypatch):
    dat = (Dat(_B, 100, 300), Dat(_A, 1600, 200), Dat(_C, 2500, 200))
    kb = KichBan("tt1", "file", 3000, {"top_n": 1, "quet_da_toc_do": False}, dat)
    kq, _, mt, _ = chay(kb, tmp_path / "moi", monkeypatch,
                        muc_tieu=ScanObjective("collect"))
    assert kq.quet_day_du
    assert all(x[1] == "" for x in mt.nhat_ky if x[0] == "khop"), "không có đường nhanh"

    tron = KichBan("tt1_cu", "file", 3000,
                   {"top_n": 1, "quet_da_toc_do": False, "quet_tang_dan": False,
                    "top1_tim_nhanh": False}, dat)
    kq_cu, *_ = chay(tron, tmp_path / "cu", monkeypatch)
    assert ([(m.clip, m.start_s, m.hashes) for m in kq.ung_vien_dat]
            == [(m.clip, m.start_s, m.hashes) for m in kq_cu.ung_vien_dat])


# ---------------------------------------------------------------------------
#  Đường YouTube (điểm 6–8, 10) và thông tin video lấy sẵn
# ---------------------------------------------------------------------------

def _tai(mt):
    return [x[1] for x in mt.nhat_ky if x[0] == "tai"]


def test_xac_minh_phan_tai_dau_du_top_n_nhung_thieu_dich_thi_tai_not(tmp_path, monkeypatch):
    kb = KichBan("yt1", "youtube", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300), Dat(_A, 2300, 300)))
    _, _, mt_cu, _ = chay(kb, tmp_path / "cu", monkeypatch)
    assert _tai(mt_cu) == [720.0], "đối chứng: chế độ cũ dừng ở 720 s đầu vì có B"

    kq, _, mt, _ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_A))
    assert _tai(mt) == [720.0, None]
    assert _clip_dat(kq) == [_A, _B]


def test_xac_minh_thay_dich_trong_phan_tai_dau_thi_khong_tai_not(tmp_path, monkeypatch):
    kb = KichBan("yt2", "youtube", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_A, 100, 300),))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A))
    assert _tai(mt) == [720.0]
    assert kq.ly_do_pham_vi == "gioi_han_tai"
    assert "video gốc cần xác minh" in kq.note


def test_xac_minh_tai_lai_file_cut_khi_chua_thay_dich(tmp_path, monkeypatch):
    kb = KichBan("yt3", "youtube", 3000,
                 {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300), Dat(_A, 2700, 200)), tai=(2500, 3000))
    _, _, mt_cu, _ = chay(kb, tmp_path / "cu", monkeypatch)
    assert _tai(mt_cu) == [None], "đối chứng: chế độ cũ giữ bằng chứng B, không tải lại"

    kq, _, mt, _ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_A))
    assert _tai(mt) == [None, None]
    assert _clip_dat(kq) == [_A, _B] and kq.quet_day_du


def test_thu_thap_tai_tron_ngay_khong_tai_mot_phan(tmp_path, monkeypatch):
    kb = KichBan("yt4", "youtube", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300),))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=ScanObjective("collect"))
    assert _tai(mt) == [None]
    assert kq.quet_day_du


def test_thu_thap_file_cut_thi_tai_lai_ke_ca_khi_da_co_ket_qua(tmp_path, monkeypatch):
    kb = KichBan("yt5", "youtube", 3000,
                 {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300), Dat(_C, 2700, 200)), tai=(2500, 3000))
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=ScanObjective("collect"))
    assert _tai(mt) == [None, None]
    assert _clip_dat(kq) == [_B, _C] and kq.quet_day_du


def test_ban_tai_lai_quet_loi_thi_giu_bang_chung_luot_dau(tmp_path, monkeypatch):
    """Điểm 10: lượt quét bản tải lại hỏng không được xoá bằng chứng của lượt đầu."""
    kb = KichBan("yt6", "youtube", 3000,
                 {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300),), tai=(2500, 3000), loi_audfprint_lan=3)
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, muc_tieu=_xm(_A))
    assert _tai(mt) == [None, None]
    assert kq.status == "ok" and _clip_dat(kq) == [_B]
    assert kq.vung_loi == [(2500.0, 3000.0)] and not kq.quet_day_du


def test_scan_youtube_dung_thong_tin_lay_san_khong_hoi_lai(tmp_path, monkeypatch):
    kb = KichBan("yt7", "youtube", 3000, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 100, 300),))
    info = {"id": "vidvipham01", "title": "Đã lấy sẵn", "duration": 3000,
            "channel": "K", "channel_id": "UCk", "channel_url": "u", "upload_date": ""}
    kq, _, mt, _ = chay(kb, tmp_path, monkeypatch, info=info)
    assert not [x for x in mt.nhat_ky if x[0] == "info"]
    assert kq.source_name == "Đã lấy sẵn"


# ---------------------------------------------------------------------------
#  Mục tiêu không rò; API job công khai
# ---------------------------------------------------------------------------

def _hai_file(tmp_path, monkeypatch, kb):
    from golden_quet import MoiTruongGia, tao_engine
    e = tao_engine(kb, tmp_path)
    mt = MoiTruongGia(kb, e, str(tmp_path))
    mt.lap(monkeypatch)
    duong = []
    for ten in ("v1.mp4", "v2.mp4"):
        p = tmp_path / ten
        p.write_bytes(b"x")
        mt.thoi_luong[mt._khoa(str(p))] = float(kb.tong_s)
        duong.append(str(p))
    return e, mt, duong


def test_muc_tieu_khong_ro_sang_luot_sau_trong_cung_job(tmp_path, monkeypatch):
    kb = KichBan("ro1", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 10, 180, mat_do=30.0), Dat(_A, 450, 100)))
    e, mt, (v1, v2) = _hai_file(tmp_path, monkeypatch, kb)
    with e.phien_job() as job:
        assert job is not e and job._la_ban_ghim
        kq1 = job.scan_media(v1, muc_tieu=_xm(_A), luu_lich_su=False)
        so_goi = len(_khop(mt))
        kq2 = job.scan_media(v2, luu_lich_su=False)
    assert _A in _clip_dat(kq1)
    assert _khop(mt)[so_goi:] == [("_uu_tien", 1)], "lượt sau phải là hành vi CŨ"
    assert kq2.chan_doan.duong_di == "dung_som_vung_dau"
    assert getattr(job, "_pham_vi", None) is None


def test_muc_tieu_khong_ro_sang_engine_goc(tmp_path, monkeypatch):
    kb = KichBan("ro2", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 10, 180, mat_do=30.0), Dat(_A, 450, 100)))
    e, mt, (v1, v2) = _hai_file(tmp_path, monkeypatch, kb)
    e.scan_media(v1, muc_tieu=_xm(_A), luu_lich_su=False)
    so_goi = len(_khop(mt))
    e.scan_media(v2, luu_lich_su=False)
    assert _khop(mt)[so_goi:] == [("_uu_tien", 1)]
    assert getattr(e, "_pham_vi", None) is None


def test_phien_job_tra_chan_doan_ve_engine_goc(tmp_path, monkeypatch):
    kb = KichBan("pj", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                 (Dat(_B, 10, 60),))
    e, _, (v1, _) = _hai_file(tmp_path, monkeypatch, kb)
    with e.phien_job() as job:
        job.config.top_n = 7
        job.scan_media(v1, luu_lich_su=False)
    assert e.config.top_n == 1, "cấu hình của job là bản sao, không đổi engine gốc"
    assert e.chan_doan_quet is job.chan_doan_quet


def test_danh_tinh_kho_cong_khai_khong_ghi_gi(tmp_path):
    from engine import Engine
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    dt = e.danh_tinh_kho()
    assert set(dt) == {"kho_id", "kho_ten", "kho_phien_ban"}
    assert dt["kho_id"] == "db:db.pklz"


# ---------------------------------------------------------------------------
#  Qua parser, `_merge`, chấp nhận THẬT — những gì chế độ nguồn chung dựa vào
# ---------------------------------------------------------------------------

def _dau_van(m):
    return (m.clip, round(m.start_s, 3), round(m.end_s, 3), round(m.matched_s, 3),
            int(m.hashes), round(m.clip_offset_s, 3), m.ty_le, m.vung)


@pytest.mark.parametrize("dat", [
    # Đoạn A thứ hai bị đổi tốc độ 2%, có mảnh trôi để lượt bù đo tốc độ.
    (Dat(_A, 10, 60), Dat(_A, 300, 250, toc_do=1.02, troi=True)),
    # Bằng chứng bù CHỒNG lên đúng vùng của A thường (lưới cao độ 1,02).
    (Dat(_A, 10, 60), Dat(_A, 20, 60, toc_do=1.02)),
], ids=["doan_khac", "chong_vung"])
def test_bang_chung_them_tu_luot_bu_toc_do_khong_lam_mat_A_da_dat(dat, tmp_path, monkeypatch):
    """A đã đạt chuẩn ở lượt thường. Xác minh một đích KHÁC (C, vắng mặt) buộc lượt bù tốc độ
    chạy, và lượt bù để lại THÊM bằng chứng của chính A. A của lượt thường phải còn y nguyên
    — không bị gộp với mảnh khác hệ số tốc độ, không bị lọc; bằng chứng bù chỉ THÊM ứng viên.
    """
    kb = KichBan("bu_them_A", "file", 600, {"top_n": 1}, dat)
    kq_cu, *_ = chay(kb, tmp_path / "cu", monkeypatch)
    assert not kq_cu.chan_doan.da_thu_toc_do, "đối chứng: chế độ cũ đã có A nên không bù"
    a_thuong = [_dau_van(m) for m in kq_cu.ung_vien_dat if m.clip == _A]
    assert len(a_thuong) == 1

    kq, *_ = chay(kb, tmp_path / "moi", monkeypatch, muc_tieu=_xm(_C))
    assert kq.status == "ok" and kq.quet_day_du
    assert kq.chan_doan.da_thu_toc_do, "đích C vắng mặt nên lượt bù PHẢI chạy dù đã có A"
    cua_a = [_dau_van(m) for m in kq.ung_vien_dat if m.clip == _A]
    assert a_thuong[0] in cua_a, "A của lượt thường phải còn nguyên"
    assert len(cua_a) == 2, "bằng chứng bù là ứng viên RIÊNG, không gộp vào A thường"

    # Chế độ nguồn chung đọc đúng điều đó: A CÓ MẶT ở video này.
    import common_original as co
    lq = co.luot_tu_ket_qua(kq, "verify", (kq.kho_id, kq.kho_phien_ban, kq.chinh_sach))
    v = co.VideoTrongLo(thu_tu=1, nguon="v", luot=[lq])
    assert v.trang_thai(co.khoa_goc(kq.kho_id, _A), kq.kho_id) == co.CO_MAT
    assert lq.thu_bu_toc_do


def test_hai_ban_ghi_cung_ten_ra_cung_match_clip_va_lo_khong_tim_thay_gia(tmp_path,
                                                                        monkeypatch):
    """«dir1/same.opus» và «dir2/same.opus» là HAI bản ghi vân tay khác nhau. audfprint báo
    đường dẫn khác nhau, nhưng `_merge` chỉ giữ basename: video 1 khớp bản ghi 1, video 2
    khớp bản ghi 2 mà cả hai đều ra Match.clip "same.opus". Lô không được coi đó là nguồn
    chung — dữ liệu không phân biệt được hai bản ghi."""
    import dataclasses as dc

    import common_original as co
    kb1 = KichBan("trung", "file", 600, {"top_n": 1, "quet_da_toc_do": False},
                  (Dat("dir1/same.opus", 10, 120),))
    e, mt, (v1, v2) = _hai_file(tmp_path, monkeypatch, kb1)
    ds_kho = [{"ten": "same.opus", "duong_dan": "D:/Kho/dir1/same.opus", "so_hash": 20000},
              {"ten": "same.opus", "duong_dan": "D:/Kho/dir2/same.opus", "so_hash": 20000},
              {"ten": _A, "duong_dan": "D:/Kho/" + _A, "so_hash": 20000}]
    e.db_clips = lambda bo_cache=False: ds_kho
    with e.phien_job() as job:
        kq1 = job.scan_media(v1, luu_lich_su=False, muc_tieu=ScanObjective("collect"))
        mt.kb = dc.replace(kb1, dat=(Dat("dir2/same.opus", 200, 120),))
        kq2 = job.scan_media(v2, luu_lich_su=False, muc_tieu=ScanObjective("collect"))
    assert _clip_dat(kq1) == _clip_dat(kq2) == ["same.opus"], \
        "hai bản ghi khác nhau ra CÙNG một tên clip — không phân biệt được"

    dd = (kq1.kho_id, kq1.kho_phien_ban, kq1.chinh_sach)
    videos = [co.VideoTrongLo(thu_tu=i, nguon=f"v{i}",
                              luot=[co.luot_tu_ket_qua(kq, "collect", dd)])
              for i, kq in enumerate((kq1, kq2), 1)]
    khong_biet = co.TrangThaiLo(kho_id=dd[0], videos=videos, cfg=e.config)
    assert co.ket_luan(khong_biet).trang_thai == co.TIM_THAY, \
        "đối chứng: không biết tên trùng thì đây là dương tính giả"
    dem = co.dem_ten_kho(ds_kho)
    tt = co.TrangThaiLo(kho_id=dd[0], videos=videos, cfg=e.config,
                        ten_trung={t: n for t, n in dem.items() if n > 1})
    kl = co.ket_luan(tt)
    assert kl.trang_thai == co.CHUA_KET_LUAN and kl.goc is None
