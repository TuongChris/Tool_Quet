# -*- coding: utf-8 -*-
"""Tiêu chí CHẤP NHẬN một ứng viên đã gộp vào báo cáo.

VẤN ĐỀ CỦA NGƯỠNG TUYỆT ĐỐI MỘT MÌNH

`min_hash_floor` là một con số hash tuyệt đối. Số hash mà một clip gốc có thể sinh
ra phụ thuộc độ dài và độ phong phú âm thanh của chính nó. Đo trên kho thật:

    kho SML          744 clip   ít hash nhất  6.239   -> ngưỡng 1000 luôn với tới
    kho Cory       1.717 clip   ít hash nhất    134   -> 3 clip KHÔNG BAO GIỜ đạt 1000
    kho duncanyounot 139 clip   ít hash nhất 17.146   -> ngưỡng 1000 luôn với tới

Với 3 clip của kho Cory, ngay cả khi video vi phạm chứa TRỌN VẸN clip gốc và khớp
100% vân tay, ứng viên vẫn bị loại vì về mặt toán học nó không thể đạt 1000 hash.
Đó là false negative do cấu trúc, không phải do bằng chứng yếu.

CÁCH XỬ LÝ

Thêm một đường chấp nhận thứ hai dựa trên chỉ số CHUẨN HOÁ, bên cạnh ngưỡng tuyệt
đối cũ. Thay đổi này CHỈ THÊM ứng viên, không bao giờ bỏ ứng viên mà luật cũ đã
nhận — nên không thể làm hồi quy kết quả đang đúng.

    Bậc A — bằng chứng tuyệt đối:  hashes >= min_hash_floor          (luật cũ, giữ nguyên)
    Bậc B — phủ vân tay cao:       ty_le >= ty_le_chap_nhan
                              VÀ   matched_s >= min_match_chap_nhan
                              VÀ   mật độ hash >= mat_do_toi_thieu

VÌ SAO BẬC B PHẢI CÓ ĐỦ BA ĐIỀU KIỆN

Đo trên dữ liệu quét thật, mỗi điều kiện chặn đúng một kiểu dương tính giả:

  * Chỉ dùng ty_le  -> lọt nhạc hiệu dùng chung. Đo được trên 11 video "Parody
    Marathon": nhạc kết dùng chung xuất hiện ở ~100 clip gốc KHÁC NHAU cùng lúc,
    mỗi lần 133 hash trong 8,8 giây, mật độ 15 hash/s. Mật độ cao nên bộ lọc mật
    độ không chặn được; chính `matched_s` mới chặn.
  * Chỉ dùng matched_s -> lọt trùng khớp thưa ngẫu nhiên. Đo trên video
    qUrJv94OzJE: một "đoạn khớp" trải 578,6 giây nhưng chỉ có 309 hash, tức
    0,53 hash/s — trong khi bản reup thật đo được 19,3 hash/s. Chính bộ lọc mật
    độ chặn ca này.
  * Chỉ dùng mật độ -> lọt mọi đoạn ngắn chất lượng tốt.

Số liệu tham chiếu dùng để hiệu chỉnh (đo thật, không phải ước lượng):

    bản reup thật (video 6,7 giờ) 15.173 hash / 786,8 s = 19,3 hash/s
    clip gốc nguyên bản            4.610 hash / 263,6 s = 17,5 hash/s   phủ 40,9%
    clip gốc nén lại Opus 32k      2.352 hash / 263,7 s =  8,9 hash/s   phủ 20,9%
    nhạc kết dùng chung              133 hash /   8,8 s = 15,1 hash/s   phủ  0,9%
    trùng khớp thưa ngẫu nhiên        309 hash / 578,6 s =  0,53 hash/s phủ  0,5%

Module thuần: không I/O, không phụ thuộc giao diện.
"""

from __future__ import annotations

from dataclasses import dataclass


BAC_TUYET_DOI = "tuyet_doi"
BAC_PHU_CAO = "phu_cao"


@dataclass
class KetQuaChapNhan:
    """Nhận hay loại, kèm lý do đọc được — phục vụ giải thích và gỡ lỗi."""
    chap_nhan: bool
    ly_do: str
    bac: str = ""

    def __bool__(self) -> bool:
        return self.chap_nhan


def mat_do_hash(m) -> float:
    """Số hash trên mỗi giây khớp. 0 khi không biết thời lượng."""
    dai = float(getattr(m, "matched_s", 0.0) or 0.0)
    if dai <= 0:
        return 0.0
    return float(getattr(m, "hashes", 0) or 0) / dai


def danh_gia_chap_nhan(m, cfg) -> KetQuaChapNhan:
    """Xét một ứng viên đã gộp theo hai bậc chấp nhận."""
    so_hash = int(getattr(m, "hashes", 0) or 0)
    ty_le = float(getattr(m, "ty_le", 0.0) or 0.0)
    dai = float(getattr(m, "matched_s", 0.0) or 0.0)
    mat_do = mat_do_hash(m)

    san = int(getattr(cfg, "min_hash_floor", 0) or 0)
    can_mat_do_a = float(getattr(cfg, "mat_do_bac_a", 0.0) or 0.0)
    if so_hash >= san:
        # Rào chắn cho bậc A: bằng chứng không được loãng tới mức vô nghĩa. Một ứng
        # viên 1.200 hash trải 2.000 giây (0,6 hash/s) vượt ngưỡng tuyệt đối nhưng
        # thực chất chỉ là các điểm trùng rải rác bám cùng một align.
        if can_mat_do_a <= 0 or mat_do >= can_mat_do_a:
            return KetQuaChapNhan(
                True, f"đạt {so_hash} hash ≥ ngưỡng tuyệt đối {san}", BAC_TUYET_DOI)

    can_ty_le = float(getattr(cfg, "ty_le_chap_nhan", 60.0) or 0.0)
    can_dai = float(getattr(cfg, "min_match_chap_nhan", 20.0) or 0.0)
    can_mat_do = float(getattr(cfg, "mat_do_toi_thieu", 3.0) or 0.0)

    # Bậc B chỉ mở khi có đủ cả ba tín hiệu; thiếu cái nào thì nói rõ thiếu cái đó.
    if can_ty_le > 0 and ty_le >= can_ty_le and dai >= can_dai and mat_do >= can_mat_do:
        return KetQuaChapNhan(
            True,
            f"phủ {ty_le:.1f}% vân tay clip gốc, khớp {dai:.0f}s, "
            f"mật độ {mat_do:.1f} hash/s",
            BAC_PHU_CAO,
        )

    if so_hash >= san:
        # Tới đây nghĩa là đủ hash nhưng trượt rào chắn mật độ — nói thẳng ra thế,
        # đừng báo "thiếu hash" vì như vậy là sai và người dùng sẽ đi hạ nhầm ngưỡng.
        thieu = [f"đủ {so_hash} hash nhưng bằng chứng quá loãng: "
                 f"mật độ {mat_do:.1f} < {can_mat_do_a:.1f} hash/s "
                 f"({so_hash} hash trải {dai:.0f}s)"]
    else:
        thieu = [f"{so_hash} hash < ngưỡng tuyệt đối {san}"]
    if can_ty_le > 0:
        if ty_le < can_ty_le:
            thieu.append(f"phủ {ty_le:.1f}% < {can_ty_le:.0f}%")
        elif dai < can_dai:
            thieu.append(f"khớp {dai:.0f}s < {can_dai:.0f}s")
        elif mat_do < can_mat_do:
            thieu.append(f"mật độ {mat_do:.1f} < {can_mat_do:.1f} hash/s")
    return KetQuaChapNhan(False, "; ".join(thieu))


def loc_chap_nhan(ds: list, cfg) -> tuple:
    """Chia ứng viên thành (đạt, không đạt, lý_do_theo_id).

    ``lý_do_theo_id`` tra bằng ``id(match)`` để chẩn đoán in được lý do đúng của
    ứng viên mạnh nhất bị loại mà không phải gắn thêm thuộc tính vào Match.
    """
    dat, loai, ly_do = [], [], {}
    for m in ds:
        kq = danh_gia_chap_nhan(m, cfg)
        ly_do[id(m)] = kq.ly_do
        (dat if kq.chap_nhan else loai).append(m)
    return dat, loai, ly_do
