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

import contextlib
import json
import math
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from dataclasses import dataclass, replace
from typing import Callable, Mapping, Optional

from clip_metadata import (basename_compatible, extract_youtube_id, filename_fallback_parts,
                           valid_upload_date)
from khoa import KhoaTienTrinh
from luu_tru import cap_nhat_json, doc_json_an_toan, ghi_json_an_toan, khoa_json
from process_runner import IM_LANG_FFMPEG_S, TRAN_FFPROBE_S, chay_lenh_media
from publication_date import resolve_publication_date
from ytdlp_chung import (
    PLAYER_CLIENTS_MAC_DINH,
    CauHinhMang,
    NhoClientTotNhat,
    chay_kem_duong_lui_cookie,
    giai_thich_loi,
    go_ma_mau,
    thu_tung_client,
)

# Ký tự Windows không cho phép đặt trong tên file
RE_XAU = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Định dạng nén tối ưu cho việc đối chiếu (đã kiểm chứng bằng thực nghiệm)
AUDIO_CODEC = "libopus"
AUDIO_BITRATE = "64k"
AUDIO_RATE = "16000"   # audfprint chỉ dùng tới ~5.5 kHz nên 16 kHz là dư
AUDIO_EXT = "opus"

# Thư mục LÀM VIỆC bên trong kho — không phải clip của kho, mọi bước liệt kê/tạo vân tay
# phải bỏ qua (audit TCP-10). `_tam`: mỗi lượt đồng bộ một thư mục con chứa file tải
# thô và bản đang nén. `_hong`: file nghi hỏng đã được THAY bằng bản tải lại thành công
# — giữ nguyên để đối chiếu, không bao giờ tự xoá.
THU_MUC_TAM = "_tam"
THU_MUC_HONG = "_hong"
DUOI_DANG_NEN = ".dang_nen." + AUDIO_EXT   # vẫn đuôi .opus để FFmpeg chọn đúng muxer
# Bản nén ngắn hơn nguồn quá mức này là bản dở/cắt cụt. Chỉ chặn chiều NGẮN: audio của
# một số video kết thúc sớm hơn hình vài giây là bình thường.
TY_LE_DO_DAI_TOI_THIEU = 0.9
# Hai lần tải độc lập lệch nhau không quá mức này thì coi là CÙNG một độ dài.
DUNG_SAI_TAI_LAI_S = 1.0
HAN_DON_TAM_CU_S = 3 * 24 * 3600            # thư mục tạm của lượt đã chết từ lâu
RE_ID_TEN_FILE = re.compile(r"\[([A-Za-z0-9_-]{6,})\]\.[^.]+$")
# Một kho chỉ có MỘT lượt đồng bộ tại một thời điểm: hai lượt song song tải trùng video
# và lượt sau từng cách ly nhầm bản tốt lượt trước vừa đặt vào (phản biện TCP-10).
TEN_KHOA_DONG_BO = ".dong_bo_kenh.lock"
# Windows chưa bật LongPathsEnabled giới hạn 260 ký tự: tên trong `_hong` dài hơn tên
# gốc nên phải rút gọn trước khi chạm trần.
DO_DAI_DUONG_DAN_TOI_DA = 240


def _dat_vao_kho(tam: str, dich: str, so_lan: int = 10) -> None:
    """``os.replace`` có thử lại: phần mềm diệt virus/chỉ mục/OneDrive hay giữ file vừa
    ghi một nhịp (WinError 32). Hết lượt thử thì ném lỗi — người gọi tự hoàn nguyên."""
    for lan in range(so_lan):
        try:
            os.replace(tam, dich)
            return
        except PermissionError:
            if lan == so_lan - 1:
                raise
            time.sleep(min(2.0, 0.1 * (2 ** lan)))


def _so_duong(x) -> float:
    try:
        gia_tri = float(x)
    except (TypeError, ValueError):
        return 0.0
    return gia_tri if math.isfinite(gia_tri) and gia_tri > 0 else 0.0


RE_TEN_TRONG_HONG = re.compile(r"^\d{6}-\d{6}_(.+)$")


def ten_da_cach_ly(thu_muc_kho: str) -> set:
    """Tên GỐC (đã ``normcase``) của các file đã bị cách ly vào ``_hong/`` — chỉ đọc.

    ``_luu_vao_hong`` đặt tên ``<yymmdd-HHMMSS>_<tên gốc>``, thêm ``_<n>`` trước đuôi khi
    trùng, hoặc rút còn ``<yymmdd-HHMMSS>_<mã video><đuôi>`` khi đường dẫn quá dài.
    """
    ra: set = set()
    try:
        ds = os.listdir(os.path.join(thu_muc_kho, THU_MUC_HONG))
    except OSError:
        return ra
    for ten in ds:
        m = RE_TEN_TRONG_HONG.match(ten)
        if not m:
            continue
        goc = m.group(1)
        ra.add(os.path.normcase(goc))
        than, duoi = os.path.splitext(goc)
        m_trung = re.fullmatch(r"(.*)_\d+", than)
        if m_trung:
            ra.add(os.path.normcase(m_trung.group(1) + duoi))
    return ra


def la_ban_da_cach_ly(ten_file: str, ten_cach_ly: set) -> bool:
    """File tên ``ten_file`` (trong kho) có một bản đã bị cách ly (``ten_da_cach_ly``)?"""
    if os.path.normcase(ten_file) in ten_cach_ly:
        return True
    m = RE_ID_TEN_FILE.search(ten_file)
    return bool(m) and os.path.normcase(
        m.group(1) + os.path.splitext(ten_file)[1]) in ten_cach_ly


NETWORK_TIMEOUT_S = 30

# Danh sách client, hàm dọn mã màu và hàm diễn giải lỗi nay nằm ở `ytdlp_chung` để
# đường quét (engine.py) và đường đồng bộ kênh (file này) dùng CHUNG một bản. Giữ tên
# ở đây làm alias vì mã cũ và test đang tham chiếu qua `channel.*`.
__all__ = [
    "PLAYER_CLIENTS_MAC_DINH", "CauHinhMang", "ChannelSync", "VideoInfo",
    "giai_thich_loi", "go_ma_mau",
]


@dataclass
class VideoInfo:
    id: str
    title: str
    upload_date: str           # ngày đăng CHÍNH TẮC dạng YYYYMMDD (xem publication_date)
    duration: float
    url: str
    publication_source: str = ""   # trường metadata đã sinh ra ngày trên


def do_dai_media(path: str) -> float | None:
    """Độ dài thật của file media, đo bằng ffprobe. Không đo được thì trả None.

    Cần trường này vì `duration` của yt-dlp là `lengthSeconds` của YouTube — một số
    nguyên ĐÃ LÀM TRÒN. Đo trên 60 clip kho SML: 58/60 khớp đúng `round(media)`, và
    ở 55% số clip nó cao hơn `floor(media)` một giây. Trình phát thì cắt phần lẻ,
    nên hiển thị theo số nguyên đó sẽ dư 1 giây ở hơn nửa số clip.

    File đã nén vẫn giữ được độ dài rất sát bản gốc: `.opus` của 3ixKzIN0et0 dài
    675,858 giây, còn `video.duration` trên chính trang YouTube là 675,861 giây.
    """
    try:
        # Trần tổng riêng cho FFprobe: treo thì coi như không đo được (audit TCP-15).
        r = chay_lenh_media(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            tran_tong_s=TRAN_FFPROBE_S,
        )
        if r.timed_out:
            return None
        gia_tri = float(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001 — thiếu thời lượng chính xác không được làm hỏng sync
        return None
    return gia_tri if math.isfinite(gia_tri) and gia_tri > 0 else None


# Lệnh ffprobe đọc MỌI luồng tiếng: chỉ số, mốc bắt đầu, độ dài và thẻ DURATION (mkv/webm
# không ghi `duration` của luồng — ffprobe báo "N/A" — mà để ở thẻ).
LENH_FFPROBE_LUONG_TIENG = ["ffprobe", "-v", "error", "-select_streams", "a",
                            "-show_entries",
                            "stream=index,start_time,duration:stream_tags=DURATION",
                            "-of", "json"]


def _giay(gia_tri) -> Optional[float]:
    """Số giây từ "12.5" hoặc thẻ "HH:MM:SS.fffffffff"; không đọc được → None."""
    if gia_tri is None:
        return None
    try:
        chuoi = str(gia_tri).strip()
        if ":" in chuoi:
            gio, phut, giay = chuoi.split(":")
            so = int(gio) * 3600 + int(phut) * 60 + float(giay)
        else:
            so = float(chuoi)
    except ValueError:
        return None
    return so if math.isfinite(so) else None


def doc_moc_het_tieng(json_ffprobe: str) -> Optional[float]:
    """Mốc KẾT THÚC (giây, trên trục thời gian của file) của luồng tiếng DUY NHẤT, từ output
    ``LENH_FFPROBE_LUONG_TIENG``. ``None`` khi không đọc được hoặc file có NHIỀU luồng
    tiếng: luồng đầu kết thúc sớm không có nghĩa là phần sau không còn tiếng (phản biện
    vòng 3). Mốc kết thúc = ``start_time`` + độ dài — luồng bắt đầu trễ kết thúc muộn hơn.
    """
    try:
        du_lieu = json.loads(json_ffprobe or "{}")
    except ValueError:
        return None
    luong = {s.get("index"): s for s in (du_lieu.get("streams") or [])
             if isinstance(s, dict)}
    if len(luong) != 1:
        return None
    s = next(iter(luong.values()))
    the = s.get("tags") or {}
    dai = _giay(s.get("duration"))
    if dai is None:
        dai = _giay(the.get("DURATION") or the.get("duration"))
    if dai is None or dai <= 0:
        return None
    bat_dau = max(0.0, _giay(s.get("start_time")) or 0.0)
    return bat_dau + dai


def do_dai_luong_tieng(path: str) -> Optional[float]:
    """Mốc kết thúc của luồng tiếng duy nhất (``doc_moc_het_tieng``); không đo được → None.

    ``do_dai_media`` đo luồng DÀI NHẤT: nguồn tải bằng client ``android`` là video tiến
    trình, hình dài hơn tiếng thì nó báo độ dài của hình (phản biện vòng 3).
    """
    try:
        r = chay_lenh_media([*LENH_FFPROBE_LUONG_TIENG, path], tran_tong_s=TRAN_FFPROBE_S)
        if r.timed_out or r.returncode != 0:
            return None
    except Exception:  # noqa: BLE001
        return None
    return doc_moc_het_tieng(r.stdout)


class DaHuyDongBo(RuntimeError):
    """Người dùng bấm Dừng trong lúc đang tải/nén — dừng cả lượt, không phải lỗi video."""


class _CoHuyTuHam:
    """Bọc ``cancel_check()`` thành đối tượng có ``is_set()`` cho helper process."""

    def __init__(self, ham: Optional[Callable[[], bool]]):
        self._ham = ham

    def is_set(self) -> bool:
        return bool(self._ham and self._ham())


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

    def __init__(self, dest: str, network_timeout_s: Optional[int] = None,
                 player_clients: Optional[list] = None,
                 cau_hinh_mang: Optional[CauHinhMang] = None):
        # Mặc định là None chứ KHÔNG phải NETWORK_TIMEOUT_S: nếu để giá trị cứng thì
        # mọi lượt khởi tạo đều ghi đè timeout mà người dùng đã đặt trong cau_hinh.json
        # lên 30 giây, và không cách nào phân biệt "người gọi chỉ định 30" với
        # "người gọi không quan tâm".
        goc = cau_hinh_mang or CauHinhMang()
        if network_timeout_s is None:
            network_timeout_s = goc.network_timeout_s
        if not 5 <= network_timeout_s <= 300:
            raise ValueError("network_timeout_s phải nằm trong khoảng 5..300 giây.")
        if player_clients is not None and (
            not isinstance(player_clients, list)
            or not all(isinstance(x, str) for x in player_clients)
            or not player_clients
        ):
            raise ValueError(
                "player_clients phải là danh sách chuỗi không rỗng; "
                "dùng [\"\"] để giữ mặc định yt-dlp."
            )
        self.dest = os.path.abspath(dest)
        self.network_timeout_s = network_timeout_s
        self.cau_hinh_mang = replace(goc, network_timeout_s=network_timeout_s)
        # Có cookie thì các client không hỗ trợ cookie bị yt-dlp gỡ; xếp lại để khỏi
        # mất lượt thử vô ích cho mỗi video.
        self.player_clients = self.cau_hinh_mang.player_clients(
            list(player_clients or PLAYER_CLIENTS_MAC_DINH))
        os.makedirs(self.dest, exist_ok=True)
        # File archive theo đúng định dạng chuẩn của yt-dlp ("youtube <id>" mỗi dòng)
        self.archive = os.path.join(self.dest, "downloaded.txt")
        self.meta_file = os.path.join(self.dest, "clips_meta.json")
        # Mỗi đối tượng (một lượt đồng bộ) có thư mục tạm RIÊNG: dọn xong lượt này không
        # đụng file của lượt khác đang chạy song song trên cùng kho (audit TCP-10).
        self.tmp_goc = os.path.join(self.dest, THU_MUC_TAM)
        self.tmp_dir = os.path.join(self.tmp_goc, f"{os.getpid()}_{uuid.uuid4().hex[:8]}")
        self.thu_muc_hong = os.path.join(self.dest, THU_MUC_HONG)
        self._da_cach_ly: list = []
        # Mã video vừa tải mà âm thanh YouTube thật sự ngắn hơn lengthSeconds (đã tải lại
        # và nhận cùng độ dài) — để dấu xác nhận ghi rõ, lượt sau khỏi coi là file cụt.
        self._ngan_hon_youtube: set = set()
        # Đồng bộ kênh chạy hàng trăm video liên tiếp nên đây là chỗ khoản tiết
        # kiệm lớn nhất: nhớ client tải được, khỏi 403 lại cho từng video.
        self.nho_client = NhoClientTotNhat()

    # ---------- metadata ----------

    def load_meta(self) -> dict:
        return doc_json_an_toan(self.meta_file, {})

    def save_meta(self, meta: dict) -> None:
        """Ghi đè TOÀN BỘ file. Chỉ dùng khi chủ ý thay cả file; muốn thêm/sửa vài
        entry thì dùng :meth:`cap_nhat_meta` để không xoá mất cập nhật của writer khác."""
        ghi_json_an_toan(self.meta_file, meta)

    def cap_nhat_meta(
        self,
        thay_doi: Mapping[str, Mapping],
        *,
        thay_ca_entry: bool = False,
        chi_khi_chua_co: bool = False,
    ) -> int:
        """Gộp ĐÚNG các entry/trường đã đổi vào bản ``clips_meta.json`` MỚI NHẤT.

        Đồng bộ kênh, vá metadata, sửa ngày đăng/thời lượng có thể chạy ở các process
        khác nhau. Trước đây mỗi bên đọc cả file lúc đầu rồi ghi đè cả file lúc cuối,
        nên entry do bên kia thêm vào giữa chừng biến mất (audit TCP-03). Ở đây việc
        đọc-gộp-ghi diễn ra dưới cùng một khoá.

        ``thay_ca_entry``: thay nguyên entry (entry mới vừa tải xong).
        ``chi_khi_chua_co``: chỉ thêm khi key chưa có (seed từ tên file — không bao giờ
        đè dữ liệu thật mà writer khác vừa ghi).
        Mặc định: gộp từng trường vào entry đang có, tạo entry nếu chưa có.
        Trả về số entry đã được ghi.
        """
        if not thay_doi:
            return 0

        def gop(meta: dict) -> int:
            so = 0
            for ten, truong in thay_doi.items():
                hien_co = meta.get(ten)
                if chi_khi_chua_co and ten in meta:
                    continue
                if thay_ca_entry or not isinstance(hien_co, dict):
                    meta[ten] = dict(truong)
                else:
                    hien_co.update(truong)
                so += 1
            return so

        return cap_nhat_json(self.meta_file, gop, mac_dinh={})

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
        # Mã video đã có mục: một video chỉ một mục. Bản sao Windows (" (1)", " - Copy")
        # cũng đọc ra được mã; tạo mục cho nó làm sổ có hai chữ ký cho một mã và resolver
        # báo `ambiguous_video_id` (phản biện vòng 2). Tên chuẩn `… [ID].opus` xét trước.
        # Mục cũ có thể chỉ mang mã ở URL hoặc ở chính TÊN khoá, không có trường `id`
        # (phản biện vòng 3).
        da_co_ma: set = set()
        for khoa_cu, m in meta.items():
            if not isinstance(m, dict):
                continue
            da_co_ma.update({
                str(m.get("id") or ""),
                str(extract_youtube_id(str(m.get("url") or "")) or ""),
                str(extract_youtube_id(basename_compatible(str(khoa_cu))) or ""),
            })
        da_co_ma.discard("")
        for ten_file in sorted(os.listdir(self.dest),
                               key=lambda t: (RE_ID_TEN_FILE.search(t) is None, t)):
            if not ten_file.lower().endswith("." + AUDIO_EXT):
                continue
            if ten_file in meta:
                continue
            phan = filename_fallback_parts(ten_file)
            video_id = str(phan.get("video_id") or "")
            if not video_id:
                continue        # không có ID thì không thể tra lại, đừng tạo rác
            if video_id in da_co_ma:
                continue
            da_co_ma.add(video_id)
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
        *,
        lay_title: bool = False,
    ) -> dict:
        """
        Bổ sung upload_date / duration còn thiếu trong clips_meta.json.
        KHÔNG tải lại video, chỉ lấy metadata.
        fetcher: hàm (video_id) -> dict, None thì dùng yt_dlp. Cho phép test offline.
        Trả về {"tong": n, "da_va": n, "bo_qua": n, "da_them_tu_dia": n, "loi": [...]}.

        ``lay_title=True`` lấy thêm TIÊU ĐỀ THẬT trên YouTube. Mặc định tắt vì đây
        là hành vi mới và tốn thêm lượt hỏi cho cả những clip đã đủ ngày/thời lượng.

        Vì sao cần: ``seed_meta_tu_dia()`` điền ``title`` suy từ TÊN FILE — mà tên
        file đã bị :func:`lam_sach_ten` thay ``< > : " / \\ | ? *`` bằng ``_`` và cắt
        còn 80 ký tự. Nếu để nguyên, báo cáo và tab «Danh sách video trong kho» sẽ
        coi cái tên hỏng đó là tên thật. Khi bật cờ này, những clip vừa seed sẽ được
        hỏi lại tiêu đề; clip nào hỏi KHÔNG được thì ``title`` bị xoá về rỗng để nơi
        khác còn biết là chưa có tên thật, thay vì tin vào tên suy từ file.
        """
        truoc_seed = set(self.load_meta())
        meta, da_them_tu_dia = self.seed_meta_tu_dia()
        vua_seed = set(meta) - truoc_seed
        # Các key VỪA được seed: `title` của chúng là tên file đã làm sạch, không
        # phải tên thật trên YouTube.
        moi_seed = vua_seed if lay_title else set()
        if da_them_tu_dia:
            # Chỉ THÊM entry còn thiếu; writer khác vừa ghi dữ liệu thật cho cùng key
            # thì giữ của họ.
            self.cap_nhat_meta({k: meta[k] for k in vua_seed}, chi_khi_chua_co=True)
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
                info = ChannelSync.lay_info_video(
                    video_id, self.network_timeout_s,
                    cau_hinh_mang=self.cau_hinh_mang)
                return {
                    # Dùng chung cách rút ngày với list_channel/sync để ba đường
                    # không hiểu khác nhau (kể cả trường hợp chỉ có timestamp).
                    "upload_date": ngay_dang_tu_info(info),
                    "duration": info.get("duration"),
                    "title": info.get("title"),
                }

        def con_thieu(ten_file: str, thong_tin: dict) -> bool:
            ngay = thong_tin.get("upload_date")
            duration = thong_tin.get("duration")
            try:
                duration_hop_le = float(duration) > 0
            except (TypeError, ValueError):
                duration_hop_le = False
            if not ngay or ngay == "00000000" or not duration_hop_le:
                return True
            if lay_title:
                # Title rỗng, hoặc title vừa seed từ tên file -> vẫn phải hỏi.
                return (not str(thong_tin.get("title") or "").strip()
                        or ten_file in moi_seed)
            return False

        can_va = [
            (ten_file, thong_tin)
            for ten_file, thong_tin in meta.items()
            if not chi_thieu or con_thieu(ten_file, thong_tin)
        ]
        tong = len(meta)
        bo_qua = tong - len(can_va)
        da_va = 0
        loi = []
        tong_can_va = len(can_va)

        # Ghi theo lô: kho lớn có thể cần vá hàng nghìn entry, ghi lại cả file sau
        # mỗi clip là O(n²) I/O. Vẫn ghi định kỳ + ở finally để crash giữa chừng
        # không mất phần đã lấy được. Mỗi lần ghi chỉ GỘP các trường đã đổi vào bản
        # mới nhất — không ghi đè cả file bằng bản đọc từ đầu lượt.
        CHU_KY_GHI = 25
        thay_doi: dict[str, dict] = {}

        def doi(ten_file: str, thong_tin: dict, truong: str, gia_tri) -> None:
            thong_tin[truong] = gia_tri
            thay_doi.setdefault(ten_file, {})[truong] = gia_tri

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
                        doi(ten_file, thong_tin, "upload_date", str(upload_date))
                    if duration:
                        doi(ten_file, thong_tin, "duration", duration)
                    if lay_title:
                        tieu_de = str(moi.get("title") or "").strip()
                        if tieu_de:
                            doi(ten_file, thong_tin, "title", tieu_de)
                        elif ten_file in moi_seed:
                            doi(ten_file, thong_tin, "title", "")
                    if len(thay_doi) >= CHU_KY_GHI:
                        self.cap_nhat_meta(thay_doi)
                        thay_doi.clear()
                    da_va += 1
                except Exception as e:  # noqa: BLE001
                    # Hỏi không được: xoá title vừa seed từ tên file, để nơi khác
                    # không tin nhầm cái tên đã bị làm sạch là tên thật YouTube.
                    if lay_title and ten_file in moi_seed:
                        doi(ten_file, thong_tin, "title", "")
                    loi.append(f"{ten_file}: {giai_thich_loi(e)}")
                if progress:
                    progress(
                        i / tong_can_va,
                        f"[{i}/{tong_can_va}] Đã xử lý metadata: {ten_file}",
                    )
        finally:
            if thay_doi:
                self.cap_nhat_meta(thay_doi)

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
        self._mark_done_nhieu([vid])

    def _mark_done_nhieu(self, vids) -> None:
        """Nối các mã CHƯA có vào archive — một lần khoá, không nhân đôi dòng.

        Cùng khoá với `sua_archive` (ghi lại cả file) để dòng vừa nối không bị mất.
        """
        with khoa_json(self.archive):
            co = self.done_ids()
            moi = [v for v in dict.fromkeys(vids) if v and v not in co]
            if moi:
                with open(self.archive, "a", encoding="utf-8") as f:
                    f.writelines(f"youtube {v}\n" for v in moi)

    # ---------- liệt kê kênh ----------

    @staticmethod
    def lay_info_video(
        video_id: str,
        network_timeout_s: int = NETWORK_TIMEOUT_S,
        cau_hinh_mang: Optional[CauHinhMang] = None,
    ) -> dict:
        """Trích xuất ĐẦY ĐỦ một video (có upload_date/duration). Không tải file."""
        import yt_dlp

        goc = cau_hinh_mang or CauHinhMang()
        opts = replace(goc, network_timeout_s=network_timeout_s).tuy_chon(
            skip_download=True, noplaylist=True)
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
        cau_hinh_mang: Optional[CauHinhMang] = None,
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

        opts = (cau_hinh_mang or CauHinhMang()).tuy_chon(
            extract_flat="in_playlist", ignoreerrors=True, skip_download=True)
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

        # Nhánh mặc định PHẢI mang theo cau_hinh_mang: đây là vòng lặp một request MỖI
        # video — nặng hơn hẳn lượt extract_flat ở trên, và đúng chỗ bot-check đánh.
        # Gọi trần `ChannelSync.lay_info_video` sẽ rơi về cấu hình mặc định, tức mất
        # cookie và mất nhịp người dùng đặt, ngay tại nơi cần chúng nhất.
        # `chi_tiet` do người gọi truyền vào giữ nguyên chữ ký (video_id) -> dict.
        def _lay_mac_dinh(video_id: str) -> dict:
            goc = cau_hinh_mang or CauHinhMang()
            return ChannelSync.lay_info_video(
                video_id, goc.network_timeout_s, cau_hinh_mang=goc)

        lay = chi_tiet or _lay_mac_dinh
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

    def _tai_thu_tung_client(self, url: str, rieng: dict):
        """Tải bằng yt-dlp với hai lớp đường lui: cookie ở ngoài, player client ở trong.

        Nhận ``rieng`` (phần tuỳ chọn riêng của lượt tải) chứ không nhận dict tuỳ chọn
        đã dựng sẵn, vì đường lui cookie phải DỰNG LẠI toàn bộ tuỳ chọn với một cấu
        hình mạng khác — sửa tại chỗ trên dict cũ sẽ để sót khoá cookie.

        Đúng cùng cặp đường lui mà :meth:`engine.Engine.download_audio` dùng; cả hai
        gọi chung `ytdlp_chung` để không đường nào bị bỏ sót khi vá.
        """
        import yt_dlp

        def chay(rieng: dict):
            with yt_dlp.YoutubeDL(rieng) as ydl:
                return ydl.extract_info(url, download=True)

        def don_file_do_dang() -> None:
            """Xoá .part/.ytdl trước khi đổi client.

            Mỗi client trả một format khác nhau; `continuedl=True` gặp .part cũ sẽ nối
            byte của luồng MỚI vào luồng CŨ, ra file audio hỏng mà không báo lỗi — và
            với kho đối chiếu thì vân tay hỏng còn tệ hơn tải thất bại. Dọn MỌI thư mục
            con của lượt (kể cả `lan2_*` của lần tải lại kiểm chứng — phản biện vòng 3).
            """
            if not os.path.isdir(self.tmp_dir):
                return
            for goc, _thu_muc_con, cac_file in os.walk(self.tmp_dir):
                for ten in cac_file:
                    if ten.endswith((".part", ".ytdl")):
                        with contextlib.suppress(OSError):
                            os.remove(os.path.join(goc, ten))

        def tai_voi(cau_hinh):
            return thu_tung_client(
                cau_hinh.player_clients(self.player_clients), chay,
                cau_hinh.tuy_chon(**rieng), truoc_khi_thu_lai=don_file_do_dang,
                bo_nho=self.nho_client)

        # Cookie hết hiệu lực làm YouTube chỉ trả storyboard nên MỌI client đều hỏng;
        # đường lui cookie phải bọc NGOÀI đường lui client. Đường quét (engine.py) làm
        # y hệt — hai đường dùng chung `chay_kem_duong_lui_cookie`.
        return chay_kem_duong_lui_cookie(self.cau_hinh_mang, tai_voi)

    @staticmethod
    def kiem_file_audio(path: str, tham_chieu_s: float = 0.0) -> tuple:
        """``(độ dài, lý do hỏng)`` của một file audio; lý do rỗng = dùng được.

        ``size > 0`` chưa đủ: FFmpeg chết giữa chừng để lại file có byte mà không đọc
        được, hoặc đọc được nhưng chỉ có đoạn đầu. Nên kiểm cả ffprobe và, khi biết độ
        dài nguồn, độ dài bản nén.
        """
        try:
            kich_thuoc = os.path.getsize(path)
        except OSError:
            return None, "không đọc được file"
        if kich_thuoc <= 0:
            return None, "file rỗng (0 byte)"
        do_dai = do_dai_media(path)
        if do_dai is None:
            return None, "ffprobe không đọc được thời lượng — file hỏng hoặc nén dở"
        if ChannelSync._nguon_ngan_bat_thuong(do_dai, tham_chieu_s):
            return do_dai, (f"chỉ dài {do_dai:.1f}s trong khi nguồn dài "
                            f"{tham_chieu_s:.1f}s — nén dở hoặc bị cắt cụt")
        return do_dai, ""

    def _nen_va_kiem(self, nguon: str, tam: str, tham_chieu_s: float, cancel_event) -> str:
        """Nén ``nguon`` sang opus vào file tạm ``tam`` rồi kiểm; trả lý do hỏng (rỗng = đạt).

        Huỷ, FFmpeg treo hay mã thoát lỗi thì ném luôn — không có gì để kiểm.
        """
        r = chay_lenh_media(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", nguon,
             "-vn", "-ac", "1", "-ar", AUDIO_RATE,
             "-c:a", AUDIO_CODEC, "-b:a", AUDIO_BITRATE, tam],
            cancel_event=cancel_event,
            theo_doi_tien_do=True,
            im_lang_toi_da_s=IM_LANG_FFMPEG_S,
        )
        if r.cancelled:
            raise DaHuyDongBo("Đã huỷ theo yêu cầu trong lúc nén audio.")
        if r.timed_out:
            raise RuntimeError(
                f"Nén audio thất bại: FFmpeg không tiến triển quá "
                f"{IM_LANG_FFMPEG_S:.0f} giây.")
        if r.returncode != 0:
            raise RuntimeError(f"Nén audio thất bại: {r.stderr.strip()[:200]}")
        return self.kiem_file_audio(tam, tham_chieu_s)[1]

    @staticmethod
    def _nguon_ngan_bat_thuong(do_dai, tham_chieu_s) -> bool:
        """``do_dai`` ngắn hơn ``tham_chieu_s`` quá mức bình thường (cùng ngưỡng mọi nơi)."""
        try:
            do_dai, tham_chieu_s = float(do_dai), float(tham_chieu_s or 0)
        except (TypeError, ValueError):
            return False
        return tham_chieu_s > 0 and do_dai + 1.0 < TY_LE_DO_DAI_TOI_THIEU * tham_chieu_s

    def _duong_dan_hong(self, path: str, vid: str = "") -> str:
        """Tên trong ``_hong/``: ``<thời điểm>_<tên gốc>``; quá dài thì rút còn mã video."""
        moc = datetime.now().strftime("%y%m%d-%H%M%S")
        ten = os.path.basename(path)
        dich = os.path.join(self.thu_muc_hong, f"{moc}_{ten}")
        if len(dich) >= DO_DAI_DUONG_DAN_TOI_DA:
            dich = os.path.join(self.thu_muc_hong,
                                f"{moc}_{vid or uuid.uuid4().hex[:11]}{os.path.splitext(ten)[1]}")
        return dich

    def _luu_vao_hong(self, path: str, vid: str = "", *, giu_ban_goc: bool) -> str:
        """Đưa một file nghi hỏng vào ``_hong/`` — KHÔNG BAO GIỜ xoá, không ghi đè.

        ``giu_ban_goc=True``: chỉ tạo bản thứ hai (hard link, hoặc bản chép khi ổ không hỗ
        trợ link) để người gọi còn hoàn nguyên được nếu bước sau thất bại.
        ``giu_ban_goc=False``: dời hẳn (``os.rename`` không ghi đè file có sẵn).
        """
        os.makedirs(self.thu_muc_hong, exist_ok=True)
        goc = self._duong_dan_hong(path, vid)
        than, duoi = os.path.splitext(goc)
        for i in range(1, 100):
            dich = goc if i == 1 else f"{than}_{i}{duoi}"
            if os.path.exists(dich):
                continue
            try:
                if not giu_ban_goc:
                    os.rename(path, dich)
                else:
                    try:
                        os.link(path, dich)
                    except FileExistsError:
                        raise
                    except OSError:
                        da_tao = False
                        try:
                            with open(path, "rb") as nguon, open(dich, "xb") as ra:
                                da_tao = True
                                shutil.copyfileobj(nguon, ra, 1024 * 1024)
                            shutil.copystat(path, dich)
                        except BaseException:
                            # Chép hỏng giữa chừng (đầy ổ…): bản dở là của CHÍNH lượt này
                            # ("xb" vừa tạo) — gỡ đi, đừng để `_hong` giữ file cụt
                            # trông như bản cách ly thật (phản biện vòng 2).
                            if da_tao:
                                with contextlib.suppress(OSError):
                                    os.remove(dich)
                            raise
                return dich
            except FileExistsError:
                continue
        raise OSError(f"Không tạo được tên mới trong {THU_MUC_HONG} cho "
                      f"{os.path.basename(path)}")

    def _la_ban_da_xac_nhan(self, path: str, tham_chieu_s: float = 0.0) -> bool:
        """File ở ``path`` có dấu xác nhận khớp (đọc metadata MỚI NHẤT)?"""
        meta = self.load_meta()
        if not isinstance(meta, dict):
            return False
        ten = os.path.basename(path)
        khoa = ten if ten in meta else self._chi_muc_meta_theo_ten(meta).get(
            os.path.normcase(ten))
        return self._da_xac_nhan(path, meta.get(khoa) if khoa else None, tham_chieu_s)

    def _tai_va_nen(self, v: VideoInfo, cancel_event=None) -> tuple:
        """Tải bestaudio rồi nén sang opus mono.

        Trả về ``(duong_dan, VideoInfo đã bổ sung)``. Lượt tải này vốn đã trích xuất
        đầy đủ trang video, nên ``upload_date``/``duration``/``title`` thật lấy được
        **miễn phí** — không tốn thêm request nào. Đây là lý do ``sync()`` không cần
        bật ``list_channel(lay_ngay_dang=True)``.

        Nén vào file TẠM riêng của lượt chạy, kiểm (mã thoát, ffprobe, độ dài so với
        nguồn) rồi mới ``os.replace`` sang tên cuối trong kho. Trước đây FFmpeg ghi
        thẳng vào tên cuối: nén lỗi để lại file rỗng/dở mang đúng mã video, và lượt
        sync sau coi là đã tải xong vĩnh viễn (audit TCP-10). Lỗi hay huỷ thì chỉ dọn
        đúng file tạm của lượt này; file nguồn tốt trong kho không bị đụng.
        """
        os.makedirs(self.tmp_dir, exist_ok=True)

        def tai_nguon(vid: str, thu_muc: str) -> tuple:
            os.makedirs(thu_muc, exist_ok=True)
            info = self._tai_thu_tung_client(v.url, dict(
                format="ba/b",
                outtmpl=os.path.join(thu_muc, "%(id)s.%(ext)s"),
                noplaylist=True, continuedl=True, retries=10, fragment_retries=10,
            ))
            tho = [os.path.join(thu_muc, f) for f in os.listdir(thu_muc)
                   if f.startswith(vid + ".") and not f.endswith((".part", ".ytdl"))
                   and not f.endswith(DUOI_DANG_NEN)]
            if not tho:
                raise RuntimeError("Tải thất bại (không thấy file sau khi tải).")
            return info, tho[0]

        def do_dai_nguon_tieng(path: str) -> Optional[float]:
            # Đo LUỒNG TIẾNG: client `android` tải video tiến trình, hình dài hơn tiếng thì
            # `do_dai_media` (luồng dài nhất) báo độ dài của hình (phản biện vòng 3).
            return do_dai_luong_tieng(path) or do_dai_media(path)

        info, nguon = tai_nguon(v.id, self.tmp_dir)
        v = bo_sung_video_info(v, info if isinstance(info, Mapping) else None)

        dich = os.path.join(self.dest, self._ten_file(v))
        tam = os.path.join(self.tmp_dir, f"{v.id}.{uuid.uuid4().hex[:8]}{DUOI_DANG_NEN}")
        # Huỷ được giữa chừng và dừng khi FFmpeg IM LẶNG quá lâu (audit TCP-15).
        if cancel_event is None:
            cancel_event = getattr(self, "_huy_luot_sync", None)
        da_cong_bo = False
        ngan_that_su = False
        try:
            tham_chieu = v.duration if v.duration and v.duration > 0 else (
                do_dai_nguon_tieng(nguon) or 0.0)
            ly_do = self._nen_va_kiem(nguon, tam, tham_chieu, cancel_event)
            do_dai_nguon = (do_dai_nguon_tieng(nguon)
                            if ly_do and v.duration and v.duration > 0 else None)
            if do_dai_nguon and self._nguon_ngan_bat_thuong(do_dai_nguon, v.duration):
                # Chính NGUỒN tải về đã ngắn hơn lengthSeconds bất thường. Chỉ lần tải ĐỘC
                # LẬP thứ hai mới phân biệt được tải đứt (độ dài thay đổi) với âm thanh
                # YouTube thật sự ngắn hơn (lần nào cũng như nhau) — trước đây ca sau thành
                # lỗi + tải lại ở MỌI lượt đồng bộ, không bao giờ dứt (phản biện vòng 2).
                with contextlib.suppress(OSError):
                    os.remove(nguon)
                with contextlib.suppress(OSError):
                    os.remove(tam)
                # Tải lại vào thư mục MỚI: nguồn cũ có thể không xoá được (phần mềm khác
                # đang giữ) và yt-dlp thấy file đích đã có thì KHÔNG tải lại — "lần tải thứ
                # hai" khi đó chính là file cũ, và file cụt được đóng dấu "ngắn thật" (vòng 3).
                _, nguon = tai_nguon(
                    v.id, os.path.join(self.tmp_dir, f"lan2_{uuid.uuid4().hex[:8]}"))
                do_dai_lai = do_dai_nguon_tieng(nguon)
                ngan_that_su = (do_dai_lai is not None
                                and abs(do_dai_lai - do_dai_nguon) <= DUNG_SAI_TAI_LAI_S)
                if ngan_that_su:
                    # lengthSeconds không còn là thước đo: bản nén phải đủ dài so với NGUỒN.
                    tham_chieu = do_dai_lai
                ly_do = self._nen_va_kiem(nguon, tam, tham_chieu, cancel_event)
            if ly_do:
                raise RuntimeError(
                    f"Nén audio thất bại: bản nén không qua kiểm tra ({ly_do}).")
            if os.path.exists(dich) and self._la_ban_da_xac_nhan(dich, tham_chieu):
                # Một lượt khác vừa đặt bản ĐÃ KIỂM vào đúng tên trong lúc lượt này đang
                # tải: giữ bản đó, bỏ bản của lượt này — không cách ly nhầm file tốt.
                pass
            else:
                # File cùng tên đang có (nếu có) chưa được xác nhận: giữ một bản trong
                # `_hong/` TRƯỚC, rồi mới thay. Thay thất bại thì gỡ bản phụ đó — bản gốc
                # vẫn nằm nguyên tại chỗ, lượt sau làm lại được (không kẹt "mất file").
                ban_hong = (self._luu_vao_hong(dich, v.id, giu_ban_goc=True)
                            if os.path.exists(dich) else "")
                try:
                    _dat_vao_kho(tam, dich)
                except OSError as e:
                    if ban_hong:
                        with contextlib.suppress(OSError):
                            os.remove(ban_hong)
                    raise RuntimeError(
                        f"Không đặt được file vào kho ({type(e).__name__}: {e}). Bản cũ "
                        "giữ nguyên tại chỗ; lần đồng bộ sau sẽ thử lại.") from e
                da_cong_bo = True
                if ban_hong:
                    self._da_cach_ly.append(os.path.basename(dich))
            if ngan_that_su:
                self._ngan_hon_youtube.add(v.id)
        finally:
            if not da_cong_bo:
                with contextlib.suppress(OSError):
                    os.remove(tam)

        with contextlib.suppress(OSError):
            os.remove(nguon)
        return dich, v

    # ---------- đồng bộ cả kênh ----------


    def sync(self, url: str, limit: Optional[int] = None,
             progress: Optional[Callable] = None,
             cancel_check: Optional[Callable] = None) -> dict:
        """
        Đồng bộ kênh: chỉ tải video CHƯA có bản đã xác nhận trong kho.
        Trả về {'tong', 'moi', 'bo_qua', 'loi', 'thu_muc', 'da_huy',
        'nghi_hong', 'da_cach_ly', 'da_doi_soat'}.

        Một kho chỉ có một lượt đồng bộ tại một thời điểm (``TEN_KHOA_DONG_BO``); lượt
        thứ hai ném ``DangChayRoi`` ngay, không đụng gì.
        """
        with KhoaTienTrinh(os.path.join(self.dest, TEN_KHOA_DONG_BO),
                           "đồng bộ kênh vào kho này"):
            return self._sync_da_khoa(url, limit, progress, cancel_check)

    def _sync_da_khoa(self, url: str, limit: Optional[int],
                      progress: Optional[Callable],
                      cancel_check: Optional[Callable]) -> dict:
        def bao(pct, msg):
            if progress:
                progress(max(0.0, min(1.0, pct)), msg)

        bao(0.0, "Đang lấy danh sách video của kênh...")
        ds, da_gap = [], set()
        # Danh sách phát có thể lặp CÙNG một video: tải hai lần thì lần sau từng cách ly
        # nhầm bản tốt của lần trước.
        for v in self.list_channel(url, limit, cau_hinh_mang=self.cau_hinh_mang) or []:
            if v.id not in da_gap:
                da_gap.add(v.id)
                ds.append(v)
        if not ds:
            raise RuntimeError("Không lấy được video nào từ kênh. Kiểm tra lại link kênh.")

        self._don_tam_cu()
        self._da_cach_ly = []
        # Dấu "âm thanh ngắn thật" chỉ có giá trị trong lượt vừa xác nhận nó — không rò sang
        # lượt sau trên cùng đối tượng (phản biện vòng 3).
        self._ngan_hon_youtube = set()
        loi: list = []
        kq = {"tong": len(ds), "moi": 0, "bo_qua": 0, "loi": loi, "thu_muc": self.dest,
              "da_huy": False, "nghi_hong": [], "da_cach_ly": [], "da_doi_soat": 0}
        # Cờ huỷ của CẢ lượt sync, để lệnh nén FFmpeg đang chạy cũng dừng được.
        self._huy_luot_sync = _CoHuyTuHam(cancel_check)
        try:
            # File trên đĩa chỉ tính là "đã có" khi đã được xác nhận (audit TCP-10). Trước
            # đây cứ có tên `[ID].opus` là bỏ qua — kể cả file 0 byte do lần nén lỗi để lại.
            try:
                tep = self.kiem_tep_tren_dia(
                    {v.id: v.duration for v in ds},
                    progress=lambda i, n, ten: bao(
                        0.01, f"Kiểm file trên đĩa {i}/{n}: {ten[:50]}"),
                    cancel_check=cancel_check,
                )
            except DaHuyDongBo:
                kq["da_huy"] = True
                return kq
            nghi = tep["nghi_hong"]
            kq["nghi_hong"] = [f"{ten}: {ly_do}" for ds_tep in nghi.values()
                               for ten, ly_do in ds_tep]
            for vid in set(nghi) & set(tep["hop_le"]):
                # Cùng mã đã có bản tốt: bản nghi hỏng chỉ là bản thừa — cách ly ngay.
                for ten, _ in nghi[vid]:
                    try:
                        self._luu_vao_hong(os.path.join(self.dest, ten), vid,
                                           giu_ban_goc=False)
                        self._da_cach_ly.append(ten)
                    except OSError as e:
                        loi.append(f"Không chuyển được {ten} vào {THU_MUC_HONG}: {e}")
            try:
                kq["da_doi_soat"] = self._doi_soat(tep["can_doi_soat"])
            except Exception as e:  # noqa: BLE001 — không được chặn cả lượt tải
                loi.append(f"Không đối soát được metadata tại chỗ cho "
                           f"{len(tep['can_doi_soat'])} file có sẵn: {e}")
            hop_le = set(tep["hop_le"])
            # Archive chỉ là sổ tay: mã có trong archive mà file trên đĩa nghi hỏng thì
            # vẫn phải tải lại. Mã có trong archive mà KHÔNG có file thì giữ nguyên ý nghĩa
            # cũ (người dùng có thể đã chủ ý xoá).
            da_co = (self.done_ids() - (set(nghi) - hop_le)) | hop_le
            can_tai = [v for v in ds if v.id not in da_co]
            kq["bo_qua"] = len(ds) - len(can_tai)
            bao(0.02, f"Kênh có {len(ds)} video — {len(can_tai)} video mới cần tải.")

            for i, v in enumerate(can_tai):
                if cancel_check and cancel_check():
                    kq["da_huy"] = True
                    break
                bao(0.02 + 0.96 * i / max(1, len(can_tai)),
                    f"[{i+1}/{len(can_tai)}] {v.title[:60]}")
                try:
                    f, v = self._tai_va_nen(v)
                    ngay = valid_upload_date(v.upload_date)
                    do_dai = do_dai_media(f)
                    entry = {
                        "id": v.id, "title": v.title,
                        # upload_date giữ tên cũ để bản đọc metadata cũ vẫn chạy;
                        # publication_date là trường chính tắc kèm nguồn gốc.
                        "upload_date": ngay,
                        "publication_date": ngay,
                        "publication_date_source": v.publication_source,
                        # `duration` là lengthSeconds của YouTube (đã làm tròn);
                        # `duration_media` là độ dài đo thẳng từ file vừa tạo, dùng cho
                        # hiển thị vì trình phát cắt phần lẻ chứ không làm tròn.
                        "duration": v.duration,
                        "duration_media": do_dai,
                        "url": f"https://youtu.be/{v.id}",
                        # Dấu xác nhận: file đúng kích thước này đã qua kiểm tra lúc nén.
                        "xac_nhan_tep": self._dau_xac_nhan(
                            f, do_dai, ngan_hon_youtube=v.id in self._ngan_hon_youtube),
                    }
                    # Chỉ ghi entry của video vừa tải, gộp vào bản mới nhất — không ghi
                    # đè cả file bằng bản đọc từ đầu lượt sync (audit TCP-03).
                    # Thứ tự: file đã kiểm → metadata → archive. Đứt giữa chừng thì lượt
                    # sau đối soát tại chỗ được (`_doi_soat`), không phải tải lại.
                    self.cap_nhat_meta({os.path.basename(f): entry}, thay_ca_entry=True)
                    self._mark_done(v.id)
                    kq["moi"] += 1
                    for ten_cu, _ in nghi.get(v.id, []):
                        cu = os.path.join(self.dest, ten_cu)
                        if os.path.exists(cu) and os.path.normcase(cu) != os.path.normcase(f):
                            try:
                                self._luu_vao_hong(cu, v.id, giu_ban_goc=False)
                                self._da_cach_ly.append(ten_cu)
                            except OSError as e:
                                loi.append(f"Không chuyển được {ten_cu} vào "
                                           f"{THU_MUC_HONG}: {e}")
                except DaHuyDongBo:
                    kq["da_huy"] = True
                    break
                except Exception as e:  # noqa: BLE001
                    # giai_thich_loi: bỏ mã màu ANSI của yt-dlp (Streamlit hiện ra rác)
                    # và nói rõ trường hợp nào là YouTube chặn chứ không phải tool hỏng.
                    loi.append(f"{v.title[:40]}: "
                               f"{giai_thich_loi(e, self.cau_hinh_mang.co_cookie)}")
        finally:
            kq["da_cach_ly"] = list(self._da_cach_ly)
            # Chỉ dọn thư mục tạm CỦA LƯỢT NÀY.
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            with contextlib.suppress(OSError):
                os.rmdir(self.tmp_goc)          # chỉ xoá được khi đã rỗng
        bao(1.0, "Đồng bộ xong.")
        return kq

    def _don_tam_cu(self) -> None:
        """Dọn thư mục tạm của các lượt đã chết từ lâu (máy tắt giữa chừng).

        Không đụng thư mục tạm còn mới: có thể là của một lượt khác đang chạy.
        """
        if not os.path.isdir(self.tmp_goc):
            return
        han = time.time() - HAN_DON_TAM_CU_S
        for ten in os.listdir(self.tmp_goc):
            p = os.path.join(self.tmp_goc, ten)
            if os.path.normcase(p) == os.path.normcase(self.tmp_dir):
                continue
            with contextlib.suppress(OSError):
                if os.path.getmtime(p) < han:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)

    @staticmethod
    def _dau_xac_nhan(path: str, do_dai: Optional[float], *,
                      ngan_hon_youtube: bool = False) -> dict:
        dau = {"kich_thuoc": os.path.getsize(path)}
        if do_dai:
            dau["do_dai"] = round(float(do_dai), 3)
        if ngan_hon_youtube:
            # Đã tải lại và nhận cùng độ dài: âm thanh YouTube ngắn hơn lengthSeconds THẬT.
            dau["am_thanh_ngan_hon_youtube"] = True
        return dau

    def _doi_soat(self, can_doi_soat: Mapping) -> int:
        """File đã kiểm đạt mà chưa có dấu xác nhận (đứt sau khi đặt file, kho cũ, hoặc
        chép tay vào kho): bổ sung TẠI CHỖ từ tên file + số đo, không gọi YouTube.

        Chỉ đóng dấu ``xac_nhan_tep`` khi có độ dài THAM CHIẾU để so: không có thì một file
        bị cắt cụt mà ffprobe vẫn đọc được sẽ được tin vĩnh viễn (phản biện TCP-10).
        """
        if not can_doi_soat:
            return 0
        viec = {}
        for vid, (ten, do_dai, *them) in can_doi_soat.items():
            khoa = them[0] if them else None
            co_tham_chieu = bool(them[1]) if len(them) > 1 else True
            with contextlib.suppress(OSError):
                viec[vid] = (ten, khoa, do_dai, co_tham_chieu,
                             self._dau_xac_nhan(os.path.join(self.dest, ten), do_dai))

        def gop(meta: dict) -> int:
            so = 0
            theo_ten = self._chi_muc_meta_theo_ten(meta)
            for vid, (ten, khoa, do_dai, co_tham_chieu, xac_nhan) in viec.items():
                if khoa not in meta:
                    khoa = ten if ten in meta else theo_ten.get(os.path.normcase(ten))
                muc = meta.get(khoa) if khoa else None
                truoc = json.dumps(muc, sort_keys=True, ensure_ascii=False)
                if not isinstance(muc, dict):
                    phan = filename_fallback_parts(ten)
                    muc = meta[ten] = {
                        "id": vid,
                        "title": str(phan.get("title") or ""),
                        "url": str(phan.get("url") or f"https://youtu.be/{vid}"),
                        "upload_date": str(phan.get("upload_date") or ""),
                        "duration": None,
                    }
                if co_tham_chieu:
                    # Chưa có tham chiếu bên ngoài thì file chưa được kiểm đủ: không ghi số
                    # đo của nó thành metadata để khỏi bị dùng làm "tham chiếu" về sau.
                    if not _so_duong(muc.get("duration_media")) and do_dai:
                        muc["duration_media"] = round(float(do_dai), 3)
                    muc["xac_nhan_tep"] = xac_nhan
                # Chỉ đếm mục THẬT SỰ đổi: file không có tham chiếu bị kiểm lại mỗi lượt mà
                # không đổi gì, báo "đã bổ sung N file" mãi là sai (phản biện vòng 3).
                if json.dumps(muc, sort_keys=True, ensure_ascii=False) != truoc:
                    so += 1
            return so

        so = cap_nhat_json(self.meta_file, gop, mac_dinh={})
        self._mark_done_nhieu(list(viec))
        return so

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
            m = RE_ID_TEN_FILE.search(f)
            if m:
                kq[m.group(1)] = f
        return kq

    def kiem_tep_tren_dia(self, thoi_luong_theo_id: Optional[Mapping] = None, *,
                          progress: Optional[Callable] = None,
                          cancel_check: Optional[Callable] = None) -> dict:
        """Phân loại file audio ở gốc kho — CHỈ ĐỌC, không ghi/xoá gì (audit TCP-10).

        * ``hop_le``: ``{id: tên file}`` — đã xác nhận, hoặc vừa kiểm đạt;
        * ``can_doi_soat``: ``{id: (tên file, độ dài, khoá metadata, có_tham_chiếu)}`` —
          kiểm đạt nhưng chưa có dấu xác nhận: ``sync`` bổ sung tại chỗ;
        * ``nghi_hong``: ``{id: [(tên file, lý do)]}`` — rỗng, ffprobe không đọc được, hoặc
          ngắn bất thường so với độ dài tham chiếu.

        "Đã xác nhận" CHỈ là dấu ``xac_nhan_tep`` khớp kích thước file (và không ngắn bất
        thường so với tham chiếu). Không tin "có trong archive + có trong metadata": hai sổ
        đó do nút «Dựng lại danh sách đã tải» và «Vá metadata» tạo được cho cả file hỏng.
        File chưa có dấu (kho cũ) bị ffprobe MỘT lần rồi được đóng dấu; các lượt sau không
        probe lại. Độ dài tham chiếu: danh sách kênh, rồi ``duration`` trong metadata — không
        bao giờ là số đo của chính file. ``progress(i, n, tên)`` báo từng file phải kiểm; ``cancel_check``
        được hỏi trước mỗi lần kiểm (ném ``DaHuyDongBo``).
        """
        kq = {"hop_le": {}, "can_doi_soat": {}, "nghi_hong": {}}
        if not os.path.isdir(self.dest):
            return kq
        tham_chieu_kenh = dict(thoi_luong_theo_id or {})
        meta = self.load_meta()
        if not isinstance(meta, dict):
            meta = {}
        theo_ten = self._chi_muc_meta_theo_ten(meta)
        can_kiem = []
        for f in sorted(os.listdir(self.dest)):
            if not f.lower().endswith("." + AUDIO_EXT):
                continue
            path = os.path.join(self.dest, f)
            m = RE_ID_TEN_FILE.search(f)
            if not m or not os.path.isfile(path):
                continue
            vid = m.group(1)
            khoa = f if f in meta else theo_ten.get(os.path.normcase(f))
            muc = meta.get(khoa) if khoa else None
            # Tham chiếu chỉ lấy từ nguồn BÊN NGOÀI file: danh sách kênh, rồi `duration`
            # (lengthSeconds) trong metadata. KHÔNG dùng `duration_media` — số đo của chính
            # file đó (đối soát, «kiem_thoi_luong --sua» ghi ra): file cụt so với chính nó
            # thì luôn đạt, rồi được đóng dấu tin cậy vĩnh viễn (phản biện vòng 2).
            tham_chieu = _so_duong(tham_chieu_kenh.get(vid))
            if not tham_chieu and isinstance(muc, Mapping):
                tham_chieu = _so_duong(muc.get("duration"))
            if self._da_xac_nhan(path, muc, tham_chieu):
                kq["hop_le"][vid] = f
            else:
                can_kiem.append((f, path, vid, khoa, tham_chieu))
        for i, (f, path, vid, khoa, tham_chieu) in enumerate(can_kiem, 1):
            if cancel_check and cancel_check():
                raise DaHuyDongBo("Đã huỷ theo yêu cầu trong lúc kiểm file trên đĩa.")
            if progress:
                progress(i, len(can_kiem), f)
            do_dai, ly_do = self.kiem_file_audio(path, tham_chieu)
            if ly_do:
                kq["nghi_hong"].setdefault(vid, []).append((f, ly_do))
            else:
                kq["hop_le"][vid] = f
                kq["can_doi_soat"][vid] = (f, do_dai, khoa, tham_chieu > 0)
        return kq

    @staticmethod
    def _chi_muc_meta_theo_ten(meta: Mapping) -> dict:
        """``normcase(tên file) -> khoá``: kho cũ có thể dùng ĐƯỜNG DẪN làm khoá
        (resolver vẫn đọc được). Không tra kiểu này thì file của kho đó bị coi là lạ và
        lượt đối soát đẻ thêm một entry khoá theo tên file, nghèo dữ liệu hơn bản cũ."""
        chi_muc: dict = {}
        for khoa in meta:
            if isinstance(khoa, str):
                chi_muc.setdefault(os.path.normcase(basename_compatible(khoa)), khoa)
        return chi_muc

    @staticmethod
    def _da_xac_nhan(path: str, muc, tham_chieu_s: float = 0.0) -> bool:
        """Dấu ``xac_nhan_tep`` khớp kích thước file và không ngắn bất thường."""
        dau = muc.get("xac_nhan_tep") if isinstance(muc, Mapping) else None
        if not isinstance(dau, Mapping):
            return False
        try:
            if int(dau.get("kich_thuoc")) != os.path.getsize(path):
                return False
        except (TypeError, ValueError, OSError):
            return False
        do_dai = _so_duong(dau.get("do_dai"))
        if dau.get("am_thanh_ngan_hon_youtube"):
            # Độ ngắn đã được chứng minh bằng hai lần tải: lengthSeconds không còn là thước
            # đo. Kích thước khớp dấu là đủ — file khác đi thì đã bị loại ở trên.
            return bool(do_dai)
        return not (do_dai and ChannelSync._nguon_ngan_bat_thuong(do_dai, tham_chieu_s))

    def sua_archive(self) -> dict:
        """
        Dựng lại downloaded.txt từ các file THỰC SỰ đang có trên đĩa.
        Dùng khi: tải bị đứt giữa chừng, archive mất/hỏng, hoặc file bị xoá thủ công.
        An toàn tuyệt đối — chỉ ghi lại file text, không đụng vào file audio.
        """
        tren_dia = self.quet_id_tren_dia()
        # Tên tạm DUY NHẤT + khoá thư mục: hai process sửa archive cùng lúc không còn
        # dùng chung một file `.tmp` (cùng kiểu lỗi với audit TCP-03).
        with khoa_json(self.archive):
            cu = self.done_ids()
            file_tam = f"{self.archive}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
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
        ds = self.list_channel(url, limit, cau_hinh_mang=self.cau_hinh_mang)
        tren_dia = self.quet_id_tren_dia()
        # File nghi hỏng tính là CÒN THIẾU — lượt đồng bộ sẽ tải lại nó (audit TCP-10).
        tep = self.kiem_tep_tren_dia({v.id: v.duration for v in ds})
        thieu = [v for v in ds if v.id not in tep["hop_le"]]
        return {"tong_kenh": len(ds), "co_roi": len(ds) - len(thieu),
                "thieu": thieu, "thua": [f for i, f in tren_dia.items()
                                         if i not in {v.id for v in ds}],
                "nghi_hong": [f"{ten}: {ly_do}" for ds_tep in tep["nghi_hong"].values()
                              for ten, ly_do in ds_tep]}

    # ---------- dung lượng ----------

    def thong_ke(self) -> dict:
        files = [f for f in os.listdir(self.dest)
                 if f.lower().endswith("." + AUDIO_EXT)] if os.path.isdir(self.dest) else []
        tong = sum(os.path.getsize(os.path.join(self.dest, f)) for f in files)
        return {"so_file": len(files), "dung_luong_mb": tong / 1024 / 1024}
