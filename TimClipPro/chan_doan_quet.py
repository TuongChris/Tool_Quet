# -*- coding: utf-8 -*-
"""Chẩn đoán phễu phát hiện của một lượt quét.

VÌ SAO CẦN FILE NÀY

Trước đây khi quét xong mà không có kết quả, hệ thống chỉ nói "Không tìm thấy clip
gốc nào". Câu đó gộp chung ÍT NHẤT NĂM tình huống hoàn toàn khác nhau:

    1. audfprint không trả về dòng khớp nào       -> nghi kho/audio/tham số
    2. có dòng khớp nhưng parser đọc không ra     -> lỗi regex, phải sửa code ngay
    3. parse được nhưng bằng chứng quá yếu        -> đúng là không có gì
    4. gộp xong nhưng không đạt tiêu chí chấp nhận-> chính sách chọn lọc quá chặt
    5. đạt tiêu chí nhưng bước chọn lọc bỏ hết    -> lỗi logic chọn Top-N

Người dùng không phân biệt được, nên một kết quả ÂM TÍNH ĐÚNG trông y hệt một con
bug. Module này đếm số ứng viên còn sống sau từng tầng, ghi lại ứng viên MẠNH NHẤT
đã bị loại kèm lý do, và chỉ đúng tên tầng đã làm mất hết kết quả.

Module thuần dữ liệu: không I/O, không phụ thuộc giao diện, test được trực tiếp.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


# Mã giai đoạn làm mất hết kết quả. Dùng mã ổn định để log/test bám vào,
# phần chữ hiển thị cho người dùng nằm ở MO_TA_GIAI_DOAN.
KHONG_CAT_DUOC_KHUC = "khong_cat_duoc_khuc"
AUDFPRINT_KHONG_RA_MATCH = "audfprint_khong_ra_match"
PARSER_HONG = "parser_hong"
BANG_CHUNG_QUA_YEU = "bang_chung_qua_yeu"
KHONG_DAT_CHAP_NHAN = "khong_dat_chap_nhan"
CHON_LOC_BO_HET = "chon_loc_bo_het"

MO_TA_GIAI_DOAN = {
    KHONG_CAT_DUOC_KHUC:
        "Không cắt được khúc audio nào từ file — nghi file tải hỏng hoặc ffmpeg lỗi.",
    AUDFPRINT_KHONG_RA_MATCH:
        "audfprint không trả về dòng khớp nào. Nghi: sai kho vân tay, kho rỗng, "
        "hoặc audio tải về không đúng nội dung.",
    PARSER_HONG:
        "audfprint CÓ trả về dòng khớp nhưng không đọc ra được dòng nào. "
        "Gần như chắc chắn định dạng output đã đổi — đây là lỗi code, phải sửa.",
    BANG_CHUNG_QUA_YEU:
        "Có dòng khớp nhưng tất cả đều quá ngắn hoặc quá ít hash, bị loại ngay ở "
        "bộ lọc thô. Nhiều khả năng video này không chứa clip gốc nào trong kho.",
    KHONG_DAT_CHAP_NHAN:
        "Đã gộp được ứng viên nhưng không ứng viên nào đạt tiêu chí chấp nhận. "
        "Xem ứng viên mạnh nhất bị loại để biết còn thiếu bao nhiêu.",
    CHON_LOC_BO_HET:
        "Có ứng viên đạt tiêu chí nhưng bước chọn Top-N không giữ lại cái nào — "
        "đây là lỗi logic chọn lọc, phải sửa.",
}


@dataclass
class UngVienBiLoai:
    """Ảnh chụp ứng viên mạnh nhất đã bị loại, kèm lý do cụ thể."""
    clip: str = ""
    hashes: int = 0
    tong_hash_clip: int = 0
    ty_le: float = 0.0
    matched_s: float = 0.0
    start_s: float = 0.0
    mat_do_hash: float = 0.0      # hash trên mỗi giây khớp
    ly_do: str = ""

    def mo_ta(self) -> str:
        phan = [f"«{self.clip}»", f"{self.hashes} hash"]
        if self.tong_hash_clip:
            phan.append(f"/{self.tong_hash_clip} của clip gốc")
        if self.ty_le:
            phan.append(f"phủ {self.ty_le:.1f}%")
        phan.append(f"khớp {self.matched_s:.1f}s")
        phan.append(f"mật độ {self.mat_do_hash:.1f} hash/s")
        chuoi = ", ".join(phan)
        return f"{chuoi}. Bị loại vì: {self.ly_do}" if self.ly_do else chuoi


@dataclass
class ChanDoanQuet:
    """Số ứng viên còn sống sau từng tầng của phễu phát hiện."""

    so_khuc: int = 0
    dong_tho: int = 0             # tổng số dòng audfprint ghi ra
    dong_co_matched: int = 0      # số dòng chứa chữ "Matched"
    parse_duoc: int = 0           # số dòng parser đọc ra được
    qua_min_hash: int = 0
    qua_min_match_s: int = 0
    gop_lai: int = 0              # số ứng viên sau _merge
    duoc_chap_nhan: int = 0       # số ứng viên qua tiêu chí chấp nhận
    da_chon: int = 0              # số kết quả cuối cùng (Top-N)

    hash_tho_lon_nhat: int = 0
    khop_tho_dai_nhat: float = 0.0

    # Trần --max-matches có bị chạm không: chạm nghĩa là ĐANG MẤT kết quả.
    tran_max_matches: int = 0
    so_khuc_cham_tran: int = 0

    manh_nhat_bi_loai: Optional[UngVienBiLoai] = None
    giai_doan_mat: str = ""
    canh_bao: list = field(default_factory=list)

    # Đường đi nhanh Top-1 đã dùng tới đâu (rỗng = không dùng).
    duong_di: str = ""

    # Bù tốc độ: các phương án đã thử, và phương án cứu được kết quả (nếu có).
    da_thu_toc_do: list = field(default_factory=list)
    toc_do_tim_duoc: str = ""

    # ---------------------------------------------------------------

    def chot_giai_doan(self) -> str:
        """Xác định tầng nào đã làm mất hết kết quả. Có kết quả thì trả về rỗng."""
        if self.da_chon > 0:
            self.giai_doan_mat = ""
            return ""
        if self.so_khuc == 0:
            self.giai_doan_mat = KHONG_CAT_DUOC_KHUC
        elif self.dong_co_matched == 0:
            self.giai_doan_mat = AUDFPRINT_KHONG_RA_MATCH
        elif self.parse_duoc == 0:
            self.giai_doan_mat = PARSER_HONG
        elif self.qua_min_match_s == 0 or self.gop_lai == 0:
            self.giai_doan_mat = BANG_CHUNG_QUA_YEU
        elif self.duoc_chap_nhan == 0:
            self.giai_doan_mat = KHONG_DAT_CHAP_NHAN
        else:
            self.giai_doan_mat = CHON_LOC_BO_HET
        return self.giai_doan_mat

    def mat_o_dau(self) -> str:
        """Câu giải thích cho người dùng; rỗng khi lượt quét có kết quả."""
        if not self.giai_doan_mat:
            return ""
        return MO_TA_GIAI_DOAN.get(self.giai_doan_mat, self.giai_doan_mat)

    def tom_tat(self) -> str:
        """Một dòng phễu gọn cho log và cho phần 'chi tiết chẩn đoán' trên UI."""
        return (
            f"khúc={self.so_khuc} → dòng khớp thô={self.dong_co_matched} "
            f"→ đọc được={self.parse_duoc} → qua lọc thô={self.qua_min_match_s} "
            f"→ gộp={self.gop_lai} → đạt chuẩn={self.duoc_chap_nhan} "
            f"→ chọn={self.da_chon}"
        )

    def dong_log(self) -> str:
        """Chuỗi key=value cho structured logging."""
        phan = [
            f"chunks={self.so_khuc}",
            f"raw_matched={self.dong_co_matched}",
            f"parsed={self.parse_duoc}",
            f"after_min_hash={self.qua_min_hash}",
            f"after_min_match_s={self.qua_min_match_s}",
            f"merged={self.gop_lai}",
            f"accepted={self.duoc_chap_nhan}",
            f"selected={self.da_chon}",
            f"strongest_raw_hash={self.hash_tho_lon_nhat}",
            f"longest_raw_s={self.khop_tho_dai_nhat:.1f}",
        ]
        if self.so_khuc_cham_tran:
            phan.append(f"chunks_at_max_matches={self.so_khuc_cham_tran}")
        if self.giai_doan_mat:
            phan.append(f"zero_stage={self.giai_doan_mat}")
        if self.duong_di:
            phan.append(f"path={self.duong_di}")
        if self.da_thu_toc_do:
            phan.append(f"tempo_tried={len(self.da_thu_toc_do)}")
        if self.toc_do_tim_duoc:
            phan.append("tempo_recovered=1")
        if self.manh_nhat_bi_loai:
            u = self.manh_nhat_bi_loai
            phan.append(f"strongest_rejected_hash={u.hashes}")
            phan.append(f"strongest_rejected_ratio={u.ty_le:.1f}")
        return " ".join(phan)

    def thanh_dict(self) -> dict:
        """Bản ghi JSON được cho file chẩn đoán; không chứa đường dẫn nhạy cảm."""
        d = asdict(self)
        d["mat_o_dau"] = self.mat_o_dau()
        return d


def ghi_nhan_bi_loai(chan_doan: ChanDoanQuet, ung_vien: list, tong_hash: dict,
                     ly_do_theo_clip: dict | None = None) -> None:
    """Ghi lại ứng viên MẠNH NHẤT bị loại để người dùng soi được.

    Chọn theo số hash tuyệt đối vì đó là thước đo bằng chứng dễ hiểu nhất khi
    giải thích "còn thiếu bao nhiêu mới đạt".
    """
    if not ung_vien:
        return
    manh = max(ung_vien, key=lambda m: (int(getattr(m, "hashes", 0) or 0),
                                        float(getattr(m, "matched_s", 0) or 0)))
    ten = str(getattr(manh, "clip", ""))
    dai = float(getattr(manh, "matched_s", 0.0) or 0.0)
    so_hash = int(getattr(manh, "hashes", 0) or 0)
    chan_doan.manh_nhat_bi_loai = UngVienBiLoai(
        clip=ten,
        hashes=so_hash,
        tong_hash_clip=int(tong_hash.get(ten, 0) or 0),
        ty_le=float(getattr(manh, "ty_le", 0.0) or 0.0),
        matched_s=dai,
        start_s=float(getattr(manh, "start_s", 0.0) or 0.0),
        mat_do_hash=round(so_hash / dai, 2) if dai > 0 else 0.0,
        ly_do=(ly_do_theo_clip or {}).get(id(manh), ""),
    )
