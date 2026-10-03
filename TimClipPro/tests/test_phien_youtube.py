# -*- coding: utf-8 -*-
"""Phiên truy cập YouTube: thử lại HỮU HẠN, huỷ được, cầu dao theo lượt chạy, số đo.

Lỗi là chuỗi tổng hợp theo khuôn câu của yt-dlp; không gọi mạng. Thời gian chờ thử lại được
thay bằng hàm ghi lại (trừ ca kiểm huỷ, dùng Event thật).
"""

import threading
import time

import pytest

import truy_cap_youtube as t
import ytdlp_chung as y

BOT = "ERROR: [youtube] x: Sign in to confirm you're not a bot."
AUTH = "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate."
GO = "ERROR: [youtube] oNgXYOLAJWk: Video unavailable"
TAM = "ERROR: [youtube] x: Unable to download API page: The read operation timed out"
R429 = "ERROR: [youtube] x: Unable to download API page: HTTP Error 429: Too Many Requests"
PHIEN_GIOI_HAN = ("ERROR: [youtube] x: This content isn't available, try again later. The current "
                  "session has been rate-limited by YouTube for up to an hour.")
C403 = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
DINH_DANG = "ERROR: [youtube] x: Requested format is not available."


class _Huy(Exception):
    pass


def _phien(**k):
    da_cho = []

    def cho(giay, ev=None):
        da_cho.append(giay)
        return False

    p = t.PhienYouTube(ham_cho=cho, **k)
    return p, da_cho


def _ham(*ket_qua):
    """Hàm giả: lần lượt ném lỗi (chuỗi) hoặc trả giá trị; đếm số lần gọi."""
    goi = []
    hang = list(ket_qua)

    def ham():
        goi.append(1)
        x = hang.pop(0) if hang else "xong"
        if isinstance(x, str) and x.startswith("ERROR"):
            raise RuntimeError(x)
        return x

    return ham, goi


# ---------------------------------------------------------------- thử lại hữu hạn

def test_thanh_cong_ngay_khong_thu_lai():
    p, cho = _phien()
    ham, goi = _ham("xong")
    assert p.chay("metadata", ham) == "xong"
    assert len(goi) == 1 and cho == []
    assert p.tom_tat()["youtube_operations"] == 1 and p.tom_tat()["retries"] == 0


def test_loi_mang_tam_thoi_roi_thanh_cong_thu_lai_dung_mot_lan():
    p, cho = _phien()
    ham, goi = _ham(TAM, "xong")
    assert p.chay("metadata", ham) == "xong"
    assert len(goi) == 2
    assert cho == list(t.NGAN_SACH["metadata"].cho_tam_thoi[:1])
    assert p.tom_tat()["retries"] == 1 and not p.mo


def test_loi_mang_het_ngan_sach_thi_dung_va_bao_tam_thoi():
    p, cho = _phien()
    ham, goi = _ham(TAM, TAM, TAM, TAM, TAM)
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        p.chay("metadata", ham)
    assert ei.value.that_bai.category == t.TRANSIENT_NETWORK
    assert len(goi) == 1 + len(t.NGAN_SACH["metadata"].cho_tam_thoi)
    assert ei.value.that_bai.attempt == len(goi)


def test_video_bi_go_khong_thu_lai_va_khong_mo_cau_dao():
    p, cho = _phien()
    for _ in range(10):
        ham, goi = _ham(GO)
        with pytest.raises(t.LoiTruyCapYouTube) as ei:
            p.chay("metadata", ham)
        assert len(goi) == 1 and ei.value.that_bai.category == t.PERMANENT_UNAVAILABLE
    assert cho == [] and not p.mo, "kênh toàn video bị gỡ vẫn là truy cập bình thường"


def test_bot_khong_thu_lai_va_mo_cau_dao_ngay():
    p, cho = _phien()
    ham, goi = _ham(BOT, "xong")
    with pytest.raises(t.LoiTruyCapYouTube):
        p.chay("metadata", ham)
    assert len(goi) == 1 and cho == []
    assert p.mo and p.ly_do.category == t.BOT_CHALLENGE
    ham2, goi2 = _ham("xong")
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        p.chay("metadata", ham2)
    assert goi2 == [], "cầu dao mở: không được gửi request nào nữa"
    assert ei.value.that_bai.category == t.BLOCKED_BY_BREAKER
    assert "đã dừng yêu cầu mới tới youtube" in str(ei.value).lower()


def test_429_thu_lai_mot_lan_co_nghi_roi_mo_cau_dao():
    p, cho = _phien()
    ham, goi = _ham(R429, R429, R429)
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        p.chay("metadata", ham)
    assert ei.value.that_bai.category == t.RATE_LIMITED
    assert len(goi) == 1 + len(t.NGAN_SACH["metadata"].cho_429)
    assert cho == list(t.NGAN_SACH["metadata"].cho_429)
    assert p.mo and p.tom_tat()["rate_limited"] == 1


def test_phien_bi_gioi_han_mot_tieng_khong_thu_lai():
    p, cho = _phien()
    ham, goi = _ham(PHIEN_GIOI_HAN)
    with pytest.raises(t.LoiTruyCapYouTube):
        p.chay("metadata", ham)
    assert len(goi) == 1 and cho == [] and p.mo


def test_tai_ve_khong_co_vong_thu_lai_ngoai():
    """Khâu tải đã có đường lui client + yt-dlp tự nối tiếp; vòng ngoài sẽ đụng bẫy `.part`."""
    p, cho = _phien()
    ham, goi = _ham(TAM, "xong")
    with pytest.raises(t.LoiTruyCapYouTube):
        p.chay("download", ham)
    assert len(goi) == 1 and cho == []


def test_toi_da_lan_gioi_han_tong_so_lan():
    p, cho = _phien()
    ham, goi = _ham(TAM, "xong")
    with pytest.raises(t.LoiTruyCapYouTube):
        p.chay("metadata", ham, toi_da_lan=1)
    assert len(goi) == 1


def test_huy_trong_luc_cho_thu_lai_thoat_nhanh():
    ev = threading.Event()
    p = t.PhienYouTube(ngan_sach={**t.NGAN_SACH,
                                  "metadata": t.NganSach(cho_tam_thoi=(30.0,))})
    ham, goi = _ham(TAM, "xong")
    threading.Timer(0.2, ev.set).start()
    bat_dau = time.monotonic()
    with pytest.raises(_Huy):
        p.chay("metadata", ham, cancel_event=ev, loi_huy=_Huy)
    assert time.monotonic() - bat_dau < 3.0, "bấm Dừng trong lúc nghỉ phải thoát ngay"
    assert len(goi) == 1


def test_huy_bang_ham_kiem_cung_thoat_nhanh():
    """Đồng bộ kênh huỷ qua `cancel_check()` (không có Event): vẫn phải thoát nhanh."""
    co = {"huy": False}

    class _Co:
        def is_set(self):
            return co["huy"]

    p = t.PhienYouTube(ngan_sach={**t.NGAN_SACH,
                                  "metadata": t.NganSach(cho_tam_thoi=(30.0,))})
    ham, goi = _ham(TAM, "xong")
    threading.Timer(0.2, lambda: co.update(huy=True)).start()
    bat_dau = time.monotonic()
    with pytest.raises(_Huy):
        p.chay("metadata", ham, cancel_event=_Co(), loi_huy=_Huy)
    assert time.monotonic() - bat_dau < 3.0


def test_loi_bo_qua_di_thang_ra_ngoai_khong_ghi():
    p, _ = _phien()

    def ham():
        raise _Huy()

    with pytest.raises(_Huy):
        p.chay("metadata", ham, bo_qua=(_Huy,))
    assert not p.mo and p.tom_tat()["youtube_operations"] == 1


# ---------------------------------------------------------------- cầu dao

@pytest.mark.parametrize("tin,nguong", [(AUTH, 3), (C403, 3), (TAM, 3), (DINH_DANG, 5)])
def test_nguong_lien_tiep_theo_loai(tin, nguong):
    p, _ = _phien()
    for i in range(nguong):
        assert not p.mo, f"chưa đủ {nguong} lần liên tiếp mà đã mở ở lần {i}"
        ham, _g = _ham(*([tin] * 5))
        with pytest.raises(t.LoiTruyCapYouTube):
            p.chay("download" if tin != AUTH else "metadata", ham)
    assert p.mo


def test_thanh_cong_xen_giua_thi_dem_lai_tu_dau():
    p, _ = _phien()
    for tin in (AUTH, AUTH, "xong", AUTH, AUTH):
        ham, _g = _ham(tin)
        try:
            p.chay("metadata", ham)
        except t.LoiTruyCapYouTube:
            pass
    assert not p.mo


def test_cookie_file_hong_mo_cau_dao_ngay():
    p, _ = _phien()

    def ham():
        raise y.LoiFileCookie("File cookie «c.txt» sai định dạng Netscape ở dòng 2.")

    with pytest.raises(t.LoiTruyCapYouTube):
        p.chay("metadata", ham)
    assert p.mo and p.ly_do.category == t.COOKIE_INVALID_OR_EXPIRED


def test_khong_co_nguong_thi_khong_bao_gio_mo():
    p, _ = _phien(nguong={})
    for _ in range(10):
        ham, _g = _ham(BOT)
        with pytest.raises(t.LoiTruyCapYouTube):
            p.chay("metadata", ham)
    assert not p.mo


def test_ghi_loi_tu_ngoai_khong_ghi_hai_lan():
    p, _ = _phien(nguong={t.AUTH_REQUIRED: 2})
    ham, _g = _ham(AUTH)
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        p.chay("metadata", ham)
    f = p.ghi_loi(ei.value)
    assert f.category == t.AUTH_REQUIRED
    assert not p.mo, "lỗi phiên này đã ghi thì tầng điều phối không được ghi lại"
    f2 = p.ghi_loi(RuntimeError(AUTH))
    assert f2.category == t.AUTH_REQUIRED and p.mo


def test_kiem_truoc_khi_mo_thi_nem_va_dem_bo_qua():
    p, _ = _phien()
    p.ghi_loi(RuntimeError(BOT))
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        p.kiem_truoc("download", "abc")
    assert ei.value.that_bai.category == t.BLOCKED_BY_BREAKER
    assert ei.value.that_bai.video_id == "abc"
    assert p.tom_tat()["skipped_by_breaker"] == 1


def test_thong_bao_dung_noi_ro_ly_do_va_khong_lo_bi_mat():
    p, _ = _phien()
    p.ghi_loi(RuntimeError(BOT + " https://x.googlevideo.com/v?sig=BIMATGIA123"))
    tin = p.thong_bao_dung()
    assert tin.startswith("Đã dừng yêu cầu mới tới YouTube")
    assert "xác minh" in tin and "BIMATGIA123" not in tin
    assert "BIMATGIA123" not in repr(p.tom_tat())


def test_nen_dung_doi_client_chi_khi_doi_client_vo_ich():
    p, _ = _phien()
    for tin in (BOT, AUTH, GO, R429, PHIEN_GIOI_HAN):
        assert p.nen_dung_doi_client(RuntimeError(tin)), tin
    for tin in (C403, DINH_DANG, TAM, "ERROR: lạ"):
        assert not p.nen_dung_doi_client(RuntimeError(tin)), tin


def test_so_do_day_du_truong():
    p, _ = _phien()
    p.dem_yeu_cau("metadata")
    p.dem_yeu_cau("download")
    p.dem_yeu_cau("download")
    p.dem_yeu_cau("listing")
    p.ghi_lui_cookie()
    p.ghi_doi_client()
    p.ghi_loi(RuntimeError(BOT))
    so = p.tom_tat()
    for k in ("youtube_operations", "metadata_requests", "download_attempts",
              "listing_requests", "retries", "auth_failures", "bot_challenges",
              "rate_limited", "http_403", "transient", "permanent_unavailable",
              "cookie_fallbacks", "client_fallbacks", "skipped_by_breaker", "breaker_events"):
        assert k in so, k
    assert so["metadata_requests"] == 1 and so["download_attempts"] == 2
    assert so["listing_requests"] == 1 and so["cookie_fallbacks"] == 1
    assert so["client_fallbacks"] == 1 and so["bot_challenges"] == 1
    assert so["breaker_events"] and so["breaker_events"][0]["category"] == t.BOT_CHALLENGE
    assert p.cookie_bi_tu_choi


# ---------------------------------------------------------------- hợp đồng chính sách

def test_ngan_sach_bao_thu_va_huu_han():
    """Con số trong bảng là CHÍNH SÁCH (brief: nhỏ, bảo thủ) — đổi thì phải đổi có chủ ý."""
    meta = t.NGAN_SACH["metadata"]
    assert meta.cho_tam_thoi == (3.0,) and meta.cho_429 == (30.0,)
    assert t.NGAN_SACH["listing"] == meta
    tai = t.NGAN_SACH["download"]
    assert tai.cho_tam_thoi == () and tai.cho_429 == (), "tải không có vòng thử lại ngoài"
    assert tai.yt_dlp_retries == 10 and tai.yt_dlp_fragment_retries == 10
    for ns in t.NGAN_SACH.values():
        assert all(0 < x <= 60 for x in (*ns.cho_tam_thoi, *ns.cho_429))
    assert t.NGUONG_MO[t.BOT_CHALLENGE] == 1 and t.NGUONG_MO[t.RATE_LIMITED] == 1
    assert t.NGUONG_MO[t.COOKIE_INVALID_OR_EXPIRED] == 1
    assert t.NGUONG_MO[t.AUTH_REQUIRED] == 3 and t.NGUONG_MO[t.HTTP_FORBIDDEN] == 3
    assert t.NGUONG_MO[t.TRANSIENT_NETWORK] == 3
    assert t.PERMANENT_UNAVAILABLE not in t.NGUONG_MO


def test_bo_ghi_yt_dlp_nghe_duoc_cookie_bi_thu_hoi_va_che_bi_mat():
    p = t.PhienYouTube()
    bo_ghi = y.BoGhiYtdlp(p)
    bo_ghi.warning("[youtube] The provided YouTube account cookies are no longer valid. They "
                   "have likely been rotated in the browser as a security measure.")
    assert p.cookie_bi_tu_choi and p.tom_tat()["cookie_rejected_warnings"] == 1
    bo_ghi.error("ERROR: unable to download: https://x.googlevideo.com/v?sig=BIMATGIA77 "
                 "Cookie: SID=BIMATGIA77")
    assert bo_ghi.loi and "BIMATGIA77" not in bo_ghi.loi[-1]


def test_thong_bao_duong_lui_client_khong_mang_bi_mat():
    def chay(opts):
        raise RuntimeError("ERROR: HTTP Error 403: Forbidden "
                           "https://x.googlevideo.com/videoplayback?sig=BIMATGIA88")

    with pytest.raises(RuntimeError) as ei:
        y.thu_tung_client(["android"], chay, {})
    assert "BIMATGIA88" not in str(ei.value) and "Đã thử: android" in str(ei.value)


# ---------------------------------------------------------------- ytdlp_chung

def test_thu_tung_client_dung_ngay_khi_bi_chan():
    da_thu = []

    def chay(opts):
        client = opts["extractor_args"]["youtube"]["player_client"][0]
        da_thu.append(client)
        raise RuntimeError(BOT)

    with pytest.raises(RuntimeError) as ei:
        y.thu_tung_client(["android", "tv", "ios"], chay, {},
                          dung_ngay=lambda e: t.phan_loai_loi(e).category == t.BOT_CHALLENGE)
    assert da_thu == ["android"], "bot-check chặn theo IP: đổi client không cứu được"
    assert t.phan_loai_loi(ei.value).category == t.BOT_CHALLENGE
    assert "Đã thử: android" in str(ei.value)


def test_thu_tung_client_van_doi_client_khi_403():
    da_thu = []

    def chay(opts):
        client = opts["extractor_args"]["youtube"]["player_client"][0]
        da_thu.append(client)
        if client != "ios":
            raise RuntimeError(C403)
        return "ok"

    assert y.thu_tung_client(["android", "tv", "ios"], chay, {},
                             dung_ngay=t.PhienYouTube().nen_dung_doi_client) == "ok"
    assert da_thu == ["android", "tv", "ios"], "403 ở khâu tải là theo từng client (mục 6)"


def test_tuy_chon_theo_thao_tac_lay_ngan_sach_noi_bo_tu_mot_bang():
    ch = y.CauHinhMang()
    tai = ch.tuy_chon("download")
    assert tai["retries"] == t.NGAN_SACH["download"].yt_dlp_retries
    assert tai["fragment_retries"] == t.NGAN_SACH["download"].yt_dlp_fragment_retries
    nghi = tai["retry_sleep_functions"]
    for loai in ("http", "fragment", "extractor"):
        cac = [nghi[loai](n) for n in range(12)]
        assert all(0 < x <= t.TRAN_NGHI_NOI_BO_S for x in cac), loai
    meta = ch.tuy_chon("metadata", noplaylist=True)
    assert meta["noplaylist"] is True and "extractor_retries" in meta
    assert "retries" not in y.CauHinhMang().tuy_chon(), "gọi kiểu cũ không đổi"
