# -*- coding: utf-8 -*-
"""Phát hiện video vi phạm đã bị ĐỔI TỐC ĐỘ để né vân tay âm thanh.

VẤN ĐỀ

audfprint cực kỳ nhạy với co giãn thời gian. Đo thật trên một clip gốc 300 giây
(4.610 hash khi nguyên bản):

    lệch  0,5%  ->  đoạn khớp dài nhất còn  21,0s,   323 hash
    lệch  1%    ->  còn  10,6s,   169 hash
    lệch  2%    ->  còn   4,5s,    65 hash
    lệch  4%    ->  còn   1,5s,    28 hash

Nghĩa là chỉ cần tăng tốc 2% — tai người gần như không nhận ra — là bản reup tàng
hình trước hệ thống. Trong khi đó nén lại, đổi âm lượng, lọc tần số đều vô hại.

CÁCH GIẢI QUYẾT: ĐỌC ĐỘ TRÔI ALIGN, KHÔNG QUÉT MÙ

Điểm mấu chốt: dù bằng chứng vỡ vụn, các mảnh còn lại **không nằm ngẫu nhiên**.
Nếu video phát nội dung gốc ở tốc độ r thì một điểm ở giây t_o của bản gốc xuất
hiện ở giây t_q = t_o / r trong video. audfprint báo align = t_q − t_clip, mà
t_clip = t_o = r·t_q, nên:

    align = t_q − r·t_q = t_q · (1 − r)

align **tuyến tính** theo t_q, độ dốc đúng bằng (1 − r). Hồi quy độ dốc là ra tốc độ.

Đo thật trên 8 mức biến đổi, sai số ước lượng ≤ 0,0005 (tức 0,05%), R² ≥ 0,99:

    tempo thật 0,940 -> ước lượng 0,9398    tempo thật 1,010 -> ước lượng 1,00996
    tempo thật 0,980 -> ước lượng 0,98001   tempo thật 1,020 -> ước lượng 1,01991
    tempo thật 0,995 -> ước lượng 0,99491   tempo thật 1,040 -> ước lượng 1,03999

Chính xác hơn lưới quét mù bước 1% khoảng **100 lần**, mà tốn 0 giây so khớp: dữ
liệu cần thiết đã nằm sẵn trong output của lượt quét thường.

Nhờ độ chính xác đó, lượt so khớp xác nhận chạy ở tốc độ đã hiệu chỉnh có sai số
tồn dư ~0,01% — nằm gọn trong vùng audfprint hoạt động gần như hoàn hảo, nên bằng
chứng thu lại được gần đủ như bản chưa bị biến đổi.

VÙNG PHỦ

Đo giới hạn phát hiện (số mảnh còn lại đủ để hồi quy):

    đổi tốc độ giữ cao độ (atempo)   : dò được 0,94 … 1,05 ; từ ±8% trở đi hết mảnh
    đổi cả cao độ (resample)         : chỉ dò được tới ~±2% ; từ ±4% là 0 mảnh

Cao độ bị đổi thì các mốc phổ dịch đi, vân tay của audfprint hỏng hoàn toàn — không
mảnh nào sống sót nên không có gì để hồi quy. Vùng đó phải quét mù bằng lưới
`luoi_resample`; sau khi lưới kéo được về trong khoảng ~1%, bộ dò độ trôi lại tiếp
quản để tinh chỉnh về đúng tốc độ.

Module thuần: không I/O, không phụ thuộc giao diện.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Hai họ biến đổi cần bù, khác nhau ở chỗ có đụng tới cao độ hay không.
HO_TEMPO = "tempo"      # đổi tốc độ, giữ cao độ
HO_RESAMPLE = "resample"  # đổi cả tốc độ lẫn cao độ


@dataclass
class UocLuongTocDo:
    """Một ước lượng tốc độ phát của video vi phạm so với clip gốc."""
    ty_le: float           # r — >1 nghĩa là video phát NHANH hơn bản gốc
    r2: float              # tỉ lệ mảnh nằm đúng trên đường trôi (0..1)
    so_manh: int           # số mảnh nằm đúng trên đường trôi
    trai_dai_s: float      # các mảnh trải trên bao nhiêu giây
    clip: str = ""

    @property
    def he_so_bu(self) -> float:
        """Hệ số cần áp lên video để đưa về đúng tốc độ bản gốc.

        Video đang nhanh gấp r lần thì phải làm chậm lại, tức nhân tốc độ với 1/r.
        """
        return 1.0 / self.ty_le if self.ty_le else 1.0

    def mo_ta(self) -> str:
        chieu = "nhanh hơn" if self.ty_le > 1 else "chậm hơn"
        return (f"{abs(self.ty_le - 1) * 100:.2f}% {chieu} bản gốc "
                f"(r={self.ty_le:.5f}, {self.so_manh} mảnh thẳng hàng "
                f"={self.r2 * 100:.0f}%, trải {self.trai_dai_s:.0f}s)")


def _trung_vi(ds: list) -> float:
    ds = sorted(ds)
    n = len(ds)
    giua = n // 2
    return ds[giua] if n % 2 else (ds[giua - 1] + ds[giua]) / 2.0


def _binh_phuong_toi_thieu(diem: list) -> tuple | None:
    """Hồi quy bình phương tối thiểu; trả (độ dốc, chặn)."""
    n = len(diem)
    if n < 2:
        return None
    mx = sum(p[0] for p in diem) / n
    my = sum(p[1] for p in diem) / n
    sxx = sum((p[0] - mx) ** 2 for p in diem)
    if sxx <= 0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in diem)
    doc = sxy / sxx
    return doc, my - doc * mx


def _hoi_quy_ben(diem: list, dung_sai: float = 1.5,
                 toi_da_diem: int = 200) -> tuple | None:
    """Hồi quy BỀN theo Theil–Sen; trả (độ dốc, tỉ lệ điểm hợp, số điểm hợp).

    VÌ SAO KHÔNG DÙNG BÌNH PHƯƠNG TỐI THIỂU:
    trong cùng một clip gốc luôn lẫn hai loại mảnh — mảnh thật của bản reup (nằm
    thẳng hàng trên đường trôi) và mảnh của nhạc hiệu dùng chung (align ngẫu nhiên).
    Bình phương tối thiểu bị kéo lệch bởi nhóm thứ hai: đo trên fixture đổi tốc độ
    3%, R² dao động quanh đúng ngưỡng 0,90 nên chỉ cần dựng lại file là kết quả lật
    từ "phát hiện được" thành "không phát hiện được".

    Theil–Sen lấy TRUNG VỊ của độ dốc từng cặp điểm nên chịu được tới ~29% điểm
    nhiễu, rồi đếm số điểm nằm trong ``dung_sai`` giây quanh đường đã dựng. Cuối
    cùng khớp lại bằng bình phương tối thiểu CHỈ trên nhóm điểm hợp để lấy độ chính
    xác cao nhất.
    """
    if len(diem) < 3:
        return None
    # Nhiều điểm quá thì lấy mẫu đều để số cặp không bùng nổ; thứ tự theo thời gian
    # nên lấy mẫu đều vẫn phủ hết trục.
    if len(diem) > toi_da_diem:
        buoc = len(diem) / toi_da_diem
        diem = [diem[int(i * buoc)] for i in range(toi_da_diem)]

    docs = []
    for i in range(len(diem)):
        xi, yi = diem[i]
        for j in range(i + 1, len(diem)):
            dx = diem[j][0] - xi
            if abs(dx) < 1e-9:
                continue
            docs.append((diem[j][1] - yi) / dx)
    if not docs:
        return None
    doc = _trung_vi(docs)
    chan = _trung_vi([y - doc * x for x, y in diem])

    hop = [p for p in diem if abs(p[1] - (doc * p[0] + chan)) <= dung_sai]
    if len(hop) < 3:
        return None
    tinh = _binh_phuong_toi_thieu(hop)
    if tinh is not None:
        doc = tinh[0]
    return doc, len(hop) / len(diem), len(hop)


def uoc_luong_toc_do(
    tho: list,
    *,
    min_manh: int = 4,
    min_ty_le_hop: float = 0.60,
    lech_toi_thieu: float = 0.0015,
    lech_toi_da: float = 0.25,
    min_trai_dai_s: float = 60.0,
    toi_da: int = 3,
) -> list:
    """Đọc tốc độ phát từ độ trôi align của các mảnh khớp thô.

    ``tho`` là danh sách dict như ``Engine._match_chunks()`` trả về.

    Các ngưỡng đều nhằm loại nhiễu chứ không nhằm bắt thêm:

    * ``min_manh`` — dưới 4 mảnh thì một đường thẳng không nói lên điều gì.
    * ``min_ty_le_hop`` — tỉ lệ mảnh phải nằm đúng trên đường trôi. Bản reup bị đổi tốc độ
      cho tỉ lệ rất cao; một chùm trùng khớp ngẫu nhiên thì không.
    * ``lech_toi_thieu`` — dưới 0,15% thì coi như không lệch; đó là dao động bình
      thường của một bản khớp nguyên tốc độ.
    * ``min_trai_dai_s`` — các mảnh phải trải đủ rộng, nếu không độ dốc chỉ là
      nhiễu cục bộ được nhân lên.

    Trả về tối đa ``toi_da`` ước lượng, mạnh nhất trước.
    """
    theo_clip: dict = {}
    for x in tho:
        ten = os.path.basename(str(x.get("clip", "")))
        theo_clip.setdefault(ten, []).append(x)

    ket = []
    for ten, ds in theo_clip.items():
        if len(ds) < min_manh:
            continue
        diem = sorted(
            (float(x["bat_dau"]), float(x["bat_dau"]) - float(x["t_clip"]))
            for x in ds
        )
        trai_dai = diem[-1][0] - diem[0][0]
        if trai_dai < min_trai_dai_s:
            continue
        kq = _hoi_quy_ben(diem)
        if kq is None:
            continue
        doc, ty_le_hop, so_hop = kq
        r = 1.0 - doc
        if ty_le_hop < min_ty_le_hop or so_hop < min_manh:
            continue
        if not lech_toi_thieu <= abs(r - 1.0) <= lech_toi_da:
            continue
        ket.append(UocLuongTocDo(ty_le=r, r2=ty_le_hop, so_manh=so_hop,
                                 trai_dai_s=trai_dai, clip=ten))

    # Gộp các ước lượng gần trùng nhau: hai clip cùng bị reup từ một video thì cho
    # ra cùng một tốc độ, không cần quét lại hai lần.
    ket.sort(key=lambda u: (-u.so_manh, -u.r2))
    gon: list = []
    for u in ket:
        if any(abs(u.ty_le - g.ty_le) < 0.0005 for g in gon):
            continue
        gon.append(u)
        if len(gon) >= toi_da:
            break
    return gon


def bo_loc_ffmpeg(he_so: float, ho: str = HO_TEMPO, sr: int = 11025) -> str:
    """Chuỗi bộ lọc ffmpeg làm audio nhanh lên ``he_so`` lần.

    ``atempo`` chỉ giữ được cao độ và chỉ nhận 0,5..100 mỗi tầng — mọi hệ số dùng ở
    đây đều nằm trong khoảng đó. ``resample`` đổi cả cao độ, dùng để bù các bản bị
    tua nhanh kiểu băng (đổi cao độ theo).

    Phải ép ``aresample`` TRƯỚC ``asetrate`` vì bộ lọc nhìn thấy luồng ở tần số gốc
    của file (thường 48 kHz), không phải tần số ``-ar`` của đầu ra.
    """
    if ho == HO_RESAMPLE:
        return (f"aresample={sr},asetrate={int(round(sr * he_so))},"
                f"aresample={sr}")
    return f"atempo={he_so:.6f}"


def ma_he_so(he_so: float) -> str:
    """Mã hoá hệ số vào tên file khúc để đọc ngược lại khi quy đổi mốc thời gian."""
    return f"{int(round(he_so * 100000)):06d}"


def giai_ma_he_so(ma: str | None) -> float:
    if not ma:
        return 1.0
    try:
        return int(ma) / 100000.0
    except (TypeError, ValueError):
        return 1.0
