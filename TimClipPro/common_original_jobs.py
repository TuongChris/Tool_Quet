# -*- coding: utf-8 -*-
"""Điều phối một lô «Một video gốc chung cho cả lô»: luồng nền, khoá, lấy thông tin, snapshot.

Không phụ thuộc Streamlit — worker không đọc/ghi ``st.session_state``; main thread của UI
chỉ đọc ``snapshot()`` và ``result`` (cùng ranh giới với ``scan_jobs.ScanJobController``).

Phần quyết định (bằng chứng, kết luận, lập kế hoạch) nằm ở ``common_original.py`` — module
thuần, test được không cần engine. Ở đây chỉ có những việc có tác dụng phụ:

* giữ ``data/tool.lock`` SUỐT lô (CLAUDE.md «Quy ước khoá»): build/Watch không chen vào giữa
  để kho đổi phiên bản — trộn hai phiên bản kho làm mọi kết luận âm tính vô nghĩa;
* ghim kho/cấu hình một lần cho cả lô (``Engine.phien_job``), chụp định danh kho + chính sách;
* lấy thông tin mọi video TRƯỚC (giãn nhịp), dùng lại khi quét — tổng request không tăng;
* chạy từng lượt quét với đúng mục tiêu, KHÔNG ghi lịch sử (lượt dừng sớm sẽ làm Watch bỏ qua
  video đó mãi mãi), và dừng hẳn nếu định danh kho/chính sách của kết quả lệch lô.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import Optional

import csv
from datetime import datetime

import common_original as co
from clip_metadata import extract_youtube_id
from engine import _mo_file_text_moi, chu_ky_chinh_sach
from khoa import DangChayRoi, KhoaTienTrinh
from truy_cap_youtube import PhienYouTube
from ytdlp_chung import giai_thich_loi


def _phien_cua(job) -> PhienYouTube:
    """Phiên YouTube của job (engine thật: dùng chung với mọi lượt lấy thông tin/tải của lô).
    Engine giả trong test không có phiên thì dùng phiên cục bộ cho riêng bộ điều phối."""
    lay = getattr(job, "phien_youtube_hien_tai", None)
    phien = lay() if callable(lay) else None
    return phien if isinstance(phien, PhienYouTube) else PhienYouTube()

LOGGER = logging.getLogger("scan.job")

PHA_CHUAN_BI = "chuan_bi"
PHA_XONG = "xong"
TEN_PHA = {PHA_CHUAN_BI: "Chuẩn bị (lấy thông tin video)", PHA_XONG: "Hoàn tất", **co.TEN_PHA}


@dataclass(frozen=True)
class VideoNguonChung:
    """Một dòng trong bảng trạng thái lúc chạy."""
    thu_tu: int
    nguon: str
    tieu_de: str = ""
    thoi_luong: Optional[float] = None
    so_luot: int = 0
    trang_thai: str = co.CHUA_QUET     # với video gốc đang xét
    dang_quet: bool = False
    pham_vi: str = ""
    loi: str = ""


@dataclass(frozen=True)
class NguonChungSnapshot:
    ma_lo: str = ""
    running: bool = False
    cancelled: bool = False
    trang_thai: str = co.DANG_TIM
    pha: str = PHA_CHUAN_BI
    message: str = ""
    tien_do: float = 0.0                # tiến độ trong video đang quét
    ung_vien: str = ""                  # tên clip đang xét
    ung_vien_tieu_de: str = ""
    so_xac_minh: int = 0                # số video đã có mặt ứng viên đang xét
    tong: int = 0
    video_dang_quet: int = 0            # thứ tự (từ 1) của video đang quét; 0 = không
    elapsed_seconds: float = 0.0
    videos: tuple = ()
    error: str = ""


def xuat_csv(kql: co.KetQuaLo, out_dir: str) -> str:
    """Ghi CSV kết quả lô vào ``out_dir`` (không ghi đè file cũ). Trả đường dẫn."""
    os.makedirs(out_dir, exist_ok=True)
    ten = os.path.join(out_dir, "nguonchung_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                       + ".csv")
    f, ten = _mo_file_text_moi(ten, newline="", encoding="utf-8-sig")
    with f:
        w = csv.writer(f)
        w.writerow(co.HEADER_NGUON_CHUNG)
        w.writerows(co.dong_bao_cao(kql))
    return ten


def _ma_offline(nguon: str, source_type: str) -> str:
    """Khoá khử trùng không cần mạng: mã YouTube trong URL, hoặc đường dẫn chuẩn hoá."""
    if source_type == "youtube":
        return extract_youtube_id(nguon) or nguon.strip()
    return os.path.normcase(os.path.abspath(nguon))


class CommonOriginalJobController:
    """Một lô, một worker thread, snapshot bất biến cho UI."""

    def __init__(self, engine):
        self.engine = engine
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._anh = NguonChungSnapshot()
        self._ket_qua: Optional[co.KetQuaLo] = None
        self._error = ""
        self._mono_dau: Optional[float] = None
        self._mono_cuoi: Optional[float] = None
        self._ten_cache: dict = {}
        self._phien: Optional[PhienYouTube] = None

    # ---------- điều khiển ----------

    def start(self, nguon: list, source_type: str = "youtube") -> str:
        with self._lock:
            if self.running:
                raise RuntimeError("Đang có lô quét nguồn chung chạy; không tạo lô trùng.")
            ma_lo = uuid.uuid4().hex
            self._anh = NguonChungSnapshot(ma_lo=ma_lo, running=True,
                                           message="Đang chuẩn bị...")
            self._ket_qua = None
            self._error = ""
            self._mono_dau = time.monotonic()
            self._mono_cuoi = None
            self._ten_cache = {}
            self._phien = None
        # Cờ huỷ xoá ĐÚNG MỘT LẦN ở đây (TCP-13): cú bấm Dừng rơi vào khoảng giữa start()
        # và lúc thread chạy không bị nuốt.
        self.engine.cancel_event.clear()
        LOGGER.info("event=scan.common.started batch_id=%s total=%d type=%s",
                    ma_lo, len(nguon), source_type)
        self._thread = threading.Thread(
            target=self._chay, args=(ma_lo, [str(x) for x in nguon], source_type),
            name=f"nguon-chung-{ma_lo[:8]}", daemon=True)
        self._thread.start()
        return ma_lo

    def cancel(self) -> None:
        with self._lock:
            self._anh = replace(self._anh, cancelled=True,
                                message="Đang yêu cầu dừng; giữ nguyên bằng chứng đã có...")
        LOGGER.warning("event=scan.common.cancel_requested batch_id=%s", self._anh.ma_lo)
        self.engine.cancel()

    # ---------- đọc trạng thái ----------

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive()) or self._anh.running

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    @property
    def result(self) -> Optional[co.KetQuaLo]:
        with self._lock:
            return self._ket_qua

    def snapshot(self) -> NguonChungSnapshot:
        with self._lock:
            dau, cuoi = self._mono_dau, self._mono_cuoi
            anh = self._anh
        da_chay = 0.0 if dau is None else (cuoi or time.monotonic()) - dau
        return replace(anh, elapsed_seconds=da_chay,
                       running=anh.running or bool(self._thread and self._thread.is_alive()))

    # ---------- worker ----------

    def _sua(self, **thay_doi) -> None:
        with self._lock:
            self._anh = replace(self._anh, **thay_doi)

    def _da_huy(self) -> bool:
        return self.engine.cancel_event.is_set()

    def _chay(self, ma_lo: str, nguon: list, source_type: str) -> None:
        try:
            with KhoaTienTrinh(os.path.join(self.engine.data_dir, "tool.lock"),
                               "quét nguồn chung cả lô"):
                with self.engine.phien_job() as job:
                    ket = self._chay_da_khoa(job, ma_lo, nguon, source_type)
            with self._lock:
                self._ket_qua = ket
        except DangChayRoi as e:
            with self._lock:
                self._error = (f"Tool đang bận ({e}). Lô nguồn chung cần giữ kho vân tay cố "
                               "định suốt lô — hãy chạy lại khi việc đó xong.")
        except Exception as e:  # noqa: BLE001 — worker không được chết câm
            with self._lock:
                self._error = str(e)
            LOGGER.exception("event=scan.common.failed batch_id=%s", ma_lo)
        finally:
            with self._lock:
                self._mono_cuoi = time.monotonic()
                kq = self._ket_qua
                self._anh = replace(
                    self._anh, running=False, pha=PHA_XONG, video_dang_quet=0,
                    trang_thai=kq.trang_thai if kq else co.CHUA_KET_LUAN,
                    message=(co.TEN_TRANG_THAI_LO.get(kq.trang_thai, "") if kq
                             else (self._error or "Đã dừng.")),
                    error=self._error)
            LOGGER.info("event=scan.common.finished batch_id=%s status=%s", ma_lo,
                        kq.trang_thai if kq else "error")

    def _chay_da_khoa(self, job, ma_lo: str, nguon: list, source_type: str):
        job.require(can_ytdlp=source_type == "youtube", can_db=True)
        dt = job.danh_tinh_kho()
        if not dt.get("kho_id"):
            raise RuntimeError(
                "Không xác định được kho vân tay đang dùng (sổ đăng ký kho không khớp file "
                "vân tay). Hãy chọn lại kho ở thanh bên rồi chạy lại.")
        dinh_danh = (dt["kho_id"], dt.get("kho_phien_ban", ""), chu_ky_chinh_sach(job.config))
        try:
            resolver = job.clip_metadata_resolver()
        except Exception:  # noqa: BLE001 — thiếu metadata không chặn việc tìm nguồn chung
            resolver = None
        # Đếm bản ghi theo tên clip: tên có >1 bản ghi không bao giờ được xác nhận là nguồn
        # chung (`Match.clip` chỉ là basename). Không đọc được danh sách thì KHÔNG chạy —
        # chạy tiếp là mất chốt chặn đó một cách lặng lẽ.
        dem_ten = co.dem_ten_kho(job.db_clips())
        if not dem_ten:
            raise RuntimeError(
                "Không đọc được danh sách clip của kho vân tay (kho rỗng hoặc file đang bị "
                "khoá) nên không kiểm được tên clip trùng — chưa chạy lô. Hãy thử lại.")
        self._resolver = resolver
        # MỘT cầu dao cho cả lô: lấy thông tin, tải, quét lại đều hỏi nó trước khi gửi request.
        phien = _phien_cua(job)
        self._phien = phien

        videos, canh_bao, loi_info, so_info = self._chuan_bi(job, nguon, source_type, phien)
        tt = co.TrangThaiLo(kho_id=dinh_danh[0], videos=videos, cfg=job.config,
                            ten_trung={t: so for t, so in dem_ten.items() if so > 1})
        tt.thu_tu_xu_ly = co.chon_thu_tu_xu_ly(videos)
        self._sua(tong=len(videos), videos=self._hang_video(tt, None, None))

        def ket_thuc(kl: co.KetLuan):
            if phien.mo and kl.trang_thai in (co.CHUA_KET_LUAN, co.DANG_TIM):
                # YouTube chặn giữa lô: KHÔNG phải "không tìm thấy" — chưa có đủ bằng chứng.
                kl = replace(kl, trang_thai=co.CHUA_KET_LUAN, ly_do=phien.thong_bao_dung())
            so_lieu = {**co.tom_tat_so_lieu(tt), "so_lan_lay_thong_tin": so_info,
                       "thoi_gian_s": round(time.monotonic() - (self._mono_dau or 0), 3),
                       "youtube": phien.tom_tat()}
            return co.dung_ket_qua_lo(
                tt, kl, ma_lo=ma_lo, kho_ten=dt.get("kho_ten", ""),
                thong_tin_goc=self._thong_tin_goc(kl.khoa_hien_thi), dem_ten=dem_ten,
                so_lieu=so_lieu, canh_bao_them=tuple(canh_bao))

        n = len(videos)
        if self._da_huy():
            return ket_thuc(co.ket_luan(tt, da_huy=True))
        if phien.mo:
            return ket_thuc(co.KetLuan(co.CHUA_KET_LUAN, tong=n, ly_do=phien.thong_bao_dung()))
        if loi_info:
            return ket_thuc(co.KetLuan(
                co.CHUA_KET_LUAN, tong=n,
                ly_do=("Không lấy được thông tin " + str(len(loi_info)) + " video: "
                       + "; ".join(loi_info) + ". Bỏ các link này hoặc thử lại sau — "
                       "thiếu một video thì không thể có nguồn chung cho cả lô.")))
        if n < 2:
            return ket_thuc(co.KetLuan(
                co.CHUA_KET_LUAN, tong=n,
                ly_do="Cần ít nhất 2 video khác nhau để tìm video gốc chung."))

        def quet(b: co.BuocQuet) -> co.LuotQuet:
            return self._quet_mot_luot(job, tt, b, source_type, dinh_danh)

        def sau_moi_luot(b, lq) -> None:
            self._sua(**self._ung_vien_hien_tai(tt))

        kl = co.dieu_phoi(tt, quet, da_huy=self._da_huy, sau_moi_luot=sau_moi_luot)
        self._sua(**self._ung_vien_hien_tai(tt, kl))
        return ket_thuc(kl)

    # ---------- chuẩn bị: khử trùng + lấy thông tin ----------

    def _chuan_bi(self, job, nguon: list, source_type: str,
                  phien: Optional[PhienYouTube] = None) -> tuple:
        phien = phien if phien is not None else PhienYouTube()
        canh_bao: list = []
        da_co: dict = {}
        duy_nhat = []
        for x in nguon:
            x = x.strip()
            if not x or x.startswith("#"):
                continue
            khoa = _ma_offline(x, source_type)
            if khoa in da_co:
                continue
            da_co[khoa] = x
            duy_nhat.append(x)
        bo_offline = sum(1 for x in nguon if x.strip() and not x.strip().startswith("#")) \
            - len(duy_nhat)

        videos: list = []
        loi_info: list = []
        so_info = 0
        ma_that: dict = {}
        for i, x in enumerate(duy_nhat):
            if self._da_huy():
                break
            self._sua(message=f"Đang lấy thông tin video {i + 1}/{len(duy_nhat)}...")
            if source_type != "youtube":
                try:
                    dai = job.duration_of(x)
                except Exception:  # noqa: BLE001
                    dai = None
                videos.append(co.VideoTrongLo(
                    thu_tu=len(videos) + 1, nguon=x, ma=_ma_offline(x, source_type),
                    tieu_de=os.path.basename(x), thoi_luong=dai or None))
                continue
            if phien.mo:
                # Bị nghi là bot / 429 / cookie hỏng ở vài link đầu: KHÔNG hỏi tiếp cả lô như máy
                # spam. Lô kết luận "chưa kết luận" (không phải "không tìm thấy").
                break
            if i and float(job.config.ytdlp_sleep_requests_s or 0) > 0:
                # Giãn nhịp giữa các lần hỏi YouTube (CLAUDE.md mục 6c); huỷ được.
                if self.engine.cancel_event.wait(float(job.config.ytdlp_sleep_requests_s)):
                    break
            so_info += 1
            try:
                info = dict(job.youtube_info(x))
            except Exception as e:  # noqa: BLE001
                phien.ghi_loi(e, "metadata")
                loi_info.append(f"{x} ({giai_thich_loi(e).splitlines()[0][:160]})")
                continue
            finally:
                for cb in list(getattr(job, "canh_bao_mang", []) or []):
                    if cb not in canh_bao:
                        canh_bao.append(cb)
            ma = str(info.get("id") or "")
            if ma and ma in ma_that:
                bo_offline += 1
                continue
            if ma:
                ma_that[ma] = x
            videos.append(co.VideoTrongLo(
                thu_tu=len(videos) + 1, nguon=x, ma=ma, tieu_de=str(info.get("title") or ""),
                kenh=str(info.get("channel") or ""),
                thoi_luong=float(info.get("duration") or 0) or None, info=info))
        if bo_offline:
            canh_bao.append(f"Đã bỏ {bo_offline} link trùng (cùng một video).")
        return videos, canh_bao, loi_info, so_info

    # ---------- một lượt quét ----------

    def _quet_mot_luot(self, job, tt: co.TrangThaiLo, b: co.BuocQuet, source_type: str,
                       dinh_danh: tuple) -> co.LuotQuet:
        phien = getattr(self, "_phien", None)
        if phien is not None and phien.mo:
            # Cầu dao mở ở lượt trước: dừng lô TRƯỚC khi tải video mới. Bằng chứng các lượt
            # trước đã được ghi (`dieu_phoi` giữ nguyên ma trận bằng chứng khi DungLo).
            raise co.DungLo(phien.thong_bao_dung())
        v = tt.videos[b.video]
        dich = (b.nhom_can_du[0] if len(b.nhom_can_du) == 1 else None)
        self._sua(pha=b.pha, video_dang_quet=v.thu_tu, tien_do=0.0,
                  message=f"[{v.thu_tu}/{len(tt.videos)}] {co.TEN_PHA.get(b.pha, b.pha)}"
                          + (f" — tìm «{dich.clip}»" if dich else ""),
                  videos=self._hang_video(tt, b.video, None))
        LOGGER.info("event=scan.common.scan batch_id=%s video=%d mode=%s phase=%s targets=%d",
                    self._anh.ma_lo, v.thu_tu, b.muc_tieu, b.pha, len(b.nhom_can_du))

        def progress(pct: float, msg: str) -> None:
            self._sua(tien_do=float(pct), message=f"[{v.thu_tu}/{len(tt.videos)}] {msg}")

        try:
            if source_type == "youtube":
                kq = job.scan_youtube(v.nguon, progress, luu_lich_su=False,
                                      muc_tieu=b.objective(), info=v.info)
            else:
                kq = job.scan_media(v.nguon, progress=progress, luu_lich_su=False,
                                    muc_tieu=b.objective())
        except Exception as e:  # noqa: BLE001 — engine ném ra ngoài: lô không thể tiếp tục
            raise co.DungLo(f"Lỗi khi quét video {v.thu_tu}: {e}") from e
        if (str(kq.kho_id or ""), str(kq.kho_phien_ban or ""),
                str(kq.chinh_sach or "")) != tuple(str(x or "") for x in dinh_danh):
            raise co.DungLo(
                f"Kho vân tay hoặc chính sách nhận diện đã đổi trong lúc quét lô (video "
                f"{v.thu_tu}). Kết quả các video trước không còn so được với video sau — "
                "hãy chạy lại lô.")
        return co.luot_tu_ket_qua(kq, b.muc_tieu, dinh_danh)

    # ---------- hiển thị ----------

    def _ten_clip(self, clip: str) -> str:
        if clip not in self._ten_cache:
            ten = ""
            resolver = getattr(self, "_resolver", None)
            if resolver is not None:
                try:
                    ten = str(getattr(resolver.resolve(clip), "title", "") or "")
                except Exception:  # noqa: BLE001
                    ten = ""
            self._ten_cache[clip] = ten or clip
        return self._ten_cache[clip]

    def _thong_tin_goc(self, khoa: Optional[co.OriginalKey]) -> dict:
        resolver = getattr(self, "_resolver", None)
        if khoa is None or resolver is None:
            return {}
        try:
            r = resolver.resolve(khoa.clip)
        except Exception:  # noqa: BLE001
            return {}
        return {
            "title": str(getattr(r, "title", "") or ""),
            "url": str(getattr(r, "url", "") or ""),
            "upload_date": str(getattr(r, "upload_date", "") or ""),
            "duration": getattr(r, "duration", None),
            "video_id": str(getattr(r, "video_id", "") or ""),
            "status": str(getattr(r, "status", "") or ""),
            "warnings": tuple(getattr(r, "warnings", ()) or ()),
        }

    def _ung_vien_hien_tai(self, tt: co.TrangThaiLo, kl: Optional[co.KetLuan] = None) -> dict:
        kl = kl or co.ket_luan(tt)
        s = co.tap_kha_di(tt)
        khoa = kl.goc
        if khoa is None and tt.muc_tieu_nhanh is not None and (s is None
                                                              or tt.muc_tieu_nhanh in s):
            khoa = tt.muc_tieu_nhanh
        if khoa is None:
            khoa = kl.tot_nhat
        if khoa is None:
            return {"ung_vien": "", "ung_vien_tieu_de": "", "so_xac_minh": 0,
                    "trang_thai": kl.trang_thai, "videos": self._hang_video(tt, None, None)}
        so = sum(1 for v in tt.videos if v.trang_thai(khoa, tt.kho_id) == co.CO_MAT)
        return {"ung_vien": khoa.clip, "ung_vien_tieu_de": self._ten_clip(khoa.clip),
                "so_xac_minh": so, "trang_thai": kl.trang_thai,
                "videos": self._hang_video(tt, None, khoa)}

    def _hang_video(self, tt: co.TrangThaiLo, dang: Optional[int],
                    khoa: Optional[co.OriginalKey]) -> tuple:
        if khoa is None:
            khoa = tt.muc_tieu_nhanh
        ra = []
        for i, v in enumerate(tt.videos):
            cuoi = v.luot[-1] if v.luot else None
            ra.append(VideoNguonChung(
                thu_tu=v.thu_tu, nguon=v.nguon, tieu_de=v.tieu_de,
                thoi_luong=v.thoi_luong, so_luot=len(v.luot),
                trang_thai=(v.trang_thai(khoa, tt.kho_id) if khoa is not None
                            else (co.CHUA_QUET if not v.luot else "")),
                dang_quet=dang == i, pham_vi=cuoi.pham_vi if cuoi else "",
                loi=next((lq.ly_do for lq in reversed(v.luot) if lq.ly_do), "")))
        return tuple(ra)
