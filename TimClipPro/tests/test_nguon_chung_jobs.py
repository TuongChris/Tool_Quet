# -*- coding: utf-8 -*-
"""Bộ điều phối lô «một video gốc chung» — chạy với engine GIẢ (không mạng, không audio).

Engine giả mô phỏng đúng hợp đồng của engine thật: lượt «thu thập» quét trọn; lượt «xác
minh» chỉ dừng sớm khi mục tiêu đạt; kết quả mang định danh kho/chính sách; ``info=`` được
dùng lại thay vì hỏi YouTube lần nữa.
"""

import contextlib
import os
import threading
import time
from types import SimpleNamespace

import pytest

import common_original as co
from common_original_jobs import CommonOriginalJobController
from engine import Config, Match, ScanResult, chu_ky_chinh_sach
from khoa import KhoaTienTrinh

A, B, C, D = "A [aaaaaaaaaaa].opus", "B [bbbbbbbbbbb].opus", "C [ccccccccccc].opus", \
    "D [ddddddddddd].opus"


def _url(vid):
    return f"https://youtu.be/{vid}"


class ResolverGia:
    def resolve(self, clip):
        return SimpleNamespace(title=f"Tên của {clip}", url="https://youtu.be/goc", video_id="",
                               upload_date="20250102", duration=600.0, status="complete",
                               warnings=())


class JobGia:
    """Bản Engine đã ghim (giả)."""

    def __init__(self, eng):
        self.eng = eng
        self.config = eng.config
        self.data_dir = eng.data_dir
        self.cancel_event = eng.cancel_event
        self.canh_bao_mang = []

    def require(self, **_k):
        pass

    def danh_tinh_kho(self):
        return {"kho_id": self.eng.kho_id, "kho_ten": "Kho thử", "kho_phien_ban": "r1:100"}

    def clip_metadata_resolver(self):
        return ResolverGia()

    def db_clips(self, bo_cache=False):
        return [{"ten": c, "so_hash": 20000} for c in self.eng.ten_kho]

    def youtube_info(self, url):
        self.eng.nhat_ky.append(("info", url, time.monotonic()))
        vid = url.rsplit("/", 1)[-1].split("=")[-1]
        tg = self.eng.the_gioi.get(self.eng.ma_that.get(vid, vid))
        if tg is None or tg.get("chet"):
            raise RuntimeError("Video không tồn tại hoặc đã bị xoá.")
        return {"id": self.eng.ma_that.get(vid, vid), "title": f"Vi phạm {vid}",
                "duration": tg["dai"], "channel": "Kênh X", "channel_id": "UCx",
                "channel_url": "u", "upload_date": "20260101"}

    def _quet(self, ma, muc_tieu, progress, nguon):
        self.eng.nhat_ky.append(("quet", ma, muc_tieu.mode if muc_tieu else None))
        if self.eng.chan is not None:
            self.eng.dang_quet.set()
            self.eng.chan.wait(10)
        tg = self.eng.the_gioi[ma]
        dai = float(tg["dai"])
        kq = ScanResult(source_name=f"Vi phạm {ma}", source_ref=nguon, source_id=ma,
                        duration_s=dai, kho_id=self.eng.kho_id,
                        kho_phien_ban=tg.get("phien_ban", "r1:100"),
                        chinh_sach=chu_ky_chinh_sach(self.config))
        if progress:
            progress(0.5, "Đang so khớp vân tay... khúc 1/2")
        if self.cancel_event.is_set():
            kq.status, kq.note, kq.ly_do_pham_vi = "error", "Đã hủy theo yêu cầu.", "huy"
            return kq
        if tg.get("loi"):
            kq.status, kq.note = "error", "Lỗi tải audio giả"
            return kq
        hien = tg["clips"]
        dung = 1.0
        if muc_tieu is not None and muc_tieu.mode == "verify":
            ung = []
            if muc_tieu.nhom_can_du and all(any(c in hien for c in g)
                                            for g in muc_tieu.nhom_can_du):
                ung.append(max(min(hien[c] for c in g if c in hien)
                               for g in muc_tieu.nhom_can_du))
            ung += [min(hien[c] for c in g if c in hien)
                    for g in muc_tieu.nhom_du_mot if any(c in hien for c in g)]
            dung = min(ung) if ung else 1.0
        kq.vung_da_khop = [(0.0, dai if dung >= 1.0 else dung * dai)]
        kq.pham_vi_quet_s = kq.vung_da_khop[0][1]
        kq.ung_vien_dat = [
            Match(clip=c, start_s=p * dai, end_s=p * dai + 300, matched_s=300.0,
                  clip_offset_s=0.0, hashes=6000, confidence="x", ty_le=50.0,
                  clip_bat_dau_s=p * dai, vung_khop_s=p * dai)
            for c, p in sorted(hien.items()) if p <= dung]
        kq.matches = kq.ung_vien_dat[:1]
        return kq

    def scan_youtube(self, url, progress=None, luu_lich_su=True, *, muc_tieu=None,
                     info=None):
        self.eng.luu_lich_su.append(luu_lich_su)
        self.eng.info_nhan.append(info is not None)
        ma = info["id"] if info else url.rsplit("/", 1)[-1]
        return self._quet(ma, muc_tieu, progress, url)

    def scan_media(self, path, label=None, ref="", source_type="file", progress=None,
                   luu_lich_su=True, pct_start=0.0, *, muc_tieu=None):
        self.eng.luu_lich_su.append(luu_lich_su)
        return self._quet(os.path.basename(path), muc_tieu, progress, path)

    def duration_of(self, path):
        return float(self.eng.the_gioi[os.path.basename(path)]["dai"])


class EngineGia:
    def __init__(self, tmp_path, the_gioi, ma_that=None, kho_id="kho1"):
        self.data_dir = str(tmp_path / "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.cancel_event = threading.Event()
        self.config = Config()
        self.config.ytdlp_sleep_requests_s = 0.0
        self.the_gioi = the_gioi
        self.ma_that = ma_that or {}
        self.kho_id = kho_id
        self.ten_kho = [A, B, C, D]
        self.nhat_ky = []
        self.luu_lich_su = []
        self.info_nhan = []
        self.chan = None
        self.dang_quet = threading.Event()
        self.job = JobGia(self)

    def cancel(self):
        self.cancel_event.set()

    @contextlib.contextmanager
    def phien_job(self):
        yield self.job


def _doi(ctl, giay=15):
    het = time.monotonic() + giay
    while ctl.running and time.monotonic() < het:
        time.sleep(0.01)
    assert not ctl.running, "bộ điều phối không kết thúc"


def _quet(eng):
    return [(x[1], x[2]) for x in eng.nhat_ky if x[0] == "quet"]


def _chay(eng, urls, **kw):
    ctl = CommonOriginalJobController(eng)
    ctl.start(urls, **kw)
    _doi(ctl)
    return ctl, ctl.result


# ---------------------------------------------------------------------------

def test_tim_thay_o_pha_nhanh_moi_video_mot_luot(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 3000, "clips": {A: 0.5, B: 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {A: 0.2, C: 0.1}},
          "v3aaaaaaaaa": {"dai": 4000, "clips": {A: 0.9, D: 0.1}}}
    eng = EngineGia(tmp_path, tg)
    ctl, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.TIM_THAY and kq.goc.clip == A
    assert _quet(eng)[0] == ("v2aaaaaaaaa", "collect"), "mốc = video NGẮN nhất"
    assert sorted(m for m, _ in _quet(eng)) == sorted(tg), "mỗi video đúng một lượt"
    assert all(md == "verify" for _, md in _quet(eng)[1:])
    assert kq.thong_tin_goc["title"] == f"Tên của {A}"
    assert [v.trang_thai for v in kq.videos] == [co.CO_MAT] * 3
    assert all(v.dai_dien is not None for v in kq.videos)


def test_ung_vien_dau_khong_chung_thi_bo_sung_tim_ra_nguon_chung_khac(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {B: 0.1, A: 0.6}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {B: 0.1, A: 0.7}},
          "v3aaaaaaaaa": {"dai": 3000, "clips": {A: 0.2, C: 0.1}}}
    eng = EngineGia(tmp_path, tg)
    # B mạnh nhất ở mốc → ứng viên nhanh = B, nhưng video 3 không có B.
    tg["v1aaaaaaaaa"]["clips"] = {B: 0.1, A: 0.6}
    ctl, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.TIM_THAY and kq.goc.clip == A
    dem = {}
    for m, _ in _quet(eng):
        dem[m] = dem.get(m, 0) + 1
    assert max(dem.values()) <= 2


def test_khong_co_nguon_chung_kem_ung_vien_tot_nhat(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {A: 0.4}},
          "v3aaaaaaaaa": {"dai": 3000, "clips": {B: 0.2}}}
    eng = EngineGia(tmp_path, tg)
    _, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.KHONG_TIM_THAY
    assert kq.goc.clip == A and kq.so_co_mat == 2 and not kq.la_nguon_chung


def test_video_loi_thi_chua_ket_luan_va_noi_ro_video_nao(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {A: 0.4}, "loi": True}}
    eng = EngineGia(tmp_path, tg)
    _, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.CHUA_KET_LUAN
    assert "video 2" in kq.ly_do
    assert sum(1 for m, _ in _quet(eng) if m == "v2aaaaaaaaa") == 2, "thử lại đúng 1 lần"


def test_lay_thong_tin_mot_lan_moi_video_va_luot_quet_dung_lai(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1, B: 0.2}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {B: 0.1}},
          "v3aaaaaaaaa": {"dai": 3000, "clips": {A: 0.5, B: 0.6}}}
    eng = EngineGia(tmp_path, tg)
    _chay(eng, [_url(v) for v in tg])
    lan_info = [x[1] for x in eng.nhat_ky if x[0] == "info"]
    assert sorted(lan_info) == sorted(_url(v) for v in tg)
    assert all(eng.info_nhan), "mọi lượt quét dùng thông tin đã lấy sẵn"


def test_lay_thong_tin_co_gian_nhip(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 4)}
    eng = EngineGia(tmp_path, tg)
    eng.config.ytdlp_sleep_requests_s = 0.05
    _chay(eng, [_url(v) for v in tg])
    moc = [x[2] for x in eng.nhat_ky if x[0] == "info"]
    assert all(b - a >= 0.045 for a, b in zip(moc, moc[1:]))


def test_gop_link_trung_ma_ke_ca_khac_dang_url(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {A: 0.4}}}
    # "shortlink" không tách được mã offline nhưng YouTube trả cùng mã v2.
    eng = EngineGia(tmp_path, tg, ma_that={"shortlink": "v2aaaaaaaaa"})
    urls = [_url("v1aaaaaaaaa"), "https://www.youtube.com/watch?v=v1aaaaaaaaa",
            _url("v2aaaaaaaaa"), "https://example.invalid/shortlink"]
    ctl, kq = _chay(eng, urls)
    assert kq.tong == 2
    assert len([x for x in eng.nhat_ky if x[0] == "info"]) == 3, "trùng offline không hỏi lại"
    assert any("trùng" in x for x in kq.canh_bao)


def test_link_chet_thi_dung_truoc_khi_quet(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {A: 0.4}, "chet": True}}
    eng = EngineGia(tmp_path, tg)
    _, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.CHUA_KET_LUAN
    assert _quet(eng) == []
    assert "v2aaaaaaaaa" in kq.ly_do


def test_can_it_nhat_hai_video_khac_nhau(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1}}}
    eng = EngineGia(tmp_path, tg)
    _, kq = _chay(eng, [_url("v1aaaaaaaaa"), _url("v1aaaaaaaaa")])
    assert kq.trang_thai == co.CHUA_KET_LUAN and "ít nhất 2" in kq.ly_do
    assert _quet(eng) == []


def test_kho_doi_giua_lo_thi_dung_khong_tron(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {A: 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {A: 0.4}, "phien_ban": "r2:999"},
          "v3aaaaaaaaa": {"dai": 3000, "clips": {A: 0.4}}}
    eng = EngineGia(tmp_path, tg)
    _, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.CHUA_KET_LUAN
    assert "Kho vân tay" in kq.ly_do
    assert ("v3aaaaaaaaa", "verify") not in _quet(eng), "dừng ngay, không quét tiếp"


def test_dinh_danh_kho_rong_thi_khong_chay(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 3)}
    eng = EngineGia(tmp_path, tg, kho_id="")
    ctl, kq = _chay(eng, [_url(v) for v in tg])
    assert kq is None and "kho" in ctl.error.lower()
    assert _quet(eng) == []


def test_huy_giua_luot_khong_mo_video_moi(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 4)}
    eng = EngineGia(tmp_path, tg)
    eng.chan = threading.Event()
    ctl = CommonOriginalJobController(eng)
    ctl.start([_url(v) for v in tg])
    assert eng.dang_quet.wait(5)
    anh = ctl.snapshot()
    assert anh.running and anh.video_dang_quet == 1 and anh.pha == co.PHA_MOC
    ctl.cancel()
    eng.chan.set()
    _doi(ctl)
    assert ctl.result.trang_thai == co.DA_HUY
    assert len(_quet(eng)) == 1


def test_khong_ghi_lich_su(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 4)}
    eng = EngineGia(tmp_path, tg)
    _chay(eng, [_url(v) for v in tg])
    assert eng.luu_lich_su and not any(eng.luu_lich_su)


def test_giu_tool_lock_suot_lo(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 3)}
    eng = EngineGia(tmp_path, tg)
    eng.chan = threading.Event()
    ctl = CommonOriginalJobController(eng)
    ctl.start([_url(v) for v in tg])
    assert eng.dang_quet.wait(5)
    from khoa import DangChayRoi
    with pytest.raises(DangChayRoi):
        with KhoaTienTrinh(os.path.join(eng.data_dir, "tool.lock"), "dựng kho vân tay"):
            pass
    eng.chan.set()
    _doi(ctl)


def test_dang_ban_thi_bao_ro_khong_quet(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 3)}
    eng = EngineGia(tmp_path, tg)
    with KhoaTienTrinh(os.path.join(eng.data_dir, "tool.lock"), "giám sát"):
        ctl, kq = _chay(eng, [_url(v) for v in tg])
    assert kq is None and "bận" in ctl.error
    assert _quet(eng) == []


def test_khong_tao_lo_trung_khi_dang_chay(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 3)}
    eng = EngineGia(tmp_path, tg)
    eng.chan = threading.Event()
    ctl = CommonOriginalJobController(eng)
    ctl.start([_url(v) for v in tg])
    with pytest.raises(RuntimeError):
        ctl.start([_url(v) for v in tg])
    eng.chan.set()
    _doi(ctl)


def test_nguon_file_dung_scan_media_va_thoi_luong_offline(tmp_path):
    tg = {"a.mp4": {"dai": 3000, "clips": {A: 0.3}},
          "b.mp4": {"dai": 1000, "clips": {A: 0.6, B: 0.1}}}
    eng = EngineGia(tmp_path, tg)
    duong = []
    for ten in tg:
        p = tmp_path / ten
        p.write_bytes(b"x")
        duong.append(str(p))
    ctl, kq = _chay(eng, duong, source_type="file")
    assert kq.trang_thai == co.TIM_THAY and kq.goc.clip == A
    assert _quet(eng)[0] == ("b.mp4", "collect")
    assert not [x for x in eng.nhat_ky if x[0] == "info"]


def test_so_lieu_va_snapshot_cuoi(tmp_path):
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 4)}
    eng = EngineGia(tmp_path, tg)
    ctl, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.so_lieu["so_luot"] == 3 and kq.so_lieu["luot_thu_thap"] == 1
    assert kq.so_lieu["thoi_gian_s"] >= 0
    anh = ctl.snapshot()
    assert not anh.running and anh.trang_thai == co.TIM_THAY
    assert anh.so_xac_minh == anh.tong == 3


def test_ten_trung_trong_kho_khong_tao_nguon_chung_gia(tmp_path):
    """Kho có HAI bản ghi «same.opus» (hai thư mục). Video 1 khớp bản này, video 2 khớp bản
    kia — engine chỉ trả basename nên trông như một nguồn chung 2/2."""
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {"same.opus": 0.1}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {"same.opus": 0.2}}}
    eng = EngineGia(tmp_path, tg)
    eng.ten_kho = [A, B, "D:/Kho1/same.opus", "D:/Kho2/same.opus"]
    _, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.CHUA_KET_LUAN and not kq.la_nguon_chung
    assert "trùng tên" in kq.ly_do
    assert any("2 bản ghi" in x for x in kq.canh_bao)


def test_ten_trung_khong_che_nguon_chung_ro_rang(tmp_path):
    tg = {"v1aaaaaaaaa": {"dai": 1000, "clips": {"same.opus": 0.1, A: 0.5}},
          "v2aaaaaaaaa": {"dai": 2000, "clips": {"same.opus": 0.2, A: 0.6}}}
    eng = EngineGia(tmp_path, tg)
    eng.ten_kho = [A, B, "D:/Kho1/same.opus", "D:/Kho2/same.opus"]
    _, kq = _chay(eng, [_url(v) for v in tg])
    assert kq.trang_thai == co.TIM_THAY and kq.goc.clip == A
    assert len(_quet(eng)) == 2, "khoá trùng tên không làm đích nên không tốn thêm lượt"


def test_khong_doc_duoc_danh_sach_clip_cua_kho_thi_khong_chay(tmp_path):
    """Không đọc được danh sách clip thì không kiểm được tên trùng — không chạy lô."""
    tg = {f"v{i}aaaaaaaaa": {"dai": 1000 * i, "clips": {A: 0.1}} for i in range(1, 3)}
    eng = EngineGia(tmp_path, tg)
    eng.ten_kho = []
    ctl, kq = _chay(eng, [_url(v) for v in tg])
    assert kq is None and "danh sách clip" in ctl.error
    assert _quet(eng) == []
