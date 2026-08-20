# -*- coding: utf-8 -*-
r"""
engine.py — LÕI của hệ thống TimClip Pro.

Nhiệm vụ: tải audio từ YouTube, cắt khúc, so khớp vân tay âm thanh với kho clip gốc,
lưu lịch sử vào SQLite và trả về kết quả dưới dạng dữ liệu Python thuần.

NGUYÊN TẮC THIẾT KẾ QUAN TRỌNG:
    File này KHÔNG BIẾT nó đang được gọi từ đâu (Streamlit, CLI, FastAPI, hay desktop app).
    Nó không print ra màn hình, không đọc bàn phím. Mọi thông tin tiến độ được gửi ra ngoài
    qua hàm callback `progress(pct, msg)`. Nhờ vậy bạn có thể thay giao diện bất cứ lúc nào
    mà không phải sửa một dòng nào trong file này.

Cách dùng từ code khác:
    from engine import Engine, Config
    eng = Engine()
    eng.build_database(r"D:\ClipGoc", mode="new", progress=print_ra_dau_do)
    kq = eng.scan_youtube("https://youtu.be/xxxx")
    for m in kq.matches:
        print(m.clip, m.start_hhmmss, m.end_hhmmss, m.confidence)
"""

from __future__ import annotations

import contextlib
import csv
import glob
import io
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, Optional

import channel
import cau_hinh
import ytdlp_chung
import dossier
from chan_doan_quet import ChanDoanQuet, ghi_nhan_bi_loai
from chap_nhan_khop import loc_chap_nhan
from toc_do_khop import (
    HO_RESAMPLE,
    HO_TEMPO,
    bo_loc_ffmpeg,
    giai_ma_he_so,
    ma_he_so,
    uoc_luong_toc_do,
)
from clip_metadata import (
    ClipMetadataResolver,
    MetadataAudit,
    MetadataRepairResult,
    basename_compatible,
    load_metadata_strict,
    source_from_mapping,
)
from fingerprint_progress import (
    dong_fingerprint_logger,
    FingerprintProgress,
    FingerprintProgressTracker,
    tao_fingerprint_logger,
    ten_file_an_toan,
)
from khoa import KhoaTienTrinh
from luu_tru import LoiDuLieu, doc_json_an_toan, ghi_json_an_toan
from process_runner import ProcessSnapshot, run_observed_process
from publication_date import ghi_log_chan_doan, resolve_publication_date


LOGGER_METADATA = logging.getLogger("clip_metadata")
LOGGER_SCAN = logging.getLogger("scan.job")

# Phase mà wrapper audfprint được phép áp cho một clip đang chạy. Danh sách hẹp để
# một dòng stdout bị hỏng không đẩy job sang trạng thái kết thúc giả.
PHASES_FINGERPRINT = frozenset({"decoding", "fingerprinting", "probing"})

# =====================================================================
#  Kiểu dữ liệu
# =====================================================================

# Các đuôi file được coi là media khi quét thư mục clip gốc
MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m4v",
              ".mpg", ".mpeg", ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"}


@dataclass
class Config:
    """Toàn bộ tham số điều chỉnh được của hệ thống."""
    chunk_s: int = 3600        # Độ dài mỗi khúc audio khi cắt video dài (giây)
    overlap_s: int = 600       # Khúc gối đề xuất khi không có metadata thời lượng
    overlap_max_s: int = 180   # Trần khúc gối; giảm quét lặp, mặc định 3 phút
    overlap_tu_dong: bool = True  # Tự tính overlap theo clip dài nhất trong kho
    min_hash: int = 15         # Số hash khớp tối thiểu để tính là kết quả
    min_match_s: float = 5.0   # Đoạn khớp phải dài tối thiểu bao nhiêu giây
    max_matches: int = 200     # Số kết quả tối đa audfprint trả về mỗi khúc
    ncores: int = 0            # 0 = tự dò theo số nhân CPU
    dedup_s: float = 20.0      # Ngưỡng gộp 2 kết quả trùng nhau (do các khúc gối nhau)
    # Shifts cao hơn tăng độ chính xác nhưng chạy chậm và làm kho lớn hơn; 0 = hành vi cũ.
    shifts_kho: int = 4        # Subframe shifts khi tạo kho vân tay
    shifts_quet: int = 4       # Subframe shifts khi quét video dài
    # Định dạng yt-dlp cho ĐƯỜNG QUÉT. Chặn trần bitrate vì `_cut_chunks()` chuyển mọi
    # thứ về WAV mono 11025 Hz trước khi đưa cho audfprint — tức phổ trên 5,5 kHz bị
    # vứt đi ngay. Tải 130 kbps là trả tiền cho dữ liệu bị ném đi.
    #
    # Đo 2026-08-19 trên 10 phút audio thật (cắt từ giờ thứ 3 của video 88 tiếng),
    # đếm hash bằng chính audfprint:
    #     128 kbps -> 47.399 hash (mốc so sánh)
    #      64 kbps -> 47.623 hash  (100,5%)
    #      48 kbps -> 47.539 hash  (100,3%)
    #      32 kbps -> 45.118 hash  ( 95,2%)
    # Nên trần 70 kbps: giữ trọn chất lượng khớp, giảm ~60% băng thông.
    #
    # `/ba/b` ở cuối là đường lui bắt buộc: video nào không có format dưới 70 kbps thì
    # vẫn tải bình thường thay vì thất bại.
    #
    # KHÔNG áp trần này cho `channel.py` (kho clip gốc): clip trong kho là VÂN TAY
    # THAM CHIẾU, hạ chất lượng nguồn ở đó là hạ chuẩn cho mọi lượt đối chiếu về sau.
    ytdlp_format: str = "ba[abr<=70]/ba/b"
    # Thứ tự "player client" thử khi tải. YouTube chặn từng client độc lập và đổi
    # theo thời gian, nên phải có đường lui thay vì khoá cứng một cái. Chuỗi rỗng
    # nghĩa là để yt-dlp tự chọn. Đo 2026-08-18: mặc định trả 403 cho mọi video tải
    # mới, `android` vẫn chạy — nên `android` đứng trước.
    # Danh sách nằm ở ytdlp_chung.py để đường quét và đường đồng bộ kênh dùng chung.
    ytdlp_player_clients: list = field(
        default_factory=lambda: list(ytdlp_chung.PLAYER_CLIENTS_MAC_DINH))
    # --- Xác thực & giãn nhịp, chống YouTube coi là bot ---
    # CHỈ lưu ĐƯỜNG DẪN file cookie, tuyệt đối không lưu nội dung: cau_hinh.lay_tu_config()
    # serialize mọi trường Config ra data/cau_hinh.json mà không có danh sách trắng.
    # Kiểu phải là `str`/`float` thuần (không Optional) vì cau_hinh.ap_vao_config so
    # kiểu bằng `type(x) is not type(y)`, giá trị None sẽ bị loại sạch.
    ytdlp_cookiefile: str = ""        # đường dẫn cookies.txt xuất từ trình duyệt
    ytdlp_cookies_browser: str = ""   # "chrome" hoặc "edge:Tên Profile"
    # Giãn nhịp giữa các request lúc TRÍCH XUẤT — đúng chỗ bot-check của YouTube đánh.
    # Đo 2026-08-18: sau khoảng 12 lượt tải liên tiếp cộng một phiên quét, YouTube chặn
    # cả IP; chính những video vừa tải xong một tiếng trước cũng bị từ chối.
    ytdlp_sleep_requests_s: float = 1.0
    ytdlp_sleep_min_s: float = 0.0    # giãn nhịp khâu TẢI (0 = tắt)
    ytdlp_sleep_max_s: float = 0.0
    # --- Quét tăng dần cho video rất dài ---
    # Quét từng đoạn từ đầu; thấy bằng chứng đạt chuẩn thì DỪNG, không thấy thì quét
    # tiếp phần còn lại. Nhờ đó không mất video nào mà vẫn nhanh cho đa số.
    #
    # Đo 19/08 trên video 35 tiếng (quét trọn hết 40 phút): 180 đoạn khớp rải ĐỀU,
    # khoảng cách giữa hai đoạn liên tiếp lớn nhất chỉ 19 phút, và cả 64 vị trí cửa sổ
    # 3 tiếng đều bắt được video. Với `top_n=1`, bằng chứng chọn từ 1 giờ đầu có 43.815
    # hash so với 47.432 hash khi quét trọn — tức 92% sức mạnh, từ 1/35 khối lượng.
    #
    # Vì sao vẫn phải quét tiếp khi không thấy: số liệu trên đúng với video TỔNG HỢP
    # dày đặc. Một video chỉ lấy trộm đúng một clip ở giờ thứ 30 sẽ bị bỏ sót nếu dừng
    # sớm. Dừng-khi-thấy giữ nguyên độ phủ, chỉ đổi THỨ TỰ làm việc.
    quet_tang_dan: bool = True
    quet_tang_dan_tu_gio: float = 10.0    # chỉ áp dụng cho video dài hơn mốc này
    quet_tang_dan_buoc_gio: float = 3.0   # mỗi lượt quét thêm bấy nhiêu giờ
    # Chỉ TẢI phần đầu thay vì cả video. Đo 19/08: yt-dlp `download_ranges` thật sự
    # chỉ lấy đúng khoảng byte cần (video 15 phút: trọn 80,50 MB, 60 giây đầu 5,50 MB).
    # Video 66 tiếng của người dùng: 18,4 GB xuống khoảng 840 MB.
    # Không thấy gì trong phần đầu thì tải nốt phần còn lại — không mất độ phủ.
    tai_mot_phan: bool = True
    network_timeout_s: int = 30  # Timeout socket cho request/tải YouTube
    keep_downloads: bool = True  # Giữ lại audio đã tải để lần sau khỏi tải lại
    ghi_tung_phan: bool = True   # Ghi Sheets ngay sau mỗi video giám sát
    dem_max_gb: float = 20.0    # Ngân sách kho đệm; đặt 0 để tắt giới hạn dung lượng
    dem_max_ngay: int = 7       # Tuổi tối đa của file đệm; đặt 0 để tắt giới hạn tuổi

    # --- Chọn lọc kết quả cuối cùng ---
    top_n: int = 5               # Chỉ giữ lại bao nhiêu kết quả tốt nhất
    min_hash_floor: int = 1000   # Dưới ngưỡng này: LOẠI HẲN, không đưa vào báo cáo
    min_hash_strong: int = 5000  # Từ ngưỡng này: coi là bằng chứng mạnh, ưu tiên chọn
    # --- Đường chấp nhận thứ hai: phủ vân tay cao (xem chap_nhan_khop.py) ---
    # Số hash tuyệt đối mà một clip gốc sinh ra phụ thuộc độ dài của chính nó, nên
    # `min_hash_floor` một mình tạo false negative với clip ngắn: đo trên kho Cory
    # có 3/1717 clip tổng hash < 1000, tức khớp 100% vẫn không bao giờ đạt ngưỡng.
    # Ba điều kiện dưới phải ĐỒNG THỜI đúng thì mới mở đường chấp nhận thứ hai;
    # mỗi cái chặn một kiểu dương tính giả đã đo được trên dữ liệu quét thật.
    ty_le_chap_nhan: float = 60.0      # % vân tay clip gốc phải khớp được
    min_match_chap_nhan: float = 20.0  # đoạn khớp phải dài tối thiểu (giây)
    mat_do_toi_thieu: float = 3.0      # hash trên mỗi giây khớp
    # Rào chắn mật độ cho BẬC A (ngưỡng hash tuyệt đối). Đây là tham số duy nhất
    # trong nhóm này có thể LẤY ĐI kết quả, nên để riêng khỏi `mat_do_toi_thieu`:
    # siết bậc B không được vô tình siết luôn bậc A. Đo trên 1.198 match đã từng
    # được báo cáo trong lịch sử: mật độ thấp nhất là 9,99 hash/s, p1 = 11,52.
    # Mức 3,0 vì vậy loại 0/1.198 kết quả cũ — nó là rào chắn chống ca bệnh lý
    # (1.200 hash trải 2.000 giây = 0,6 hash/s), không phải bộ lọc. Đặt 0 để tắt.
    mat_do_bac_a: float = 3.0
    # --- Tìm nhanh một kết quả khi top_n = 1 ---
    top1_tim_nhanh: bool = True   # Quét vùng đầu trước, đủ mạnh thì dừng luôn
    top1_khuc_toi_thieu: int = 3  # Chỉ bật khi video có từ ngần này khúc trở lên
    top1_hash_dung_som: int = 5000     # Dừng sớm nếu ứng viên đạt ngần này hash
    top1_match_s_dung_som: float = 60.0  # ... và khớp liên tục ngần này giây
    # --- Bù video bị đổi tốc độ để né vân tay (xem toc_do_khop.py) ---
    # Chỉ chạy khi lượt quét thường KHÔNG có ứng viên nào đạt chuẩn, nên đường đi
    # bình thường không tốn thêm một giây nào.
    quet_da_toc_do: bool = True
    # Ước lượng tốc độ từ độ trôi align: gần như miễn phí, phủ đổi tốc độ ±6%.
    toc_do_min_manh: int = 4          # Số mảnh tối thiểu để hồi quy
    toc_do_thang_hang: float = 0.60   # Tỉ lệ mảnh phải nằm đúng trên đường trôi
    toc_do_lech_toi_thieu: float = 0.0015   # Dưới 0,15% coi như không lệch
    toc_do_lech_toi_da: float = 0.25
    # Lưới quét mù, chỉ để bù vùng bộ dò độ trôi không thấy: cao độ bị đổi thì mọi
    # mốc phổ dịch đi, không mảnh nào sống sót nên không có gì để hồi quy.
    luoi_resample: list = field(default_factory=lambda: [0.96, 0.98, 1.02, 1.04])
    # Đổi tốc độ giữ cao độ đã được bộ dò độ trôi phủ tới ±6% nên lưới này để rỗng.
    luoi_tempo: list = field(default_factory=list)
    toc_do_toi_da_thu: int = 6        # Trần số lượt so khớp phụ mỗi video
    phan_bo_deu: bool = True     # Chia video vi phạm thành N vùng, mỗi vùng lấy 1 kết quả
    uu_tien_clip_khac_nhau: bool = True  # Ưu tiên 5 clip GỐC KHÁC NHAU thay vì trùng lặp
    # Hai ứng viên chênh nhau trong dung sai này thì coi là NGANG BẰNG về bằng
    # chứng; lúc đó mới ưu tiên đoạn dễ kiểm tra hơn. Đo trên 200 job thật:
    # trung vị hashes(#2)/hashes(#1) = 0,92 nên near-tie là chuyện thường —
    # dung sai lỏng sẽ đảo phần lớn kết quả. Ở mức 0,03 chỉ 24% job có ứng viên
    # lọt dải, và chỉ một phần trong đó thực sự sớm hơn.
    dung_sai_gan_bang: float = 0.03
    # "ty_le" = % vân tay của clip gốc khớp được — chỉ số CHUẨN HOÁ, so sánh công
    # bằng giữa clip dài và clip ngắn. "hashes" = số hash tuyệt đối, phụ thuộc độ
    # dài và độ phong phú âm thanh. Đổi được mà không phải sửa code.
    khoa_chat_luong: str = "ty_le"
    # Sàn bằng chứng cho khoá chuẩn hoá: ứng viên chỉ được phép thắng nhờ ty_le nếu
    # bằng chứng TUYỆT ĐỐI của nó không sụp đổ so với ứng viên mạnh nhất trong nhóm.
    # Đo trên 283 job thật: bỏ sàn thì 18% số ca đổi là đánh đổi nặng — ví dụ thay
    # đoạn 22,8 phút / 36.939 hash bằng đoạn 9,4 phút / 13.129 hash chỉ vì tỉ lệ
    # phần trăm cao hơn. Ở mức 0,70 những ca đó bị chặn, các ca cải thiện vẫn giữ.
    san_bang_chung: float = 0.70

    def validate(self, overlap_s: Optional[int] = None) -> None:
        if self.chunk_s <= 60:
            raise ValueError("chunk_s phải lớn hơn 60 giây.")
        if self.overlap_max_s < 60:
            raise ValueError("overlap_max_s phải >= 60 giây.")
        if self.overlap_max_s >= self.chunk_s:
            raise ValueError("overlap_max_s phải nhỏ hơn chunk_s.")
        de_xuat = self.overlap_s if overlap_s is None else overlap_s
        overlap = min(self.overlap_max_s, de_xuat)
        if self.chunk_s <= overlap:
            raise ValueError("chunk_s phải lớn hơn overlap_s.")
        if overlap < 60:
            raise ValueError("overlap_s nên >= 60 giây để không bỏ sót clip nằm vắt qua ranh giới.")
        if self.min_hash < 1:
            raise ValueError("min_hash phải >= 1.")
        if self.min_match_s < 0:
            raise ValueError("min_match_s không được âm.")
        if self.max_matches < 1:
            raise ValueError("max_matches phải >= 1.")
        if not 0 <= self.ncores <= 64:
            raise ValueError("ncores phải nằm trong khoảng 0..64.")
        if not isinstance(self.ytdlp_player_clients, list) or not all(
            isinstance(x, str) for x in self.ytdlp_player_clients
        ):
            raise ValueError("ytdlp_player_clients phải là danh sách chuỗi.")
        if not self.ytdlp_player_clients:
            raise ValueError(
                "ytdlp_player_clients không được rỗng; dùng [\"\"] để giữ mặc định yt-dlp."
            )
        # KHÔNG kiểm tra os.path.exists() ở đây: validate() chạy lúc nạp cấu hình trong
        # try/except, ném lỗi sẽ reset TOÀN BỘ cấu hình người dùng về mặc định. File
        # cookie thiếu chỉ được cảnh báo ở thời điểm dùng.
        for ten in ("ytdlp_cookiefile", "ytdlp_cookies_browser"):
            if not isinstance(getattr(self, ten), str):
                raise ValueError(f"{ten} phải là chuỗi.")
        for ten in ("ytdlp_sleep_requests_s", "ytdlp_sleep_min_s", "ytdlp_sleep_max_s"):
            if not 0 <= float(getattr(self, ten)) <= 60:
                raise ValueError(f"{ten} phải nằm trong khoảng 0..60 giây.")
        if self.ytdlp_sleep_max_s and self.ytdlp_sleep_max_s < self.ytdlp_sleep_min_s:
            raise ValueError("ytdlp_sleep_max_s không được nhỏ hơn ytdlp_sleep_min_s.")
        if not 5 <= self.network_timeout_s <= 300:
            raise ValueError("network_timeout_s phải nằm trong khoảng 5..300 giây.")
        if self.dedup_s < 0:
            raise ValueError("dedup_s không được âm.")
        if not 0 <= self.shifts_kho <= 8 or not 0 <= self.shifts_quet <= 8:
            raise ValueError("shifts_kho và shifts_quet phải nằm trong khoảng 0..8.")
        if self.top_n < 1:
            raise ValueError("top_n phải >= 1.")
        if not 0.0 <= self.dung_sai_gan_bang <= 0.5:
            raise ValueError("dung_sai_gan_bang phải nằm trong khoảng 0..0.5.")
        if self.khoa_chat_luong not in {"hashes", "ty_le"}:
            raise ValueError("khoa_chat_luong phải là 'hashes' hoặc 'ty_le'.")
        if not 0.0 <= self.san_bang_chung <= 1.0:
            raise ValueError("san_bang_chung phải nằm trong khoảng 0..1.")
        if self.min_hash_floor < 0 or self.min_hash_strong < 0:
            raise ValueError("Ngưỡng hash chọn lọc không được âm.")
        if not 0.0 <= self.ty_le_chap_nhan <= 100.0:
            raise ValueError("ty_le_chap_nhan phải nằm trong khoảng 0..100.")
        if self.min_match_chap_nhan < 0 or self.mat_do_toi_thieu < 0:
            raise ValueError("Tiêu chí chấp nhận theo tỷ lệ không được âm.")
        if self.mat_do_bac_a < 0:
            raise ValueError("mat_do_bac_a không được âm.")
        if self.mat_do_bac_a > 9.0:
            # Đo trên 1.198 match thật: mật độ thấp nhất là 9,99 hash/s. Vượt 9,0 là
            # bắt đầu cắt vào bằng chứng thật, gần như chắc chắn do gõ nhầm.
            raise ValueError(
                "mat_do_bac_a > 9,0 hash/s sẽ loại cả những đoạn khớp thật "
                "(đo trên lịch sử: mật độ thấp nhất của match hợp lệ là 9,99)."
            )
        if self.top1_khuc_toi_thieu < 1:
            raise ValueError("top1_khuc_toi_thieu phải >= 1.")
        if self.top1_hash_dung_som < 0 or self.top1_match_s_dung_som < 0:
            raise ValueError("Ngưỡng dừng sớm Top-1 không được âm.")
        if self.toc_do_min_manh < 3:
            raise ValueError("toc_do_min_manh phải >= 3 để hồi quy có nghĩa.")
        if not 0.0 <= self.toc_do_thang_hang <= 1.0:
            raise ValueError("toc_do_thang_hang phải nằm trong khoảng 0..1.")
        if not 0 < self.toc_do_lech_toi_thieu < self.toc_do_lech_toi_da <= 0.5:
            raise ValueError(
                "Phải có 0 < toc_do_lech_toi_thieu < toc_do_lech_toi_da <= 0.5."
            )
        if self.toc_do_toi_da_thu < 0:
            raise ValueError("toc_do_toi_da_thu không được âm.")
        for ten in ("luoi_resample", "luoi_tempo"):
            for k in getattr(self, ten):
                if not isinstance(k, (int, float)) or not 0.5 <= float(k) <= 2.0:
                    raise ValueError(f"{ten} chỉ nhận hệ số trong khoảng 0,5..2,0.")
        if self.dem_max_gb < 0 or self.dem_max_ngay < 0:
            raise ValueError("Giới hạn kho đệm không được âm.")


@dataclass
class Match:
    """Một lần clip gốc xuất hiện trong video dài."""
    clip: str              # tên file clip gốc
    start_s: float         # thời điểm clip bắt đầu trong video dài
    end_s: float           # đến giây thứ mấy
    matched_s: float       # độ dài đoạn khớp đã xác nhận
    clip_offset_s: float   # khớp bắt đầu từ giây thứ mấy CỦA CLIP GỐC
    hashes: int            # số hash khớp — bằng chứng, càng cao càng chắc
    confidence: str        # đánh giá dạng chữ
    ty_le: float = 0.0     # % vân tay của clip gốc khớp được (chỉ số CHUẨN HOÁ)
    vung: str = ""         # Đầu / Giữa / Cuối video vi phạm
    clip_bat_dau_s: float = 0.0  # thời điểm CLIP bắt đầu trong video dài
    vung_khop_s: float = 0.0     # thời điểm VÙNG KHỚP bắt đầu

    @property
    def start_hhmmss(self) -> str:
        return hhmmss(self.start_s)

    @property
    def clip_bat_dau_hhmmss(self) -> str:
        return hhmmss(self.clip_bat_dau_s)

    @property
    def end_hhmmss(self) -> str:
        return hhmmss(self.end_s)


@dataclass
class ScanResult:
    """Kết quả quét một nguồn (1 link YouTube hoặc 1 file)."""
    source_name: str
    source_ref: str = ""
    source_id: str = ""      # ID video YouTube (để tạo link nhảy tới đúng mốc)
    duration_s: float = 0.0
    matches: list = field(default_factory=list)        # kết quả ĐÃ CHỌN (top N)
    matches_loai: list = field(default_factory=list)   # bị loại vì dưới ngưỡng
    status: str = "ok"      # ok | error
    note: str = ""
    job_id: Optional[int] = None
    channel_name: str = ""
    channel_id: str = ""
    channel_url: str = ""
    upload_date: str = ""
    # Số ứng viên ĐẠT tiêu chí chấp nhận trước khi cắt còn Top-N. Ý nghĩa này giữ
    # nguyên như trước; chỉ có định nghĩa "đạt" là mở rộng thêm bậc phủ vân tay cao.
    so_dat_nguong: int = 0
    # Phễu phát hiện của chính lượt quét này. Nhờ nó mà một kết quả 0 đoạn nói được
    # nó mất ở tầng nào, thay vì chỉ nói "không tìm thấy".
    chan_doan: Optional[ChanDoanQuet] = None
    # Đã quét tới giây thứ mấy của video. BẰNG `duration_s` khi quét trọn vẹn.
    #
    # Phải tách khỏi `duration_s` chứ không thể dùng chung: `duration_s` là thời lượng
    # VIDEO VI PHẠM (đi vào hồ sơ khiếu nại, cột Thời lượng trên Sheets), còn trường
    # này là TRỤC THỜI GIAN ĐÃ QUÉT (dùng chia vùng khi chọn lọc). Quét trọn thì hai
    # cái trùng khít nên trước đây một trường phục vụ được cả hai; quét tăng dần làm
    # chúng tách đôi, và không giá trị đơn nào đúng cho cả hai mục đích.
    pham_vi_quet_s: float = 0.0

    @property
    def quet_mot_phan(self) -> bool:
        """Có phải chỉ quét một phần video không? Dùng để ghi rõ trên báo cáo."""
        return bool(self.duration_s and 0 < self.pham_vi_quet_s < self.duration_s - 1)


class Cancelled(Exception):
    """Ném ra khi người dùng bấm Dừng."""


# =====================================================================
#  Hàm tiện ích dùng chung
# =====================================================================

def hhmmss(giay: float) -> str:
    """Định dạng một mốc/độ dài MEDIA thành HH:MM:SS, CẮT phần lẻ (không làm tròn).

    VÌ SAO CẮT CHỨ KHÔNG LÀM TRÒN

    Trình phát hiển thị giây theo kiểu cắt: khi playhead ở giây 1441,8 thì đồng hồ
    ghi 24:01, không phải 24:02. Thời lượng cũng vậy — video còn 0,019 giây cuối vẫn
    hiển thị mốc giây trước. Đo trực tiếp trên YouTube (đọc `.ytp-time-duration` và
    `video.duration` trong trang):

        video           duration thật   UI YouTube   round()    cắt
        D-sVTRR5jm0     21219,981       5:53:39      5:53:40 ✗  5:53:39 ✓
        3ixKzIN0et0       675,861         11:15        11:16 ✗    11:15 ✓

    Làm tròn khiến 43,3% video quét được (đo trên 60 file đã tải) bị báo dư 1 giây.

    Cắt còn khớp với link nhảy mốc `?t=`, vốn đã dùng ``int(giay)``: trước đây báo
    cáo ghi 00:24:02 nhưng link lại nhảy tới 00:24:01 — lệch nhau một giây.

    Hàm này dành cho THỜI GIAN MEDIA (độ dài, mốc trong video). Thời gian vận hành
    (đã chạy, ETA) dùng ``app._thoi_luong()`` và không đi qua đây.
    """
    giay = max(0, int(giay))
    return f"{giay // 3600:02d}:{(giay % 3600) // 60:02d}:{giay % 60:02d}"


def chi_phi_kiem_tra(m, duration: float) -> tuple:
    """Chi phí để một người kiểm tra độc lập tua tới đoạn này. Nhỏ hơn = dễ hơn.

    Đây **không** phải chỉ số pháp lý — nó chỉ nói đoạn nào tua tới nhanh hơn.
    Dùng cả vị trí tương đối lẫn tuyệt đối: 45% của video 12 tiếng vẫn là hơn 5
    tiếng tua, nên tỉ lệ một mình chưa đủ. Khi không biết thời lượng video thì
    lùi về giây tuyệt đối thay vì bỏ qua tín hiệu.
    """
    bat_dau = max(0.0, float(getattr(m, "start_s", 0.0) or 0.0))
    ty_le = bat_dau / duration if duration and duration > 0 else 1.0
    return (round(max(0.0, min(1.0, ty_le)), 4), bat_dau)


def loc_du_bang_chung(ung_vien: list, san: float) -> list:
    """Bỏ ứng viên có bằng chứng TUYỆT ĐỐI sụp đổ so với ứng viên mạnh nhất nhóm.

    Cần thiết khi xếp hạng bằng chỉ số **chuẩn hoá** như ``ty_le`` (% vân tay của
    clip gốc khớp được): tỉ lệ cố tình bỏ qua độ lớn, nên một đoạn 9 phút có thể
    có tỉ lệ cao hơn một đoạn 23 phút. Với hồ sơ khiếu nại thì 23 phút vi phạm là
    bằng chứng mạnh hơn, dù phần trăm thấp hơn.

    Đo trên 283 job thật: không có sàn thì 18% số ca đổi là đánh đổi nặng
    (mất >30% hash hoặc >30% thời lượng).

    Ứng viên mạnh nhất về hash luôn tự thoả sàn nên danh sách không bao giờ rỗng.
    """
    if san <= 0 or len(ung_vien) <= 1:
        return list(ung_vien)

    def so_hash(m) -> float:
        return float(getattr(m, "hashes", 0) or 0)

    def do_dai(m) -> float:
        return float(getattr(m, "matched_s", 0) or 0)

    moc = max(ung_vien, key=so_hash)
    nguong_hash, nguong_dai = so_hash(moc) * san, do_dai(moc) * san
    giu = [
        m for m in ung_vien
        if so_hash(m) >= nguong_hash and do_dai(m) >= nguong_dai
    ]
    return giu or [moc]


def chon_dai_dien(ung_vien: list, duration: float, dung_sai: float, khoa_chat_luong,
                  san_bang_chung: float = 0.0):
    """Chọn ứng viên ĐẠI DIỆN tốt nhất trong một nhóm.

    Thứ tự giá trị, không được đảo:

    1. Chất lượng bằng chứng (``khoa_chat_luong``) — quyết định trước hết.
    2. Chỉ trong nhóm **ngang bằng** về chất lượng mới xét tới độ dễ kiểm tra.
    3. Hoà tiếp thì phá hoà tất định.

    Nhờ vậy một đoạn khớp yếu ở đầu video **không bao giờ** vượt được đoạn khớp
    mạnh hơn đáng kể ở cuối video — nhưng hai đoạn thực sự tương đương thì đoạn
    tua tới nhanh hơn sẽ thắng.

    "Ngang bằng" đòi hỏi cả bằng chứng lẫn thời lượng đều nằm trong dung sai:
    một đoạn 20 giây không được coi là tương đương một đoạn 15 phút chỉ vì tình
    cờ có số hash xấp xỉ.
    """
    if not ung_vien:
        raise ValueError("Không có ứng viên nào để chọn.")
    if len(ung_vien) == 1:
        return ung_vien[0]

    ung_vien = loc_du_bang_chung(ung_vien, san_bang_chung)
    if len(ung_vien) == 1:
        return ung_vien[0]

    tot_nhat = max(ung_vien, key=khoa_chat_luong)
    if dung_sai <= 0:
        return tot_nhat

    hang_tot_nhat = khoa_chat_luong(tot_nhat)
    san = 1.0 - dung_sai

    def ngang_bang(m) -> bool:
        hang = khoa_chat_luong(m)
        # Các bậc phân loại (bằng chứng mạnh, clip chưa dùng) phải trùng khớp —
        # dung sai chỉ áp cho phần định lượng ở cuối khoá.
        if hang[:-1] != hang_tot_nhat[:-1]:
            return False
        if hang_tot_nhat[-1] > 0 and hang[-1] < hang_tot_nhat[-1] * san:
            return False
        dai_nhat = float(getattr(tot_nhat, "matched_s", 0.0) or 0.0)
        dai = float(getattr(m, "matched_s", 0.0) or 0.0)
        return not (dai_nhat > 0 and dai < dai_nhat * san)

    gan_bang = [m for m in ung_vien if ngang_bang(m)]
    if len(gan_bang) <= 1:
        return tot_nhat

    # Phá hoà tất định: dễ kiểm tra nhất, rồi bằng chứng mạnh nhất, rồi tên clip.
    return min(
        gan_bang,
        key=lambda m: (
            chi_phi_kiem_tra(m, duration),
            -float(getattr(m, "hashes", 0) or 0),
            str(getattr(m, "clip", "")),
        ),
    )


def o_bang_tinh_an_toan(gia_tri):
    """Ép chuỗi có thể bị spreadsheet hiểu là công thức thành dữ liệu thuần."""
    if not isinstance(gia_tri, str):
        return gia_tri
    noi_dung = gia_tri.lstrip(" \t\r\n")
    if noi_dung.startswith(("=", "+", "-", "@")):
        return "'" + gia_tri
    return gia_tri


def _mo_file_text_moi(path: str, **kwargs):
    """Mở file text bằng mode độc quyền và thêm hậu tố nếu tên đã tồn tại."""
    goc, duoi = os.path.splitext(path)
    thu_tu = 1
    while True:
        ung_vien = path if thu_tu == 1 else f"{goc}_{thu_tu}{duoi}"
        try:
            return open(ung_vien, "x", **kwargs), ung_vien
        except FileExistsError:
            thu_tu += 1


def so_nhan_nen_dung() -> int:
    """Tự chọn số nhân CPU cho tác vụ nền, luôn chừa ít nhất một nhân cho hệ thống."""
    so_nhan = os.cpu_count() or 1
    return max(1, min(8, so_nhan - 1))


def danh_gia(so_hash: int) -> str:
    if so_hash >= 100:
        return "Rất chắc chắn"
    if so_hash >= 40:
        return "Chắc chắn"
    return "Nên kiểm tra lại"


def liet_ke_media(thumuc: str) -> list:
    """Liệt kê mọi file media trong thư mục (kể cả thư mục con)."""
    ds = []
    for goc, _, files in os.walk(thumuc):
        for f in files:
            if os.path.splitext(f)[1].lower() in MEDIA_EXTS:
                ds.append(os.path.join(goc, f))
    return sorted(ds)


# Dòng kết quả của audfprint:
# Matched  54.5 s starting at 402.7 s in <khúc> to time 2.7 s in <clip gốc> with 321 of 605 common hashes at rank 0
RE_MATCH = re.compile(
    r"Matched\s+([\d.]+)\s+s\s+starting\s+at\s+([\d.]+)\s+s\s+in\s+(.+?)"
    r"\s+to\s+time\s+([\d.]+)\s+s\s+in\s+(.+?)\s+with\s+(\d+)\s+of\s+(\d+)\s+common\s+hashes"
)

# Tên khúc: `chunk_<mốc bắt đầu>.wav`, hoặc `chunk_<mốc>_k<hệ số x100000>.wav` khi
# khúc đã bị đổi tốc độ để bù né tránh. Hậu tố là tuỳ chọn nên tên cũ vẫn đọc được.
RE_TEN_KHUC = re.compile(r"chunk_(\d+)(?:_k(\d+))?\.wav")


# =====================================================================
#  Engine
# =====================================================================

def thu_muc_data_mac_dinh(root: Optional[str] = None) -> str:
    """Thư mục `data/` mà Engine sẽ dùng, tính được mà KHÔNG cần dựng Engine.

    Có hàm này để các lệnh nhẹ (`cli.py vameta`) đọc được cấu hình người dùng mà
    không phải khởi tạo Engine — dựng Engine nạp kho vân tay và giành khoá liên
    tiến trình. Giữ đúng một công thức đường dẫn cho cả hai đường, khỏi trôi dạt.
    """
    goc = os.path.abspath(root or os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.environ.get("TIMCLIP_DATA_DIR")
                           or os.path.join(goc, "data"))


class Engine:
    """Lõi xử lý. Không phụ thuộc vào bất kỳ giao diện nào."""

    def __init__(self, root: Optional[str] = None, config: Optional[Config] = None,
                 data_dir: Optional[str] = None, out_dir: Optional[str] = None):
        self.root = os.path.abspath(root or os.path.dirname(os.path.abspath(__file__)))
        self.config = config or Config()
        self.canh_bao_khoi_dong: list = []
        self.canh_bao_gop: list = []
        # Kênh riêng cho cảnh báo tầng MẠNG (cookie hết hạn...). Không dùng chung
        # `canh_bao_gop` vì `_merge()` xoá trắng danh sách đó ở mỗi lượt khớp, mà
        # cảnh báo mạng lại sinh ra TRƯỚC đó — dùng chung là mất trắng.
        self.canh_bao_mang: list = []
        # Nhớ client vừa tải được, để không trả giá 403 cho TỪNG video khi thứ tự
        # mong muốn đang bị YouTube chặn. Tự quên sau 30 phút để dò lại.
        self.nho_client = ytdlp_chung.NhoClientTotNhat()
        self.chan_doan_quet = ChanDoanQuet()
        self.cau_hinh_da_luu: dict = {}

        self.bin_dir = os.path.join(self.root, "bin")
        self.data_dir = os.path.abspath(data_dir or os.path.join(self.root, "data"))
        self.db_file = os.path.join(self.data_dir, "db.pklz")  # sẽ được _init_kho ghi đè
        self.kho_dang_dung = ""
        self.kho_thu_muc = ""
        self.dl_dir = os.path.join(self.data_dir, "downloads")
        self.chunk_dir = os.path.join(self.data_dir, "chunks")
        self.out_dir = os.path.abspath(out_dir or os.path.join(self.root, "ketqua"))
        self.sqlite_file = os.path.join(self.data_dir, "lichsu.db")

        for d in (self.data_dir, self.dl_dir, self.out_dir):
            os.makedirs(d, exist_ok=True)

        # Cho phép đặt ffmpeg/ffprobe trong bin\ mà không cần sửa PATH hệ thống
        if self.bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = self.bin_dir + os.pathsep + os.environ.get("PATH", "")

        self.kho_file = os.path.join(self.data_dir, "khos.json")
        self.audfprint = self._tim_audfprint()
        self.cancel_event = threading.Event()
        self._cache_khoa = None
        self._cache_clips = []
        self._metadata_cache_key = None
        self._metadata_resolver_cache: Optional[ClipMetadataResolver] = None
        self.canh_bao_metadata: list[str] = []
        self._nap_cau_hinh()
        self._init_sqlite()
        self._init_kho()

    @property
    def chan_doan_quet(self) -> ChanDoanQuet:
        """Phễu phát hiện của lượt quét đang chạy; đặt lại ở đầu mỗi `scan_media()`.

        Tự tạo khi truy cập lần đầu để các test logic thuần dựng Engine bằng
        ``Engine.__new__(Engine)`` (không chạy ``__init__``) vẫn gọi được
        ``_merge()`` và ``_chon_loc()`` mà không phải chuẩn bị thêm gì.
        """
        cd = getattr(self, "_chan_doan_quet", None)
        if cd is None:
            cd = ChanDoanQuet()
            self._chan_doan_quet = cd
        return cd

    @chan_doan_quet.setter
    def chan_doan_quet(self, gia_tri: ChanDoanQuet) -> None:
        self._chan_doan_quet = gia_tri

    def _nap_cau_hinh(self) -> None:
        """Nạp cấu hình bền vững; mọi lỗi đều được hạ thành cảnh báo khởi động."""
        try:
            du_lieu = cau_hinh.doc_cau_hinh(self.data_dir)
            self.cau_hinh_da_luu = du_lieu
            bi_bo_qua = cau_hinh.ap_vao_config(self.config, du_lieu)
            bi_bo_qua = [
                khoa for khoa in bi_bo_qua
                if khoa not in cau_hinh.GIA_TRI_GIAO_DIEN_MAC_DINH
            ]
            if bi_bo_qua:
                self.canh_bao_khoi_dong.append(
                    "Đã bỏ qua khóa cấu hình lạ hoặc sai kiểu: "
                    + ", ".join(sorted(bi_bo_qua))
                )
            if du_lieu:
                self.config.validate()
        except Exception as e:  # noqa: BLE001
            self.config = Config()
            self.cau_hinh_da_luu = {}
            self.canh_bao_khoi_dong.append(
                f"Không nạp được cấu hình người dùng; đang dùng mặc định: {e}"
            )

    def luu_cau_hinh(self, them: dict | None = None) -> None:
        """Lưu Config và các tùy chọn giao diện không bí mật được cho phép."""
        self.config.validate()
        du_lieu = cau_hinh.lay_tu_config(self.config)
        for khoa, mac_dinh in cau_hinh.GIA_TRI_GIAO_DIEN_MAC_DINH.items():
            if them and khoa in them and type(them[khoa]) is type(mac_dinh):
                du_lieu[khoa] = them[khoa]
        cau_hinh.ghi_cau_hinh(self.data_dir, du_lieu)
        self.cau_hinh_da_luu = dict(du_lieu)

    def khoi_phuc_cau_hinh_mac_dinh(self) -> None:
        """Xóa cấu hình đã lưu và áp Config mặc định ngay trong phiên hiện tại."""
        duong_dan = os.path.join(self.data_dir, cau_hinh.TEN_FILE)
        for hau_to in ("", ".bak", ".tmp"):
            with contextlib.suppress(FileNotFoundError):
                os.remove(duong_dan + hau_to)
        self.config = Config()
        self.cau_hinh_da_luu = {}

    # =================================================================
    #  QUẢN LÝ NHIỀU KHO CLIP GỐC
    #  Mỗi kho = 1 tên + 1 thư mục + 1 file vân tay riêng.
    #  Ví dụ: kho "Ẩm thực", kho "Du lịch", kho "Review" — quét video vi phạm
    #  nào thì chọn đúng kho tương ứng, vừa nhanh vừa ít báo nhầm.
    # =================================================================

    @staticmethod
    def _slug(ten: str) -> str:
        import hashlib
        sach = re.sub(r"[^a-zA-Z0-9]+", "_", ten).strip("_").lower()[:30]
        return (sach or "kho") + "_" + hashlib.md5(ten.encode("utf-8")).hexdigest()[:6]

    def _doc_khos(self) -> dict:
        return doc_json_an_toan(
            self.kho_file,
            {"dang_dung": "", "danh_sach": []},
        )

    def _ghi_khos(self, d: dict) -> None:
        ghi_json_an_toan(self.kho_file, d)

    def _duong_dan_db_kho(self, ten_file: str) -> str:
        """Chỉ chấp nhận basename `.pklz` nằm trực tiếp trong data_dir."""
        if not isinstance(ten_file, str) or not ten_file:
            raise LoiDuLieu("Tên file vân tay trong khos.json không hợp lệ.")
        if (
            os.path.isabs(ten_file)
            or os.path.basename(ten_file) != ten_file
            or not ten_file.lower().endswith(".pklz")
        ):
            raise LoiDuLieu(
                "Tên file vân tay trong khos.json phải là một file .pklz "
                "nằm trực tiếp trong thư mục data."
            )
        duong_dan = os.path.abspath(os.path.join(self.data_dir, ten_file))
        try:
            nam_trong_data = os.path.commonpath(
                [self.data_dir, duong_dan]
            ) == os.path.commonpath([self.data_dir])
        except ValueError:
            nam_trong_data = False
        if not nam_trong_data:
            raise LoiDuLieu("Đường dẫn file vân tay thoát khỏi thư mục data.")
        return duong_dan

    def _init_kho(self) -> None:
        """Nạp kho đang dùng. Tự chuyển đổi dữ liệu từ phiên bản cũ (1 kho duy nhất)."""
        try:
            d = self._doc_khos()
        except LoiDuLieu as e:
            self.canh_bao_khoi_dong.append(str(e))
            self._ap_dung_kho(
                "",
                {"dang_dung": "", "danh_sach": []},
            )
            return
        # Nâng cấp: đã có db.pklz kiểu cũ mà chưa khai báo kho nào
        if not d["danh_sach"] and os.path.exists(os.path.join(self.data_dir, "db.pklz")):
            d = {"dang_dung": "Kho mặc định",
                 "danh_sach": [{"ten": "Kho mặc định", "thu_muc": "", "db": "db.pklz"}]}
            self._ghi_khos(d)
        try:
            self._ap_dung_kho(d.get("dang_dung", ""), d)
        except LoiDuLieu as e:
            self.canh_bao_khoi_dong.append(str(e))
            self._ap_dung_kho("", {"dang_dung": "", "danh_sach": []})

    def _ap_dung_kho(self, ten: str, d: Optional[dict] = None) -> None:
        d = d or self._doc_khos()
        kho = next((k for k in d["danh_sach"] if k["ten"] == ten), None)
        if kho is None and d["danh_sach"]:
            kho = d["danh_sach"][0]
        self.db_file = self._duong_dan_db_kho(kho["db"]) if kho else \
            os.path.join(self.data_dir, "db.pklz")
        self.kho_dang_dung = kho["ten"] if kho else ""
        self.kho_thu_muc = kho.get("thu_muc", "") if kho else ""
        self._cache_khoa = None   # đổi kho -> đọc lại danh sách clip
        self._invalidate_metadata_cache()

    def _invalidate_metadata_cache(self) -> None:
        """Buộc dựng lại metadata index ở lần đọc kế tiếp."""
        self._metadata_cache_key = None
        self._metadata_resolver_cache = None
        self.canh_bao_metadata = []

    def list_khos(self) -> list:
        """Danh sách các kho + trạng thái (đã có vân tay chưa, bao nhiêu clip)."""
        d = self._doc_khos()
        ds = []
        for k in d["danh_sach"]:
            db = self._duong_dan_db_kho(k["db"])
            ds.append({**k, "duong_dan_db": db, "co_van_tay": os.path.exists(db),
                       "dang_dung": k["ten"] == self.kho_dang_dung})
        return ds

    def add_kho(self, ten: str, thu_muc: str = "") -> dict:
        ten = (ten or "").strip()
        if not ten:
            raise RuntimeError("Tên kho không được để trống.")
        d = self._doc_khos()
        if any(k["ten"] == ten for k in d["danh_sach"]):
            raise RuntimeError(f"Đã có kho tên «{ten}» rồi.")
        kho = {"ten": ten, "thu_muc": thu_muc.strip('" '),
               "db": f"kho_{self._slug(ten)}.pklz"}
        d["danh_sach"].append(kho)
        d["dang_dung"] = ten
        self._ghi_khos(d)
        self._ap_dung_kho(ten, d)
        return kho

    def use_kho(self, ten: str) -> None:
        d = self._doc_khos()
        if not any(k["ten"] == ten for k in d["danh_sach"]):
            raise RuntimeError(f"Không có kho tên «{ten}».")
        d["dang_dung"] = ten
        self._ghi_khos(d)
        self._ap_dung_kho(ten, d)

    def update_kho(self, ten: str, thu_muc: str) -> None:
        d = self._doc_khos()
        for k in d["danh_sach"]:
            if k["ten"] == ten:
                k["thu_muc"] = thu_muc.strip('" ')
        self._ghi_khos(d)
        self._ap_dung_kho(d.get("dang_dung", ""), d)

    def delete_kho(self, ten: str, xoa_van_tay: bool = True) -> None:
        """Xoá kho khỏi danh sách. KHÔNG bao giờ đụng vào file video/audio gốc."""
        d = self._doc_khos()
        kho = next((k for k in d["danh_sach"] if k["ten"] == ten), None)
        if not kho:
            return
        if xoa_van_tay:
            self._cache_khoa = None
            self._xoa_an_toan(self._duong_dan_db_kho(kho["db"]))
        d["danh_sach"] = [k for k in d["danh_sach"] if k["ten"] != ten]
        if d.get("dang_dung") == ten:
            d["dang_dung"] = d["danh_sach"][0]["ten"] if d["danh_sach"] else ""
        self._ghi_khos(d)
        self._ap_dung_kho(d.get("dang_dung", ""), d)

    # ---------- hạ tầng ----------

    def _tim_audfprint(self) -> Optional[str]:
        for ten in ("audfprint-master", "audfprint"):
            p = os.path.join(self.root, ten, "audfprint.py")
            if os.path.isfile(p):
                return p
        return None

    def _init_sqlite(self) -> None:
        with self._db() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS jobs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT, source_type TEXT, source_name TEXT, source_ref TEXT,
                duration_s REAL, status TEXT, n_matches INTEGER, note TEXT,
                source_id TEXT DEFAULT '')""")
            # Nâng cấp DB tạo bởi phiên bản cũ
            with contextlib.suppress(sqlite3.OperationalError):
                c.execute("ALTER TABLE jobs ADD COLUMN source_id TEXT DEFAULT ''")
            c.execute("""CREATE TABLE IF NOT EXISTS matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER,
                clip TEXT, start_s REAL, end_s REAL, matched_s REAL,
                clip_offset_s REAL, hashes INTEGER, confidence TEXT)""")
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_source_id "
                "ON jobs(source_id)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_matches_job_id "
                "ON matches(job_id)"
            )

    @contextlib.contextmanager
    def _db(self):
        con = sqlite3.connect(self.sqlite_file)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _bao(progress: Optional[Callable], pct: float, msg: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, pct)), msg)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def _run_stream(
        self,
        lenh: list,
        on_line: Optional[Callable] = None,
        *,
        on_heartbeat: Optional[Callable[[ProcessSnapshot], None]] = None,
        logger=None,
        process_name: str = "audfprint",
        include_in_tail: Optional[Callable[[str], bool]] = None,
        heartbeat_seconds: float = 10.0,
    ) -> tuple:
        """
        Chạy lệnh con, đọc stdout từng dòng (để báo tiến độ), hỗ trợ hủy giữa chừng.
        Trả về (return_code, 30 dòng cuối) — dòng cuối dùng để báo lỗi cho ra hồn.

        QUAN TRỌNG — vì sao phải ép UTF-8:
        Windows tiếng Việt dùng bảng mã cp1258/cp1252. audfprint mở file danh sách bằng
        open() không chỉ định encoding, nên khi đường dẫn có dấu tiếng Việt nó sẽ chết
        ngay với UnicodeDecodeError → không in ra dòng nào → tiến độ đứng ở 0%.
        Đặt PYTHONUTF8=1 buộc tiến trình con dùng UTF-8, sửa triệt để mà KHÔNG phải
        sửa thư viện bên thứ ba.
        """
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"          # ép open() mặc định UTF-8
        env["PYTHONIOENCODING"] = "utf-8"  # in tên file tiếng Việt không lỗi
        env["PYTHONUNBUFFERED"] = "1"     # đẩy tiến độ ra ngay, không đệm

        result = run_observed_process(
            lenh,
            on_line=on_line,
            on_heartbeat=on_heartbeat,
            cancel_event=self.cancel_event,
            logger=logger,
            process_name=process_name,
            heartbeat_seconds=heartbeat_seconds,
            slow_warning_seconds=120.0,
            include_in_tail=include_in_tail,
            env=env,
        )
        if result.cancelled:
            raise Cancelled()
        return result.returncode, list(result.tail)

    # ---------- kiểm tra môi trường ----------

    def check_env(self) -> dict:
        """Trả về tình trạng từng thành phần — giao diện dùng để hiển thị đèn xanh/đỏ."""
        try:
            import yt_dlp  # noqa: F401
            co_ytdlp, ver_ytdlp = True, yt_dlp.version.__version__
        except Exception:
            co_ytdlp, ver_ytdlp = False, ""
        return {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "yt_dlp": co_ytdlp,
            "yt_dlp_version": ver_ytdlp,
            "audfprint": self.audfprint is not None,
            "database": os.path.exists(self.db_file),
        }

    def require(self, can_ytdlp: bool = False, can_db: bool = False) -> None:
        env = self.check_env()
        thieu = []
        if not env["ffmpeg"]:
            thieu.append("ffmpeg.exe (đặt vào thư mục bin\\ hoặc cài vào PATH)")
        if not env["ffprobe"]:
            thieu.append("ffprobe.exe (đặt vào thư mục bin\\ hoặc cài vào PATH)")
        if not env["audfprint"]:
            thieu.append("thư mục audfprint-master\\")
        if can_ytdlp and not env["yt_dlp"]:
            thieu.append("thư viện yt-dlp (chạy: pip install -U yt-dlp)")
        if can_db and not env["database"]:
            thieu.append("kho vân tay clip gốc (hãy tạo ở tab \"Kho clip gốc\")")
        if thieu:
            raise RuntimeError("Còn thiếu: " + "; ".join(thieu))

    # ---------- thông tin media ----------

    @staticmethod
    def duration_of(path: str) -> Optional[float]:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            return float(r.stdout.strip().splitlines()[-1])
        except Exception:
            return None

    # =================================================================
    #  1) KHO VÂN TAY CLIP GỐC
    # =================================================================

    def db_clips(self, bo_cache: bool = False) -> list:
        """
        Đọc danh sách clip trong kho vân tay.

        QUAN TRỌNG — vì sao KHÔNG dùng hash_table.HashTable(path):
        Hàm load_pkl() của thư viện gọi gzip.open() mà KHÔNG đóng file.
        Trên Windows, một handle còn mở là đủ để chặn os.remove() → WinError 32
        "The process cannot access the file because it is being used by another
        process". Ở đây ta tự đọc toàn bộ file vào RAM trong khối `with`
        (đảm bảo đóng 100%) rồi mới giải nén — không bao giờ giữ handle.

        Kèm cache theo (đường dẫn, mtime, kích thước): Streamlit vẽ lại màn hình
        liên tục, mỗi lần đọc lại file vân tay hàng trăm MB sẽ rất chậm.
        """
        if not os.path.exists(self.db_file) or not self.audfprint:
            return []
        try:
            st_ = os.stat(self.db_file)
            khoa = (self.db_file, st_.st_mtime_ns, st_.st_size)
        except OSError:
            return []
        if not bo_cache and getattr(self, "_cache_khoa", None) == khoa:
            return self._cache_clips

        thu_muc_af = os.path.dirname(self.audfprint)
        if thu_muc_af not in sys.path:
            sys.path.insert(0, thu_muc_af)
        ds = []
        try:
            import gzip
            import pickle
            # Đọc trọn vào RAM rồi ĐÓNG NGAY — chốt chặn WinError 32
            with gzip.open(self.db_file, "rb") as f:
                raw = f.read()
            with contextlib.redirect_stdout(io.StringIO()):
                ht = pickle.loads(raw, encoding="latin1")
            del raw
            for i, ten in enumerate(getattr(ht, "names", []) or []):
                if not ten:
                    continue
                hpid = getattr(ht, "hashesperid", [])
                so_hash = hpid[i] if i < len(hpid) else 0
                ds.append({"ten": os.path.basename(ten), "duong_dan": ten,
                           "so_hash": int(so_hash)})
            del ht
        except Exception:
            ds = []
        self._cache_khoa, self._cache_clips = khoa, ds
        return ds

    # ---------- xử lý file bị khoá trên Windows ----------

    @staticmethod
    def _xoa_an_toan(path: str, so_lan: int = 6) -> bool:
        """
        Xoá file, chịu được việc Windows/phần mềm diệt virus tạm khoá file.
        Trả về True nếu xoá được. KHÔNG ném lỗi.
        """
        import gc
        if not os.path.exists(path):
            return True
        gc.collect()   # ép Python đóng mọi handle còn sót
        for i in range(so_lan):
            try:
                os.remove(path)
                return True
            except PermissionError:
                time.sleep(0.4 * (i + 1))   # chờ tăng dần: 0.4s, 0.8s, 1.2s...
                gc.collect()
            except OSError:
                return False
        return not os.path.exists(path)

    def _metadata_snapshot_path(self) -> str:
        """Đường dẫn snapshot riêng, ổn định và không thể thoát khỏi data_dir."""
        dinh_danh = self.kho_dang_dung or os.path.splitext(
            os.path.basename(self.db_file)
        )[0]
        ten_file = f"kho_{self._slug(dinh_danh or 'mac_dinh')}.json"
        thu_muc = os.path.abspath(os.path.join(self.data_dir, "metadata"))
        duong_dan = os.path.abspath(os.path.join(thu_muc, ten_file))
        try:
            hop_le = os.path.commonpath([thu_muc, duong_dan]) == thu_muc
        except ValueError:
            hop_le = False
        if not hop_le:
            raise LoiDuLieu("Đường dẫn snapshot metadata thoát khỏi thư mục data.")
        return duong_dan

    @staticmethod
    def _metadata_file_signature(path: str) -> tuple:
        try:
            stat = os.stat(path)
        except OSError:
            return os.path.normcase(os.path.abspath(path)), False, 0, 0
        return (
            os.path.normcase(os.path.abspath(path)),
            True,
            stat.st_mtime_ns,
            stat.st_size,
        )

    def _metadata_source_candidates(self, clips: list[dict]) -> list[tuple[str, str, int]]:
        """Nguồn chỉ thuộc kho active, theo thứ tự xác định; không dùng set last-wins."""
        candidates: list[tuple[str, str, int]] = []
        seen: set[str] = set()

        def add(path: str, kind: str, priority: int) -> None:
            absolute = os.path.abspath(path)
            key = os.path.normcase(absolute)
            if key not in seen:
                seen.add(key)
                candidates.append((absolute, kind, priority))

        if self.kho_dang_dung:
            add(self._metadata_snapshot_path(), "snapshot", 0)
        if self.kho_thu_muc:
            add(os.path.join(self.kho_thu_muc, "clips_meta.json"), "live", 10)

        # Legacy fallback: chỉ các directory thực sự được tham chiếu bởi DB active.
        thu_muc_db = sorted({
            os.path.abspath(os.path.dirname(str(clip.get("duong_dan") or "")))
            for clip in clips
            if os.path.dirname(str(clip.get("duong_dan") or ""))
        }, key=os.path.normcase)
        for index, folder in enumerate(thu_muc_db, start=20):
            add(os.path.join(folder, "clips_meta.json"), "legacy_db_folder", index)

        # Chỉ kho mặc định kiểu cũ mới được phép đọc metadata ở data_dir. Không
        # áp dụng vô điều kiện vì sẽ trộn metadata giữa nhiều kho.
        if self.kho_dang_dung in {"", "Kho mặc định"}:
            add(os.path.join(self.data_dir, "clips_meta.json"), "legacy_data", 100)
        return candidates

    def _metadata_cache_signature(
        self,
        candidates: list[tuple[str, str, int]],
    ) -> tuple:
        db_signature = self._metadata_file_signature(self.db_file)
        source_signatures = tuple(
            (
                kind,
                priority,
                self._metadata_file_signature(path),
                self._metadata_file_signature(path + ".bak"),
            )
            for path, kind, priority in candidates
        )
        return (
            self.kho_dang_dung,
            os.path.normcase(os.path.abspath(self.kho_thu_muc))
            if self.kho_thu_muc else "",
            db_signature,
            source_signatures,
        )

    def clip_metadata_resolver(self, bo_cache: bool = False) -> ClipMetadataResolver:
        """Dựng/cached index exact, canonical và YouTube-ID của đúng kho active."""
        clips = self.db_clips()
        candidates = self._metadata_source_candidates(clips)
        cache_key = self._metadata_cache_signature(candidates)
        if (
            not bo_cache
            and self._metadata_cache_key == cache_key
            and self._metadata_resolver_cache is not None
        ):
            return self._metadata_resolver_cache

        sources = []
        for path, kind, priority in candidates:
            expected = self.kho_dang_dung if kind == "snapshot" else ""
            source = load_metadata_strict(
                path,
                kind=kind,
                priority=priority,
                expected_warehouse=expected,
            )
            sources.append(source)
            # Backup chỉ là fallback đọc; tuyệt đối không phục hồi/rename file chính.
            bi_loi = bool(source.warnings) and not source.entries
            if (bi_loi or not source.exists) and os.path.isfile(path + ".bak"):
                backup = load_metadata_strict(
                    path + ".bak",
                    kind=kind + "_backup",
                    priority=priority + 1,
                    expected_warehouse=expected,
                )
                if backup.entries:
                    sources.append(backup)

        resolver = ClipMetadataResolver(sources, windows_semantics=os.name == "nt")
        audit = resolver.audit(
            clips,
            warehouse=self.kho_dang_dung,
            database_file=self.db_file,
            warehouse_folder=self.kho_thu_muc,
            sample_limit=0,
        )
        warnings = []
        for source in sources:
            for warning in source.warnings:
                warnings.append(
                    f"{os.path.basename(source.path) or source.kind}: {warning}"
                )
        if resolver.conflicts:
            warnings.append(
                f"Phát hiện {len(set(resolver.conflicts))} xung đột metadata; "
                "các ánh xạ mơ hồ không được tự động chọn."
            )
        if audit.total_db_clips and audit.complete < audit.total_db_clips:
            warnings.append(
                f"Metadata kho chưa đầy đủ: {audit.complete}/{audit.total_db_clips} "
                "clip có đủ ID, title, URL, ngày đăng và thời lượng."
            )
        self.canh_bao_metadata = list(dict.fromkeys(warnings))
        self._metadata_cache_key = cache_key
        self._metadata_resolver_cache = resolver

        LOGGER_METADATA.info(
            "event=metadata.index warehouse=%r db_clips=%d metadata_entries=%d "
            "complete=%d partial=%d fallback=%d unresolved=%d ambiguous=%d",
            self.kho_dang_dung,
            audit.total_db_clips,
            audit.metadata_entries,
            audit.complete,
            audit.partial,
            audit.filename_fallbacks,
            audit.missing,
            audit.ambiguous,
        )
        if self.canh_bao_metadata:
            LOGGER_METADATA.warning(
                "event=metadata.coverage warehouse=%r warnings=%d complete=%d total=%d",
                self.kho_dang_dung,
                len(self.canh_bao_metadata),
                audit.complete,
                audit.total_db_clips,
            )
        return resolver

    def clip_meta(self) -> dict:
        """Compatibility mapping đã validate; call site báo cáo dùng resolver trực tiếp."""
        return self.clip_metadata_resolver().compatibility_mapping()

    def resolve_metadata_for_matches(self, matches: Iterable) -> tuple:
        """Resolve một batch đúng thứ tự và giữ duplicate đoạn ↔ clip."""
        resolver = self.clip_metadata_resolver()
        return tuple(resolver.resolve(str(match.clip)) for match in matches)

    def metadata_coverage(self, matches: Iterable):
        names = [
            str(item.clip) if hasattr(item, "clip") else str(item)
            for item in matches
        ]
        return self.clip_metadata_resolver().coverage(names)

    def kiem_tra_metadata_kho(self, sample_limit: int = 20) -> MetadataAudit:
        """Audit chỉ đọc; không sửa clips_meta, snapshot hay database fingerprint."""
        resolver = self.clip_metadata_resolver(bo_cache=True)
        audit = resolver.audit(
            self.db_clips(),
            warehouse=self.kho_dang_dung,
            database_file=self.db_file,
            warehouse_folder=self.kho_thu_muc,
            sample_limit=max(0, min(int(sample_limit), 20)),
        )
        LOGGER_METADATA.info(
            "event=metadata.audit warehouse=%r db_clips=%d metadata_entries=%d "
            "exact=%d normalized=%d id=%d fallback=%d missing=%d ambiguous=%d",
            self.kho_dang_dung,
            audit.total_db_clips,
            audit.metadata_entries,
            audit.exact_matches + audit.exact_basename_matches,
            audit.normalized_matches,
            audit.id_matches,
            audit.filename_fallbacks,
            audit.missing,
            audit.ambiguous,
        )
        return audit

    @staticmethod
    def _snapshot_entry(item) -> dict:
        entry = item.public_dict()
        entry["resolution_method"] = item.resolution_method
        return entry

    def _khoi_phuc_metadata_offline_da_khoa(
        self,
        *,
        dry_run: bool,
        preserve_existing: bool = True,
    ) -> MetadataRepairResult:
        clips = self.db_clips(bo_cache=True)
        resolver = self.clip_metadata_resolver(bo_cache=True)
        audit = resolver.audit(
            clips,
            warehouse=self.kho_dang_dung,
            database_file=self.db_file,
            warehouse_folder=self.kho_thu_muc,
            sample_limit=20,
        )
        snapshot_path = self._metadata_snapshot_path()
        existing_source = load_metadata_strict(
            snapshot_path,
            kind="snapshot",
            priority=0,
            expected_warehouse=self.kho_dang_dung,
        )
        backup_source = None
        if not existing_source.exists and os.path.isfile(snapshot_path + ".bak"):
            backup_source = load_metadata_strict(
                snapshot_path + ".bak",
                kind="snapshot_backup",
                priority=1,
                expected_warehouse=self.kho_dang_dung,
            )
        seed_source = backup_source if backup_source and backup_source.entries else existing_source
        existing = {
            entry.key: {
                **entry.public_dict(),
                "resolution_method": entry.origin_method or "exact",
            }
            for entry in seed_source.entries
        }
        output = dict(existing) if preserve_existing else {}
        updated = unchanged = skipped_ambiguous = unresolved = 0
        errors: list[str] = []

        if not os.path.isfile(self.db_file):
            errors.append("Database fingerprint của kho không tồn tại; không ghi snapshot.")
        elif not clips:
            errors.append(
                "Database tồn tại nhưng API không đọc được clip; không ghi snapshot rỗng."
            )
        if existing_source.exists and existing_source.warnings and not existing_source.entries:
            errors.append(
                "Snapshot chính hiện có nhưng không hợp lệ; từ chối ghi để không phá "
                "bản chính hoặc .bak. Hãy kiểm tra/chuyển file lỗi thủ công trước."
            )

        for clip in clips:
            name = str(clip.get("ten") or basename_compatible(clip.get("duong_dan")))
            path = str(clip.get("duong_dan") or "")
            item = resolver.resolve(name, path)
            if item.status == "ambiguous":
                skipped_ambiguous += 1
                continue
            if item.status == "unresolved":
                unresolved += 1
                continue
            candidate = self._snapshot_entry(item)
            if output.get(name) == candidate:
                unchanged += 1
            else:
                output[name] = candidate
                updated += 1

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        payload = {
            "schema_version": 1,
            "warehouse": self.kho_dang_dung,
            "warehouse_id": self._slug(self.kho_dang_dung or "mac_dinh"),
            "database": os.path.basename(self.db_file),
            "updated_at": now,
            "sources": [
                {"kind": source.kind, "file": os.path.basename(source.path)}
                for source in resolver.sources
                if source.entries and not source.kind.startswith("snapshot")
            ],
            "stats": {
                "database_clips": len(clips),
                "complete": audit.complete,
                "partial": audit.partial,
                "filename_fallbacks": audit.filename_fallbacks,
                "unresolved": unresolved,
                "ambiguous": skipped_ambiguous,
            },
            "clips": output,
        }
        validated = source_from_mapping(
            payload["clips"],
            path=snapshot_path,
            kind="snapshot",
            priority=0,
        )
        if validated.invalid_entries:
            errors.append(
                f"Snapshot mới có {validated.invalid_entries} entry sai schema."
            )

        if not dry_run and not errors:
            try:
                ghi_json_an_toan(snapshot_path, payload)
                self._invalidate_metadata_cache()
                LOGGER_METADATA.info(
                    "event=metadata.snapshot_write warehouse=%r entries=%d updated=%d",
                    self.kho_dang_dung,
                    len(output),
                    updated,
                )
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"Không ghi được snapshot: {type(exc).__name__}: {exc}")
                LOGGER_METADATA.exception(
                    "event=metadata.snapshot_error warehouse=%r category=%s",
                    self.kho_dang_dung,
                    type(exc).__name__,
                )

        return MetadataRepairResult(
            dry_run=dry_run,
            snapshot_path=snapshot_path,
            total_db_clips=len(clips),
            updated=updated,
            unchanged=unchanged,
            skipped_ambiguous=skipped_ambiguous,
            unresolved=unresolved,
            errors=tuple(errors),
            audit=audit,
        )

    def khoi_phuc_metadata_offline(
        self,
        *,
        dry_run: bool = True,
    ) -> MetadataRepairResult:
        """Tạo/merge snapshot từ dữ liệu local; mặc định dry-run và không gọi mạng."""
        if dry_run:
            return self._khoi_phuc_metadata_offline_da_khoa(dry_run=True)
        with KhoaTienTrinh(
            os.path.join(self.data_dir, "tool.lock"),
            "khôi phục metadata offline",
        ):
            return self._khoi_phuc_metadata_offline_da_khoa(dry_run=False)

    def _cap_nhat_snapshot_sau_build(self, mode: str) -> list[str]:
        """Snapshot là hậu xử lý best-effort sau khi DB fingerprint đã an toàn."""
        try:
            result = self._khoi_phuc_metadata_offline_da_khoa(
                dry_run=False,
                preserve_existing=mode != "new",
            )
        except Exception as exc:  # noqa: BLE001 - DB đã commit, chỉ hạ snapshot thành warning
            LOGGER_METADATA.exception(
                "event=metadata.snapshot_after_build_error warehouse=%r category=%s",
                self.kho_dang_dung,
                type(exc).__name__,
            )
            return [
                "Kho vân tay đã ghi thành công nhưng snapshot metadata chưa cập nhật: "
                f"{exc}"
            ]
        return list(result.errors)

    def va_metadata_thieu(
        self,
        progress: Optional[Callable] = None,
        *,
        fetcher: Optional[Callable[[str], dict]] = None,
        max_retries: int = 3,
    ) -> dict:
        """Vá field thiếu vào snapshot; chỉ caller rõ ràng mới kích hoạt I/O mạng."""
        max_retries = max(1, min(int(max_retries), 5))
        prepared = self.khoi_phuc_metadata_offline(dry_run=False)
        if prepared.errors:
            raise RuntimeError("; ".join(prepared.errors))

        if fetcher is None:
            def fetcher(video_id: str) -> dict:
                import yt_dlp

                options = self.cau_hinh_mang().tuy_chon(
                    skip_download=True, noplaylist=True, retries=2)
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(
                        f"https://youtu.be/{video_id}",
                        download=False,
                    )
                return {
                    "id": info.get("id") or video_id,
                    "title": info.get("title") or "",
                    "url": info.get("webpage_url") or f"https://youtu.be/{video_id}",
                    # Dùng chung cách rút ngày với channel.list_channel/sync để
                    # ba đường lấy metadata không hiểu khác nhau.
                    "upload_date": channel.ngay_dang_tu_info(info),
                    "duration": info.get("duration"),
                }

        with KhoaTienTrinh(
            os.path.join(self.data_dir, "tool.lock"),
            "vá metadata thiếu từ YouTube",
        ):
            snapshot_path = self._metadata_snapshot_path()
            source = load_metadata_strict(
                snapshot_path,
                kind="snapshot",
                priority=0,
                expected_warehouse=self.kho_dang_dung,
            )
            if source.warnings or not source.entries:
                raise RuntimeError(
                    "Snapshot metadata chưa hợp lệ; hãy audit/khôi phục offline trước."
                )
            records = {
                entry.key: {
                    **entry.public_dict(),
                    "resolution_method": entry.origin_method or "exact",
                }
                for entry in source.entries
            }
            resolver = self.clip_metadata_resolver(bo_cache=True)
            candidates = []
            for clip in self.db_clips():
                name = str(
                    clip.get("ten") or basename_compatible(clip.get("duong_dan"))
                )
                item = resolver.resolve(name, str(clip.get("duong_dan") or ""))
                if item.video_id and not item.complete and item.status != "ambiguous":
                    candidates.append((name, item))

            total = len(candidates)
            updated = unchanged = 0
            errors: list[str] = []
            for index, (name, current) in enumerate(candidates, start=1):
                self._check_cancel()
                fetched = None
                last_error = None
                for attempt in range(1, max_retries + 1):
                    try:
                        fetched = fetcher(current.video_id)
                        break
                    except Exception as exc:  # noqa: BLE001 - retry có giới hạn
                        last_error = exc
                        if attempt < max_retries:
                            time.sleep(min(2.0, 0.5 * (2 ** (attempt - 1))))
                if fetched is None:
                    errors.append(
                        f"{basename_compatible(name)}: "
                        f"{type(last_error).__name__ if last_error else 'UnknownError'}: "
                        f"{last_error or 'không có dữ liệu'}"
                    )
                    LOGGER_METADATA.warning(
                        "event=metadata.network_patch_failed warehouse=%r clip=%r "
                        "video_id=%s category=%s",
                        self.kho_dang_dung,
                        basename_compatible(name),
                        current.video_id,
                        type(last_error).__name__ if last_error else "UnknownError",
                    )
                elif not isinstance(fetched, dict):
                    errors.append(f"{basename_compatible(name)}: response không phải object.")
                else:
                    raw = {
                        "id": fetched.get("id") or current.video_id,
                        "title": fetched.get("title") or "",
                        "url": fetched.get("url") or f"https://youtu.be/{current.video_id}",
                        "upload_date": str(fetched.get("upload_date") or ""),
                        "duration": fetched.get("duration"),
                    }
                    validated = source_from_mapping(
                        {name: raw},
                        kind="network_patch",
                        priority=0,
                    )
                    entry = validated.entries[0] if validated.entries else None
                    if entry is None or entry.video_id != current.video_id:
                        errors.append(
                            f"{basename_compatible(name)}: metadata trả về sai identity/schema."
                        )
                    else:
                        old = dict(records.get(name) or current.public_dict())
                        patched = dict(old)
                        official = entry.public_dict()
                        replace_inferred = current.resolution_method == "filename_fallback"
                        for field in ("id", "title", "url", "upload_date", "duration"):
                            value = official.get(field)
                            if value not in ("", None) and (
                                replace_inferred or patched.get(field) in ("", None)
                            ):
                                patched[field] = value
                        patched["resolution_method"] = (
                            "video_id"
                            if all(
                                patched.get(field) not in ("", None)
                                for field in ("id", "title", "url", "upload_date", "duration")
                            )
                            else current.resolution_method
                        )
                        if patched == old:
                            unchanged += 1
                        else:
                            records[name] = patched
                            updated += 1
                            payload = {
                                "schema_version": 1,
                                "warehouse": self.kho_dang_dung,
                                "warehouse_id": self._slug(
                                    self.kho_dang_dung or "mac_dinh"
                                ),
                                "database": os.path.basename(self.db_file),
                                "updated_at": datetime.now().astimezone().isoformat(
                                    timespec="seconds"
                                ),
                                "sources": [{
                                    "kind": "explicit_network_patch",
                                    "file": "YouTube metadata API via yt-dlp",
                                }],
                                "stats": {
                                    "database_clips": len(self.db_clips()),
                                    "network_updated": updated,
                                    "network_errors": len(errors),
                                },
                                "clips": records,
                            }
                            ghi_json_an_toan(snapshot_path, payload)
                if progress:
                    progress(
                        index / total if total else 1.0,
                        f"[{index}/{total}] Metadata: {basename_compatible(name)}",
                    )

        self._invalidate_metadata_cache()
        LOGGER_METADATA.info(
            "event=metadata.network_patch_complete warehouse=%r total=%d "
            "updated=%d unchanged=%d errors=%d",
            self.kho_dang_dung,
            total,
            updated,
            unchanged,
            len(errors),
        )
        return {
            "tong": total,
            "da_va": updated,
            "bo_qua": unchanged,
            "loi": errors,
            "snapshot_path": snapshot_path,
        }

    def _audfprint_cmd(
        self,
        sub: str,
        *them: str,
        db_file: Optional[str] = None,
    ) -> list:
        ncores = self.config.ncores
        if ncores <= 0:
            ncores = so_nhan_nen_dung()
        return [sys.executable, "-u", self.audfprint, sub, "--dbase", db_file or self.db_file,
                "--ncores", str(ncores), "--continue-on-error", *them]

    def _audfprint_build_cmd(
        self,
        sub: str,
        *them: str,
        db_file: str,
    ) -> list:
        """Bọc audfprint để nhận event per-file, không sửa code vendored."""
        lenh_goc = self._audfprint_cmd(sub, *them, db_file=db_file)
        wrapper = os.path.join(self.root, "audfprint_progress_runner.py")
        return [sys.executable, "-u", wrapper, self.audfprint, *lenh_goc[3:]]

    def build_database(
        self,
        thumuc: str,
        mode: str = "new",
        progress: Optional[Callable] = None,
        progress_event: Optional[Callable[[FingerprintProgress], None]] = None,
        job_id: Optional[str] = None,
    ) -> dict:
        """Tạo/bổ sung vân tay với progress event thật và khóa liên tiến trình."""
        # Reset trước khi chờ khóa. Nếu người dùng bấm Dừng trong lúc chờ khóa,
        # _build_database_da_khoa phải nhìn thấy cờ đó thay vì xóa mất yêu cầu.
        self.cancel_event.clear()
        job_id = job_id or uuid.uuid4().hex
        tracker = FingerprintProgressTracker(
            job_id,
            callback=progress_event,
            legacy_callback=progress,
            logger=tao_fingerprint_logger(self.out_dir),
        )
        tracker.discovering()
        try:
            with KhoaTienTrinh(
                os.path.join(self.data_dir, "tool.lock"),
                "dựng kho vân tay",
            ):
                return self._build_database_da_khoa(
                    thumuc,
                    mode=mode,
                    progress=progress,
                    tracker=tracker,
                )
        except Cancelled:
            tracker.cancelled(
                "Đã dừng. Kho vân tay trước job vẫn nguyên; phần chưa ghi không được tính."
            )
            state = tracker.state
            return {
                "so_clip": state.total,
                "da_xu_ly": state.processed_count,
                "thanh_cong": 0,
                "da_tinh_xong_chua_ghi": state.success_count,
                "bo_qua": state.skipped_count,
                "that_bai": state.failed_count,
                "da_huy": True,
                "loi_file": [x["message"] for x in tracker.errors],
                "giay": state.elapsed_seconds,
                "canh_bao": [
                    f"{state.success_count} clip đã tính xong trong workspace tạm nhưng "
                    "chưa commit khi hủy; kho trước job vẫn nguyên."
                ],
            }
        except Exception as exc:
            tracker.logger.exception(
                "job_id=%s event=job_exception category=%s",
                job_id,
                type(exc).__name__,
            )
            if tracker.state.status != "failed":
                tracker.failed(
                    f"Không thể hoàn tất tạo vân tay: {exc}",
                    type(exc).__name__,
                )
            raise
        finally:
            dong_fingerprint_logger(tracker.logger)

    def _build_database_da_khoa(
        self,
        thumuc: str,
        mode: str = "new",
        progress: Optional[Callable] = None,
        tracker: Optional[FingerprintProgressTracker] = None,
    ) -> dict:
        """
        Tạo (mode='new') hoặc bổ sung (mode='add') kho vân tay từ thư mục clip gốc.
        Trả về {'so_clip': n, 'giay': t}.
        """
        tracker = tracker or FingerprintProgressTracker(
            uuid.uuid4().hex,
            legacy_callback=progress,
            logger=tao_fingerprint_logger(self.out_dir),
        )
        if mode not in {"new", "add"}:
            raise ValueError("mode tạo vân tay phải là 'new' hoặc 'add'.")
        self.require()
        self._check_cancel()
        if not os.path.isdir(thumuc):
            raise RuntimeError(f"Không tìm thấy thư mục: {thumuc}")
        files = liet_ke_media(thumuc)
        tracker.set_files(files)
        if not files:
            raise RuntimeError(f"Thư mục không có file media nào: {thumuc}")

        if self.kho_dang_dung:
            self.update_kho(self.kho_dang_dung, thumuc)

        shifts_kho = max(0, int(self.config.shifts_kho))
        db_da_ton_tai = os.path.exists(self.db_file)
        shifts_da_luu = 0
        if self.kho_dang_dung:
            dang_ky = self._doc_khos()
            kho_hien_tai = next(
                (k for k in dang_ky["danh_sach"]
                 if k["ten"] == self.kho_dang_dung),
                None,
            )
            if kho_hien_tai:
                shifts_da_luu = max(0, int(kho_hien_tai.get("shifts", 0) or 0))

        canh_bao = []
        if db_da_ton_tai and mode != "new" and shifts_da_luu != shifts_kho:
            canh_bao.append(
                f"Kho «{self.kho_dang_dung or os.path.basename(self.db_file)}» "
                f"được tạo với shifts={shifts_da_luu}, nhưng cấu hình hiện tại là "
                f"shifts={shifts_kho}. Nên tạo lại kho từ đầu để đồng bộ."
            )

        tong = len(files)
        da_co = set()
        if mode != "new" and os.path.exists(self.db_file):
            da_co = {
                os.path.normcase(os.path.abspath(clip["duong_dan"]))
                for clip in self.db_clips(bo_cache=True)
                if int(clip.get("so_hash", 0)) > 0
            }
        can_xu_ly = []
        for path in files:
            if os.path.normcase(os.path.abspath(path)) in da_co:
                tracker.skipped(path)
            else:
                can_xu_ly.append(path)

        if not can_xu_ly:
            tracker.saving()
            canh_bao.extend(self._cap_nhat_snapshot_sau_build(mode))
            tracker.completed("Mọi clip đều đã có vân tay; không cần ghi lại kho.", db_written=False)
            state = tracker.state
            return {
                "so_clip": tong,
                "da_xu_ly": state.processed_count,
                "thanh_cong": state.success_count,
                "bo_qua": state.skipped_count,
                "that_bai": state.failed_count,
                "da_huy": False,
                "loi_file": [],
                "giay": state.elapsed_seconds,
                "canh_bao": canh_bao,
            }

        workspace = os.path.join(self.data_dir, "fingerprint_jobs", tracker.job_id)
        os.makedirs(workspace, exist_ok=True)
        listfile = os.path.join(workspace, "clips.txt")
        db_tam = os.path.join(workspace, "database.pklz")
        with open(listfile, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(can_xu_ly))
        sub = "new"
        if mode != "new" and os.path.exists(self.db_file):
            tracker.phase("validating", "Đang tạo bản làm việc an toàn của kho hiện có...")
            with open(self.db_file, "rb") as nguon, open(db_tam, "xb") as dich:
                while True:
                    self._check_cancel()
                    khoi = nguon.read(8 * 1024 * 1024)
                    if not khoi:
                        break
                    dich.write(khoi)
                dich.flush()
                os.fsync(dich.fileno())
            shutil.copystat(self.db_file, db_tam)
            sub = "add"

        loi_file = []
        structured_seen = False
        started_paths: set[str] = set()

        def key(path: str) -> str:
            return os.path.normcase(os.path.abspath(path))

        def on_line(dong: str):
            nonlocal structured_seen
            if dong.startswith("TIMCLIP_FINGERPRINT_EVENT "):
                structured_seen = True
                try:
                    event = json.loads(dong.split(" ", 1)[1])
                    path = str(event.get("file") or "")
                    if event.get("event") == "clip_started" and path:
                        started_paths.add(key(path))
                        tracker.clip_started(path, int(event.get("process_pid") or 0) or None)
                    elif event.get("event") == "clip_phase" and path:
                        # Phase thật do chính tiến trình đang giải mã phát ra, không
                        # phải suy đoán từ việc bắt gặp tiến trình ffmpeg khi lấy mẫu.
                        phase = str(event.get("phase") or "")
                        if phase in PHASES_FINGERPRINT:
                            tracker.phase(
                                phase,
                                (
                                    f"Đang giải mã audio: {ten_file_an_toan(path)}"
                                    if phase == "decoding"
                                    else f"Đang tạo vân tay: {ten_file_an_toan(path)}"
                                ),
                                path,
                                int(event.get("process_pid") or 0) or None,
                            )
                    elif event.get("event") == "clip_finished" and path:
                        tracker.clip_finished(
                            path,
                            success=event.get("status") == "success",
                            elapsed=float(event.get("elapsed_seconds") or 0.0),
                            error_category=str(event.get("category") or ""),
                            message=str(event.get("message") or ""),
                        )
                        if tracker.state.processed_count >= tong:
                            tracker.saving(tracker.state.active_subprocess_pid)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    loi_file.append(f"Progress event không hợp lệ: {exc}")
                return
            if "ingesting #" in dong and not structured_seen:
                ten = dong.split(":", 1)[-1].replace("...", "").strip()
                started_paths.add(key(ten))
                tracker.clip_started(ten)
            if "Saved fprints for" in dong:
                tracker.saving(tracker.state.active_subprocess_pid)
            if any(k in dong for k in ("Error", "error", "Traceback", "Failed", "Cannot")):
                loi_file.append(dong)

        def on_heartbeat(snapshot: ProcessSnapshot) -> None:
            ffmpeg = [child for child in snapshot.children if "ffmpeg" in child.name]
            workers = [child for child in snapshot.children if "python" in child.name]
            phase = (
                "saving"
                if tracker.state.phase == "saving"
                else ("decoding" if ffmpeg else "fingerprinting")
            )
            detail = (
                f"Job vẫn hoạt động — audfprint PID {snapshot.pid}, "
                f"worker {len(workers)}, FFmpeg {len(ffmpeg)}, "
                f"im lặng {snapshot.silent_seconds:.0f} giây."
            )
            tracker.heartbeat(snapshot.pid, detail, phase=phase)

        # --maxtimebits 16: cho phép clip gốc dài tới ~25 phút vẫn định vị đúng mốc thời gian
        tham_so = ["--maxtimebits", "16"]
        if shifts_kho > 0:
            tham_so.extend(["--shifts", str(shifts_kho)])
        tham_so.extend(["--list", listfile])
        try:
            rc, duoi = self._run_stream(
                self._audfprint_build_cmd(sub, *tham_so, db_file=db_tam),
                on_line,
                on_heartbeat=on_heartbeat,
                logger=tracker.logger,
                process_name="audfprint-build",
                include_in_tail=lambda line: not line.startswith(
                    "TIMCLIP_FINGERPRINT_EVENT "
                ),
            )
            if rc != 0:
                chi_tiet = "\n".join(duoi[-12:]) or "(không có thông báo nào)"
                raise RuntimeError(
                    f"audfprint kết thúc với mã lỗi {rc}.\n\n"
                    f"Thông báo cuối cùng:\n{chi_tiet}"
                )

            # Tương thích adapter/test cũ: nếu không có structured event nhưng process
            # thành công, chỉ lúc này mới đánh dấu các file còn lại thành công.
            if not structured_seen:
                for path in can_xu_ly:
                    if key(path) not in started_paths:
                        tracker.clip_started(path)
                    tracker.clip_finished(path, success=True, elapsed=0.0)

            if not os.path.isfile(db_tam):
                raise RuntimeError("audfprint báo thành công nhưng không tạo database tạm.")
            tracker.saving(tracker.state.active_subprocess_pid)
            self._cache_khoa = None
            try:
                os.replace(db_tam, self.db_file)
            except PermissionError:
                ten_moi = (
                    f"kho_{self._slug(self.kho_dang_dung or 'kho')}_"
                    f"{uuid.uuid4().hex[:6]}.pklz"
                )
                db_moi = os.path.join(self.data_dir, ten_moi)
                os.replace(db_tam, db_moi)
                dang_ky = self._doc_khos()
                for kho in dang_ky["danh_sach"]:
                    if kho["ten"] == self.kho_dang_dung:
                        kho["db_cu"] = kho["db"]
                        kho["db"] = ten_moi
                self._ghi_khos(dang_ky)
                self._ap_dung_kho(self.kho_dang_dung, dang_ky)
                canh_bao.append(
                    "File vân tay cũ đang bị khóa; đã ghi kết quả vào file mới an toàn."
                )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        # Chỉ đổi metadata khi toàn bộ kho vừa được tạo mới, hoặc khi phần bổ sung
        # dùng đúng shifts cũ. Kho add lệch shifts phải tiếp tục mang metadata cũ
        # để những lượt sau vẫn cảnh báo cho tới khi người dùng chủ động tạo lại.
        if self.kho_dang_dung and (sub == "new" or shifts_da_luu == shifts_kho):
            dang_ky = self._doc_khos()
            for kho in dang_ky["danh_sach"]:
                if kho["ten"] == self.kho_dang_dung:
                    kho["shifts"] = shifts_kho
                    break
            self._ghi_khos(dang_ky)

        canh_bao.extend(self._cap_nhat_snapshot_sau_build(mode))
        tracker.completed()
        state = tracker.state
        return {
            "so_clip": tong,
            "da_xu_ly": state.processed_count,
            "thanh_cong": state.success_count,
            "bo_qua": state.skipped_count,
            "that_bai": state.failed_count,
            "da_huy": False,
            "loi_file": [*loi_file, *[x["message"] for x in tracker.errors]],
            "giay": state.elapsed_seconds,
            "canh_bao": canh_bao,
        }

    # =================================================================
    #  2) TẢI AUDIO TỪ YOUTUBE (dùng yt-dlp như một THƯ VIỆN)
    # =================================================================

    def cau_hinh_mang(self) -> "ytdlp_chung.CauHinhMang":
        """Tham số mạng/xác thực dùng chung cho mọi lượt gọi yt-dlp của engine."""
        return ytdlp_chung.CauHinhMang.tu_config(self.config)

    def _canh_bao_cookie_chet(self, loi: BaseException) -> None:
        """Ghi nhận việc phải bỏ cookie, để người dùng biết mà đi sửa gốc."""
        tin = ("Cookie YouTube đã hết hiệu lực — đang thử lại KHÔNG dùng cookie. "
               "Hãy xoá trống ô đường dẫn cookie ở thanh bên → «🔐 Kết nối YouTube», "
               "hoặc xuất lại file cookie mới.")
        LOGGER_SCAN.warning("event=cookie.het_han loi=%s",
                            ytdlp_chung.go_ma_mau(loi)[:160])
        if tin not in self.canh_bao_mang:
            self.canh_bao_mang.append(tin)

    def youtube_info(self, url: str) -> dict:
        import yt_dlp

        def lay(cau_hinh):
            opts = cau_hinh.tuy_chon(noplaylist=True, skip_download=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        # Cookie chết làm YouTube chỉ trả storyboard, và yt-dlp báo "Requested format
        # is not available" — câu chữ dẫn người dùng đi sai hướng hoàn toàn. Tự lùi về
        # không-cookie thay vì để cả lượt quét chết.
        info = ytdlp_chung.chay_kem_duong_lui_cookie(
            self.cau_hinh_mang(), lay, khi_bo_cookie=self._canh_bao_cookie_chet)
        # Ngày đăng phải được chốt NGAY TẠI ĐÂY, ở tầng nạp metadata. Exporter chỉ
        # định dạng lại, không bao giờ hỏi YouTube lần nữa.
        ngay = resolve_publication_date(info)
        ghi_log_chan_doan(str(info.get("id") or ""), ngay, info)
        return {
            "id": info.get("id", ""),
            "title": info.get("title", url),
            "duration": info.get("duration") or 0,
            "uploader": info.get("uploader", ""),
            "channel": info.get("channel") or info.get("uploader") or "",
            "channel_id": info.get("channel_id", ""),
            "channel_url": (
                info.get("channel_url") or info.get("uploader_url") or ""
            ),
            # Giữ tên khoá cũ nhưng mang giá trị CHÍNH TẮC; `upload_date_raw` để
            # chẩn đoán, không dùng cho báo cáo.
            "upload_date": ngay.yyyymmdd,
            "upload_date_raw": str(info.get("upload_date") or ""),
            "publication_date_source": ngay.source_field or "",
            "publication_date_confidence": ngay.confidence,
        }

    def _ten_phan_dau(self, video_id: str, gioi_han_giay: float) -> str:
        """Tiền tố tên file cho bản tải MỘT PHẦN.

        Dùng dấu `__` nên `glob(video_id + ".*")` — thứ tìm bản ĐẦY ĐỦ — không bao giờ
        khớp phải nó. Nếu bản một phần bị nhận nhầm là đầy đủ thì lượt quét sau sẽ
        lặng lẽ chỉ quét 3 tiếng rồi báo "không tìm thấy" cho cả video 66 tiếng: sai
        mà không có dấu hiệu nào.
        """
        return f"{video_id}__p{int(gioi_han_giay)}"

    def download_audio(self, url: str, video_id: str,
                       progress: Optional[Callable] = None,
                       gioi_han_giay: Optional[float] = None) -> str:
        """Tải RIÊNG phần audio (nhẹ hơn video hàng chục lần). Trả về đường dẫn file.

        ``gioi_han_giay``: chỉ tải bấy nhiêu giây ĐẦU thay vì cả video. Đo 19/08 trên
        video 15 phút: tải trọn 80,50 MB, tải 60 giây đầu chỉ 5,50 MB — tỉ lệ byte
        đúng bằng tỉ lệ thời lượng, tức yt-dlp thật sự chỉ lấy phần cần chứ không tải
        hết rồi cắt. Với video 66 tiếng: 18,4 GB xuống còn khoảng 840 MB.

        Bản một phần được đặt tên riêng để không bao giờ bị dùng nhầm làm bản đầy đủ.
        """
        import yt_dlp

        ten = (self._ten_phan_dau(video_id, gioi_han_giay) if gioi_han_giay
               else video_id)
        san_co = [f for f in glob.glob(os.path.join(self.dl_dir, ten + ".*"))
                  if not f.endswith((".part", ".ytdl"))]
        if san_co:
            self._bao(progress, 0.40, "Đã có sẵn audio, bỏ qua bước tải.")
            return san_co[0]

        def hook(d):
            self._check_cancel()
            if d.get("status") == "downloading":
                tong = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                da = d.get("downloaded_bytes") or 0
                ty_le = (da / tong) if tong else 0
                mb = da / 1024 / 1024
                self._bao(progress, 0.40 * ty_le,
                          f"Đang tải audio... {mb:,.0f} MB" +
                          (f" ({ty_le*100:.0f}%)" if tong else ""))
            elif d.get("status") == "finished":
                self._bao(progress, 0.40, "Tải xong, đang chuẩn bị xử lý...")

        # Tách phần riêng ra dict để dựng lại được tuỳ chọn với cấu hình mạng khác
        # (đường lui khi cookie hết hạn dựng lại toàn bộ opts, không sửa tại chỗ).
        rieng_cua_tai = dict(
            format=self.config.ytdlp_format,
            outtmpl=os.path.join(self.dl_dir, ten + ".%(ext)s"),
            noplaylist=True,
            continuedl=True,          # đứt mạng thì lần sau tải tiếp
            retries=10, fragment_retries=10,
            progress_hooks=[hook],
        )
        if gioi_han_giay:
            # `download_ranges` là HÀM (info_dict, ydl) -> Iterable[Section], KHÔNG
            # phải list — truyền list vào là yt-dlp gọi nó như hàm rồi nổ TypeError.
            rieng_cua_tai["download_ranges"] = (
                lambda info, ydl: [{"start_time": 0, "end_time": float(gioi_han_giay)}])
            # Không ép keyframe: ta chỉ cần audio, và ép keyframe buộc phải mã hoá lại.
            rieng_cua_tai["force_keyframes_at_cuts"] = False

        # YouTube chặn từng "player client" một cách độc lập và thay đổi theo thời
        # gian. Đo ngày 2026-08-18: client mặc định trả HTTP 403 cho MỌI video tải
        # mới, trong khi `android` tải bình thường — trích metadata thì vẫn chạy, nên
        # tool lấy được tiêu đề rồi mới chết ở khâu tải, rất dễ tưởng là hỏng link.
        #
        # Vòng lặp thử nằm ở `ytdlp_chung.thu_tung_client` để đường đồng bộ kênh dùng
        # chung đúng một bản. Khi YouTube chặn tiếp client khác, chỉ cần đổi thứ tự
        # trong `ytdlp_player_clients` là xong, không phải sửa code.
        da_thu: list = []

        def ghi_that_bai(ten: str, loi: BaseException) -> None:
            da_thu.append(ten)
            LOGGER_SCAN.warning(
                "event=download.client_failed video=%s client=%s loi=%s",
                video_id, ten, ytdlp_chung.go_ma_mau(loi)[:200],
            )
            self._bao(progress, 0.05,
                      f"Cách tải «{ten}» không được, đang thử cách khác...")

        def chay(rieng: dict):
            with yt_dlp.YoutubeDL(rieng) as ydl:
                ydl.download([url])

        def don_file_do_dang() -> None:
            """Xoá .part/.ytdl trước khi đổi client.

            Mỗi client trả một format khác nhau; `continuedl=True` gặp .part cũ sẽ nối
            byte của luồng MỚI vào luồng CŨ, ra file audio hỏng mà không báo lỗi.
            """
            for f in glob.glob(os.path.join(self.dl_dir, ten + ".*")):
                if f.endswith((".part", ".ytdl")):
                    with contextlib.suppress(OSError):
                        os.remove(f)

        def ghi_thanh_cong(ten: str, truoc_do: list) -> None:
            if truoc_do:
                LOGGER_SCAN.info(
                    "event=download.client_fallback video=%s dung=%s da_thu=%s",
                    video_id, ten, ",".join(truoc_do),
                )

        def tai_voi(cau_hinh):
            """Một lượt tải đầy đủ với MỘT bộ cấu hình mạng (có hoặc không cookie)."""
            return ytdlp_chung.thu_tung_client(
                cau_hinh.player_clients(self.config.ytdlp_player_clients),
                chay,
                cau_hinh.tuy_chon(**rieng_cua_tai),
                khi_that_bai=ghi_that_bai,
                bo_qua=(Cancelled,),   # huỷ là ý người dùng, không thử tiếp
                truoc_khi_thu_lai=don_file_do_dang,
                khi_thanh_cong=ghi_thanh_cong,
                bo_nho=self.nho_client,
            )

        goc = self.cau_hinh_mang()
        try:
            # Đường lui cookie bọc NGOÀI đường lui client: cookie chết thì mọi client
            # đều hỏng, nên thử hết client rồi mới bỏ cookie và thử lại từ đầu.
            ytdlp_chung.chay_kem_duong_lui_cookie(
                goc, tai_voi, khi_bo_cookie=self._canh_bao_cookie_chet)
        except RuntimeError as e:
            raise RuntimeError(ytdlp_chung.giai_thich_loi(e, goc.co_cookie)) from e

        san_co = [f for f in glob.glob(os.path.join(self.dl_dir, ten + ".*"))
                  if not f.endswith((".part", ".ytdl"))]
        if not san_co:
            raise RuntimeError("Tải audio thất bại (không thấy file sau khi tải).")
        return san_co[0]

    # =================================================================
    #  3) CẮT KHÚC + SO KHỚP
    # =================================================================

    def _overlap_thuc_te(
        self,
        progress: Optional[Callable] = None,
        pct: float = 0.0,
    ) -> int:
        """Tính overlap hiệu lực từ metadata, không làm thay đổi cấu hình gốc."""
        cfg = self.config
        tran = int(cfg.overlap_max_s)
        san = min(120, tran)
        de_xuat = int(cfg.overlap_s)
        clip_dai_nhat = 0.0

        if cfg.overlap_tu_dong:
            for meta in self.clip_meta().values():
                try:
                    duration = float(meta.get("duration") or 0)
                except (TypeError, ValueError):
                    continue
                if duration > clip_dai_nhat:
                    clip_dai_nhat = duration

            if clip_dai_nhat > 0:
                de_xuat = max(san, math.ceil(clip_dai_nhat + 30))

        overlap = min(tran, de_xuat)
        cfg.validate(overlap)
        if clip_dai_nhat > 0:
            thong_tin = (
                f"Khúc gối thực tế: {overlap} giây "
                f"(clip dài nhất: {math.ceil(clip_dai_nhat)} giây)."
            )
        else:
            thong_tin = (
                f"Khúc gối thực tế: {overlap} giây "
                "(không có metadata thời lượng, dùng cấu hình hiện tại)."
            )
        self._bao(progress, pct, thong_tin)
        return overlap

    @contextlib.contextmanager
    def scan_workspace(self, scan_job_id: Optional[str] = None):
        """Workspace riêng cho MỘT lượt quét.

        Trước đây mọi lượt quét dùng chung ``data/chunks``, ``data/_ds_khuc.txt`` và
        ``data/_raw_match.txt``; ``_cut_chunks`` còn ``rmtree`` thư mục chung ngay
        đầu hàm. Hai luồng quét đồng thời (GUI + Watch, hoặc hai batch) sẽ xoá chunk
        của nhau — đó là lỗi ĐÚNG/SAI chứ không phải chậm. Mỗi lượt quét nay có thư
        mục riêng nên không thể giẫm chân nhau.
        """
        goc = os.path.join(self.data_dir, "scan_jobs", scan_job_id or uuid.uuid4().hex)
        os.makedirs(os.path.join(goc, "chunks"), exist_ok=True)
        try:
            yield goc
        finally:
            shutil.rmtree(goc, ignore_errors=True)

    def _cut_chunks(self, media: str, progress: Optional[Callable] = None,
                    pct0: float = 0.40, pct1: float = 0.60,
                    workspace: Optional[str] = None,
                    tu_giay: float = 0.0, den_giay: Optional[float] = None) -> tuple:
        """Cắt file thành khúc WAV mono 11025 Hz. Trả ``(danh sách khúc, thời lượng)``.

        ``tu_giay``/``den_giay`` giới hạn phần được cắt, phục vụ quét tăng dần. Lưới
        mốc vẫn tính từ giây 0 rồi mới LỌC — nhờ vậy mốc của từng khúc y hệt như khi
        quét trọn, nên hai đường cho ra cùng kết quả và các đoạn nối nhau không cắt
        trùng. Thời lượng trả về luôn là của CẢ file, không phải của đoạn.
        """
        cfg = self.config
        overlap = self._overlap_thuc_te(progress, pct0)
        # Không có workspace (call site cũ) thì giữ nguyên hành vi cũ để tương thích.
        chunk_dir = os.path.join(workspace, "chunks") if workspace else self.chunk_dir
        if not workspace:
            shutil.rmtree(chunk_dir, ignore_errors=True)
        os.makedirs(chunk_dir, exist_ok=True)

        tong = self.duration_of(media)
        if not tong:
            raise RuntimeError(f"Không đọc được thời lượng file: {media}")

        buoc = cfg.chunk_s - overlap
        het = tong if den_giay is None else min(den_giay, tong)
        moc = [
            bat_dau
            for bat_dau in range(0, int(tong) + 1, buoc)
            if bat_dau < tong and tu_giay <= bat_dau < het
        ]
        ds = []
        if not moc:
            return ds, tong
        for i, bat_dau in enumerate(moc):
            self._check_cancel()
            out = os.path.join(chunk_dir, f"chunk_{int(bat_dau):07d}.wav")
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", str(bat_dau), "-t", str(cfg.chunk_s), "-i", media,
                 "-vn", "-ac", "1", "-ar", "11025", out],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024:
                ds.append(out)
            self._bao(progress, pct0 + (pct1 - pct0) * (i + 1) / len(moc),
                      f"Đang cắt khúc {i+1}/{len(moc)} (mốc {hhmmss(bat_dau)})...")
        return ds, tong

    def _match_chunks(self, chunks: list, progress: Optional[Callable] = None,
                      pct0: float = 0.60, pct1: float = 0.95,
                      workspace: Optional[str] = None,
                      hau_to: str = "") -> list:
        """So khớp một nhóm khúc với kho vân tay, trả về danh sách kết quả thô.

        VÌ SAO KHÔNG CÒN DÙNG ``--sortbytime``:
        audfprint cắt bớt kết quả THEO THỨ TỰ ĐANG CÓ, và nó cắt SAU khi đã sắp lại:

            results = results[(-results[:, 1]).argsort(),]   # mạnh nhất lên đầu
            if self.sort_by_time:
                rslts = rslts[(-rslts[:, 2]).argsort(), :]   # sắp lại theo align time
            return rslts[:self.max_returns, :]               # RỒI MỚI cắt

        Nghĩa là khi một khúc có nhiều hơn ``--max-matches`` kết quả, phần được giữ
        lại là phần có align time LỚN NHẤT, không phải phần MẠNH NHẤT. Đo trên khúc
        đầu của video sljyQs9RAhE: cấu hình cũ chỉ thấy khoảng t=[1482..1847]s, bỏ
        mất 207 kết quả nằm ở t=[3313..3505]s. Bỏ ``--sortbytime`` thì phần bị cắt
        là phần yếu nhất — đúng ngữ nghĩa mong muốn. Thứ tự thời gian vẫn được bảo
        đảm vì ``_merge()`` tự sắp theo ``start_s`` ở cuối.
        """
        goc = workspace or self.data_dir
        listfile = os.path.join(goc, f"_ds_khuc{hau_to}.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            f.write("\n".join(chunks))
        opfile = os.path.join(goc, f"_raw_match{hau_to}.txt")
        if os.path.exists(opfile):
            os.remove(opfile)

        dem = {"n": 0}

        def on_line(dong: str):
            if "Analyzed #" in dong:
                dem["n"] += 1
                self._bao(progress, pct0 + (pct1 - pct0) * dem["n"] / max(1, len(chunks)),
                          f"Đang so khớp vân tay... khúc {dem['n']}/{len(chunks)}")

        tham_so = [
            "--find-time-range", "--exact-count",
            "--min-count", "10", "--max-matches", str(self.config.max_matches),
        ]
        shifts_quet = max(0, int(self.config.shifts_quet))
        if shifts_quet > 0:
            tham_so.extend(["--shifts", str(shifts_quet)])
        tham_so.extend(["--opfile", opfile, "--list", listfile])
        self._bao(
            progress,
            pct0,
            "Đang nạp kho vân tay và bắt đầu so khớp...",
        )
        rc, duoi = self._run_stream(
            self._audfprint_cmd("match", *tham_so),
            on_line,
        )
        if rc != 0:
            raise RuntimeError("Lỗi khi so khớp:\n" + "\n".join(duoi[-10:]))

        tho = []
        dong_tho = dong_co_matched = 0
        theo_khuc: dict = {}
        if os.path.exists(opfile):
            with open(opfile, "r", encoding="utf-8", errors="replace") as f:
                for dong in f:
                    dong_tho += 1
                    dong = dong.strip()
                    if "Matched" not in dong:
                        continue
                    dong_co_matched += 1
                    m = RE_MATCH.search(dong)
                    if not m:
                        continue
                    khop = float(m.group(1))
                    t_khuc = float(m.group(2))
                    file_khuc = m.group(3).strip()
                    t_clip = float(m.group(4))
                    file_clip = m.group(5).strip()
                    so_hash = int(m.group(6))
                    ten_khuc = os.path.basename(file_khuc)
                    theo_khuc[ten_khuc] = theo_khuc.get(ten_khuc, 0) + 1
                    mk = RE_TEN_KHUC.search(ten_khuc)
                    offset = int(mk.group(1)) if mk else 0
                    # Khúc đã bị đổi tốc độ để bù né tránh thì mọi mốc thời gian
                    # ĐO TRONG khúc phải nhân ngược lại mới về đúng trục thời gian
                    # của video gốc. Mốc bắt đầu khúc (offset) thì không đổi.
                    he_so = giai_ma_he_so(mk.group(2) if mk else None)
                    bat_dau = offset + t_khuc * he_so
                    khop = khop * he_so
                    tho.append({"clip": file_clip, "bat_dau": bat_dau,
                                "khop": khop, "t_clip": t_clip, "hash": so_hash,
                                "align": bat_dau - t_clip})

        # Cộng dồn vào chẩn đoán của lượt quét: hàm này có thể được gọi nhiều lần
        # (đường đi nhanh Top-1 gọi hai lần) nên phải cộng chứ không gán đè.
        cd = self.chan_doan_quet
        cd.so_khuc += len(chunks)
        cd.dong_tho += dong_tho
        cd.dong_co_matched += dong_co_matched
        cd.parse_duoc += len(tho)
        cd.tran_max_matches = int(self.config.max_matches)
        cd.so_khuc_cham_tran += sum(
            1 for n in theo_khuc.values() if n >= self.config.max_matches
        )
        if dong_co_matched and not tho:
            cd.canh_bao.append(
                f"audfprint trả về {dong_co_matched} dòng khớp nhưng không đọc ra "
                "được dòng nào — nghi định dạng output đã đổi."
            )
            LOGGER_SCAN.warning(
                "event=scan.parser_mismatch matched_lines=%d parsed=0", dong_co_matched
            )
        return tho

    def _merge(self, tho: list) -> list:
        """
        Lọc và gộp các mảnh cùng lần xuất hiện.

        ``dedup_s`` vừa là dung sai align, vừa là khoảng trống tối đa giữa hai
        interval. Hash được tích phân theo mật độ tốt nhất trên từng đoạn con
        của hợp interval, tránh đếm đôi vùng overlap nhưng vẫn giữ đủ bằng
        chứng khi clip bị chia qua ranh giới khúc.
        """
        cfg = self.config
        self.canh_bao_gop = []
        qua_hash = [x for x in tho if x["hash"] >= cfg.min_hash]
        loc = [
            x for x in qua_hash
            if x["khop"] >= cfg.min_match_s
            and x["khop"] > 0
        ]
        # Ghi lại từng tầng để một kết quả 0 đoạn chỉ được đúng chỗ nó biến mất.
        cd = self.chan_doan_quet
        cd.qua_min_hash = len(qua_hash)
        cd.qua_min_match_s = len(loc)
        cd.hash_tho_lon_nhat = max((int(x["hash"]) for x in tho), default=0)
        cd.khop_tho_dai_nhat = round(max((float(x["khop"]) for x in tho), default=0.0), 1)
        loc.sort(key=lambda x: (x["clip"], x["align"], -x["hash"]))

        try:
            tong_hash = {
                os.path.basename(c["ten"]): int(c["so_hash"])
                for c in self.db_clips()
                if c.get("ten") and int(c.get("so_hash") or 0) > 0
            }
        except Exception as e:  # kho lỗi vẫn phải trả được kết quả chưa kẹp
            tong_hash = {}
            self.canh_bao_gop.append(
                f"Không đọc được tổng hash trong kho để áp cận trên: {e}"
            )

        def khoang_cach_interval(a: dict, b: dict) -> float:
            a0, a1 = a["bat_dau"], a["bat_dau"] + a["khop"]
            b0, b1 = b["bat_dau"], b["bat_dau"] + b["khop"]
            return max(0.0, max(a0, b0) - min(a1, b1))

        def tinh_hash_va_hop(manh: list) -> tuple:
            bien = sorted({
                moc
                for x in manh
                for moc in (x["bat_dau"], x["bat_dau"] + x["khop"])
                if x["khop"] > 0
            })
            cong_don = 0.0
            do_dai_hop = 0.0
            for a, b in zip(bien, bien[1:]):
                if b <= a:
                    continue
                phu = [
                    x for x in manh
                    if x["khop"] > 0
                    and x["bat_dau"] <= a
                    and b <= x["bat_dau"] + x["khop"]
                ]
                if not phu:
                    continue
                mat_do_tot_nhat = max(x["hash"] / x["khop"] for x in phu)
                do_dai_hop += b - a
                cong_don += (b - a) * mat_do_tot_nhat
            return round(cong_don), do_dai_hop

        gop = []
        for x in loc:
            trung = next(
                (
                    g for g in gop
                    if g["clip"] == x["clip"]
                    and abs(g["align"] - x["align"]) <= cfg.dedup_s
                    and any(
                        khoang_cach_interval(cu, x) <= cfg.dedup_s
                        for cu in g["manh"]
                    )
                ),
                None,
            )
            if trung is None:
                gop.append({
                    "clip": x["clip"],
                    "align": x["align"],
                    "manh": [dict(x)],
                })
            else:
                trung["manh"].append(dict(x))

        ket_qua = []
        for g in gop:
            manh = g["manh"]
            som_nhat = min(manh, key=lambda x: (x["bat_dau"], x["t_clip"]))
            vung_khop_s = min(x["bat_dau"] for x in manh)
            end_s = max(x["bat_dau"] + x["khop"] for x in manh)
            hash_uoc, do_dai_hop = tinh_hash_va_hop(manh)
            ten_clip = os.path.basename(g["clip"])
            gioi_han = tong_hash.get(ten_clip)
            if gioi_han is None:
                self.canh_bao_gop.append(
                    f"Không tra được tổng hash của clip «{ten_clip}»; "
                    f"giữ kết quả ước tính {hash_uoc}, không áp cận trên."
                )
                hashes = hash_uoc
            else:
                hashes = min(hash_uoc, gioi_han)
                if hash_uoc > gioi_han:
                    self.canh_bao_gop.append(
                        f"Hash ước tính của clip «{ten_clip}» là {hash_uoc}, "
                        f"đã chạm cận trên {gioi_han}; có dấu hiệu đếm trùng."
                    )
            clip_bat_dau_s = max(
                0.0,
                som_nhat["bat_dau"] - som_nhat["t_clip"],
            )
            ket_qua.append(Match(
                clip=ten_clip,
                start_s=clip_bat_dau_s,
                end_s=end_s,
                matched_s=do_dai_hop,
                clip_offset_s=vung_khop_s - clip_bat_dau_s,
                hashes=hashes,
                confidence=danh_gia(hashes),
                clip_bat_dau_s=clip_bat_dau_s,
                vung_khop_s=vung_khop_s,
            ))
        return sorted(ket_qua, key=lambda m: m.start_s)

    def _chon_loc_dai_dien(self, *args, **kwargs):
        """Giữ chỗ cho khả năng ghi đè trong test; mặc định dùng hàm thuần."""
        return chon_dai_dien(*args, **kwargs)

    def _tong_hash_kho(self) -> dict:
        """Bản đồ tên clip -> tổng số hash trong kho. Kho lỗi thì trả về rỗng."""
        try:
            return {c["ten"]: c["so_hash"] for c in self.db_clips() if c["so_hash"]}
        except Exception:  # noqa: BLE001 — chẩn đoán không được phép làm hỏng lượt quét
            return {}

    def _gan_chi_so(self, ds: list, duration: float) -> None:
        """Tính tỷ lệ vân tay khớp (%) và vùng vị trí cho từng kết quả."""
        tong_hash = self._tong_hash_kho()
        for m in ds:
            goc = tong_hash.get(m.clip, 0)
            m.ty_le = min(100.0, round(100.0 * m.hashes / goc, 1)) if goc else 0.0
            if duration:
                p = m.start_s / duration
                m.vung = "Đầu" if p < 1 / 3 else ("Giữa" if p < 2 / 3 else "Cuối")

    def _chon_loc(self, ds: list, duration: float) -> tuple:
        """
        Chọn ra top N kết quả tốt nhất, PHÂN BỔ ĐỀU theo vị trí trong video vi phạm.

        Vì sao phải phân bổ đều: một video vi phạm 3 tiếng thường ghép 9–18 clip gốc.
        Nếu chỉ lấy 5 cái nhiều hash nhất, chúng có thể nằm sát nhau ở đầu video —
        làm hồ sơ khiếu nại sẽ yếu vì trông như chỉ vi phạm một đoạn. Chia video
        thành N vùng đều nhau rồi mỗi vùng lấy một bằng chứng mạnh nhất thì hồ sơ
        chứng minh được vi phạm trải dài toàn bộ video.

        Trả về (danh_sách_chọn, danh_sách_bị_loại).

        Tiêu chí "đạt" do `chap_nhan_khop.loc_chap_nhan()` quyết định: ngoài ngưỡng
        hash tuyệt đối cũ còn có đường thứ hai cho clip gốc ngắn (phủ vân tay cao +
        đủ dài + đủ dày). Đường thứ hai CHỈ THÊM ứng viên nên không thể làm mất kết
        quả mà luật cũ đã nhận.
        """
        cfg = self.config
        dat, loai, ly_do = loc_chap_nhan(ds, cfg)
        cd = self.chan_doan_quet
        cd.duoc_chap_nhan = len(dat)
        if not dat:
            ghi_nhan_bi_loai(cd, loai, self._tong_hash_kho(), ly_do)
            return [], loai

        # `ty_le` chỉ dùng được khi _gan_chi_so đã chạy. Nếu chưa (gọi trực tiếp,
        # hoặc kho không tra được số hash gốc) thì mọi ty_le đều bằng 0 và xếp hạng
        # sẽ vô nghĩa — lúc đó lùi về `hashes` thay vì im lặng cho ra thứ tự tuỳ tiện.
        dung_ty_le = cfg.khoa_chat_luong == "ty_le" and any(
            float(getattr(m, "ty_le", 0.0) or 0.0) > 0 for m in dat
        )

        def do_manh(m) -> float:
            return float(m.ty_le) if dung_ty_le else float(m.hashes)

        def uu_tien(m, da_dung: set) -> tuple:
            """Xếp hạng: mạnh trước, clip chưa dùng trước, rồi tới độ mạnh khớp."""
            return (m.hashes >= cfg.min_hash_strong,
                    (m.clip not in da_dung) if cfg.uu_tien_clip_khac_nhau else True,
                    do_manh(m))

        def dai_dien(ung_vien: list, da_dung: set):
            """Chọn một đại diện: chất lượng trước, dễ kiểm tra chỉ để phá hoà."""
            return chon_dai_dien(
                ung_vien, duration, cfg.dung_sai_gan_bang,
                lambda m: uu_tien(m, da_dung),
                # Sàn chỉ có ý nghĩa khi xếp hạng bằng chỉ số chuẩn hoá; xếp bằng
                # `hashes` thì bản thân khoá đã là độ lớn tuyệt đối rồi.
                san_bang_chung=cfg.san_bang_chung if dung_ty_le else 0.0,
            )

        n = max(1, cfg.top_n)
        if not cfg.phan_bo_deu or not duration or len(dat) <= n:
            con, chon, da_dung = list(dat), [], set()
            while con and len(chon) < n:
                tot = dai_dien(con, da_dung)
                chon.append(tot)
                con.remove(tot)
                da_dung.add(tot.clip)
            loai = loai + con
        else:
            con = list(dat)
            chon, da_dung = [], set()
            buoc = duration / n
            # Lượt 1: mỗi vùng thời gian lấy 1 kết quả tốt nhất
            for i in range(n):
                t0, t1 = i * buoc, (i + 1) * buoc
                uv = [m for m in con if t0 <= m.start_s < t1]
                if uv:
                    tot = dai_dien(uv, da_dung)
                    chon.append(tot)
                    con.remove(tot)
                    da_dung.add(tot.clip)
            # Lượt 2: vùng nào trống thì bù bằng kết quả mạnh nhất còn lại
            while len(chon) < n and con:
                tot = dai_dien(con, da_dung)
                chon.append(tot)
                con.remove(tot)
                da_dung.add(tot.clip)
            loai = loai + con

        chon.sort(key=lambda m: m.start_s)   # xếp theo thời gian cho dễ đọc
        cd.da_chon = len(chon)
        if not chon:
            ghi_nhan_bi_loai(cd, loai, self._tong_hash_kho(), ly_do)
        return chon, loai

    # =================================================================
    #  3a) CHỐT CHẨN ĐOÁN PHỄU PHÁT HIỆN
    # =================================================================

    def _chot_chan_doan(self, kq: ScanResult) -> ChanDoanQuet:
        """Chốt phễu, ghi log có cấu trúc và lưu bản ghi cho ca không có kết quả."""
        cd = self.chan_doan_quet
        cd.da_chon = len(kq.matches)
        cd.chot_giai_doan()
        if cd.so_khuc_cham_tran:
            cd.canh_bao.append(
                f"{cd.so_khuc_cham_tran} khúc chạm trần --max-matches "
                f"({cd.tran_max_matches}); có thể còn kết quả yếu hơn chưa được xét. "
                "Tăng «Số kết quả tối đa mỗi khúc» nếu cần soi kỹ hơn."
            )
        LOGGER_SCAN.info(
            "event=scan.funnel source_id=%s %s",
            kq.source_id or kq.source_name, cd.dong_log(),
        )
        if cd.giai_doan_mat and kq.status == "ok":
            with contextlib.suppress(Exception):
                self._luu_chan_doan(kq, cd)
        return cd

    def _luu_chan_doan(self, kq: ScanResult, cd: ChanDoanQuet) -> None:
        """Lưu bản ghi JSON nhẹ cho ca 0 kết quả, để soi lại mà không cần quét lại.

        Chỉ ghi số liệu phễu và cấu hình đã dùng — không ghi media, không ghi cookie
        hay khoá API. Giữ tối đa 200 file gần nhất.
        """
        thu_muc = os.path.join(self.data_dir, "chan_doan")
        os.makedirs(thu_muc, exist_ok=True)
        ban_ghi = {
            "thoi_diem": datetime.now().isoformat(timespec="seconds"),
            "video": kq.source_id or kq.source_name,
            "source_ref": kq.source_ref,
            "duration_s": round(kq.duration_s, 1),
            "kho": self.kho_dang_dung,
            "kho_db": os.path.basename(self.db_file),
            "cau_hinh": {
                k: getattr(self.config, k) for k in (
                    "chunk_s", "overlap_max_s", "min_hash", "min_match_s",
                    "max_matches", "shifts_quet", "min_hash_floor",
                    "min_hash_strong", "ty_le_chap_nhan", "min_match_chap_nhan",
                    "mat_do_toi_thieu", "top_n",
                )
            },
            "phieu_phat_hien": cd.thanh_dict(),
        }
        ten = ten_file_an_toan(f"{ban_ghi['video']}_{int(time.time())}") + ".json"
        ghi_json_an_toan(os.path.join(thu_muc, ten), ban_ghi)
        cu = sorted(glob.glob(os.path.join(thu_muc, "*.json")), key=os.path.getmtime)
        for path in cu[:-200]:
            with contextlib.suppress(OSError):
                os.remove(path)

    # =================================================================
    #  3b) ĐƯỜNG ĐI NHANH KHI CHỈ CẦN MỘT KẾT QUẢ (top_n = 1)
    # =================================================================

    def _du_manh_de_dung_som(self, tho: list, duration: float) -> Optional[Match]:
        """Trong nhóm khúc vừa quét đã có ứng viên đủ mạnh để dừng hẳn chưa?

        Cổng dừng sớm phải CHẶT hơn hẳn tiêu chí chấp nhận thường: dừng sớm đồng
        nghĩa với việc không bao giờ nhìn phần còn lại của video, nên chỉ được dừng
        khi bằng chứng mạnh tới mức phần còn lại không thể đổi kết luận.

        Số tham chiếu đo thật: một bản reup nguyên vẹn cho 15.173 hash trên 786,8
        giây; clip gốc nguyên bản cho 4.610 hash trên 263,6 giây. Trong khi đó nhiễu
        mạnh nhất đo được trên 11 video âm tính chỉ đạt 309 hash và nhạc hiệu dùng
        chung chỉ đạt 133 hash / 8,8 giây. Cổng mặc định 5.000 hash + 60 giây nằm
        giữa hai vùng đó, lệch hẳn về phía an toàn.
        """
        cfg = self.config
        if not tho:
            return None
        ung_vien = self._merge(tho)
        if not ung_vien:
            return None
        self._gan_chi_so(ung_vien, duration)
        dat, _, _ = loc_chap_nhan(ung_vien, cfg)
        du = [
            m for m in dat
            if m.hashes >= cfg.top1_hash_dung_som
            and m.matched_s >= cfg.top1_match_s_dung_som
        ]
        if not du:
            return None
        return max(du, key=lambda m: (m.hashes, m.matched_s))

    def _quet_tho(self, chunks: list, duration: float,
                  progress: Optional[Callable], pct0: float, pct1: float,
                  workspace: str) -> list:
        """Lấy kết quả thô cho toàn bộ khúc, có thể dừng sớm khi top_n = 1.

        Chiến lược: quét khúc ĐẦU trước (nơi người kiểm tra dễ tua tới nhất), nếu đã
        có bằng chứng vượt cổng dừng sớm thì trả về luôn; nếu chưa thì quét nốt phần
        còn lại TRONG MỘT LẦN GỌI nữa và ghép kết quả thô lại.

        Nhờ ghép kết quả thô thay vì quét lại từ đầu, đường đi nhanh không làm tăng
        khối lượng so khớp — chỉ tốn thêm đúng một lần nạp kho vân tay (đo được
        khoảng 13 giây) trong trường hợp phải quét tiếp. Đổi lại, khi gặp bản reup
        rõ ràng nằm ở đầu video thì bỏ qua được toàn bộ phần sau.
        """
        cfg = self.config
        cd = self.chan_doan_quet
        du_dieu_kien = (
            cfg.top1_tim_nhanh
            and cfg.top_n == 1
            and len(chunks) >= max(2, cfg.top1_khuc_toi_thieu)
        )
        if not du_dieu_kien:
            cd.duong_di = "quet_toan_bo"
            return self._match_chunks(chunks, progress, pct0, pct1, workspace=workspace)

        # Chia đôi tiến độ: phần đầu cho vùng ưu tiên, phần sau cho quét bù.
        giua = pct0 + (pct1 - pct0) * 0.35
        self._bao(progress, pct0,
                  "Tìm nhanh 1 kết quả đáng tin — đang kiểm tra phần đầu video...")
        dau = self._match_chunks(chunks[:1], progress, pct0, giua,
                                 workspace=workspace, hau_to="_uu_tien")
        som = self._du_manh_de_dung_som(dau, duration)
        if som is not None:
            cd.duong_di = "dung_som_vung_dau"
            LOGGER_SCAN.info(
                "event=scan.top1.early_accept clip=%s hashes=%d matched_s=%.1f ratio=%.1f",
                som.clip, som.hashes, som.matched_s, som.ty_le,
            )
            self._bao(progress, pct1,
                      f"✓ Đã tìm thấy bằng chứng đủ mạnh ở phần đầu "
                      f"({som.hashes} hash, khớp {hhmmss(som.matched_s)}) — "
                      "bỏ qua phần còn lại.")
            return dau

        cd.duong_di = "quet_bu_toan_bo"
        self._bao(progress, giua,
                  "Chưa có bằng chứng đủ mạnh ở phần đầu — đang mở rộng quét toàn bộ video...")
        con_lai = self._match_chunks(chunks[1:], progress, giua, pct1,
                                     workspace=workspace, hau_to="_con_lai")
        return dau + con_lai

    # =================================================================
    #  3c) BÙ VIDEO BỊ ĐỔI TỐC ĐỘ ĐỂ NÉ VÂN TAY
    # =================================================================

    def _gioi_han_tai(self, tong: float) -> Optional[float]:
        """Chỉ tải bao nhiêu giây đầu? ``None`` = tải trọn như cũ.

        Dùng chung ngưỡng và bước với quét tăng dần: phần tải về đúng bằng phần lượt
        quét đầu tiên cần, không thừa không thiếu.
        """
        cfg = self.config
        if not getattr(cfg, "tai_mot_phan", False):
            return None
        buoc = float(getattr(cfg, "quet_tang_dan_buoc_gio", 0) or 0) * 3600
        nguong = float(getattr(cfg, "quet_tang_dan_tu_gio", 0) or 0) * 3600
        if buoc <= 0 or not tong or tong <= nguong or buoc >= tong:
            return None
        return buoc

    def _doan_quet_tang_dan(self, tong: float) -> list:
        """Chia trục thời gian thành các đoạn để quét lần lượt.

        Trả về ``[(0, tổng)]`` — tức quét trọn một lượt như cũ — khi tính năng tắt,
        khi video ngắn hơn ngưỡng, hoặc khi cấu hình vô lý. Giữ đúng hành vi cũ cho
        video ngắn là có chủ đích: chia nhỏ một video 20 phút chỉ tốn thêm chi phí nạp
        kho vân tay cho mỗi đoạn mà chẳng tiết kiệm được gì.
        """
        cfg = self.config
        buoc = float(getattr(cfg, "quet_tang_dan_buoc_gio", 0) or 0) * 3600
        nguong = float(getattr(cfg, "quet_tang_dan_tu_gio", 0) or 0) * 3600
        if not getattr(cfg, "quet_tang_dan", False) or buoc <= 0 or tong <= nguong:
            return [(0.0, tong)]
        doan = []
        tu = 0.0
        while tu < tong:
            doan.append((tu, min(tu + buoc, tong)))
            tu += buoc
        return doan or [(0.0, tong)]

    def _co_ung_vien_dat(self, tho: list, duration: float) -> bool:
        """Đã có ứng viên nào đạt tiêu chí chấp nhận chưa? Không đụng chẩn đoán cuối."""
        if not tho:
            return False
        ung_vien = self._merge(tho)
        if not ung_vien:
            return False
        self._gan_chi_so(ung_vien, duration)
        dat, _, _ = loc_chap_nhan(ung_vien, self.config)
        return bool(dat)

    def _bien_doi_khuc(self, chunks: list, he_so: float, ho: str,
                       workspace: str) -> list:
        """Tạo bản khúc đã đổi tốc độ ``he_so`` lần; mã hệ số vào tên file.

        Đổi tốc độ trên chính file khúc (đã là WAV 11 kHz mono) chứ không giải mã
        lại video gốc — rẻ hơn nhiều lần.
        """
        thu_muc = os.path.join(workspace, "chunks")
        os.makedirs(thu_muc, exist_ok=True)
        ma = ma_he_so(he_so)
        ra = []
        for khuc in chunks:
            self._check_cancel()
            mk = RE_TEN_KHUC.search(os.path.basename(khuc))
            if not mk:
                continue
            out = os.path.join(thu_muc, f"chunk_{int(mk.group(1)):07d}_k{ma}.wav")
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", khuc,
                 "-vn", "-ac", "1", "-ar", "11025",
                 "-af", bo_loc_ffmpeg(he_so, ho), out],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024:
                ra.append(out)
        return ra

    def _ke_hoach_toc_do(self, tho: list) -> list:
        """Danh sách (hệ số, họ biến đổi, mô tả) cần thử, theo thứ tự ưu tiên.

        Ưu tiên tuyệt đối cho ước lượng đọc từ độ trôi align: nó chính xác tới
        ~0,01% và không tốn một giây so khớp nào để có được. Lưới quét mù chỉ chạy
        khi không đọc được gì, và chỉ nhằm bù vùng cao độ bị đổi — vùng mà không
        mảnh khớp nào sống sót nên không có gì để hồi quy.
        """
        cfg = self.config
        ke_hoach = []
        uoc = uoc_luong_toc_do(
            tho,
            min_manh=cfg.toc_do_min_manh,
            min_ty_le_hop=cfg.toc_do_thang_hang,
            lech_toi_thieu=cfg.toc_do_lech_toi_thieu,
            lech_toi_da=cfg.toc_do_lech_toi_da,
        )
        for u in uoc:
            ke_hoach.append((u.he_so_bu, HO_TEMPO,
                             f"đo từ độ trôi: video {u.mo_ta()}"))
        if not ke_hoach:
            for k in cfg.luoi_tempo:
                ke_hoach.append((1.0 / float(k), HO_TEMPO,
                                 f"lưới tốc độ {float(k):.3f}"))
            for k in cfg.luoi_resample:
                ke_hoach.append((1.0 / float(k), HO_RESAMPLE,
                                 f"lưới cao độ {float(k):.3f}"))
        return ke_hoach[: max(0, cfg.toc_do_toi_da_thu)]

    def _quet_da_toc_do(self, chunks: list, tho: list,
                        progress: Optional[Callable], pct0: float, pct1: float,
                        workspace: str) -> list:
        """Quét lại ở các tốc độ đã hiệu chỉnh; trả về kết quả thô ĐÃ quy đổi mốc.

        Chỉ được gọi khi lượt quét thường không có ứng viên nào đạt chuẩn.
        """
        cfg = self.config
        cd = self.chan_doan_quet
        hang_doi = self._ke_hoach_toc_do(tho)
        if not hang_doi:
            return []

        def uoc_lai(tat_ca_tho: list) -> list:
            return uoc_luong_toc_do(
                tat_ca_tho,
                min_manh=cfg.toc_do_min_manh,
                min_ty_le_hop=cfg.toc_do_thang_hang,
                lech_toi_thieu=cfg.toc_do_lech_toi_thieu,
                lech_toi_da=cfg.toc_do_lech_toi_da,
            )

        da_thu: set = set()
        them: list = []
        lan = 0
        while hang_doi and lan < max(0, cfg.toc_do_toi_da_thu):
            he_so, ho, mo_ta = hang_doi.pop(0)
            khoa = (round(he_so, 5), ho)
            if khoa in da_thu:
                continue
            da_thu.add(khoa)
            lan += 1
            self._check_cancel()

            p0 = pct0 + (pct1 - pct0) * (lan - 1) / max(1, cfg.toc_do_toi_da_thu)
            p1 = pct0 + (pct1 - pct0) * lan / max(1, cfg.toc_do_toi_da_thu)
            cd.da_thu_toc_do.append(mo_ta)
            self._bao(progress, p0, f"Thử bù tốc độ (lượt {lan}) — {mo_ta}...")

            khuc_moi = self._bien_doi_khuc(chunks, he_so, ho, workspace)
            if not khuc_moi:
                continue
            ket = self._match_chunks(khuc_moi, progress, p0, p1,
                                     workspace=workspace,
                                     hau_to=f"_k{ma_he_so(he_so)}_{ho}")
            for khuc in khuc_moi:
                with contextlib.suppress(OSError):
                    os.remove(khuc)
            if not ket:
                continue
            them.extend(ket)

            if self._co_ung_vien_dat(tho + them, 0.0):
                cd.toc_do_tim_duoc = mo_ta
                LOGGER_SCAN.info(
                    "event=scan.tempo.recovered factor=%.5f family=%s note=%s",
                    he_so, ho, mo_ta,
                )
                self._bao(progress, p1,
                          f"✓ Tìm thấy bằng chứng sau khi bù tốc độ — {mo_ta}")
                break

            # Chưa đạt nhưng lượt vừa rồi thường để lại NHIỀU mảnh hơn hẳn, nên ước
            # lượng lại sẽ chính xác hơn. Mọi mốc đã được quy về trục thời gian gốc
            # nên độ dốc luôn cho ra TỔNG tỉ lệ, không phải phần dư — cứ ước lượng
            # lại trên toàn bộ mảnh đã có là hội tụ dần. Giữ nguyên họ biến đổi:
            # sai cao độ thì phải bù bằng resample, đổi tốc độ suông không cứu được.
            for u in uoc_lai(tho + them):
                moi = (round(u.he_so_bu, 5), ho)
                if moi in da_thu:
                    continue
                hang_doi.insert(0, (u.he_so_bu, ho, f"tinh chỉnh: video {u.mo_ta()}"))
        return them

    # =================================================================
    #  4) CÁC HÀM QUÉT CẤP CAO (giao diện chỉ cần gọi những hàm này)
    # =================================================================

    def scan_media(self, path: str, label: Optional[str] = None, ref: str = "",
                   source_type: str = "file", progress: Optional[Callable] = None,
                   luu_lich_su: bool = True, pct_start: float = 0.0) -> ScanResult:
        """
        Quét 1 file media dài có sẵn trên đĩa.
        pct_start: mốc % bắt đầu — bằng 0 khi quét file trực tiếp, bằng 0.40 khi
        được gọi sau bước tải YouTube (để thanh tiến độ chạy liền mạch 0 -> 100%).
        """
        self.require(can_db=True)
        # Mốc phần trăm cắt-khúc cũ không còn cố định: quét tăng dần chia dải
        # `pct_start..p_match1` cho từng đoạn, mỗi đoạn tự có phần cắt và phần khớp.
        p_match1 = 0.95
        if source_type == "file":
            self.cancel_event.clear()
        ten = label or os.path.basename(path)
        kq = ScanResult(source_name=ten, source_ref=ref or path)
        self.chan_doan_quet = ChanDoanQuet()
        try:
            if not os.path.isfile(path):
                raise RuntimeError(f"Không tìm thấy file: {path}")
            with self.scan_workspace() as ws:
                tong = self.duration_of(path)
                if not tong:
                    raise RuntimeError(f"Không đọc được thời lượng file: {path}")
                kq.duration_s = tong
                doan = self._doan_quet_tang_dan(tong)
                tho: list = []
                chunks: list = []
                da_quet_den = 0.0
                for i, (tu, den) in enumerate(doan):
                    # Chia dải phần trăm cho từng đoạn để thanh tiến độ không giật lùi.
                    a = pct_start + (p_match1 - pct_start) * i / len(doan)
                    b = pct_start + (p_match1 - pct_start) * (i + 1) / len(doan)
                    giua = a + (b - a) * 0.35
                    if len(doan) > 1:
                        self._bao(progress, a,
                                  f"Quét đoạn {i+1}/{len(doan)} "
                                  f"({hhmmss(tu)} → {hhmmss(min(den, tong))})...")
                    moi, _ = self._cut_chunks(path, progress, a, giua, workspace=ws,
                                              tu_giay=tu, den_giay=den)
                    if not moi:
                        continue
                    chunks += moi
                    tho += self._quet_tho(moi, tong, progress, giua, b, ws)
                    da_quet_den = min(den, tong)
                    # DỪNG KHI THẤY: đã có bằng chứng đạt chuẩn thì phần còn lại không
                    # đổi được kết luận. Không mất độ phủ vì nếu KHÔNG thấy gì, vòng lặp
                    # vẫn chạy hết video.
                    if len(doan) > 1 and self._co_ung_vien_dat(tho, tong):
                        break
                if not chunks:
                    raise RuntimeError("Không cắt được khúc nào từ file này.")
                kq.pham_vi_quet_s = da_quet_den
                # Không có gì đạt chuẩn thì thử bù tốc độ trước khi kết luận là
                # không có. Đây là lúc DUY NHẤT lượt quét phụ được chạy, nên video
                # có kết quả bình thường không tốn thêm giây nào.
                if self.config.quet_da_toc_do and not self._co_ung_vien_dat(tho, tong):
                    tho = tho + self._quet_da_toc_do(
                        chunks, tho, progress, p_match1, p_match1, ws
                    )
            tat_ca = self._merge(tho)
            if self.canh_bao_gop:
                kq.note = "\n".join(self.canh_bao_gop)
                for canh_bao in self.canh_bao_gop:
                    self._bao(progress, p_match1, f"⚠️ {canh_bao}")
            # Chặn tự khớp: nếu chính file đang quét cũng nằm trong kho vân tay
            # (do lỡ để chung thư mục), nó sẽ khớp 100% với chính nó — vô nghĩa.
            goc = os.path.basename(path).lower()
            tat_ca = [m for m in tat_ca if m.clip.lower() != goc]
            self._gan_chi_so(tat_ca, tong)
            self.chan_doan_quet.gop_lai = len(tat_ca)
            # Hợp đồng cũ giữ nguyên: số ứng viên ĐẠT chuẩn TRƯỚC khi cắt còn Top-N.
            # Chỉ định nghĩa "đạt" là mở rộng thêm bậc phủ vân tay cao.
            dat_chuan, _, _ = loc_chap_nhan(tat_ca, self.config)
            kq.so_dat_nguong = len(dat_chuan)
            # Chia vùng chọn lọc theo PHẦN ĐÃ QUÉT, không theo cả video: chia theo cả
            # video thì các vùng sau rơi vào khoảng chưa quét — vùng rỗng, và Top-N trả
            # về ít kết quả hơn hẳn mức đáng ra có. Còn nhãn Đầu/Giữa/Cuối ở
            # `_gan_chi_so` thì vẫn theo VIDEO THẬT, vì đó là sự thật về video.
            kq.matches, kq.matches_loai = self._chon_loc(
                tat_ca, kq.pham_vi_quet_s or tong)
            if kq.quet_mot_phan:
                tin = (f"Đã dừng sớm sau khi quét {hhmmss(kq.pham_vi_quet_s)}"
                       f"/{hhmmss(tong)} — đã đủ bằng chứng nên không quét tiếp. "
                       "Bằng chứng chỉ nằm trong phần đã quét.")
                kq.note = "\n".join([x for x in (kq.note, tin) if x])
                self._bao(progress, p_match1, "ℹ️ " + tin)
            tb = f"Xong — chọn {len(kq.matches)} kết quả tốt nhất"
            if kq.matches_loai:
                tb += f" (loại {len(kq.matches_loai)} kết quả yếu)"
            self._bao(progress, 1.0, tb + ".")
        except Cancelled:
            kq.status, kq.note = "error", "Đã hủy theo yêu cầu."
        except Exception as e:
            kq.status, kq.note = "error", ytdlp_chung.giai_thich_loi(e)
        finally:
            shutil.rmtree(self.chunk_dir, ignore_errors=True)
            kq.chan_doan = self._chot_chan_doan(kq)
        if luu_lich_su:
            kq.job_id = self.save_job(kq, source_type)
        return kq

    def scan_youtube(self, url: str, progress: Optional[Callable] = None,
                     luu_lich_su: bool = True) -> ScanResult:
        """Tải audio 1 link YouTube rồi quét."""
        self.require(can_ytdlp=True, can_db=True)
        self.cancel_event.clear()
        self.canh_bao_mang = []
        kq = ScanResult(source_name=url, source_ref=url)
        try:
            self._bao(progress, 0.02, "Đang lấy thông tin video...")
            info = self.youtube_info(url)
            kq.source_name = info["title"] or url
            kq.source_id = info["id"]
            kq.channel_name = info["channel"]
            kq.channel_id = info["channel_id"]
            kq.channel_url = info["channel_url"]
            kq.upload_date = info["upload_date"]
            self._bao(progress, 0.05,
                      f"{kq.source_name} ({hhmmss(info['duration'])}) — chuẩn bị tải audio...")
            # Tải một phần trước cho video rất dài. Không thấy gì thì mới tải trọn —
            # nhờ vậy KHÔNG mất độ phủ, chỉ đổi thứ tự. Đo 19/08: video 66 tiếng có
            # 18,4 GB, tải 3 tiếng đầu chỉ khoảng 840 MB.
            gioi_han = self._gioi_han_tai(info.get("duration") or 0)
            f = self.download_audio(url, info["id"], progress,
                                    gioi_han_giay=gioi_han)
            r = self.scan_media(f, label=kq.source_name, ref=url,
                                source_type="youtube", progress=progress,
                                luu_lich_su=False, pct_start=0.40)
            if gioi_han and not r.matches:
                # Phần đầu sạch không kết luận được gì cho cả video: phải tải nốt.
                self._bao(progress, 0.40,
                          f"Không thấy gì trong {hhmmss(gioi_han)} đầu — "
                          "tải nốt phần còn lại để quét trọn...")
                f = self.download_audio(url, info["id"], progress)
                r = self.scan_media(f, label=kq.source_name, ref=url,
                                    source_type="youtube", progress=progress,
                                    luu_lich_su=False, pct_start=0.40)
            elif gioi_han:
                # File chỉ dài `gioi_han` nên scan_media tưởng đã quét trọn "video" và
                # KHÔNG ghi chú gì. Sửa lại theo thời lượng THẬT, rồi phải TỰ ghi chú ở
                # đây — nếu không, báo cáo và lịch sử im lặng như thể đã quét cả 66
                # tiếng, đúng cái hiểu nhầm mà ghi chú đó sinh ra để chặn.
                r.duration_s = float(info.get("duration") or r.duration_s)
                r.pham_vi_quet_s = min(r.pham_vi_quet_s or gioi_han, gioi_han)
                if r.quet_mot_phan:
                    tin = (f"Chỉ TẢI và quét {hhmmss(r.pham_vi_quet_s)} đầu "
                           f"/{hhmmss(r.duration_s)} — đã đủ bằng chứng nên không tải "
                           "tiếp. Bằng chứng chỉ nằm trong phần đã quét.")
                    r.note = "\n".join([x for x in (r.note, tin) if x])
            r.source_ref = url
            r.source_id = info["id"]
            r.channel_name = info["channel"]
            r.channel_id = info["channel_id"]
            r.channel_url = info["channel_url"]
            r.upload_date = info["upload_date"]
            if not self.config.keep_downloads:
                with contextlib.suppress(Exception):
                    os.remove(f)
            kq = r
        except Cancelled:
            kq.status, kq.note = "error", "Đã hủy theo yêu cầu."
        except Exception as e:
            kq.status, kq.note = "error", ytdlp_chung.giai_thich_loi(
                e, self.cau_hinh_mang().co_cookie)
        # Cảnh báo mạng phải đi kèm kết quả, nếu không người dùng chỉ thấy "chạy được"
        # mà không biết cookie đã chết và tool đang âm thầm chạy không cookie.
        if self.canh_bao_mang:
            kq.note = "\n".join([*self.canh_bao_mang, kq.note or ""]).strip()
        if luu_lich_su:
            kq.job_id = self.save_job(kq, "youtube")
        return kq

    def scan_iter(
        self,
        nguon: Iterable,
        source_type: str = "youtube",
        progress: Optional[Callable] = None,
        on_video: Optional[Callable] = None,
    ):
        """Quét lần lượt nhiều nguồn, **yield từng ScanResult ngay khi xong**.

        Đây là API nền cho streaming result: người dùng thấy kết quả video 1 mà
        không phải chờ video 10. ``scan_many()`` giờ chỉ là ``list(scan_iter(...))``
        nên mọi call site cũ (CLI, Watch, test) giữ nguyên hành vi.

        ``on_video(index, total, ket_qua)`` được gọi ngay sau mỗi video — dùng để
        đẩy Sheets/ghi UI mà không chặn video kế tiếp. Ngoại lệ trong callback được
        nuốt có chủ đích và ghi log: một lỗi ở tầng giao hàng không được phép làm
        hỏng lượt quét đang chạy tốt.
        """
        nguon = list(nguon)
        tong = len(nguon)
        for i, x in enumerate(nguon, 1):
            def p(pct, msg, i=i):
                self._bao(progress, (i - 1 + pct) / max(1, tong), f"[{i}/{tong}] {msg}")

            ket_qua = (
                self.scan_youtube(x, p) if source_type == "youtube"
                else self.scan_media(x, progress=p)
            )
            if on_video:
                try:
                    on_video(i, tong, ket_qua)
                except Exception:  # noqa: BLE001
                    LOGGER_SCAN.exception(
                        "event=scan.on_video_callback_failed index=%d total=%d", i, tong
                    )
            yield ket_qua

    def scan_many(self, nguon: Iterable, source_type: str = "youtube",
                  progress: Optional[Callable] = None) -> list:
        """Quét lần lượt nhiều nguồn. progress nhận thêm tiền tố [i/n]."""
        return list(self.scan_iter(nguon, source_type, progress))

    def cancel(self) -> None:
        self.cancel_event.set()

    # =================================================================
    #  5) LỊCH SỬ (SQLite) & XUẤT BÁO CÁO
    # =================================================================

    def save_job(self, kq: ScanResult, source_type: str) -> int:
        with self._db() as c:
            cur = c.execute(
                "INSERT INTO jobs(created_at, source_type, source_name, source_ref,"
                " duration_s, status, n_matches, note, source_id)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), source_type,
                 kq.source_name, kq.source_ref, kq.duration_s, kq.status,
                 len(kq.matches), kq.note, kq.source_id))
            job_id = cur.lastrowid
            for m in kq.matches:
                c.execute("INSERT INTO matches(job_id, clip, start_s, end_s, matched_s,"
                          " clip_offset_s, hashes, confidence) VALUES(?,?,?,?,?,?,?,?)",
                          (job_id, m.clip, m.start_s, m.end_s, m.matched_s,
                           m.clip_offset_s, m.hashes, m.confidence))
        return job_id

    def list_jobs(self, limit: int = 200) -> list:
        with self._db() as c:
            rows = c.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def ids_da_quet(self, chi_thanh_cong: bool = True) -> set:
        """Trả về tập source_id đã quét, truy vấn thẳng trong SQLite."""
        dieu_kien = "source_id IS NOT NULL AND source_id != ''"
        if chi_thanh_cong:
            dieu_kien += " AND status = 'ok'"
        with self._db() as c:
            rows = c.execute(
                f"SELECT DISTINCT source_id FROM jobs WHERE {dieu_kien}"
            ).fetchall()
        return {row["source_id"] for row in rows}

    def job_matches(self, job_id: int) -> list:
        with self._db() as c:
            rows = c.execute("SELECT * FROM matches WHERE job_id=? ORDER BY start_s",
                             (job_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_job(self, job_id: int) -> None:
        with self._db() as c:
            c.execute("DELETE FROM matches WHERE job_id=?", (job_id,))
            c.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    HEADER = ["Thời điểm quét", "Nguồn video dài", "Link / đường dẫn",
              "Clip gốc tìm thấy", "Tên video gốc (YouTube)", "Link video gốc",
              "Vùng", "Clip bắt đầu từ", "Vùng khớp từ", "Đến",
              "🔗 Nhảy tới đúng mốc vi phạm",
              "Đoạn khớp (giây)", "Khớp từ giây thứ (của clip)", "Số hash khớp",
              "Tỷ lệ vân tay khớp (%)", "Đánh giá"]

    # Các cột phải mang KIỂU SỐ. Dòng của nguồn lỗi / không có kết quả điền chuỗi rỗng
    # vào đúng những cột này, nên khi một lượt quét trộn cả hai loại thì cột thành
    # dtype object lẫn số với chuỗi — pandas dựng được nhưng PyArrow (Streamlit dùng
    # để vẽ bảng) từ chối:
    #     ArrowInvalid: Could not convert '' with type str: tried to convert to int64
    # Giao diện phải ép kiểu theo danh sách này trước khi vẽ. Để ở đây (cạnh HEADER)
    # cho mọi nơi hiển thị dùng chung, khỏi phải đoán lại cột nào là số.
    COT_SO = ("Đoạn khớp (giây)", "Khớp từ giây thứ (của clip)",
              "Số hash khớp", "Tỷ lệ vân tay khớp (%)")

    @staticmethod
    def link_moc(source_id: str, source_ref: str, giay: float) -> str:
        """Tạo link YouTube mở thẳng tới đúng giây xảy ra vi phạm."""
        if source_id:
            return f"https://youtu.be/{source_id}?t={int(giay)}"
        if "youtu" in (source_ref or ""):
            noi = "&" if "?" in source_ref else "?"
            return f"{source_ref}{noi}t={int(giay)}"
        return ""

    def to_rows(self, ket: Iterable) -> list:
        """Chuyển danh sách ScanResult thành các dòng phẳng để xuất CSV / hiện bảng."""
        resolver = self.clip_metadata_resolver()
        luc = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for kq in ket:
            dau = [luc, kq.source_name, kq.source_ref]
            if kq.status != "ok":
                rows.append(dau + [f"(LỖI: {kq.note})"] + [""] * 12)
            elif not kq.matches:
                gc = "(không có kết quả nào đạt ngưỡng)" if kq.matches_loai \
                     else "(không tìm thấy clip nào)"
                rows.append(dau + [gc] + [""] * 12)
            else:
                for m in kq.matches:
                    mt = resolver.resolve(m.clip)
                    rows.append(dau + [
                        m.clip, mt.title, mt.url,
                        m.vung, m.start_hhmmss, hhmmss(m.vung_khop_s),
                        m.end_hhmmss,
                        Engine.link_moc(kq.source_id, kq.source_ref, m.start_s),
                        round(m.matched_s), round(m.clip_offset_s),
                        m.hashes, m.ty_le, m.confidence])
        return rows

    def export_csv(self, ket: Iterable, ten_file: Optional[str] = None) -> str:
        os.makedirs(self.out_dir, exist_ok=True)
        ten_file = ten_file or os.path.join(
            self.out_dir, "ketqua_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
        f, ten_file = _mo_file_text_moi(
            ten_file, newline="", encoding="utf-8-sig"
        )
        with f:
            w = csv.writer(f)
            w.writerow(self.HEADER)
            w.writerows([
                [o_bang_tinh_an_toan(o) for o in dong]
                for dong in self.to_rows(ket)
            ])
        return ten_file

    def to_rows_ngang(self, ket: Iterable) -> list:
        """Mỗi ScanResult -> đúng 1 dòng 34 cột. Bỏ qua kết quả status != 'ok'."""
        import bang_ngang

        resolver = self.clip_metadata_resolver()
        return [
            bang_ngang.dung_dong_ngang(kq, resolver=resolver)
            for kq in ket
            if kq.status == "ok" and kq.matches
        ]

    def export_csv_ngang(self, ket: Iterable, ten_file: Optional[str] = None) -> str:
        """Xuất CSV dạng ngang, encoding utf-8-sig. Trả về đường dẫn."""
        import bang_ngang

        rows = self.to_rows_ngang(ket)
        if not rows:
            return ""
        os.makedirs(self.out_dir, exist_ok=True)
        ten_file = ten_file or os.path.join(
            self.out_dir,
            "ketqua_ngang_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv",
        )
        f, ten_file = _mo_file_text_moi(
            ten_file, newline="", encoding="utf-8-sig"
        )
        with f:
            w = csv.writer(f)
            w.writerow(bang_ngang.HEADER_NGANG)
            w.writerows([
                [o_bang_tinh_an_toan(o) for o in dong]
                for dong in rows
            ])
        return ten_file

    def export_ho_so(self, ket: Iterable, ten_file: Optional[str] = None) -> list:
        """Xuất mỗi ScanResult thành một file .md. Trả về danh sách đường dẫn đã tạo."""
        os.makedirs(self.out_dir, exist_ok=True)
        resolver = self.clip_metadata_resolver()
        duong_dan_da_tao = []

        for kq in ket:
            if kq.status != "ok" or not kq.matches:
                continue

            ho_so = dossier.dung_ho_so(kq, resolver=resolver)
            noi_dung = dossier.render_markdown(ho_so)
            if ten_file:
                goc_ten, _ = os.path.splitext(ten_file)
                duong_dan = goc_ten + ".md"
            else:
                ten_nguon = channel.lam_sach_ten(kq.source_name)
                dau_thoi_gian = datetime.now().strftime("%Y%m%d_%H%M%S")
                duong_dan = os.path.join(
                    self.out_dir,
                    f"hoso_{ten_nguon}_{dau_thoi_gian}.md",
                )

            goc_ten, duoi = os.path.splitext(duong_dan)
            so_hau_to = 2
            while os.path.exists(duong_dan):
                duong_dan = f"{goc_ten}_{so_hau_to}{duoi}"
                so_hau_to += 1

            with open(duong_dan, "w", encoding="utf-8") as f:
                f.write(noi_dung)
            duong_dan_da_tao.append(duong_dan)

        return duong_dan_da_tao
