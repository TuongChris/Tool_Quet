# -*- coding: utf-8 -*-
"""Cầu dao + đếm request trên đường chạy THẬT: quét lô, quét lẻ, Watch, lô nguồn chung,
bảng điều khiển quét.

Engine, sổ kho, SQLite, Watch, bộ điều phối là thật; chỉ yt-dlp là bản giả theo kịch bản
(`tests/ytdlp_gia.py`) đếm từng lần mở phiên — đúng đơn vị "request" cần chứng minh. Không mạng.
"""

import sqlite3
from pathlib import Path

import pytest
import yt_dlp

import common_original as co
import truy_cap_youtube as t
import watch
from common_original_jobs import CommonOriginalJobController
from engine import Engine, Match, ScanResult, chu_ky_chinh_sach
from kho_gia import ghi_kho
from scan_jobs import ScanJobController
from watch import MucTheoDoi, WatchList, chay_giam_sat
from ytdlp_gia import AUTH, BOT, C403, GO, R429, TAM, YdlKichBan, info_mau

BI_MAT = "GIA_TRI_BI_MAT_GIA_51d0"


def _ma(i: int) -> str:
    return f"vid{i:08d}"


def _url(ma: str) -> str:
    return f"https://youtu.be/{ma}"


def _eng(tmp_path, monkeypatch, ydl) -> Engine:
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    thu_muc = tmp_path / "kho"
    thu_muc.mkdir(exist_ok=True)
    e.add_kho("A", str(thu_muc))
    ghi_kho(e.db_file, [(str(thu_muc / "goc [ggggggggggg].opus"), 9)])
    e.use_kho("A")
    # `db_clips()` đọc kho qua thư viện audfprint của dự án (lô nguồn chung đếm tên clip).
    e.audfprint = str(Path(__file__).resolve().parents[1] / "audfprint-master" / "audfprint.py")
    e.config.ytdlp_sleep_requests_s = 0.0
    monkeypatch.setattr(Engine, "require", lambda self, **k: None)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", ydl)
    # Nghỉ thử lại ngắn: test kiểm SỐ LẦN, không kiểm đồng hồ (ca huỷ có test riêng).
    monkeypatch.setitem(t.NGAN_SACH, "metadata", t.NganSach(cho_tam_thoi=(0.01,),
                                                            cho_429=(0.01,)))
    return e


def _quet_gia(e, clip="goc [ggggggggggg].opus"):
    """`scan_media` giả: kết quả hợp lệ, quét trọn, có một ứng viên đạt chuẩn."""
    dt = e.danh_tinh_kho()

    def quet(path, label=None, ref="", source_type="file", progress=None, luu_lich_su=True,
             pct_start=0.0, *, muc_tieu=None):
        m = Match(clip=clip, start_s=60.0, end_s=360.0, matched_s=300.0, clip_offset_s=0.0,
                  hashes=6000, confidence="x", ty_le=50.0, clip_bat_dau_s=60.0, vung_khop_s=60.0)
        kq = ScanResult(source_name=label or path, source_ref=ref, duration_s=600.0,
                        vung_da_khop=[(0.0, 600.0)], kho_id=dt["kho_id"], kho_ten=dt["kho_ten"],
                        kho_phien_ban=dt["kho_phien_ban"], chinh_sach=chu_ky_chinh_sach(e.config))
        kq.matches = [m]
        kq.ung_vien_dat = [m]
        kq.so_dat_nguong = 1
        return kq

    return quet


# =====================================================================
#  Quét lô (scan_iter — giao diện «Quét YouTube», CLI `youtube`)
# =====================================================================

def test_lo_20_link_bi_bot_check_chi_ton_mot_request(tmp_path, monkeypatch):
    ydl = YdlKichBan(info={"*": BOT})
    e = _eng(tmp_path, monkeypatch, ydl)
    goi_lai = []
    ket = list(e.scan_iter([_url(_ma(i)) for i in range(20)],
                           on_video=lambda i, n, kq: goi_lai.append(i)))
    assert ydl.goi == [("info", _ma(0), "")], "URL 2–20 không được gửi request nào"
    assert len(ket) == 20 and goi_lai == list(range(1, 21))
    assert ket[0].status == "error" and ket[0].loi_truy_cap.category == t.BOT_CHALLENGE
    for kq in ket[1:]:
        assert kq.status == "error", "không bao giờ là âm tính"
        assert kq.loi_truy_cap.category == t.BLOCKED_BY_BREAKER
        assert kq.note.startswith("Chưa quét") and not kq.matches
        assert not kq.quet_day_du
    assert len(e.list_jobs()) == 1, "video bị bỏ qua không được ghi vào lịch sử"
    assert e.ids_da_quet() == set()
    so = e.phien_youtube_cuoi.tom_tat()
    assert so["metadata_requests"] == 1 and so["skipped_by_breaker"] == 19


def test_video_bi_go_khong_lam_dung_lo(tmp_path, monkeypatch):
    """Tier 2 Job 43/130: video bị gỡ là chuyện của video đó, không phải truy cập bị chặn."""
    ydl = YdlKichBan(info={"*": GO})
    e = _eng(tmp_path, monkeypatch, ydl)
    ket = list(e.scan_iter([_url(_ma(i)) for i in range(5)]))
    assert ydl.dem("info") == 5
    assert all(k.loi_truy_cap.category == t.PERMANENT_UNAVAILABLE for k in ket)
    assert all("không còn xem được" in k.note for k in ket)
    assert not e.phien_youtube_cuoi.mo


def test_loi_mang_tam_thoi_thu_lai_dung_mot_lan(tmp_path, monkeypatch):
    lan = {"n": 0}

    def info(_p, ma):
        lan["n"] += 1
        if lan["n"] == 1:
            raise RuntimeError(TAM.format(id=ma))
        return info_mau(ma)

    ydl = YdlKichBan(info={"*": info})
    e = _eng(tmp_path, monkeypatch, ydl)
    assert e.youtube_info(_url(_ma(1)))["id"] == _ma(1)
    assert ydl.dem("info") == 2


def test_429_thu_lai_mot_lan_roi_mo_cau_dao(tmp_path, monkeypatch):
    ydl = YdlKichBan(info={"*": R429})
    e = _eng(tmp_path, monkeypatch, ydl)
    ket = list(e.scan_iter([_url(_ma(i)) for i in range(6)]))
    assert ydl.dem("info") == 2, "một lần thử lại có nghỉ, rồi dừng hẳn"
    assert ket[0].loi_truy_cap.category == t.RATE_LIMITED
    assert all(k.loi_truy_cap.category == t.BLOCKED_BY_BREAKER for k in ket[1:])
    assert "giới hạn" in ket[1].note


# =====================================================================
#  Quét lẻ: dùng lại metadata, đường lui client không nhân request khi bị chặn
# =====================================================================

def test_quet_co_info_khong_hoi_lai_metadata(tmp_path, monkeypatch):
    ydl = YdlKichBan(tai={"*": C403})
    e = _eng(tmp_path, monkeypatch, ydl)
    ma = _ma(1)
    kq = e.scan_youtube(_url(ma), info=info_mau(ma))
    assert ydl.dem("info") == 0, "info= đã có thì không hỏi YouTube lần nữa"
    assert ydl.dem("tai") == len(e.config.ytdlp_player_clients), "403: vẫn đổi client (mục 6)"
    assert kq.status == "error" and kq.loi_truy_cap.category == t.HTTP_FORBIDDEN
    ydl.goi.clear()
    e.scan_youtube(_url(ma))
    assert ydl.dem("info") == 1


@pytest.mark.parametrize("loi,loai", [(BOT, t.BOT_CHALLENGE), (AUTH, t.AUTH_REQUIRED),
                                      (GO, t.PERMANENT_UNAVAILABLE)])
def test_tai_bi_chan_khong_doi_client(tmp_path, monkeypatch, loi, loai):
    """CLAUDE.md 6c: bot-check chặn theo IP ở khâu trích xuất — đổi client không cứu được."""
    ydl = YdlKichBan(tai={"*": loi})
    e = _eng(tmp_path, monkeypatch, ydl)
    with pytest.raises(RuntimeError) as ei:
        e.download_audio(_url(_ma(1)), _ma(1))
    assert ydl.dem("tai") == 1
    assert t.phan_loai_loi(ei.value).category == loai


def test_tai_loi_mang_khong_chay_lai_ca_danh_sach_client(tmp_path, monkeypatch):
    """Khâu tải không có vòng thử lại NGOÀI: chạy lại cả danh sách client sẽ gặp `.part` của
    client khác (engine `don_file_do_dang`). Mỗi client đúng một lượt."""
    ydl = YdlKichBan(tai={"*": TAM})
    e = _eng(tmp_path, monkeypatch, ydl)
    with pytest.raises(RuntimeError) as ei:
        e.download_audio(_url(_ma(1)), _ma(1))
    assert ydl.dem("tai") == len(e.config.ytdlp_player_clients)
    assert t.phan_loai_loi(ei.value).category == t.TRANSIENT_NETWORK


def test_tai_mot_phan_xong_roi_bi_chan_khi_tai_not_thi_khong_thanh_am_tinh(tmp_path,
                                                                           monkeypatch):
    """Video 11 tiếng: 3 tiếng đầu tải + quét xong (không thấy gì), lượt tải nốt bị bot-check →
    kết quả là LỖI, không bao giờ "quét trọn, không tìm thấy" (vung_loi/phạm vi giữ sự thật)."""
    def tai(p, ma):
        if not p.opts.get("download_ranges"):
            raise RuntimeError(BOT.format(id=ma))

    ydl = YdlKichBan(info={"*": lambda _p, m: info_mau(m, dai=40000.0)}, tai={"*": tai})
    e = _eng(tmp_path, monkeypatch, ydl)
    e.config.quet_tang_dan = True
    e.config.tai_mot_phan = True
    dt = e.danh_tinh_kho()

    def quet_rong(path, label=None, ref="", source_type="file", progress=None, luu_lich_su=True,
                  pct_start=0.0, *, muc_tieu=None):
        return ScanResult(source_name=label or path, source_ref=ref, duration_s=10800.0,
                          vung_da_khop=[(0.0, 10800.0)], kho_id=dt["kho_id"],
                          kho_ten=dt["kho_ten"], kho_phien_ban=dt["kho_phien_ban"],
                          chinh_sach=chu_ky_chinh_sach(e.config))

    monkeypatch.setattr(e, "scan_media", quet_rong)
    kq = e.scan_youtube(_url(_ma(1)))
    assert [g[0] for g in ydl.goi] == ["info", "tai", "tai"]
    assert kq.status == "error" and kq.loi_truy_cap.category == t.BOT_CHALLENGE
    assert not kq.quet_day_du and not kq.matches
    assert e.ids_da_quet() == set()


def test_link_kenh_trong_o_quet_video_chi_ton_mot_request(tmp_path, monkeypatch):
    """Không `extract_flat`, yt-dlp resolve TỪNG video của kênh trước khi tool kịp thấy."""
    ydl = YdlKichBan(info={"*": lambda _p, _m: {"_type": "playlist", "id": "UCabc",
                                                "entries": [{"id": "x1"}, {"id": "x2"}]}})
    e = _eng(tmp_path, monkeypatch, ydl)
    with pytest.raises(RuntimeError) as ei:
        e.youtube_info("https://www.youtube.com/@kenh/videos")
    assert t.phan_loai_loi(ei.value).category == t.INVALID_INPUT
    assert ydl.dem("info") == 1 and ydl.opts[0].get("extract_flat") == "in_playlist"


def test_cookie_chet_duoc_ghi_vao_phien_va_canh_bao(tmp_path, monkeypatch):
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("# Netscape HTTP Cookie File\n"
                      + "\t".join([".youtube.com", "TRUE", "/", "TRUE", "0", "PREF", "x"])
                      + "\n", encoding="utf-8")

    def info(p, ma):
        if p.opts.get("cookiefile"):
            raise RuntimeError(f"ERROR: [youtube] {ma}: Requested format is not available.")
        return info_mau(ma)

    ydl = YdlKichBan(info={"*": info})
    e = _eng(tmp_path, monkeypatch, ydl)
    e.config.ytdlp_cookiefile = str(cookie)
    ket = list(e.scan_iter([_url(_ma(1))]))
    assert ydl.dem("info") == 2
    phien = e.phien_youtube_cuoi
    assert phien.cookie_bi_tu_choi and phien.tom_tat()["cookie_fallbacks"] == 1
    assert "hết hiệu lực" in ket[0].note


def test_bi_mat_trong_loi_khong_vao_ghi_chu_hay_lich_su(tmp_path, monkeypatch):
    loi = (f"ERROR: [youtube] {{id}}: Unable to download webpage: HTTP Error 403: Forbidden "
           f"Cookie: SID={BI_MAT} https://rr1.googlevideo.com/videoplayback?sig={BI_MAT}")
    ydl = YdlKichBan(info={"*": loi})
    e = _eng(tmp_path, monkeypatch, ydl)
    kq = e.scan_youtube(_url(_ma(1)))
    assert kq.status == "error" and BI_MAT not in kq.note
    with sqlite3.connect(e.sqlite_file) as c:
        ghi_chu = [r[0] or "" for r in c.execute("SELECT note FROM jobs")]
    assert ghi_chu and all(BI_MAT not in x for x in ghi_chu)


# =====================================================================
#  Watch
# =====================================================================

class _SheetsDem:
    lan_ghi = 0

    def __init__(self, sheet=""):
        pass

    def san_sang(self):
        return True

    def append(self, header, rows):
        type(self).lan_ghi += 1
        return len(rows)


@pytest.fixture()
def sheets_dem(monkeypatch):
    _SheetsDem.lan_ghi = 0
    monkeypatch.setattr(watch, "SheetsExporter", _SheetsDem)
    return _SheetsDem


# Dạng NGANG (mặc định, `GiamSat.bat`) vốn bỏ qua kết quả lỗi khi dựng dòng (`to_rows_ngang`);
# dạng DỌC (`--dang-doc`) thì dựng dòng "(LỖI: …)" cho mọi kết quả lỗi — test cả hai.
@pytest.mark.parametrize("dang_ngang", [True, False])
def test_watch_50_link_dang_nhap_lien_tiep_thi_dung_khong_ghi_sheet(tmp_path, monkeypatch,
                                                                    sheets_dem, dang_ngang):
    ydl = YdlKichBan(info={"*": AUTH})
    e = _eng(tmp_path, monkeypatch, ydl)
    wl = WatchList(muc=[MucTheoDoi("link", _url(_ma(i))) for i in range(50)], kho="A",
                   gioi_han_moi_lan=50)
    bc = chay_giam_sat(e, wl, sheet_link="https://docs.google.com/spreadsheets/d/x/edit",
                       dang_ngang=dang_ngang)
    nguong = t.NGUONG_MO[t.AUTH_REQUIRED]
    assert ydl.dem("info") == nguong, "không tiếp tục 40+ video sau khi cầu dao mở"
    assert bc.quet_moi == nguong and bc.chua_quet_do_chan == 50 - nguong
    assert "Đã dừng yêu cầu mới tới YouTube" in bc.chan_youtube
    assert sheets_dem.lan_ghi == 0, "lỗi truy cập không bao giờ thành dòng trên Sheets"
    assert e.ids_da_quet() == set(), "video chưa kiểm không được tính là đã quét"
    assert len(e.list_jobs()) == nguong
    assert str(50 - nguong) in bc.tom_tat()


@pytest.mark.parametrize("dang_ngang", [True, False])
def test_watch_chi_day_sheet_ket_qua_hop_le(tmp_path, monkeypatch, sheets_dem, dang_ngang):
    ydl = YdlKichBan(info={_ma(2): GO})
    e = _eng(tmp_path, monkeypatch, ydl)
    monkeypatch.setattr(e, "scan_media", _quet_gia(e))
    wl = WatchList(muc=[MucTheoDoi("link", _url(_ma(i))) for i in (1, 2)], kho="A")
    bc = chay_giam_sat(e, wl, sheet_link="https://docs.google.com/spreadsheets/d/x/edit",
                       dang_ngang=dang_ngang)
    assert sheets_dem.lan_ghi == 1, "chỉ video quét hợp lệ lên Sheets; video bị gỡ thì không"
    assert bc.nguon_co_vi_pham == 1 and not bc.chan_youtube


def test_watch_liet_ke_kenh_bi_429_thi_khong_hoi_kenh_khac(tmp_path, monkeypatch, sheets_dem):
    ydl = YdlKichBan()
    e = _eng(tmp_path, monkeypatch, ydl)
    goi = []

    def lister(url, limit=None):
        goi.append(url)
        raise RuntimeError(R429.format(id="UCx"))

    wl = WatchList(muc=[MucTheoDoi("kenh", f"https://www.youtube.com/@k{i}") for i in range(3)],
                   kho="A")
    bc = chay_giam_sat(e, wl, lister=lister)
    assert len(goi) == 1 and ydl.goi == []
    assert bc.chan_youtube and bc.quet_moi == 0


# =====================================================================
#  Lô «một video gốc chung»
# =====================================================================

def _chay_lo(e, nguon):
    ctl = CommonOriginalJobController(e)
    ctl.start(nguon)
    ctl._thread.join(60)
    assert not ctl._thread.is_alive()
    return ctl


def test_lo_nguon_chung_bot_check_khi_lay_thong_tin_dung_ngay(tmp_path, monkeypatch):
    ma = [_ma(i) for i in range(10)]
    ydl = YdlKichBan(info={ma[2]: BOT})
    e = _eng(tmp_path, monkeypatch, ydl)
    da_quet = []
    monkeypatch.setattr(e, "scan_media", lambda *a, **k: da_quet.append(a))
    kq = _chay_lo(e, [_url(m) for m in ma]).result
    assert ydl.dem("info") == 3 and ydl.dem("tai") == 0 and da_quet == []
    assert kq.trang_thai == co.CHUA_KET_LUAN, "chưa có bằng chứng âm tính nào"
    assert "Đã dừng yêu cầu mới tới YouTube" in kq.ly_do
    assert kq.so_lieu["youtube"]["bot_challenges"] == 1
    # Bộ điều phối tự dừng — không đẩy 7 link còn lại xuống engine để engine từ chối hộ.
    assert kq.so_lieu["so_lan_lay_thong_tin"] == 3
    assert kq.so_lieu["youtube"]["skipped_by_breaker"] == 0


def test_lo_nguon_chung_3_video_dung_3_lan_lay_thong_tin(tmp_path, monkeypatch):
    ma = [_ma(i) for i in range(3)]
    ydl = YdlKichBan()
    e = _eng(tmp_path, monkeypatch, ydl)
    monkeypatch.setattr(e, "scan_media", _quet_gia(e))
    kq = _chay_lo(e, [_url(m) for m in ma]).result
    assert kq.trang_thai == co.TIM_THAY
    assert ydl.dem("info") == 3, "lượt quét dùng lại info= — không hỏi lại 6 hay 9 lần"
    assert ydl.dem("tai") == 3
    assert kq.so_lieu["youtube"]["metadata_requests"] == 3


def test_lo_nguon_chung_cau_dao_mo_giua_luot_quet_thi_dung_lo(tmp_path, monkeypatch):
    ma = [_ma(i) for i in range(4)]
    ydl = YdlKichBan(tai={ma[1]: BOT})
    e = _eng(tmp_path, monkeypatch, ydl)
    monkeypatch.setattr(e, "scan_media", _quet_gia(e))
    kq = _chay_lo(e, [_url(m) for m in ma]).result
    assert kq.trang_thai == co.CHUA_KET_LUAN
    assert "Đã dừng yêu cầu mới tới YouTube" in kq.ly_do
    tai = [g[1] for g in ydl.goi if g[0] == "tai"]
    assert tai[-1] == ma[1], "sau khi cầu dao mở không tải thêm video nào"
    assert tai.count(ma[1]) == 1, "bot-check: không đổi client"
    assert kq.so_lieu["youtube"]["skipped_by_breaker"] == 0, "lô tự dừng, không quét tiếp"


# =====================================================================
#  Bảng điều khiển quét + CLI
# =====================================================================

def test_bang_dieu_khien_bao_ro_da_dung_vi_youtube(tmp_path, monkeypatch):
    ydl = YdlKichBan(info={"*": BOT})
    e = _eng(tmp_path, monkeypatch, ydl)
    ctl = ScanJobController(e)
    ctl.start([_url(_ma(i)) for i in range(4)])
    ctl._thread.join(30)
    anh = ctl.snapshot()
    assert "Đã dừng yêu cầu mới tới YouTube" in anh.message
    assert ydl.dem("info") == 1
    assert all("Chưa quét" in v.error for v in anh.videos[1:])
