# -*- coding: utf-8 -*-
r"""
channel.py — Đồng bộ toàn bộ video từ kênh YouTube GỐC của bạn về làm kho đối chiếu.

Thiết kế theo đúng các mẹo chuẩn của yt-dlp mà bạn đã nêu, và bổ sung thêm:
  • --download-archive: chạy lại chỉ tải video MỚI, không tải trùng (đồng bộ tăng dần)
  • Đặt tên: "NGÀY ĐĂNG - Tiêu đề [ID].opus" — giữ nguyên tiêu đề trên YouTube,
    kèm ID để định danh bền vững (tiêu đề có thể bị sửa, ID thì không)
  • Nén còn audio mono 16 kHz / 64 kbps: KHÔNG giảm chất lượng đối chiếu
    (đã đo thực nghiệm) nhưng nhẹ hơn video ~100 lần
  • Ghi metadata (id, tiêu đề gốc, ngày đăng, link) vào clips_meta.json để báo cáo
    hiện ĐÚNG TÊN video trên YouTube chứ không phải tên file

Lưu ý: file này chỉ lo phần TẢI VỀ. Việc tạo vân tay vẫn do engine.build_database() làm.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Mapping, Optional

from clip_metadata import filename_fallback_parts, valid_upload_date
from luu_tru import doc_json_an_toan, ghi_json_an_toan
from publication_date import resolve_publication_date

# Ký tự Windows không cho phép đặt trong tên file
RE_XAU = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Định dạng nén tối ưu cho việc đối chiếu (đã kiểm chứng bằng thực nghiệm)
AUDIO_CODEC = "libopus"
AUDIO_BITRATE = "64k"
AUDIO_RATE = "16000"   # audfprint chỉ dùng tới ~5.5 kHz nên 16 kHz là dư
AUDIO_EXT = "opus"
NETWORK_TIMEOUT_S = 30


@dataclass
class VideoInfo:
    id: str
    title: str
    upload_date: str           # ngày đăng CHÍNH TẮC dạng YYYYMMDD (xem publication_date)
    duration: float
    url: str
    publication_source: str = ""   # trường metadata đã sinh ra ngày trên


def lam_sach_ten(s: str, max_len: int = 80) -> str:
    """Bỏ ký tự Windows cấm, cắt bớt tên quá dài (tránh lỗi đường dẫn > 260 ký tự)."""
    s = RE_XAU.sub("_", s or "").strip().rstrip(". ")
    s = re.sub(r"\s+", " ", s)
    return s[:max_len].rstrip(". ") or "khong_ten"


def ngay_dang_tu_info(info: Mapping | None) -> str:
    """Ngày đăng chính tắc (``YYYYMMDD``) từ info của yt-dlp.

    Uỷ quyền cho :mod:`publication_date` để cả dự án dùng chung một quy tắc.
    Trước đây hàm này ưu tiên ``upload_date`` — mà đó là ngày theo lịch **UTC**,
    lệch một ngày so với ngày người dùng Việt Nam nhìn thấy đối với video phát
    hành từ 17:00 UTC trở đi. Nay ưu tiên trường có thời điểm chính xác
    (``release_timestamp``/``timestamp``) vì chỉ nó mới quy đổi được múi giờ.
    """
    return resolve_publication_date(info or {}).yyyymmdd


def provenance_ngay_dang(info: Mapping | None) -> dict:
    """Ngày đăng kèm nguồn gốc, để lưu vào clips_meta.json cho audit về sau."""
    return resolve_publication_date(info or {}).to_dict()


def bo_sung_video_info(v: VideoInfo, info: Mapping | None) -> VideoInfo:
    """Trả về VideoInfo đã điền bằng metadata THẬT từ yt-dlp.

    Chỉ ghi đè khi giá trị mới thực sự có; không bao giờ thay dữ liệu tốt bằng rỗng.
    """
    info = info or {}
    ket_qua = resolve_publication_date(info)
    try:
        thoi_luong = float(info.get("duration") or 0)
    except (TypeError, ValueError):
        thoi_luong = 0.0
    return VideoInfo(
        id=str(info.get("id") or v.id),
        title=str(info.get("title") or v.title),
        upload_date=ket_qua.yyyymmdd or v.upload_date,
        duration=thoi_luong if thoi_luong > 0 else v.duration,
        url=v.url,
        publication_source=ket_qua.source_field or v.publication_source,
    )


class ChannelSync:
    """Đồng bộ kênh YouTube về thư mục kho clip gốc."""

    def __init__(self, dest: str, network_timeout_s: int = NETWORK_TIMEOUT_S):
        if not 5 <= network_timeout_s <= 300:
            raise ValueError("network_timeout_s phải nằm trong khoảng 5..300 giây.")
        self.dest = os.path.abspath(dest)
        self.network_timeout_s = network_timeout_s
        os.makedirs(self.dest, exist_ok=True)
        # File archive theo đúng định dạng chuẩn của yt-dlp ("youtube <id>" mỗi dòng)
        self.archive = os.path.join(self.dest, "downloaded.txt")
        self.meta_file = os.path.join(self.dest, "clips_meta.json")
        self.tmp_dir = os.path.join(self.dest, "_tam")

    # ---------- metadata ----------

    def load_meta(self) -> dict:
        return doc_json_an_toan(self.meta_file, {})

    def save_meta(self, meta: dict) -> None:
        ghi_json_an_toan(self.meta_file, meta)

    def seed_meta_tu_dia(self) -> tuple[dict, int]:
        """Tạo entry rỗng cho clip đã có trên đĩa nhưng chưa có trong clips_meta.json.

        Kho tải từ trước khi có tính năng metadata chỉ còn bằng chứng duy nhất là
        tên file ``<ngày> - <tiêu đề> [<VIDEO_ID>].opus``. Không có bước này thì
        ``va_metadata()`` chỉ lặp qua các key sẵn có nên những clip đó không bao giờ
        vá được ngày đăng/thời lượng. Chỉ điền dữ liệu suy ra được từ chính tên file;
        ``upload_date``/``duration`` để trống cho fetcher điền bằng dữ liệu thật.
        """
        meta = self.load_meta()
        them = 0
        if not os.path.isdir(self.dest):
            return meta, 0
        for ten_file in sorted(os.listdir(self.dest)):
            if not ten_file.lower().endswith("." + AUDIO_EXT):
                continue
            if ten_file in meta:
                continue
            phan = filename_fallback_parts(ten_file)
            video_id = str(phan.get("video_id") or "")
            if not video_id:
                continue        # không có ID thì không thể tra lại, đừng tạo rác
            meta[ten_file] = {
                "id": video_id,
                "title": str(phan.get("title") or ""),
                "url": str(phan.get("url") or ""),
                "upload_date": str(phan.get("upload_date") or ""),
                "duration": None,
            }
            them += 1
        return meta, them

    def va_metadata(
        self,
        progress: Optional[Callable] = None,
        fetcher: Optional[Callable] = None,
        chi_thieu: bool = True,
    ) -> dict:
        """
        Bổ sung upload_date / duration còn thiếu trong clips_meta.json.
        KHÔNG tải lại video, chỉ lấy metadata.
        fetcher: hàm (video_id) -> dict, None thì dùng yt_dlp. Cho phép test offline.
        Trả về {"tong": n, "da_va": n, "bo_qua": n, "da_them_tu_dia": n, "loi": [...]}.
        """
        meta, da_them_tu_dia = self.seed_meta_tu_dia()
        if da_them_tu_dia:
            self.save_meta(meta)
        if not meta:
            return {
                "tong": 0,
                "da_va": 0,
                "bo_qua": 0,
                "da_them_tu_dia": 0,
                "loi": [],
            }

        if fetcher is None:
            def fetcher(video_id: str) -> dict:
                info = ChannelSync.lay_info_video(video_id, self.network_timeout_s)
                return {
                    # Dùng chung cách rút ngày với list_channel/sync để ba đường
                    # không hiểu khác nhau (kể cả trường hợp chỉ có timestamp).
                    "upload_date": ngay_dang_tu_info(info),
                    "duration": info.get("duration"),
                }

        def con_thieu(thong_tin: dict) -> bool:
            ngay = thong_tin.get("upload_date")
            duration = thong_tin.get("duration")
            try:
                duration_hop_le = float(duration) > 0
            except (TypeError, ValueError):
                duration_hop_le = False
            return not ngay or ngay == "00000000" or not duration_hop_le

        can_va = [
            (ten_file, thong_tin)
            for ten_file, thong_tin in meta.items()
            if not chi_thieu or con_thieu(thong_tin)
        ]
        tong = len(meta)
        bo_qua = tong - len(can_va)
        da_va = 0
        loi = []
        tong_can_va = len(can_va)

        # Ghi theo lô: kho lớn có thể cần vá hàng nghìn entry, ghi lại cả file sau
        # mỗi clip là O(n²) I/O. Vẫn ghi định kỳ + ở finally để crash giữa chừng
        # không mất phần đã lấy được.
        CHU_KY_GHI = 25
        chua_ghi = 0
        try:
            for i, (ten_file, thong_tin) in enumerate(can_va, start=1):
                video_id = thong_tin.get("id") or ""
                try:
                    if not video_id:
                        raise RuntimeError("Thiếu ID video.")
                    moi = fetcher(video_id)
                    upload_date = moi.get("upload_date")
                    duration = moi.get("duration")
                    if upload_date and upload_date != "00000000":
                        thong_tin["upload_date"] = str(upload_date)
                    if duration:
                        thong_tin["duration"] = duration
                    chua_ghi += 1
                    if chua_ghi >= CHU_KY_GHI:
                        self.save_meta(meta)
                        chua_ghi = 0
                    da_va += 1
                except Exception as e:  # noqa: BLE001
                    loi.append(f"{ten_file}: {e}")
                if progress:
                    progress(
                        i / tong_can_va,
                        f"[{i}/{tong_can_va}] Đã xử lý metadata: {ten_file}",
                    )
        finally:
            if chua_ghi:
                self.save_meta(meta)

        return {
            "tong": tong,
            "da_va": da_va,
            "bo_qua": bo_qua,
            "da_them_tu_dia": da_them_tu_dia,
            "loi": loi,
        }

    def done_ids(self) -> set:
        """Đọc file archive để biết video nào đã tải."""
        ids = set()
        if os.path.exists(self.archive):
            with open(self.archive, encoding="utf-8", errors="replace") as f:
                for dong in f:
                    p = dong.split()
                    if len(p) >= 2:
                        ids.add(p[1])
        return ids

    def _mark_done(self, vid: str) -> None:
        with open(self.archive, "a", encoding="utf-8") as f:
            f.write(f"youtube {vid}\n")

    # ---------- liệt kê kênh ----------

    @staticmethod
    def lay_info_video(
        video_id: str,
        network_timeout_s: int = NETWORK_TIMEOUT_S,
    ) -> dict:
        """Trích xuất ĐẦY ĐỦ một video (có upload_date/duration). Không tải file."""
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": network_timeout_s,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"https://youtu.be/{video_id}", download=False) or {}

    @staticmethod
    def list_channel(
        url: str,
        limit: Optional[int] = None,
        *,
        lay_ngay_dang: bool = False,
        chi_tiet: Optional[Callable[[str], dict]] = None,
        progress: Optional[Callable] = None,
    ) -> list:
        """
        Lấy danh sách video của kênh mà CHƯA tải gì.
        Chấp nhận link dạng @TenKenh, /channel/UC..., /playlist?list=...

        Mặc định dùng ``extract_flat``: **một** request cho cả kênh nên rất nhanh,
        nhưng yt-dlp ở chế độ này KHÔNG trả ``upload_date`` cho entry của kênh /
        playlist — đó là lý do kho cũ có toàn tên file ``00000000 - ...``. Khi entry
        có sẵn ``release_timestamp``/``timestamp`` (premiere, livestream đã kết thúc)
        thì ngày đăng vẫn được lấy đúng, miễn phí.

        ``lay_ngay_dang=True`` bổ sung ngày đăng/thời lượng bằng **một request mỗi
        video còn thiếu** — chính xác nhưng chậm tỉ lệ với số video; đừng bật cho kênh
        hàng nghìn video.

        ``sync()`` KHÔNG cần bật cờ này: ``_tai_va_nen()`` lấy metadata thật ngay
        trong lượt tải, không tốn thêm request nào.

        ``chi_tiet``: hàm ``(video_id) -> dict`` để test offline.
        """
        import yt_dlp

        if "/@" in url and "/videos" not in url and "/playlist" not in url:
            url = url.rstrip("/") + "/videos"

        opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
                "ignoreerrors": True, "skip_download": True,
                "socket_timeout": NETWORK_TIMEOUT_S}
        if limit:
            opts["playlistend"] = limit

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        ds = []
        for e in (info or {}).get("entries", []) or []:
            if not e or not e.get("id"):
                continue
            ds.append(VideoInfo(
                id=e["id"],
                title=e.get("title") or e["id"],
                upload_date=ngay_dang_tu_info(e),
                duration=float(e.get("duration") or 0),
                url=e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
            ))

        if not lay_ngay_dang:
            return ds

        lay = chi_tiet or ChannelSync.lay_info_video
        con_thieu = [i for i, v in enumerate(ds) if not v.upload_date]
        for thu_tu, i in enumerate(con_thieu, start=1):
            if progress:
                progress(
                    thu_tu / len(con_thieu),
                    f"[{thu_tu}/{len(con_thieu)}] Lấy ngày đăng: {ds[i].title[:50]}",
                )
            try:
                ds[i] = bo_sung_video_info(ds[i], lay(ds[i].id))
            except Exception:  # noqa: BLE001
                # Một video bị xoá/riêng tư không được làm hỏng cả danh sách; mục đó
                # giữ ngày rỗng và sẽ hiện là thiếu chứ không bị bịa.
                continue
        return ds

    # ---------- tải + nén một video ----------

    def _ten_file(self, v: VideoInfo) -> str:
        # "00000000" chỉ dùng khi thật sự không có ngày đăng. Không bịa ngày hôm nay:
        # tên file là bằng chứng offline duy nhất còn lại nếu clips_meta.json mất.
        ngay = valid_upload_date(v.upload_date) or "00000000"
        return f"{ngay} - {lam_sach_ten(v.title)} [{v.id}].{AUDIO_EXT}"

    def _tim_file_cua(self, vid: str) -> Optional[str]:
        for f in os.listdir(self.dest):
            if f"[{vid}]" in f and f.lower().endswith("." + AUDIO_EXT):
                return os.path.join(self.dest, f)
        return None

    def _tai_va_nen(self, v: VideoInfo) -> tuple:
        """Tải bestaudio rồi nén sang opus mono.

        Trả về ``(duong_dan, VideoInfo đã bổ sung)``. Lượt tải này vốn đã trích xuất
        đầy đủ trang video, nên ``upload_date``/``duration``/``title`` thật lấy được
        **miễn phí** — không tốn thêm request nào. Đây là lý do ``sync()`` không cần
        bật ``list_channel(lay_ngay_dang=True)``.
        """
        import yt_dlp

        os.makedirs(self.tmp_dir, exist_ok=True)
        opts = {
            "format": "ba/b",
            "outtmpl": os.path.join(self.tmp_dir, "%(id)s.%(ext)s"),
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "continuedl": True, "retries": 10, "fragment_retries": 10,
            "socket_timeout": self.network_timeout_s,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(v.url, download=True)
        v = bo_sung_video_info(v, info if isinstance(info, Mapping) else None)

        tho = [os.path.join(self.tmp_dir, f) for f in os.listdir(self.tmp_dir)
               if f.startswith(v.id + ".") and not f.endswith((".part", ".ytdl"))]
        if not tho:
            raise RuntimeError("Tải thất bại (không thấy file sau khi tải).")
        nguon = tho[0]

        dich = os.path.join(self.dest, self._ten_file(v))
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", nguon,
             "-vn", "-ac", "1", "-ar", AUDIO_RATE,
             "-c:a", AUDIO_CODEC, "-b:a", AUDIO_BITRATE, dich],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0 or not os.path.exists(dich):
            raise RuntimeError(f"Nén audio thất bại: {r.stderr.strip()[:200]}")

        os.remove(nguon)
        return dich, v

    # ---------- đồng bộ cả kênh ----------

    def sync(self, url: str, limit: Optional[int] = None,
             progress: Optional[Callable] = None,
             cancel_check: Optional[Callable] = None) -> dict:
        """
        Đồng bộ kênh: chỉ tải video CHƯA có trong archive.
        Trả về {'tong': n, 'moi': n, 'bo_qua': n, 'loi': [...], 'thu_muc': ...}
        """
        def bao(pct, msg):
            if progress:
                progress(max(0.0, min(1.0, pct)), msg)

        bao(0.0, "Đang lấy danh sách video của kênh...")
        ds = self.list_channel(url, limit)
        if not ds:
            raise RuntimeError("Không lấy được video nào từ kênh. Kiểm tra lại link kênh.")

        # Lấy hợp của archive VÀ file thực tế trên đĩa — chống trường hợp archive
        # bị lệch do tải đứt giữa chừng hoặc người dùng chép file thủ công vào.
        da_co = self.done_ids() | set(self.quet_id_tren_dia())
        can_tai = [v for v in ds if v.id not in da_co]
        bao(0.02, f"Kênh có {len(ds)} video — {len(can_tai)} video mới cần tải.")

        meta = self.load_meta()
        loi = []
        da_tai = 0
        da_huy = False
        for i, v in enumerate(can_tai):
            if cancel_check and cancel_check():
                da_huy = True
                break
            bao(0.02 + 0.96 * i / max(1, len(can_tai)),
                f"[{i+1}/{len(can_tai)}] {v.title[:60]}")
            try:
                f, v = self._tai_va_nen(v)
                ngay = valid_upload_date(v.upload_date)
                meta[os.path.basename(f)] = {
                    "id": v.id, "title": v.title,
                    # upload_date giữ tên cũ để bản đọc metadata cũ vẫn chạy;
                    # publication_date là trường chính tắc kèm nguồn gốc.
                    "upload_date": ngay,
                    "publication_date": ngay,
                    "publication_date_source": v.publication_source,
                    "duration": v.duration, "url": f"https://youtu.be/{v.id}",
                }
                self.save_meta(meta)
                self._mark_done(v.id)
                da_tai += 1
            except Exception as e:  # noqa: BLE001
                loi.append(f"{v.title[:40]}: {e}")

        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        bao(1.0, "Đồng bộ xong.")
        return {"tong": len(ds), "moi": da_tai,
                "bo_qua": len(ds) - len(can_tai), "loi": loi,
                "thu_muc": self.dest, "da_huy": da_huy}

    # ---------- khôi phục / đối chiếu ----------

    def quet_id_tren_dia(self) -> dict:
        """
        Quét thư mục kho, lấy ID video từ phần [ID] trong tên file.
        Dùng để khôi phục khi downloaded.txt bị mất/hỏng, hoặc để đối chiếu.
        Trả về {video_id: ten_file}.
        """
        kq = {}
        if not os.path.isdir(self.dest):
            return kq
        for f in os.listdir(self.dest):
            if not f.lower().endswith("." + AUDIO_EXT):
                continue
            m = re.search(r"\[([A-Za-z0-9_-]{6,})\]\.[^.]+$", f)
            if m:
                kq[m.group(1)] = f
        return kq

    def sua_archive(self) -> dict:
        """
        Dựng lại downloaded.txt từ các file THỰC SỰ đang có trên đĩa.
        Dùng khi: tải bị đứt giữa chừng, archive mất/hỏng, hoặc file bị xoá thủ công.
        An toàn tuyệt đối — chỉ ghi lại file text, không đụng vào file audio.
        """
        tren_dia = self.quet_id_tren_dia()
        cu = self.done_ids()
        file_tam = self.archive + ".tmp"
        try:
            with open(file_tam, "w", encoding="utf-8") as f:
                for vid in sorted(tren_dia):
                    f.write(f"youtube {vid}\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(file_tam, self.archive)
        except BaseException:
            try:
                if os.path.exists(file_tam):
                    os.remove(file_tam)
            except OSError:
                pass
            raise
        return {
            "tren_dia": len(tren_dia),
            "archive_cu": len(cu),
            "ma_bi_ghi_thua": sorted(cu - set(tren_dia))[:20],  # có trong archive mà mất file
            "ma_bi_thieu": sorted(set(tren_dia) - cu)[:20],     # có file mà archive quên
        }

    def kiem_tra_thieu(self, url: str, limit: Optional[int] = None) -> dict:
        """
        Đối chiếu kênh YouTube với thư mục kho: còn thiếu đúng những video nào.
        Không tải gì cả — chỉ đọc danh sách.
        """
        ds = self.list_channel(url, limit)
        tren_dia = self.quet_id_tren_dia()
        thieu = [v for v in ds if v.id not in tren_dia]
        return {"tong_kenh": len(ds), "co_roi": len(ds) - len(thieu),
                "thieu": thieu, "thua": [f for i, f in tren_dia.items()
                                         if i not in {v.id for v in ds}]}

    # ---------- dung lượng ----------

    def thong_ke(self) -> dict:
        files = [f for f in os.listdir(self.dest)
                 if f.lower().endswith("." + AUDIO_EXT)] if os.path.isdir(self.dest) else []
        tong = sum(os.path.getsize(os.path.join(self.dest, f)) for f in files)
        return {"so_file": len(files), "dung_luong_mb": tong / 1024 / 1024}
