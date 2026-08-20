# -*- coding: utf-8 -*-
r"""
danh_sach_video.py — Kiểm kê một kho clip gốc: liệt kê mọi file audio đã tải về
kèm TÊN VIDEO THẬT trên YouTube, rồi ghi đè danh sách đó lên một trang tính riêng.

Ba lời hứa của module này:

 1. **Chạy 100% offline.** Chỉ ``os.listdir`` + đọc ``clips_meta.json``. Không gọi
    mạng, không yt-dlp, không đụng vào database vân tay.
 2. **Chỉ đọc.** Không ghi, không đổi tên, không tạo file nào trong thư mục kho —
    kể cả khi ``clips_meta.json`` hỏng. Vì thế dùng
    :func:`clip_metadata.load_metadata_strict` chứ KHÔNG dùng
    ``luu_tru.doc_json_an_toan`` (hàm sau gặp file hỏng sẽ đổi tên file gốc thành
    ``.hong.<timestamp>``).
 3. **Tên video lấy từ metadata, không bao giờ parse tên file.**
    ``channel.lam_sach_ten()`` thay ``< > : " / \ | ? *`` bằng ``_`` rồi cắt còn 80
    ký tự, nên tên file là bản đã hỏng không phục hồi được. Ví dụ thật:
    file ``00000000 - SML Movie_ The World Cup! [gRZah-YY0FM].opus`` nhưng tên
    đúng trên YouTube là ``SML Movie: The World Cup!`` (dấu HAI CHẤM).

Không import ``streamlit`` và không import ``engine`` — tầng logic thuần, gọi được
từ giao diện nào cũng được.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from channel import AUDIO_EXT
from clip_metadata import (
    ClipMetadataResolver,
    ResolvedClipMetadata,
    filename_fallback_parts,
    load_metadata_strict,
)
from sheets import TEN_FILE_KEY, SheetsExporter

TEN_FILE_META = "clips_meta.json"

# Đúng hai cột đã chốt với người dùng. Thêm cột là đổi hợp đồng — đừng tự ý.
HEADER: list[str] = ["STT", "Tên video"]

TIEN_TO_TRANG_TINH = "DanhSachVideo_"
GIOI_HAN_TEN_TRANG_TINH = 100
# Ký tự Google Sheets cấm trong tên trang tính. Dấu nháy đơn cũng phải thay vì nó
# phải được nhân đôi trong ký hiệu A1.
_RE_CAM_TRANG_TINH = re.compile(r"""[\[\]:\\/?*']""")
# Dấu vết của một tên ĐÃ được gắn hậu tố băm. Tên nào trông giống vậy thì cũng phải
# gắn băm, nếu không hai không gian tên chồng lên nhau — xem ``ten_trang_tinh``.
_RE_DA_CO_BAM = re.compile(r"_[0-9a-f]{6}$")

GHI_CHU_SUY_TU_TEN_FILE = (
    "Chưa có trong clips_meta.json — tên suy từ tên file, có thể mất dấu câu "
    "và bị cắt ở 80 ký tự."
)
GHI_CHU_TITLE_RONG = (
    "Có trong clips_meta.json nhưng trường «title» để trống — tên suy từ tên file, "
    "có thể mất dấu câu và bị cắt ở 80 ký tự."
)
GHI_CHU_MAU_THUAN_DANH_TINH = (
    "Tên lấy từ clips_meta.json (khoá khớp đúng tên file) nhưng mã video trong "
    "«id»/«url» không khớp mã ở cuối tên file — mở youtu.be/<mã 11 ký tự trong "
    "ngoặc vuông ở cuối tên file> để xem tiêu đề thật."
)
GHI_CHU_MUC_HONG = (
    "Mục trong clips_meta.json bị hỏng định dạng nên không dùng được — tên đang "
    "suy từ tên file."
)
GHI_CHU_KHONG_XAC_DINH = (
    "Không tra được tên video — tên file không chứa mã video 11 ký tự, "
    "hoặc metadata mâu thuẫn."
)

# Đuôi media KHÁC .opus, để phân biệt «kho rỗng thật» với «kho chép tay từ video
# gốc». Giữ bản sao cục bộ thay vì import `engine.MEDIA_EXTS`: module này cố ý
# không kéo 3300 dòng engine vào chỉ để lấy một tập hằng.
# Đổi mã `invalid_field:<mã>` của clip_metadata sang (tên trường THẬT, cách sửa).
_TRUONG_HONG: dict[str, tuple[str, str]] = {
    "invalid_title": ("title", "sai kiểu dữ liệu — phải là một chuỗi"),
    "invalid_publication_date": (
        "publication_date", "sai định dạng ngày — phải là 8 chữ số YYYYMMDD"),
    "invalid_upload_date": (
        "upload_date", "sai định dạng ngày — phải là 8 chữ số YYYYMMDD"),
    "invalid_url": ("url", "không phải link YouTube hợp lệ"),
    "invalid_id": ("id", "không chứa mã video 11 ký tự"),
    "invalid_duration": (
        "duration", "không phải số dương — dùng dấu chấm thập phân, không dùng dấu phẩy"),
    "invalid_duration_media": (
        "duration_media",
        "không phải số dương — dùng dấu chấm thập phân, không dùng dấu phẩy"),
}

DUOI_MEDIA_KHAC = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m4v",
    ".mpg", ".mpeg", ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac",
})


class LoiKho(Exception):
    """Kho không dùng được: chưa đặt thư mục, thư mục biến mất, không đọc được đĩa.

    Thông điệp LUÔN là câu tiếng Việt hoàn chỉnh, hiển thị thẳng lên giao diện được.
    Tách riêng khỏi ``Exception`` thường để giao diện phân biệt «lỗi người dùng sửa
    được» với «lỗi lập trình cần hiện nguyên văn».

    KHÔNG ném cho dữ liệu bẩn (clips_meta.json hỏng/trùng khoá/rỗng): những ca đó
    đi vào ``KetQuaKho.canh_bao`` để người dùng vẫn xem được danh sách.
    """


@dataclass(frozen=True)
class DongVideo:
    """Một dòng của bảng danh sách.

    ``ten_video``  tên hiển thị, đã sẵn sàng đẩy lên Sheet.
    ``ten_file``   tên file .opus trên đĩa, giữ để người dùng đối chiếu khi nghi ngờ.
    ``chinh_xac``  True khi tên lấy từ trường ``title`` của một mục THẬT trong
                   clips_meta.json — tức tên đúng như trên YouTube. False khi phải
                   suy từ tên file (đã bị ``channel.lam_sach_ten`` thay ký tự cấm
                   bằng ``_`` và cắt còn 80 ký tự).
    ``ghi_chu``    rỗng khi không có gì bất thường; ngược lại là lý do tiếng Việt.
    """

    stt: int
    ten_video: str
    ten_file: str
    chinh_xac: bool
    ghi_chu: str = ""


@dataclass(frozen=True)
class KetQuaKho:
    """Kết quả kiểm kê MỘT kho tại MỘT thời điểm. Bất biến — chụp xong là đông cứng.

    ``canh_bao`` là các câu TIẾNG VIỆT ĐÃ DIỄN GIẢI, không phải mã lỗi thô: giao
    diện chỉ việc ``for cb in canh_bao: st.warning(cb)``.
    ``thoi_diem`` là HH:MM:SS lúc chụp; kho đổi sau đó thì bảng này đã cũ.
    """

    ten_kho: str
    thu_muc: str
    dong: tuple[DongVideo, ...] = ()
    canh_bao: tuple[str, ...] = ()
    thoi_diem: str = ""
    # Số file .mp4/.mkv/... tìm thấy trong kho. Chỉ dùng để phân biệt «kho rỗng
    # thật» với «kho chép tay từ video gốc» — hai ca cần lời khuyên trái ngược nhau.
    so_media_khac: int = 0

    @property
    def so_video(self) -> int:
        return len(self.dong)

    @property
    def so_chinh_xac(self) -> int:
        return sum(1 for d in self.dong if d.chinh_xac)

    @property
    def so_can_kiem_tra(self) -> int:
        return self.so_video - self.so_chinh_xac

    def dong_can_kiem_tra(self) -> tuple[DongVideo, ...]:
        """Các dòng chưa lấy được tên chính xác, để giao diện hiện riêng."""
        return tuple(d for d in self.dong if not d.chinh_xac)

    def tom_tat(self) -> str:
        """Một câu tiếng Việt cho ``st.success``. Không bao giờ ném lỗi.

        Cố ý KHÔNG hứa «chính xác 100%»: ``ChannelSync.seed_meta_tu_dia()`` có thể
        đã ghi title ĐÃ qua ``lam_sach_ten`` xuống clips_meta.json từ trước, và khi
        đó không còn dấu vết nào để phân biệt.
        """
        if not self.dong:
            if self.so_media_khac:
                return (f"Kho «{self.ten_kho}» có {self.so_media_khac} file "
                        f"video/audio khác nhưng chưa có file .opus nào — tab này "
                        f"chỉ liệt kê được kho tải bằng «Đồng bộ kênh gốc».")
            return f"Kho «{self.ten_kho}» chưa có file audio nào (.opus)."
        if self.so_can_kiem_tra == 0:
            return (f"Kho «{self.ten_kho}»: {self.so_video} video, đã lấy đúng tên "
                    f"từ metadata cho cả {self.so_video}.")
        return (f"Kho «{self.ten_kho}»: {self.so_video} video, "
                f"{self.so_chinh_xac} lấy đúng tên từ metadata, "
                f"{self.so_can_kiem_tra} phải suy từ tên file "
                f"(có thể thiếu dấu câu hoặc bị cắt ngắn).")


def _dich_canh_bao(ma: str, duong_dan_meta: str) -> str:
    """Dịch mã cảnh báo kỹ thuật của ``clip_metadata`` sang câu tiếng Việt.

    KHÔNG BAO GIỜ trả chuỗi rỗng: mã lạ vẫn phải hiện ra, nếu không giao diện sẽ
    im lặng đúng lúc dữ liệu có vấn đề.
    """
    ma = str(ma or "")
    if ma.startswith("metadata_duplicate_keys:"):
        so = ma.split(":", 1)[1]
        return (f"clips_meta.json có {so} khoá trùng nhau nên bị TỪ CHỐI TOÀN BỘ — "
                f"không lấy được tên video nào từ metadata. "
                f"Mở {duong_dan_meta} và xoá mục trùng.")
    if ma.startswith("metadata_read_error:"):
        loai = ma.split(":", 1)[1]
        return (f"Không đọc được clips_meta.json ({loai}). File có thể đã hỏng. "
                f"Đường dẫn: {duong_dan_meta}")
    if ma == "metadata_root_not_object":
        return ('clips_meta.json không phải một đối tượng JSON '
                '(phải có dạng {"tên file": {...}}).')
    if ma == "invalid_field:conflicting_ids_in_entry":
        # KHÔNG phải sai kiểu dữ liệu, và mục KHÔNG bị bỏ qua. Nói đúng như vậy —
        # câu cũ vu cho file lành lặn là hỏng và đẩy người dùng đi sửa nhầm chỗ.
        return ("Có mục trong clips_meta.json mà mã video ở «id»/«url» không khớp "
                "mã 11 ký tự tìm thấy trong tên file. Cũng xảy ra khi chính TIÊU ĐỀ "
                "chứa chuỗi 11 ký tự trong ngoặc vuông (ví dụ «[Compilation]») — "
                "khi đó dữ liệu vẫn đúng. Tên các clip liên quan vẫn lấy từ "
                "clips_meta.json nhưng được đánh dấu cần kiểm tra.")
    if ma.startswith("entry_not_object:"):
        ten_f = ma.split(":", 1)[1]
        return (f"Mục của file «{ten_f}» trong clips_meta.json bị hỏng định dạng: "
                f'nó phải có dạng {{"tên file": {{"id": …, "title": …}}}} nhưng hiện '
                f"là một giá trị đơn. Mở {duong_dan_meta} sửa lại mục đó, hoặc xoá "
                f"hẳn mục đó đi — tab này sẽ suy tên từ tên file.")
    if ma.startswith("invalid_field:"):
        # ``clip_metadata`` nối tiền tố «invalid_field:» vào các mã vốn ĐÃ mang
        # tiền tố «invalid_», nên phần đuôi KHÔNG phải tên trường thật. Người dùng
        # mở clips_meta.json tìm trường «invalid_publication_date» sẽ không bao giờ
        # thấy. Bảng tra dưới đây đổi về tên trường có thật + cách sửa.
        truong, mo_ta = _TRUONG_HONG.get(
            ma.split(":", 1)[1], ("", ""))
        if truong:
            return (f"Có mục trong clips_meta.json có trường «{truong}» {mo_ta} "
                    f"nên trường đó bị bỏ qua.")
    return f"Cảnh báo metadata: «{ma}» (file {duong_dan_meta})."


def _duyet_file(thu_muc: str, ten_kho: str) -> tuple[list[str], int]:
    """Duyệt kho, trả ``(danh sách đường dẫn .opus tương đối, số file media khác)``.

    Dùng ``os.walk`` chứ không ``os.listdir``: ``engine.liet_ke_media`` cũng dùng
    ``os.walk`` nên vân tay ĐƯỢC tạo cho cả thư mục con. Chỉ duyệt một tầng thì
    người gom clip theo năm/theo series sẽ thấy bảng thiếu hẳn một phần kho mà
    không có lấy một dòng cảnh báo.

    ``os.walk`` chỉ trả file thật trong danh sách thứ ba nên không cần
    ``os.path.isfile``: một THƯ MỤC CON tên ``gia.opus`` vẫn bị loại đúng, mà lại
    bỏ được một lệnh ``stat`` cho từng file (đáng kể trên ổ USB / ổ mạng).

    Raises:
        LoiKho: không đọc được thư mục.
    """
    duoi = "." + AUDIO_EXT
    files: list[str] = []
    so_media_khac = 0
    try:
        for goc, _thu_muc_con, ten_files in os.walk(thu_muc):
            for f in ten_files:
                thap = f.lower()
                if thap.endswith(duoi):
                    files.append(os.path.relpath(os.path.join(goc, f), thu_muc))
                elif os.path.splitext(thap)[1] in DUOI_MEDIA_KHAC:
                    so_media_khac += 1
    except OSError as e:
        raise LoiKho(f"Không đọc được thư mục kho «{ten_kho}»: {e}") from e
    return sorted(files), so_media_khac


def _ten_hien_thi(
    r: ResolvedClipMetadata,
    ten_file: str,
    tieu_de_goc: dict[str, str],
    muc_hong: frozenset[str] = frozenset(),
) -> tuple[str, bool, str]:
    """Chọn tên hiển thị cho một clip: ``(tên, có_chính_xác_không, ghi_chú)``.

    Mức 1 lấy title THẲNG từ mục gốc trong clips_meta.json chứ không lấy
    ``r.title``: ``_resolved_from_entry`` dựng ``title = entry.title or
    fallback["title"]``, tức ``r.title`` bị pha tên file đã làm sạch khi mục gốc có
    title rỗng.

    Mức 2 cứu ca resolver TỪ CHỐI dù khoá khớp y hệt tên file. Nguyên nhân thật:
    ``clip_metadata._ids_from_value`` quét ``[11 ký tự]`` trên TOÀN chuỗi, nên một
    tiêu đề chứa ``[Compilation]``, ``[Official_MV]``, ``[4K-REMASTER]``… (đều đúng
    11 ký tự) làm mục metadata trông như có hai mã video và bị gắn
    ``conflicting_ids_in_entry``. Không có mức này thì đúng những video đó bị đẩy
    lên Sheet bằng tên file đã làm sạch — mất dấu câu, cắt 80 ký tự — trong khi
    clips_meta.json có sẵn tên đúng. Khoá khớp y hệt là bằng chứng mạnh nhất về
    «title này thuộc file này», nên dùng title đó; nhưng vẫn ``chinh_xac=False``
    vì mâu thuẫn ``id`` có thể là mâu thuẫn THẬT, và người dùng cần được biết.

    Mức 2-3 CỐ Ý không dùng ``r.title``: với ``status="ambiguous"`` và
    ``basename_fallback``, ``r.title`` là NGUYÊN tên file kèm tiền tố ngày và đuôi
    ``.opus`` — đẩy thẳng lên Sheet sẽ ra dòng rất xấu.
    """
    if r.metadata_key:
        tieu_de = str(tieu_de_goc.get(r.metadata_key) or "").strip()
        if tieu_de:
            return tieu_de, True, ""

    if ten_file in tieu_de_goc:
        tieu_de = str(tieu_de_goc[ten_file] or "").strip()
        if tieu_de:
            return tieu_de, False, GHI_CHU_MAU_THUAN_DANH_TINH
        ghi_chu_lui = GHI_CHU_TITLE_RONG
    elif ten_file in muc_hong:
        # Mục CÓ trong file nhưng hỏng định dạng. Nói «chưa có trong clips_meta.json»
        # sẽ xui người dùng đi vá metadata (vô ích) thay vì mở file sửa mục hỏng.
        ghi_chu_lui = GHI_CHU_MUC_HONG
    else:
        ghi_chu_lui = GHI_CHU_SUY_TU_TEN_FILE

    phan = filename_fallback_parts(ten_file)
    tu_ten_file = str(phan.get("title") or "").strip()
    # Hai chốt chặn cho cùng một ca: khi regex không khớp,
    # ``_filename_fallback_parts`` trả ``title = name`` tức nguyên tên file KÈM đuôi.
    # So với bản ``.strip()`` vì ``basename_compatible`` đã cắt hai đầu — file tên
    # « test.opus» sẽ lọt nếu so với chuỗi thô.
    if (tu_ten_file and tu_ten_file != ten_file.strip()
            and not tu_ten_file.lower().endswith("." + AUDIO_EXT)):
        return tu_ten_file, False, ghi_chu_lui

    goc = os.path.splitext(ten_file)[0].strip()
    return (goc or ten_file), False, GHI_CHU_KHONG_XAC_DINH


def liet_ke_kho(
    ten_kho: str,
    thu_muc: str,
    *,
    progress: Optional[Callable[[float, str], None]] = None,
) -> KetQuaKho:
    r"""Liệt kê mọi file audio trong kho kèm TÊN VIDEO THẬT trên YouTube.

    Chạy hoàn toàn offline: chỉ ``os.walk`` + ``clip_metadata.load_metadata_strict``.
    KHÔNG ghi/đổi tên bất cứ file nào — kể cả khi ``clips_meta.json`` hỏng.

    CÁCH QUYẾT ĐỊNH một tên có phải tên YouTube thật hay không::

        chinh_xac = bool(r.metadata_key) and bool(tieu_de_goc.get(r.metadata_key, "").strip())

    nghĩa đen: «có một mục trong clips_meta.json đã khớp, VÀ chính mục đó cấp title
    không rỗng». ``metadata_key`` chỉ khác rỗng ở đúng một nhánh của ``resolve()`` là
    ``_resolved_from_entry``; mọi nhánh fallback/ambiguous đều đặt nó về rỗng.

    KHÔNG dùng ``r.status``: kho msa có 100/100 mục ``status="partial"`` (chỉ thiếu
    ``upload_date``) nhưng title hoàn toàn đúng — lọc theo status là mất trắng cả kho.

    KHÔNG dùng ``r.resolution_method``: ``_resolved_from_entry`` ép
    ``effective_method = "filename_fallback"`` khi BẤT KỲ trường nào trong
    ``{video_id, title, url, upload_date}`` rỗng mà tên file suy ra được. Chỉ cần
    metadata thiếu ngày đăng trong khi tên file có ngày thật là cả mục bị gắn cờ
    sai, dù title chuẩn.

    Raises:
        LoiKho: kho chưa gán thư mục, thư mục không tồn tại, hoặc không đọc được.
    """
    ten_kho = (ten_kho or "").strip()
    thu_muc = (thu_muc or "").strip().strip('"')

    if not thu_muc:
        raise LoiKho(
            f"Kho «{ten_kho}» chưa gán thư mục. Vào tab «Kho clip gốc» để đặt "
            f"đường dẫn thư mục chứa audio của kho này.")
    if not os.path.isdir(thu_muc):
        raise LoiKho(
            f"Không tìm thấy thư mục «{thu_muc}» của kho «{ten_kho}». "
            f"Ổ đĩa chưa cắm, hoặc thư mục đã bị xoá/đổi tên.")

    def bao(pct: float, msg: str) -> None:
        if progress:
            progress(pct, msg)

    bao(0.05, "Đang đọc metadata của kho...")
    duong_dan_meta = os.path.join(thu_muc, TEN_FILE_META)
    nguon = load_metadata_strict(duong_dan_meta, kind="live", priority=10)

    canh_bao: list[str] = []
    if not nguon.exists:
        # KHÔNG khuyên chạy «Vá metadata thiếu»: `Engine.va_metadata_thieu` chỉ ghi
        # vào snapshot data/metadata/, còn `ChannelSync.va_metadata` chỉ ghi
        # upload_date/duration — cả hai KHÔNG BAO GIỜ ghi `title`. Chỉ nút «Lấy lại
        # tên video thật cho kho này» mới sửa được.
        canh_bao.append(
            f"Kho «{ten_kho}» chưa có file clips_meta.json — mọi tên video đang "
            f"phải suy từ tên file nên có thể mất dấu câu và bị cắt ở 80 ký tự. "
            f"Bấm «🌐 Lấy lại tên video thật cho kho này» ở tab «Đồng bộ kênh gốc» "
            f"để hỏi YouTube tên đúng. (Lưu ý: chạy lại «Đồng bộ kênh gốc» KHÔNG "
            f"cứu được, vì nó chỉ ghi metadata cho video tải MỚI.)")
    muc_hong = frozenset(
        ma.split(":", 1)[1] for ma in nguon.warnings
        if ma.startswith("entry_not_object:"))
    for ma in nguon.warnings:
        canh_bao.append(_dich_canh_bao(ma, duong_dan_meta))
    if nguon.exists and not nguon.warnings and not nguon.entries:
        # Ca `{}`: exists=True, warnings=(), entries=() — im lặng hoàn toàn nếu
        # không có nhánh riêng này.
        canh_bao.append(
            f"clips_meta.json của kho «{ten_kho}» tồn tại nhưng RỖNG — chưa có "
            f"metadata nào. Tên video sẽ phải suy từ tên file.")

    res = ClipMetadataResolver([nguon], windows_semantics=(os.name == "nt"))
    tieu_de_goc = {e.key: e.title for e in nguon.entries}

    # `ambiguous_video_id` = NHIỀU FILE dùng chung một mã video. `resolve()` khớp
    # theo khoá nên vẫn trả tên bình thường cho từng file — vấn đề thật không phải
    # «tên sai» mà là MỘT video hiện thành nhiều dòng. Nói «đều bị đánh dấu cần
    # kiểm tra» là sai: người dùng sẽ mở bảng tìm mãi không thấy dòng nào bị đánh dấu.
    trung_ma = [c.split(":", 1)[1] for c in res.conflicts
                if c.startswith("ambiguous_video_id:")]
    if trung_ma:
        theo_ma: dict[str, list[str]] = {}
        for e in nguon.entries:
            if e.video_id in trung_ma:
                theo_ma.setdefault(e.video_id, []).append(e.key)
        lien_quan = sorted(k for ds in theo_ma.values() for k in ds)
        canh_bao.append(
            f"clips_meta.json có {len(trung_ma)} mã video bị hai hoặc nhiều file "
            f"dùng chung — cùng một video có thể xuất hiện thành nhiều dòng trong "
            f"danh sách này (số video thật ít hơn số dòng). "
            f"Các file liên quan: {', '.join(lien_quan)}.")
    # Chỉ báo con số tổng khi CHƯA có cảnh báo `invalid_field:` nào — nếu không thì
    # cùng một mục bị kể tới ba lần và người dùng tưởng kho hỏng nặng. Mục
    # `entry_not_object` cũng loại ra: hỏng cả mục chứ không phải một trường.
    so_hong_truong = nguon.invalid_entries - len(muc_hong)
    if so_hong_truong > 0 and not any(
            m.startswith("invalid_field:") for m in nguon.warnings):
        canh_bao.append(
            f"{so_hong_truong} mục trong clips_meta.json có trường không "
            f"hợp lệ nên trường đó bị bỏ qua.")

    bao(0.3, "Đang duyệt file audio...")
    files, so_media_khac = _duyet_file(thu_muc, ten_kho)

    thoi_diem = datetime.now().strftime("%H:%M:%S")
    if not files:
        if so_media_khac:
            # Kho chép tay từ thư mục video gốc: `engine.liet_ke_media` nhận cả
            # .mp4/.mkv/... nên vân tay của kho VẪN TỐT. Đừng xui đi đồng bộ kênh —
            # đó là tải lại hàng chục GB để chữa một thứ không hỏng.
            canh_bao.append(
                f"Kho «{ten_kho}» có {so_media_khac} file video/audio khác "
                f"(.mp4, .mkv…) nhưng chưa có file .opus nào. Tab này chỉ liệt kê "
                f"được kho tải bằng «Đồng bộ kênh gốc». Kho chép tay từ video gốc "
                f"thì chưa liệt kê được — ĐỪNG chạy đồng bộ kênh, vân tay của kho "
                f"bạn vẫn tốt.")
        else:
            canh_bao.append(f"Thư mục «{thu_muc}» chưa có file .opus nào.")
        bao(1.0, "Xong — kho chưa có file audio nào.")
        return KetQuaKho(ten_kho=ten_kho, thu_muc=thu_muc, dong=(),
                         canh_bao=tuple(canh_bao), thoi_diem=thoi_diem,
                         so_media_khac=so_media_khac)

    # ``resolve_many`` giữ nguyên thứ tự và giữ cả bản trùng, nên khớp 1-1 với
    # ``files`` và ``enumerate`` đánh STT an toàn.
    #
    # Tra bằng BASENAME chứ KHÔNG bằng đường dẫn: (a) khoá do channel.py ghi luôn là
    # basename; (b) ``resolve`` gom mọi chuỗi ``[11 ký tự]`` trong TẤT CẢ tên được
    # đưa vào, nên kho đặt ở ``D:\Kho\[SML-Channel]\audio`` sẽ khiến MỌI file trông
    # như có hai mã video và cả kho mất tên thật.
    ket = res.resolve_many((os.path.basename(f), None) for f in files)

    dong: list[DongVideo] = []
    tong = len(files)
    for i, (duong_tuong_doi, r) in enumerate(zip(files, ket), start=1):
        # Tra metadata bằng basename, nhưng HIỂN THỊ đường dẫn tương đối để cột
        # «Tên file» chỉ đúng chỗ khi kho có thư mục con.
        ten, chinh_xac, ghi_chu = _ten_hien_thi(
            r, os.path.basename(duong_tuong_doi), tieu_de_goc, muc_hong)
        dong.append(DongVideo(stt=i, ten_video=ten, ten_file=duong_tuong_doi,
                              chinh_xac=chinh_xac, ghi_chu=ghi_chu))
        if i % 200 == 0:
            bao(0.3 + 0.65 * i / tong, f"Đã đọc {i}/{tong} video...")

    thieu = sum(1 for d in dong if not d.chinh_xac)
    if thieu:
        canh_bao.append(
            f"{thieu}/{tong} video chưa lấy được tên chính xác từ metadata — "
            f"xem danh sách chi tiết bên dưới bảng.")

    bao(1.0, f"Xong — {tong} video.")
    return KetQuaKho(ten_kho=ten_kho, thu_muc=thu_muc, dong=tuple(dong),
                     canh_bao=tuple(canh_bao), thoi_diem=thoi_diem,
                     so_media_khac=so_media_khac)


def liet_ke_theo_ten_kho(
    khos: list[dict],
    ten_kho: str,
    *,
    progress: Optional[Callable[[float, str], None]] = None,
) -> KetQuaKho:
    """Tra kho theo TÊN trong danh sách ``Engine.list_khos()`` rồi gọi ``liet_ke_kho``.

    Nhận thẳng ``khos`` (list dict) chứ không nhận ``Engine``: giao diện đã có sẵn
    biến đó, và như vậy module này hoàn toàn không phụ thuộc ``Engine`` — test được
    mà không phải dựng Engine (vốn tạo thư mục + mở SQLite).

    KHÔNG gọi ``eng.use_kho()`` — chỉ ĐỌC, tuyệt đối không đổi kho quét toàn cục.

    Raises:
        LoiKho: không còn kho tên đó, hoặc kho đó không dùng được.
    """
    ten = (ten_kho or "").strip()
    if not khos:
        raise LoiKho("Chưa có kho nào. Tạo kho ở tab «Kho clip gốc».")
    kho = next((k for k in khos if k.get("ten") == ten), None)
    if kho is None:
        co_gi = ", ".join(str(x.get("ten")) for x in khos)
        raise LoiKho(
            f"Không còn kho tên «{ten}» — có thể kho đã bị xoá. "
            f"Các kho hiện có: {co_gi}")
    # ``k.get`` chứ không ``k[...]``: kho tạo bằng ``add_kho(ten)`` mặc định thu_muc="".
    return liet_ke_kho(ten, kho.get("thu_muc") or "", progress=progress)


def ten_trang_tinh(ten_kho: str) -> str:
    r"""Tên trang tính Google Sheets cho một kho: ``DanhSachVideo_<Tên kho>``.

    Tên kho do người dùng tự gõ nên có thể chứa ``[ ] : \ / ? *`` (Google Sheets
    cấm) hoặc dài quá 100 ký tự.

    Tên an toàn sẵn thì GIỮ NGUYÊN, kể cả dấu tiếng Việt: ``"SML"`` →
    ``"DanhSachVideo_SML"``, ``"Ẩm thực"`` → ``"DanhSachVideo_Ẩm thực"``. CHỈ khi
    phải sửa (thay ký tự cấm hoặc cắt ngắn) mới nối hậu tố md5 6 ký tự: không có
    nó thì ``"A/B"`` và ``"A?B"`` cùng ra ``DanhSachVideo_A_B``, và kho ghi sau sẽ
    XOÁ TRẮNG danh sách của kho trước — mất dữ liệu im lặng, không hoàn tác được.

    Điều kiện thứ ba (``_RE_DA_CO_BAM``) tồn tại vì hậu tố băm chia kết quả thành
    hai không gian tên, và chúng phải RỜI NHAU. Không có nó thì kho tên
    ``"A_B_0a85c0"`` — một cái tên hoàn toàn an toàn nên không được gắn băm — sẽ
    ra đúng cùng trang tính với kho ``"A:B"`` (băm của ``"A:B"`` chính là
    ``0a85c0``). Gắn băm cho cả những tên TRÔNG GIỐNG đã băm khiến mọi tên trong
    nhóm «có băm» đều kết thúc bằng ``_<6 hex>`` còn nhóm «giữ nguyên» thì không
    bao giờ — hai nhóm không thể chạm nhau.

    DANH TÍNH của một kho là tên đã ``.strip()`` — đúng thứ ``Engine.add_kho()``
    lưu vào khos.json. Khoảng trắng BÊN TRONG là khác biệt thật: ``add_kho`` nhận
    cả ``"SML A"`` lẫn ``"SML  A"`` làm hai kho riêng, mỗi kho một file vân tay.
    Vì vậy phải so và băm trên ``goc`` (chỉ strip hai đầu) chứ KHÔNG trên bản đã
    gộp khoảng trắng: gộp trước rồi mới so thì hai tên đó cùng ra
    ``DanhSachVideo_SML A``, và băm cũng vô dụng vì băm của hai bản đã gộp giống
    hệt nhau. Trên dropdown Streamlit, HTML còn gộp khoảng trắng nên người dùng
    KHÔNG nhìn thấy mình đang chọn kho nào — đẩy nhầm là mất trắng, không hoàn tác.

    Hàm THUẦN: tất định, không I/O, không ném lỗi với bất kỳ đầu vào nào.
    """
    goc = (ten_kho or "").strip()
    if not goc:
        goc = "KhongTen"
    # Bản hiển thị gộp khoảng trắng cho tên tab dễ đọc; danh tính vẫn là ``goc``.
    an_toan = _RE_CAM_TRANG_TINH.sub("_", " ".join(goc.split()))
    ten = TIEN_TO_TRANG_TINH + an_toan
    if (an_toan != goc or len(ten) > GIOI_HAN_TEN_TRANG_TINH
            or _RE_DA_CO_BAM.search(an_toan)):
        hau_to = "_" + hashlib.md5(goc.encode("utf-8")).hexdigest()[:6]
        con_lai = GIOI_HAN_TEN_TRANG_TINH - len(TIEN_TO_TRANG_TINH) - len(hau_to)
        ten = TIEN_TO_TRANG_TINH + an_toan[:max(con_lai, 1)].rstrip() + hau_to
    return ten


def hang_bang_tinh(ket_qua: KetQuaKho) -> tuple[list[str], list[list]]:
    """Đổi kết quả thành ``(header, rows)`` đúng 2 cột để ghi lên Google Sheets.

    STT giữ nguyên kiểu ``int`` chứ KHÔNG f-string: ``sheets._o_sheets`` giữ số
    nguyên vẹn và Sheets sắp xếp đúng theo số (chuỗi ``"9"`` đứng SAU ``"10"``).

    Tiêu đề gửi NGUYÊN VĂN, cố ý KHÔNG bọc ``engine.o_bang_tinh_an_toan``.
    ``SheetsExporter.ghi_de`` ghi bằng ``value_input_option="RAW"``, mà RAW thì
    Google lưu đúng chuỗi được gửi và không phân tích công thức. Thêm dấu nháy đơn
    ở đây sẽ khiến dấu nháy được lưu THÀNH KÝ TỰ THẬT và hiện ra trong ô — tên
    không còn là «tên chính xác trên YouTube», mà không đổi lại được chút an toàn nào.
    """
    return list(HEADER), [[d.stt, d.ten_video] for d in ket_qua.dong]


def _dich_thieu_gi(sx) -> str:
    """Đổi câu ``SheetsExporter.thieu_gi()`` sang lời người dùng làm theo được.

    Bản gốc bảo «xem hướng dẫn ở đầu sheets.py» — tức bảo người làm nội dung mở mã
    nguồn bằng trình soạn thảo. Giữ nguyên văn kỹ thuật trong ngoặc cuối câu cho ai
    cần tra cứu.
    """
    thieu = sx.thieu_gi()
    if "thư viện" in thieu:
        return ("Máy chưa cài thư viện đọc Google Sheets. Nhờ người cài đặt chạy "
                "giúp lệnh trong HUONG_DAN.md mục D. "
                "(chi tiết: pip install gspread google-auth)")
    if TEN_FILE_KEY in thieu:
        return (f"Máy chưa có file khoá Google ({TEN_FILE_KEY}) đặt cạnh "
                f"ChayTool.bat. Xem HUONG_DAN.md mục D để tạo file này — chỉ làm "
                f"một lần. (chi tiết: {TEN_FILE_KEY})")
    if "link" in thieu.lower():
        return "Chưa nhập link Google Sheet — mở «📊 Google Sheets» ở thanh bên."
    return thieu


def day_len_sheet(
    ket_qua: KetQuaKho,
    sheet_link: str,
    *,
    tao_exporter: Optional[Callable[[str, str], Any]] = None,
) -> tuple[bool, str]:
    """Ghi ĐÈ danh sách lên trang tính riêng của kho. Trả ``(thành_công, thông_báo)``.

    KHÔNG BAO GIỜ ném exception ra ngoài — cùng khuôn ``app.day_len_sheets`` để
    giao diện chỉ việc ``(st.success if ok else st.error)(tb)``.

    ``tao_exporter(sheet_link, ten_trang_tinh) -> SheetsExporter`` để test không
    cần gspread và không phải monkeypatch gì.

    Bảng RỖNG thì TỪ CHỐI ghi, chặn TRƯỚC khi mở kết nối: chọn nhầm một kho chưa
    đồng bộ mà vẫn đẩy sẽ xoá sạch trang tính cũ và ``ghi_de`` không hoàn tác được;
    chặn sớm cũng tránh tạo một tab rỗng trên Sheet của người dùng.

    CỐ Ý KHÔNG dùng ``SheetDeliveryWorker``: ``khoa_giao_hang`` băm cả nội dung
    ``rows`` nên chạy lại khi kho chưa đổi sẽ bị BỎ QUA IM LẶNG — trái hẳn yêu cầu
    «chạy lại thì ghi đè». Chống trùng sinh ra để chống NỐI trùng dòng; ghi đè vốn
    đã miễn nhiễm.
    """
    if not ket_qua.dong:
        return False, (f"Kho «{ket_qua.ten_kho}» không có video nào — không ghi đè "
                       f"trang tính để tránh xoá nhầm dữ liệu cũ.")

    ten_tab = ten_trang_tinh(ket_qua.ten_kho)
    tao = tao_exporter or (lambda link, ten: SheetsExporter(sheet=link, worksheet=ten))
    sx = tao(sheet_link, ten_tab)
    if not sx.san_sang():
        return False, _dich_thieu_gi(sx)

    header, rows = hang_bang_tinh(ket_qua)
    try:
        n = sx.ghi_de(header, rows)
    except Exception as e:  # noqa: BLE001 — giao diện chỉ nhận câu tiếng Việt
        loi = str(e)
        if "PERMISSION_DENIED" in loi or "403" in loi:
            goi_y = (f" → Hãy mở Google Sheet, bấm Chia sẻ và cấp quyền "
                     f"«Người chỉnh sửa» cho: {sx.email_service_account()}")
        elif "404" in loi or "not found" in loi.lower():
            goi_y = " → Kiểm tra lại link Google Sheet."
        else:
            goi_y = (" → Kiểm tra kết nối mạng rồi bấm lại; "
                     "ghi đè lặp lại không tạo dòng trùng.")
        return False, f"Lỗi ghi Sheets: {loi}{goi_y}"
    return True, (f"Đã viết lại toàn bộ trang tính «{ten_tab}» với {n} video của "
                  f"kho «{ket_qua.ten_kho}» — mọi cột và dòng bạn tự thêm trong "
                  f"trang tính đó đã bị thay thế.")
