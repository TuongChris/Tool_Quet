# -*- coding: utf-8 -*-
"""Chế độ «Một video gốc chung cho cả lô» — phần THUẦN.

Không I/O, không mạng, không Streamlit. Bộ điều phối (``common_original_jobs.py``) lo tải,
quét, khoá và luồng; module này chỉ trả lời ba câu hỏi trên dữ liệu đã có:

1. Với mỗi cặp (video vi phạm, video gốc) ta BIẾT gì — có mặt, chắc chắn vắng mặt, hay
   chưa rõ?
2. Đã đủ để kết luận cho cả lô chưa — và nếu chưa thì quét video nào, với mục tiêu gì?
3. Kết quả trình bày ra sao (đại diện mỗi video, cảnh báo, dòng CSV)?

QUY TẮC KHÔNG ĐƯỢC PHÁ (xem ``docs/COMMON_ORIGINAL_DESIGN.md``):

* Ứng viên lấy từ ``ScanResult.ung_vien_dat`` (đạt chuẩn TRƯỚC khi cắt Top-N), không bao
  giờ từ ``matches``: video gốc chung có thể không là Top-1 của video nào.
* Một video gốc chỉ bị LOẠI bằng bằng chứng âm ĐẦY ĐỦ: lượt quét hợp lệ, phủ trọn video,
  không vùng lỗi. Quét dở / dừng sớm / lỗi không bao giờ là «vắng mặt».
* Bằng chứng dương trong một phần video là đủ để nói «có mặt».
* Định danh = (kho, tên clip trong kho vân tay). Không dùng tiêu đề, không gộp theo mã
  ``[ID]`` trong tên file — tên kiểu "X [Compilation].mp3" cũng đọc ra mã 11 ký tự.
* Mỗi video bị quét tối đa ``toi_da_luot`` (2) lượt; bộ điều phối luôn dừng.
* Khớp vân tay KHÔNG phải xác nhận quyền sở hữu: kết quả cần người kiểm tra trước khi
  khiếu nại.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

from chap_nhan_khop import BAC_PHU_CAO, danh_gia_chap_nhan
from clip_metadata import basename_compatible, extract_youtube_id
from engine import (
    MUC_TIEU_THU_THAP,
    MUC_TIEU_XAC_MINH,
    Engine,
    ScanObjective,
    chon_dai_dien,
    hhmmss,
    mo_ta_pham_vi,
    o_bang_tinh_an_toan,
)
from publication_date import format_publication_date

# --- Trạng thái của một cặp (video vi phạm, video gốc) ---
CO_MAT = "co_mat"              # có ứng viên đạt chuẩn trong ít nhất một lượt hợp lệ
VANG_MAT_DU = "vang_mat_du"    # có lượt hợp lệ quét TRỌN mà không thấy
CHUA_RO = "chua_ro"            # có lượt hợp lệ nhưng chưa trọn, chưa thấy
LOI_QUET = "loi_quet"          # chỉ có lượt lỗi / bị huỷ / khác kho
CHUA_QUET = "chua_quet"        # chưa quét lượt nào

TEN_TRANG_THAI_CAP = {
    CO_MAT: "Có mặt",
    VANG_MAT_DU: "Không có (đã quét trọn)",
    CHUA_RO: "Chưa rõ (chưa quét trọn)",
    LOI_QUET: "Lỗi quét",
    CHUA_QUET: "Chưa quét",
}

# --- Trạng thái của cả lô ---
DANG_TIM = "dang_tim"
TIM_THAY = "tim_thay"
KHONG_TIM_THAY = "khong_tim_thay"
CHUA_KET_LUAN = "chua_ket_luan"
DA_HUY = "da_huy"

TEN_TRANG_THAI_LO = {
    DANG_TIM: "Đang tìm",
    TIM_THAY: "Tìm thấy video gốc chung",
    # «Không TÌM THẤY», không phải «không CÓ»: trần max_matches và luật bù tốc độ giới hạn
    # điều một lượt quét trọn chứng minh được (xem `_gioi_han_ket_luan_am`).
    KHONG_TIM_THAY: "Không tìm thấy video gốc chung",
    CHUA_KET_LUAN: "Chưa kết luận được",
    DA_HUY: "Đã dừng",
}

# --- Pha của bộ lập kế hoạch ---
PHA_MOC = "moc"            # quét TRỌN video mốc để biết đủ ứng viên
PHA_NHANH = "nhanh"        # xác minh ứng viên đứng đầu trên các video còn lại
PHA_BO_SUNG = "bo_sung"    # nhắm đúng phần còn chưa rõ sau khi ứng viên đầu bị loại

TEN_PHA = {
    PHA_MOC: "Quét trọn video mốc",
    PHA_NHANH: "Xác minh nhanh",
    PHA_BO_SUNG: "Quét bổ sung để kết luận",
}

TOI_DA_LUOT_MOI_VIDEO = 2


class DungLo(Exception):
    """Lô phải dừng hẳn (ví dụ kho đổi giữa chừng). Thông điệp là lý do cho người dùng."""


# =====================================================================
#  Định danh và bằng chứng
# =====================================================================

@dataclass(frozen=True, order=True)
class OriginalKey:
    """Một video gốc trong lô: kho + tên clip trong kho vân tay."""
    kho_id: str
    clip: str

    def __str__(self) -> str:
        return self.clip


def khoa_goc(kho_id: str, clip: str) -> OriginalKey:
    """Khoá của clip trong kho. ``Match.clip`` vốn đã là basename; vẫn cắt để chắc."""
    return OriginalKey(str(kho_id or ""), basename_compatible(clip))


@dataclass(frozen=True)
class LuotQuet:
    """Một lượt quét một video, rút gọn thành bằng chứng cho chế độ nguồn chung."""
    muc_tieu: str                   # MUC_TIEU_THU_THAP | MUC_TIEU_XAC_MINH
    hop_le: bool                    # status ok VÀ cùng kho/chính sách với lô
    tron: bool                      # hợp lệ VÀ phủ trọn video, không vùng lỗi
    ung_vien: tuple = ()            # Match đạt chuẩn (rỗng khi không hợp lệ)
    ly_do: str = ""                 # vì sao không hợp lệ
    pham_vi: str = ""               # mô tả phần đã so khớp
    so_khuc_cham_tran: int = 0      # khúc audfprint trả đủ trần max_matches
    thoi_luong: float = 0.0         # thời lượng video theo kết quả quét
    thu_bu_toc_do: bool = False     # đã chạy ít nhất một lượt bù tốc độ


def luot_tu_ket_qua(kq, muc_tieu: str, dinh_danh: tuple) -> LuotQuet:
    """Rút một ``ScanResult`` thành ``LuotQuet``.

    ``dinh_danh`` = (kho_id, kho_phien_ban, chinh_sach) chụp lúc bắt đầu lô. Lượt quét
    dùng kho/chính sách khác không được trộn vào kết luận của lô.
    """
    cung_kho = (str(kq.kho_id or ""), str(kq.kho_phien_ban or ""),
                str(kq.chinh_sach or "")) == tuple(str(x or "") for x in dinh_danh)
    hop_le = kq.status == "ok" and cung_kho
    if not cung_kho:
        ly_do = "Kho vân tay hoặc chính sách nhận diện khác với lúc bắt đầu lô."
    elif kq.status != "ok":
        ly_do = kq.note or "Lỗi quét."
    else:
        ly_do = ""
    cd = getattr(kq, "chan_doan", None)
    return LuotQuet(
        muc_tieu=muc_tieu,
        hop_le=hop_le,
        tron=bool(hop_le and kq.quet_day_du),
        ung_vien=tuple(getattr(kq, "ung_vien_dat", ()) or ()) if hop_le else (),
        ly_do=ly_do,
        pham_vi=mo_ta_pham_vi(kq),
        so_khuc_cham_tran=int(getattr(cd, "so_khuc_cham_tran", 0) or 0) if cd else 0,
        thoi_luong=float(kq.duration_s or 0.0),
        thu_bu_toc_do=bool(getattr(cd, "da_thu_toc_do", None)) if cd else False,
    )


@dataclass
class VideoTrongLo:
    """Một video vi phạm của lô cùng mọi lượt quét đã làm trên nó."""
    thu_tu: int                         # thứ tự người dùng nhập (từ 1)
    nguon: str                          # link hoặc đường dẫn như người dùng nhập
    ma: str = ""                        # mã video YouTube (hoặc đường dẫn chuẩn hoá)
    tieu_de: str = ""
    kenh: str = ""
    thoi_luong: Optional[float] = None
    info: Optional[dict] = None         # thông tin YouTube đã lấy sẵn
    luot: list = field(default_factory=list)

    def ung_vien(self, kho_id: str) -> dict:
        """Khoá -> danh sách Match đạt chuẩn, gộp qua MỌI lượt hợp lệ."""
        ra: dict = {}
        for lq in self.luot:
            if not lq.hop_le:
                continue
            for m in lq.ung_vien:
                ra.setdefault(khoa_goc(kho_id, m.clip), []).append(m)
        return ra

    @property
    def tron(self) -> bool:
        return any(lq.tron for lq in self.luot)

    def trang_thai(self, khoa: OriginalKey, kho_id: str) -> str:
        if khoa in self.ung_vien(kho_id):
            return CO_MAT
        if self.tron:
            return VANG_MAT_DU
        if any(lq.hop_le for lq in self.luot):
            return CHUA_RO
        return LOI_QUET if self.luot else CHUA_QUET

    def thoi_luong_that(self) -> float:
        return float(self.thoi_luong or max((lq.thoi_luong for lq in self.luot),
                                            default=0.0) or 0.0)


def mau_thuan(video: VideoTrongLo, kho_id: str) -> set:
    """Khoá có mặt ở một lượt nhưng vắng ở một lượt quét TRỌN khác của cùng video.

    Bằng chứng dương thắng (đã thấy là đã thấy), nhưng mâu thuẫn phải được nói ra.
    """
    co = set(video.ung_vien(kho_id))
    ra: set = set()
    for lq in video.luot:
        if lq.tron:
            ra |= co - {khoa_goc(kho_id, m.clip) for m in lq.ung_vien}
    return ra


# =====================================================================
#  Trạng thái lô, xếp hạng, đại diện
# =====================================================================

@dataclass
class TrangThaiLo:
    kho_id: str
    videos: list                       # list[VideoTrongLo], theo thứ tự nhập
    cfg: object                        # Config đã ghim của job (chỉ đọc)
    thu_tu_xu_ly: list = field(default_factory=list)
    moc: Optional[int] = None          # chỉ số video mốc (lượt thu thập trọn đầu tiên)
    muc_tieu_nhanh: Optional[OriginalKey] = None
    toi_da_luot: int = TOI_DA_LUOT_MOI_VIDEO
    # Tên clip có >1 bản ghi vân tay trong kho -> số bản ghi. `Match.clip` chỉ là basename
    # (`_merge` bỏ đường dẫn audfprint trả về), nên khớp HAI bản ghi khác nhau trông y hệt
    # nhau: khoá đó không bao giờ được xác nhận là nguồn chung, và không điều khiển kế
    # hoạch (không làm đích, không xác nhận ngay — tức không làm dừng sớm).
    ten_trung: dict = field(default_factory=dict)


def dem_ten_kho(ds_clip) -> dict:
    """Số bản ghi vân tay của từng tên clip (basename) — đầu vào là ``Engine.db_clips()``."""
    dem: dict = {}
    for c in ds_clip or ():
        ten = basename_compatible(c.get("ten") or c.get("duong_dan") or "")
        if ten:
            dem[ten] = dem.get(ten, 0) + 1
    return dem


def la_ten_trung(tt: TrangThaiLo, khoa: OriginalKey) -> bool:
    return khoa.clip in (tt.ten_trung or {})


def _xac_nhan_duoc(tt: TrangThaiLo, khoa) -> set:
    """Bỏ các khoá trùng tên: chỉ khoá còn lại mới có thể thành «tìm thấy»."""
    return {k for k in khoa if not la_ten_trung(tt, k)}


def chon_thu_tu_xu_ly(videos: list) -> list:
    """Video ngắn trước (mốc rẻ nhất), chưa biết thời lượng xếp sau; hoà theo thứ tự nhập."""
    def khoa(i):
        d = videos[i].thoi_luong
        return (d is None or d <= 0, d or 0.0, videos[i].thu_tu)
    return sorted(range(len(videos)), key=khoa)


def _thu_tu(tt: TrangThaiLo) -> list:
    return tt.thu_tu_xu_ly or chon_thu_tu_xu_ly(tt.videos)


def tap_kha_di(tt: TrangThaiLo) -> Optional[set]:
    """Giao tập ứng viên của các video đã quét TRỌN; ``None`` khi chưa có video nào trọn.

    Mọi video gốc chung (nếu có) bắt buộc nằm trong tập này.
    """
    s: Optional[set] = None
    for v in tt.videos:
        if v.tron:
            uv = set(v.ung_vien(tt.kho_id))
            s = uv if s is None else s & uv
    return s


def _khoa_chung(tt: TrangThaiLo) -> set:
    if not tt.videos:
        return set()
    s: Optional[set] = None
    for v in tt.videos:
        uv = set(v.ung_vien(tt.kho_id))
        s = uv if s is None else s & uv
    return s or set()


def _manh(m, cfg) -> bool:
    return int(m.hashes) >= int(getattr(cfg, "min_hash_strong", 5000) or 0)


def xep_hang_ung_vien(video: VideoTrongLo, kho_id: str, cfg) -> list:
    """Ứng viên của video mốc, xếp theo khả năng là bằng chứng đáng dùng.

    Bằng chứng mạnh trước, rồi đoạn khớp DÀI, rồi số hash — để intro/nhạc hiệu ngắn có
    phủ vân tay cao không chiếm chỗ ứng viên kiểm đầu tiên.
    """
    uv = video.ung_vien(kho_id)

    def khoa(k):
        tot = max(uv[k], key=lambda m: (_manh(m, cfg), m.matched_s, m.hashes))
        return (not _manh(tot, cfg), -float(tot.matched_s), -int(tot.hashes), k.clip)

    return sorted(uv, key=khoa)


def dai_dien(video: VideoTrongLo, khoa: OriginalKey, cfg):
    """Bằng chứng đại diện của ``khoa`` trên video: chất lượng trước, vị trí phá hoà.

    Dùng đúng ``chon_dai_dien`` và khoá chất lượng của chế độ cũ (``_chon_loc``).
    """
    ds = video.ung_vien(khoa.kho_id).get(khoa) or []
    if not ds:
        return None
    dung_ty_le = getattr(cfg, "khoa_chat_luong", "ty_le") == "ty_le" and any(
        float(m.ty_le or 0) > 0 for m in ds)

    def chat_luong(m) -> tuple:
        return (_manh(m, cfg), float(m.ty_le) if dung_ty_le else float(m.hashes))

    return chon_dai_dien(
        ds, video.thoi_luong_that(), float(getattr(cfg, "dung_sai_gan_bang", 0.0) or 0.0),
        chat_luong,
        san_bang_chung=float(getattr(cfg, "san_bang_chung", 0.0) or 0.0) if dung_ty_le else 0.0,
    )


def _dai_dien_moi_video(tt: TrangThaiLo, khoa: OriginalKey) -> list:
    return [m for m in (dai_dien(v, khoa, tt.cfg) for v in tt.videos) if m is not None]


def _hang_chat_luong(tt: TrangThaiLo, khoa: OriginalKey) -> tuple:
    """«Mắt xích yếu nhất»: nguồn chung đáng dùng là nguồn mạnh ở MỌI video."""
    dd = _dai_dien_moi_video(tt, khoa)
    if not dd:
        return (0, 0.0, 0.0, khoa.clip)
    return (-sum(1 for m in dd if _manh(m, tt.cfg)),
            -min(float(m.matched_s) for m in dd),
            -min(float(m.ty_le or 0) for m in dd),
            khoa.clip)


def _tot_nhat(tt: TrangThaiLo) -> tuple:
    """Video gốc có mặt ở NHIỀU video nhất (để báo «ứng viên tốt nhất k/N»)."""
    dem: dict = {}
    for v in tt.videos:
        for k in v.ung_vien(tt.kho_id):
            dem[k] = dem.get(k, 0) + 1
    if not dem:
        return None, 0
    k = min(dem, key=lambda x: (-dem[x], *_hang_chat_luong(tt, x)))
    return k, dem[k]


# =====================================================================
#  Lập kế hoạch
# =====================================================================

@dataclass(frozen=True)
class BuocQuet:
    """Lượt quét kế tiếp: video nào, mục tiêu gì."""
    video: int
    muc_tieu: str
    nhom_can_du: tuple = ()     # tuple[OriginalKey]: MỌI khoá phải có mặt mới được dừng
    nhom_du_mot: tuple = ()     # tuple[OriginalKey]: MỘT khoá có mặt là đủ (xác nhận ngay)
    pha: str = ""

    def objective(self) -> ScanObjective:
        if self.muc_tieu == MUC_TIEU_THU_THAP:
            return ScanObjective(MUC_TIEU_THU_THAP)
        return ScanObjective(MUC_TIEU_XAC_MINH,
                             nhom_can_du=tuple({k.clip} for k in self.nhom_can_du),
                             nhom_du_mot=tuple({k.clip} for k in self.nhom_du_mot))


def _xac_nhan_ngay(tt: TrangThaiLo, i: int, s: set) -> tuple:
    """Khoá khả dĩ đã CÓ MẶT ở mọi video khác: thấy nó ở video ``i`` là đủ cả lô."""
    ra = []
    for k in sorted(s):
        if all(v.trang_thai(k, tt.kho_id) == CO_MAT
               for j, v in enumerate(tt.videos) if j != i):
            ra.append(k)
    return tuple(ra)


def buoc_tiep(tt: TrangThaiLo) -> Optional[BuocQuet]:
    """Lượt quét kế tiếp, hoặc ``None`` khi không còn gì để làm (đã/không thể kết luận)."""
    if not tt.videos:
        return None
    thu_tu = _thu_tu(tt)
    s = tap_kha_di(tt)
    if s is None:
        # Chưa video nào quét trọn: cần một video MỐC — ưu tiên video chưa quét lần nào.
        for toi_da in (0, tt.toi_da_luot - 1):
            for i in thu_tu:
                if len(tt.videos[i].luot) <= toi_da:
                    return BuocQuet(video=i, muc_tieu=MUC_TIEU_THU_THAP, pha=PHA_MOC)
        return None
    # Chỉ khoá xác nhận được mới đáng một lượt quét: khoá trùng tên không bao giờ thành
    # «tìm thấy», nên nó không làm đích và không được làm dừng sớm (xác nhận ngay).
    s = _xac_nhan_duoc(tt, s)
    if not s or _xac_nhan_duoc(tt, _khoa_chung(tt)):
        return None
    t = tt.muc_tieu_nhanh
    if t is not None and t in s:
        for i in thu_tu:
            if not tt.videos[i].luot:
                return BuocQuet(video=i, muc_tieu=MUC_TIEU_XAC_MINH, nhom_can_du=(t,),
                                nhom_du_mot=_xac_nhan_ngay(tt, i, s), pha=PHA_NHANH)
    for i in thu_tu:
        v = tt.videos[i]
        if len(v.luot) >= tt.toi_da_luot:
            continue
        chua_ro = tuple(k for k in sorted(s)
                        if v.trang_thai(k, tt.kho_id) not in (CO_MAT, VANG_MAT_DU))
        if chua_ro:
            return BuocQuet(video=i, muc_tieu=MUC_TIEU_XAC_MINH, nhom_can_du=chua_ro,
                            nhom_du_mot=_xac_nhan_ngay(tt, i, s), pha=PHA_BO_SUNG)
    return None


def ghi_luot(tt: TrangThaiLo, buoc: BuocQuet, luot: LuotQuet) -> None:
    """Ghi một lượt quét; lượt THU THẬP trọn đầu tiên chốt video mốc và ứng viên nhanh."""
    tt.videos[buoc.video].luot.append(luot)
    if tt.moc is None and luot.tron and buoc.muc_tieu == MUC_TIEU_THU_THAP:
        tt.moc = buoc.video
        xep = [k for k in xep_hang_ung_vien(tt.videos[buoc.video], tt.kho_id, tt.cfg)
               if not la_ten_trung(tt, k)]
        tt.muc_tieu_nhanh = xep[0] if xep else None


# =====================================================================
#  Kết luận
# =====================================================================

@dataclass(frozen=True)
class KetLuan:
    trang_thai: str
    goc: Optional[OriginalKey] = None       # TÌM THẤY: video gốc chung được chọn
    goc_khac: tuple = ()                    # các video gốc chung khác (cũng có ở mọi video)
    tot_nhat: Optional[OriginalKey] = None  # không tìm thấy / chưa kết luận: ứng viên tốt nhất
    so_co_mat: int = 0
    tong: int = 0
    ly_do: str = ""
    gioi_han: tuple = ()      # KHÔNG TÌM THẤY: vì sao kết luận chưa phải chứng minh tuyệt đối

    @property
    def khoa_hien_thi(self) -> Optional[OriginalKey]:
        return self.goc or self.tot_nhat


def _gioi_han_ket_luan_am(tt: TrangThaiLo) -> tuple:
    """Điều các lượt quét TRỌN đã báo khiến «không tìm thấy» chưa loại trừ tuyệt đối.

    Chỉ lượt trọn mới loại được một video gốc, nên chỉ xét chúng. Trần ``max_matches``
    chạm ở gần như mọi lượt quét thật (`docs/ZERO_MATCH_ROOT_CAUSE.md` mục 9), nên hạ hẳn
    thành «chưa kết luận» sẽ khiến chế độ này không bao giờ nói được «không tìm thấy»;
    thay vào đó kết luận mang giới hạn đi kèm tới tận giao diện và CSV.
    """
    tron = [lq for v in tt.videos for lq in v.luot if lq.tron]
    ra = []
    cham = sum(lq.so_khuc_cham_tran for lq in tron)
    if cham:
        ra.append(f"{cham} khúc chạm trần số kết quả mỗi khúc của audfprint (max_matches = "
                  f"{int(getattr(tt.cfg, 'max_matches', 0) or 0)}): clip gốc khớp rất ngắn "
                  "hoặc yếu trong các khúc đó chưa được xét.")
    if not getattr(tt.cfg, "quet_da_toc_do", True):
        ra.append("Bù tốc độ đang tắt (quet_da_toc_do): video gốc bị đổi tốc độ không được "
                  "xét.")
    else:
        khong_bu = sum(1 for lq in tron if not lq.thu_bu_toc_do)
        if khong_bu:
            ra.append(f"{khong_bu}/{len(tron)} lượt quét trọn không thử bù tốc độ (đã có ứng "
                      "viên đạt chuẩn ở tốc độ gốc, hoặc không đọc được độ trôi): video gốc "
                      "chỉ xuất hiện ở dạng bị đổi tốc độ trong các lượt đó chưa được xét.")
    return tuple(ra)


def _ly_do_ten_trung(tt: TrangThaiLo, s: set) -> str:
    phan = ", ".join(f"«{k.clip}» ({int(tt.ten_trung.get(k.clip, 0))} bản ghi)"
                     for k in sorted(s)[:5])
    return ("Không xác nhận được video gốc chung: các ứng viên còn lại trùng tên với nhiều bản "
            f"ghi vân tay khác nhau trong kho — {phan}. Kết quả quét chỉ giữ tên clip nên "
            "không biết các video có khớp CÙNG một bản ghi hay không. Hãy kiểm tra thủ công, "
            "hoặc bỏ bản ghi trùng khỏi kho rồi chạy lại.")


def _ly_do_chua_ket_luan(tt: TrangThaiLo) -> str:
    s = tap_kha_di(tt)
    ten = []
    for v in tt.videos:
        chua = (s is None and not v.tron) or (s is not None and any(
            v.trang_thai(k, tt.kho_id) not in (CO_MAT, VANG_MAT_DU) for k in s))
        if chua:
            loi = next((lq.ly_do for lq in reversed(v.luot) if lq.ly_do), "")
            ten.append(f"video {v.thu_tu}" + (f" ({loi.splitlines()[0][:120]})" if loi else ""))
    phan = "; ".join(ten) if ten else "một số video"
    return (f"Chưa đủ căn cứ kết luận: {phan} chưa quét được trọn hoặc bị lỗi. "
            "Hãy chạy lại lô.")


def ket_luan(tt: TrangThaiLo, *, da_huy: bool = False, ly_do_dung: str = "") -> KetLuan:
    """Kết luận trên ma trận bằng chứng hiện có. Hàm thuần."""
    n = len(tt.videos)
    chung = _xac_nhan_duoc(tt, _khoa_chung(tt))
    if chung:
        xep = sorted(chung, key=lambda k: _hang_chat_luong(tt, k))
        return KetLuan(TIM_THAY, goc=xep[0], goc_khac=tuple(xep[1:]), so_co_mat=n, tong=n,
                       ly_do=f"Video gốc «{xep[0].clip}» khớp vân tay ở cả {n}/{n} video.")
    tot, so = _tot_nhat(tt)
    s = tap_kha_di(tt)
    if s is not None and not _xac_nhan_duoc(tt, s):
        if s:
            # Chỉ còn khoá trùng tên khả dĩ: không xác nhận được, cũng không loại được.
            return KetLuan(CHUA_KET_LUAN, tot_nhat=tot, so_co_mat=so, tong=n,
                           ly_do=_ly_do_ten_trung(tt, s))
        gioi_han = _gioi_han_ket_luan_am(tt)
        ly_do = (f"Không tìm thấy video gốc nào khớp vân tay ở cả {n} video "
                 "(đã loại bằng các lượt quét trọn).")
        if gioi_han:
            ly_do += " Kết luận này chưa loại trừ tuyệt đối: " + " ".join(gioi_han)
        return KetLuan(KHONG_TIM_THAY, tot_nhat=tot, so_co_mat=so, tong=n, ly_do=ly_do,
                       gioi_han=gioi_han)
    if ly_do_dung:
        return KetLuan(CHUA_KET_LUAN, tot_nhat=tot, so_co_mat=so, tong=n, ly_do=ly_do_dung)
    if da_huy:
        return KetLuan(DA_HUY, tot_nhat=tot, so_co_mat=so, tong=n,
                       ly_do="Đã dừng theo yêu cầu; bằng chứng đã có vẫn được giữ.")
    if buoc_tiep(tt) is not None:
        return KetLuan(DANG_TIM, tot_nhat=tot, so_co_mat=so, tong=n)
    return KetLuan(CHUA_KET_LUAN, tot_nhat=tot, so_co_mat=so, tong=n,
                   ly_do=_ly_do_chua_ket_luan(tt))


def dieu_phoi(tt: TrangThaiLo, quet: Callable, *, da_huy: Callable = lambda: False,
              sau_moi_luot: Optional[Callable] = None) -> KetLuan:
    """Vòng điều phối thuần: kết luận → lập kế hoạch → quét → ghi, tới khi dứt điểm.

    ``quet(BuocQuet) -> LuotQuet`` làm việc thật (hoặc giả trong test); ném ``DungLo`` để
    dừng hẳn lô. Luôn kết thúc vì mỗi video bị quét tối đa ``toi_da_luot`` lượt.
    """
    if not tt.thu_tu_xu_ly:
        tt.thu_tu_xu_ly = chon_thu_tu_xu_ly(tt.videos)
    while True:
        kl = ket_luan(tt)
        if kl.trang_thai in (TIM_THAY, KHONG_TIM_THAY):
            return kl
        if da_huy():
            return ket_luan(tt, da_huy=True)
        buoc = buoc_tiep(tt)
        if buoc is None:
            return ket_luan(tt)
        try:
            luot = quet(buoc)
        except DungLo as e:
            return ket_luan(tt, ly_do_dung=str(e))
        ghi_luot(tt, buoc, luot)
        if sau_moi_luot is not None:
            sau_moi_luot(buoc, luot)


# =====================================================================
#  Cảnh báo và báo cáo
# =====================================================================

def canh_bao_goc(tt: TrangThaiLo, khoa: OriginalKey, dem_ten: dict) -> list:
    """Những điều người kiểm tra cần biết về video gốc được báo cáo."""
    ra = []
    so_ban = int(dem_ten.get(khoa.clip, 0) or 0)
    if so_ban > 1:
        ra.append(f"Tên clip «{khoa.clip}» có {so_ban} bản ghi vân tay trong kho (có thể do "
                  "chép hoặc đổi thư mục kho) — hãy kiểm tra đúng file trước khi dùng.")
    dd = _dai_dien_moi_video(tt, khoa)
    if dd and all(danh_gia_chap_nhan(m, tt.cfg).bac == BAC_PHU_CAO for m in dd):
        ra.append("Ở mọi video, clip gốc này chỉ đạt chuẩn nhờ phủ vân tay cao (đoạn khớp "
                  "ngắn) — có thể là intro/nhạc hiệu dùng chung, hãy xem lại.")
    ma = extract_youtube_id(khoa.clip) or ""
    for v in tt.videos:
        if ma and v.ma == ma:
            ra.append(f"Link video {v.thu_tu} có thể chính là video gốc «{khoa.clip}».")
    for v in tt.videos:
        if khoa in mau_thuan(v, tt.kho_id):
            ra.append(f"Video {v.thu_tu}: một lượt quét thấy clip gốc, một lượt quét trọn "
                      "khác lại không thấy — đã tính là CÓ MẶT, nên kiểm tra lại bằng mắt.")
    return ra


def canh_bao_ten_trung_chung(tt: TrangThaiLo, khoa_bao_cao: Optional[OriginalKey]) -> list:
    """Khoá trùng tên có mặt ở MỌI video nhưng bị loại khỏi kết luận — phải nói ra."""
    n = len(tt.videos)
    return [f"Clip «{k.clip}» cũng có mặt ở cả {n}/{n} video nhưng tên này ứng với "
            f"{int(tt.ten_trung.get(k.clip, 0))} bản ghi vân tay trong kho — không tính là "
            "nguồn chung vì không biết các video có khớp cùng một bản ghi."
            for k in sorted(_khoa_chung(tt))
            if la_ten_trung(tt, k) and k != khoa_bao_cao]


@dataclass(frozen=True)
class VideoKetQua:
    thu_tu: int
    nguon: str
    ma: str
    tieu_de: str
    kenh: str
    thoi_luong: float
    trang_thai: str               # trạng thái với video gốc được báo cáo
    dai_dien: object = None       # Match | None
    pham_vi: str = ""
    so_luot: int = 0
    loi: str = ""


@dataclass(frozen=True)
class KetQuaLo:
    ma_lo: str
    trang_thai: str
    ly_do: str
    kho_id: str
    kho_ten: str
    goc: Optional[OriginalKey]           # video gốc được báo cáo (chung, hoặc tốt nhất)
    la_nguon_chung: bool
    so_co_mat: int
    tong: int
    goc_khac: tuple = ()
    thong_tin_goc: dict = field(default_factory=dict)
    canh_bao: tuple = ()
    videos: tuple = ()
    so_lieu: dict = field(default_factory=dict)
    gioi_han: tuple = ()                 # KHÔNG TÌM THẤY: vì sao chưa loại trừ tuyệt đối


def dung_ket_qua_lo(tt: TrangThaiLo, kl: KetLuan, *, ma_lo: str, kho_ten: str,
                    thong_tin_goc: dict, dem_ten: dict, so_lieu: Optional[dict] = None,
                    canh_bao_them: tuple = ()) -> KetQuaLo:
    """Đóng băng kết quả lô để hiển thị/xuất — không phụ thuộc kho đang chọn sau này."""
    khoa = kl.khoa_hien_thi
    videos = []
    for v in tt.videos:
        tt_cap = v.trang_thai(khoa, tt.kho_id) if khoa is not None else (
            CHUA_QUET if not v.luot else (LOI_QUET if not any(lq.hop_le for lq in v.luot)
                                          else (VANG_MAT_DU if v.tron else CHUA_RO)))
        cuoi = v.luot[-1] if v.luot else None
        videos.append(VideoKetQua(
            thu_tu=v.thu_tu, nguon=v.nguon, ma=v.ma, tieu_de=v.tieu_de, kenh=v.kenh,
            thoi_luong=v.thoi_luong_that(), trang_thai=tt_cap,
            dai_dien=dai_dien(v, khoa, tt.cfg) if khoa is not None else None,
            pham_vi=cuoi.pham_vi if cuoi else "", so_luot=len(v.luot),
            loi=next((lq.ly_do for lq in reversed(v.luot) if lq.ly_do), "")))
    canh_bao = list(canh_bao_them)
    if khoa is not None:
        canh_bao += canh_bao_goc(tt, khoa, dem_ten)
    canh_bao += canh_bao_ten_trung_chung(tt, khoa)
    return KetQuaLo(
        ma_lo=ma_lo, trang_thai=kl.trang_thai, ly_do=kl.ly_do, kho_id=tt.kho_id,
        kho_ten=kho_ten, goc=khoa, la_nguon_chung=kl.trang_thai == TIM_THAY,
        so_co_mat=kl.so_co_mat, tong=kl.tong, goc_khac=kl.goc_khac,
        thong_tin_goc=dict(thong_tin_goc or {}), canh_bao=tuple(canh_bao),
        videos=tuple(videos), so_lieu=dict(so_lieu or {}), gioi_han=tuple(kl.gioi_han))


HEADER_NGUON_CHUNG = [
    "Mã lô", "Kết luận", "Video gốc", "Link video gốc", "Ngày đăng video gốc",
    "Thời lượng video gốc", "Clip trong kho", "Video vi phạm", "Link video vi phạm",
    "Kênh vi phạm", "Trạng thái trên video này", "Clip bắt đầu từ", "Đến",
    "🔗 Nhảy tới đúng mốc vi phạm", "Khớp từ giây thứ (của clip)", "Đoạn khớp (giây)",
    "Số hash khớp", "Tỷ lệ vân tay khớp (%)", "Phạm vi đã quét", "Ghi chú",
]
# Cột SỐ — giao diện ép kiểu theo danh sách này (ô trống thành NaN, xem CLAUDE.md mục 7).
COT_SO_NGUON_CHUNG = ("Khớp từ giây thứ (của clip)", "Đoạn khớp (giây)", "Số hash khớp",
                      "Tỷ lệ vân tay khớp (%)")


def nhan_ket_luan(kql: KetQuaLo) -> str:
    n = kql.tong
    if kql.trang_thai == TIM_THAY:
        return f"Tìm thấy video gốc chung {n}/{n}"
    if kql.trang_thai == KHONG_TIM_THAY:
        phan = (f" — ứng viên tốt nhất có mặt {kql.so_co_mat}/{n}" if kql.goc is not None
                else "")
        if kql.gioi_han:
            phan += " (chưa loại trừ tuyệt đối — xem Ghi chú)"
        return "Không tìm thấy video gốc chung" + phan
    if kql.trang_thai == DA_HUY:
        return "Đã dừng — chưa kết luận"
    return "Chưa kết luận được" + (
        f" — ứng viên tốt nhất có mặt {kql.so_co_mat}/{n}" if kql.goc is not None else "")


def dong_bao_cao(kql: KetQuaLo, an_toan: bool = True) -> list:
    """Mỗi video vi phạm đúng MỘT dòng; thông tin video gốc lặp lại để lọc dễ.

    ``an_toan``: chặn ô bị bảng tính hiểu là công thức (CSV). Bảng trên giao diện hiện
    nguyên văn nên truyền ``False``.
    """
    tt_goc = kql.thong_tin_goc or {}
    thoi_luong_goc = tt_goc.get("duration")
    ket = nhan_ket_luan(kql)
    # Giới hạn và cảnh báo của cả lô đi theo MỌI dòng: CSV là thứ được lưu lại và chuyển
    # tiếp, không được mất điều người kiểm tra cần biết (giống thông tin video gốc lặp lại).
    ghi_chu_lo = [*kql.gioi_han, *kql.canh_bao]
    rows = []
    for v in kql.videos:
        m = v.dai_dien
        rieng = v.loi.splitlines()[0][:200] if (
            v.loi and v.trang_thai in (LOI_QUET, CHUA_RO)) else ""
        ghi_chu = " | ".join(x for x in (rieng, *ghi_chu_lo) if x)
        dong = [
            kql.ma_lo, ket,
            tt_goc.get("title") or (kql.goc.clip if kql.goc else ""),
            tt_goc.get("url") or "",
            format_publication_date(tt_goc.get("upload_date") or ""),
            hhmmss(thoi_luong_goc) if isinstance(thoi_luong_goc, (int, float))
            and thoi_luong_goc > 0 else "",
            kql.goc.clip if kql.goc else "",
            v.tieu_de or v.nguon, v.nguon, v.kenh,
            TEN_TRANG_THAI_CAP.get(v.trang_thai, v.trang_thai),
            hhmmss(m.clip_bat_dau_s) if m else "",
            hhmmss(m.end_s) if m else "",
            Engine.link_moc(v.ma, v.nguon, m.start_s) if m else "",
            round(m.clip_offset_s) if m else "",
            round(m.matched_s) if m else "",
            int(m.hashes) if m else "",
            m.ty_le if m else "",
            v.pham_vi,
            ghi_chu,
        ]
        rows.append([o_bang_tinh_an_toan(o) for o in dong] if an_toan else dong)
    return rows


def tom_tat_so_lieu(tt: TrangThaiLo) -> dict:
    """Số liệu để đo hiệu năng: số lượt, trọn/một phần, theo mục tiêu."""
    tat_ca = [lq for v in tt.videos for lq in v.luot]
    return {
        "so_video": len(tt.videos),
        "so_luot": len(tat_ca),
        "luot_thu_thap": sum(1 for lq in tat_ca if lq.muc_tieu == MUC_TIEU_THU_THAP),
        "luot_xac_minh": sum(1 for lq in tat_ca if lq.muc_tieu == MUC_TIEU_XAC_MINH),
        "luot_tron": sum(1 for lq in tat_ca if lq.tron),
        "luot_mot_phan": sum(1 for lq in tat_ca if lq.hop_le and not lq.tron),
        "luot_loi": sum(1 for lq in tat_ca if not lq.hop_le),
        "luot_toi_da_moi_video": max((len(v.luot) for v in tt.videos), default=0),
        "trung_vi_luot_moi_video": statistics.median(
            [len(v.luot) for v in tt.videos]) if tt.videos else 0,
    }
