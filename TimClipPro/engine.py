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
import copy
import csv
import glob
import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
import sqlite3
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
import lich_su
from chan_doan_quet import (
    AUDFPRINT_KHONG_RA_MATCH,
    ChanDoanQuet,
    ghi_nhan_bi_loai,
)
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
    extract_youtube_id,
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
from khoa import DangChayRoi, KhoaTienTrinh
from luu_tru import (
    LoiDuLieu,
    cap_nhat_json,
    doc_json_an_toan,
    ghi_json_an_toan,
    ten_file_hop_le,
)
from process_runner import (
    IM_LANG_FFMPEG_S,
    TRAN_FFPROBE_S,
    KetQuaLenh,
    ProcessSnapshot,
    chay_lenh_media,
    run_observed_process,
)
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
    # Phạm vi THỰC SỰ đã so khớp (audit TCP-04/TCP-06). ``None`` = không biết (kết quả
    # dựng theo kiểu cũ) — khi đó không khẳng định gì về độ phủ.
    vung_da_khop: Optional[list] = None   # [(từ, đến)] giây, đã hợp
    vung_loi: list = field(default_factory=list)   # vùng cắt/giải mã/khớp LỖI, chưa phủ
    # "" | "dung_som" (đủ bằng chứng) | "gioi_han_tai" (chỉ tải phần đầu)
    # | "loi_khuc" (có vùng lỗi) | "huy" (người dùng dừng)
    ly_do_pham_vi: str = ""
    # Chính sách chọn lọc (đủ Top-N, clip khác nhau nếu bật) ĐÃ thoả trong phần đã quét.
    # Khác hẳn "đã khảo sát toàn bộ video".
    dat_muc_tieu: bool = False
    # Kho đã dùng cho lượt quét (audit TCP-07): định danh BỀN, tên hiển thị lúc quét,
    # phiên bản hiệu lực của file kho và chữ ký chính sách nhận diện. Lịch sử dựa vào
    # chúng để biết một kết luận cũ còn áp dụng cho kho/chính sách hiện tại hay không.
    kho_id: str = ""
    kho_ten: str = ""
    kho_phien_ban: str = ""
    chinh_sach: str = ""

    @property
    def quet_day_du(self) -> bool:
        """Đã so khớp HẾT video và không có vùng lỗi. Không biết phạm vi → False."""
        if self.vung_da_khop is None or self.vung_loi:
            return False
        if not self.duration_s:
            return bool(self.vung_da_khop)
        return tong_do_dai(self.vung_da_khop) >= self.duration_s - DUNG_SAI_PHU_S

    @property
    def quet_mot_phan(self) -> bool:
        """Có phải chỉ quét một phần video không? Dùng để ghi rõ trên báo cáo."""
        if self.vung_da_khop is not None:
            return not self.quet_day_du
        return bool(self.duration_s and 0 < self.pham_vi_quet_s < self.duration_s - 1)


class Cancelled(Exception):
    """Ném ra khi người dùng bấm Dừng."""


class SoKhoHong(RuntimeError):
    """Sổ đăng ký kho (``khos.json``) vừa hỏng hoặc bị mất: không quét, không tạo kho.

    Lúc đó Engine chỉ còn trỏ tạm về ``data/db.pklz``; dùng nó là đối chiếu (hoặc ghi vân
    tay) nhầm kho mà không ai hay (phản biện vòng 2 + 3).
    """


# Tham số làm THAY ĐỔI kết luận "video này không chứa clip nào trong kho" (audit
# TCP-07): cắt khúc, ngưỡng audfprint, gộp, ngưỡng chấp nhận, bù tốc độ. Đổi một
# trong số này thì âm tính cũ không còn chứng minh được gì nên Watch phải quét lại.
# Tham số chỉ đổi cách CHỌN/HIỂN THỊ kết quả (top_n, phân bố đều...), cách tải hay
# thứ tự quét (quét tăng dần — không thấy gì thì vẫn quét hết) KHÔNG nằm ở đây, để
# một lần chỉnh Top-N không kéo theo việc tải lại hàng nghìn video dài.
TRUONG_CHINH_SACH = (
    "chunk_s", "overlap_s", "overlap_max_s", "overlap_tu_dong", "min_hash",
    "min_match_s", "max_matches", "dedup_s", "shifts_quet", "min_hash_floor",
    "ty_le_chap_nhan", "min_match_chap_nhan", "mat_do_toi_thieu", "mat_do_bac_a",
    "quet_da_toc_do", "toc_do_min_manh", "toc_do_thang_hang", "toc_do_lech_toi_thieu",
    "toc_do_lech_toi_da", "luoi_resample", "luoi_tempo", "toc_do_toi_da_thu",
)


def chu_ky_chinh_sach(cfg) -> str:
    """Chữ ký ngắn của chính sách nhận diện; tiền tố là phiên bản danh sách trường."""
    gia_tri = {k: getattr(cfg, k, None) for k in TRUONG_CHINH_SACH}
    tom = hashlib.sha256(json.dumps(gia_tri, sort_keys=True, ensure_ascii=False,
                                    default=str).encode("utf-8")).hexdigest()[:16]
    return f"v1:{tom}"


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


# =====================================================================
#  Phạm vi quét: tập khoảng thời gian (audit TCP-04/TCP-06)
#
#  "Đã quét tới giây X" (`max(end)`) KHÔNG phải độ phủ: một khúc giữa lỗi để lại lỗ
#  hổng mà `max(end)` vẫn bằng cả video. Phạm vi thật là HỢP các khoảng đã thực sự
#  so khớp; phần lỗi là các khoảng KHÔNG được phủ bởi khúc nào khác.
# =====================================================================

# Sai số cho phép khi so tổng độ phủ với thời lượng video (độ dài WAV đo từ header có
# thể ngắn hơn thời lượng ffprobe vài phần trăm giây).
DUNG_SAI_PHU_S = 2.0
# File tải về ngắn hơn lengthSeconds của YouTube quá mức này thì phải giải thích được
# (tải lại để kiểm). Cố định theo GIÂY, không theo tỉ lệ: dung sai 0,2% cũ cho video 10
# tiếng là 72 giây đuôi không ai quét mà vẫn ghi "quét trọn" (phản biện vòng 2).
DUNG_SAI_TAI_THIEU_S = 5.0
# Hai lần tải độc lập lệch nhau không quá mức này thì coi là CÙNG một độ dài.
DUNG_SAI_TAI_LAI_S = 1.0


def hop_khoang(khoang) -> list:
    """Hợp các khoảng ``[a, b)``: sắp xếp, gộp phần chồng/kề nhau. Bỏ khoảng rỗng."""
    ds = sorted((float(a), float(b)) for a, b in khoang if float(b) > float(a))
    ra: list = []
    for a, b in ds:
        if ra and a <= ra[-1][1]:
            ra[-1] = (ra[-1][0], max(ra[-1][1], b))
        else:
            ra.append((a, b))
    return ra


def tong_do_dai(khoang) -> float:
    """Tổng độ dài của HỢP các khoảng — phần chồng lặp chỉ tính một lần."""
    return sum(b - a for a, b in hop_khoang(khoang))


def tru_khoang(goc, bo) -> list:
    """Phần của ``goc`` KHÔNG nằm trong ``bo``."""
    con = hop_khoang(goc)
    for c, d in hop_khoang(bo):
        moi = []
        for a, b in con:
            if d <= a or c >= b:
                moi.append((a, b))
                continue
            if a < c:
                moi.append((a, c))
            if d < b:
                moi.append((d, b))
        con = moi
    return hop_khoang(con)


def mo_ta_pham_vi(kq) -> str:
    """Một dòng tiếng Việt nói phần nào của video đã thực sự được so khớp."""
    tong = float(getattr(kq, "duration_s", 0.0) or 0.0)
    vung = getattr(kq, "vung_da_khop", None)
    da_khop = tong_do_dai(vung) if vung is not None else float(
        getattr(kq, "pham_vi_quet_s", 0.0) or 0.0)
    phan = f"{hhmmss(da_khop)}/{hhmmss(tong)}" if tong else hhmmss(da_khop)
    ly_do = getattr(kq, "ly_do_pham_vi", "") or ""
    loi = list(getattr(kq, "vung_loi", []) or [])
    if loi:
        vi_du = ", ".join(f"{hhmmss(a)}–{hhmmss(b)}" for a, b in loi[:3])
        them = f" (+{len(loi) - 3} vùng)" if len(loi) > 3 else ""
        return (f"lỗi xử lý {len(loi)} vùng ({vi_du}{them}); "
                f"đã so khớp {phan}")
    if ly_do == "gioi_han_tai":
        return f"chỉ tải và so khớp {phan} — đã đủ bằng chứng nên không tải tiếp"
    if ly_do == "dung_som":
        return f"đã đủ bằng chứng sau khi so khớp {phan}, phần còn lại chưa quét"
    return f"đã so khớp {phan}"


def nhan_pham_vi(kq) -> str:
    """Hậu tố gắn vào TÊN video trên báo cáo khi chưa quét trọn; rỗng nếu đã trọn.

    Không thêm cột: hợp đồng 34 cột (ngang) / 16 cột (dọc) và Apps Script đọc cột theo
    tên. Cột tên video vốn đã mang trạng thái — dòng lỗi ghi "(LỖI: …)" ngay tại đó.
    """
    if getattr(kq, "status", "ok") != "ok" or not getattr(kq, "quet_mot_phan", False):
        return ""
    return f" [QUÉT MỘT PHẦN — {mo_ta_pham_vi(kq)}]"


@dataclass
class _PhamViQuet:
    """Sổ ghi phạm vi của MỘT lượt quét; chỉ tồn tại trong ``_scan_media``."""
    do_dai_khuc: dict = field(default_factory=dict)     # tên khúc -> giây đo thật
    loi_cat: list = field(default_factory=list)         # [(a, b)] cắt/giải mã lỗi
    da_gui: list = field(default_factory=list)          # khúc gốc đã gửi đi so khớp
    khong_phan_tich: set = field(default_factory=set)   # gửi đi mà audfprint không báo
    dung_som: bool = False                              # bỏ qua phần sau vì đủ bằng chứng
    # Luồng ÂM THANH kết thúc trước hình (giây); 0 = như cả file. Phần sau đó không có
    # tiếng nên không có gì để so khớp — không phải vùng lỗi.
    het_am_thanh: float = 0.0
    # Lượt bù tốc độ: cặp (lượt, mốc khúc gốc) biến đổi/khớp lỗi và cặp đã khớp được.
    # Tính THEO TỪNG LƯỢT: hệ số này chạy được không bù cho hệ số kia bị hỏng.
    loi_bu_toc_do: set = field(default_factory=set)
    bu_toc_do_ok: set = field(default_factory=set)


def do_dai_wav(path: str) -> Optional[float]:
    """Độ dài THẬT của một khúc WAV, hoặc ``None`` nếu không đọc được.

    Lấy giá trị nhỏ hơn giữa header và lượng dữ liệu thật trên đĩa: file bị cắt dở
    có thể mang header ghi độ dài dự kiến.
    """
    import wave

    try:
        with wave.open(path, "rb") as w:
            khung, tan_so = w.getnframes(), w.getframerate()
            byte_moi_khung = w.getnchannels() * w.getsampwidth()
        if tan_so <= 0 or byte_moi_khung <= 0:
            return None
        theo_kich_thuoc = max(0, os.path.getsize(path) - 44) / (tan_so * byte_moi_khung)
        return min(khung / tan_so, theo_kich_thuoc)
    except (OSError, EOFError, wave.Error):
        return None


def wav_co_tieng(path: str, nguong_dbfs: Optional[float] = None) -> bool:
    """Khúc WAV PCM 16-bit có tiếng rõ (độ lệch chuẩn — RMS QUANH giá trị trung bình — trên
    ``nguong_dbfs``, mặc định ``NGUONG_CO_TIENG_DBFS``) không? Không đọc được → False.

    Đo quanh trung bình chứ không quanh 0: PCM hằng số khác 0 (lệch DC) không có biến thiên
    nào nên audfprint ra 0 hash — đó là im lặng, không phải tiếng (phản biện vòng 3).
    Đọc theo từng khối để khúc dài không chiếm nhiều RAM.
    """
    import wave

    import numpy as np

    if nguong_dbfs is None:
        nguong_dbfs = NGUONG_CO_TIENG_DBFS
    try:
        with wave.open(path, "rb") as w:
            if w.getsampwidth() != 2:
                return False
            tong, tong_binh_phuong, so_mau = 0.0, 0.0, 0
            while True:
                khoi = w.readframes(1 << 18)
                if not khoi:
                    break
                mau = np.frombuffer(khoi[: len(khoi) - len(khoi) % 2],
                                    dtype="<i2").astype(np.float64)
                tong += float(mau.sum())
                tong_binh_phuong += float(np.square(mau).sum())
                so_mau += mau.size
    except (OSError, EOFError, wave.Error):
        return False
    if not so_mau:
        return False
    trung_binh = tong / so_mau
    phuong_sai = max(0.0, tong_binh_phuong / so_mau - trung_binh * trung_binh)
    do_lech = math.sqrt(phuong_sai) / 32768.0
    return do_lech > 0 and 20 * math.log10(do_lech) > nguong_dbfs


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


def liet_ke_media(thumuc: str, bo_thu_muc_lam_viec: bool = False) -> list:
    """Liệt kê mọi file media trong thư mục (kể cả thư mục con).

    ``bo_thu_muc_lam_viec=True`` (dùng khi TẠO VÂN TAY kho): bỏ qua thư mục làm việc
    của đồng bộ kênh (``_tam``: file tải thô, bản đang nén; ``_hong``: file nghi hỏng đã
    cách ly) — đưa chúng vào vân tay là đưa file dở/hỏng vào kho đối chiếu (audit
    TCP-10). Mặc định KHÔNG bỏ gì: quét thư mục video của người dùng không được lặng lẽ
    bỏ một thư mục chỉ vì nó tên ``_tam``.
    """
    bo_qua = ({channel.THU_MUC_TAM.lower(), channel.THU_MUC_HONG.lower()}
              if bo_thu_muc_lam_viec else set())
    ds = []
    for goc, cac_tm, files in os.walk(thumuc):
        cac_tm[:] = [d for d in cac_tm if d.lower() not in bo_qua]
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
# "NOMATCH <khúc> <độ dài> sec <n> raw hashes". "Độ dài" là mốc HASH CUỐI chứ không phải
# độ dài file, nên MỌI khúc 0 hash đều ghi "0.0 sec" — khúc không đọc được (với
# `--continue-on-error`) lẫn khúc IM LẶNG hoàn toàn. Chỉ số hash không phân biệt được
# hai ca đó (phản biện vòng 2, N1).
RE_NOMATCH_SO_HASH = re.compile(r"\ssec\s+(\d+)\s+raw\s+hashes\s*$")
# "wavfile2peaks: Error reading <đường dẫn>/chunk_<mốc>[_k<hệ số>].wav" — neo vào cụm
# "Error reading" để mỗi lần xuất hiện cho đúng khúc của nó, kể cả khi dòng bị xen.
RE_LOI_DOC_KHUC = re.compile(r"Error reading .*?(chunk_\d+(?:_k\d+)?\.wav)")
# Khúc 0 hash mà tiếng to hơn mức này thì KHÔNG thể đã được phân tích: audfprint chuẩn
# hoá phổ theo đỉnh của chính khúc nên âm thanh thật luôn sinh hash. Đặt thấp hơn hẳn
# tiếng thật nhưng cao hơn nhiễu nền của video bị tắt tiếng (phản biện vòng 3).
NGUONG_CO_TIENG_DBFS = -50.0


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
        """Ghi đè TOÀN BỘ sổ đăng ký. Thao tác sửa vài trường phải dùng ``_sua_khos``."""
        ghi_json_an_toan(self.kho_file, d)

    def _sua_khos(self, ham_sua: Callable[[dict], object]):
        """Giao dịch đọc-sửa-ghi trên ``khos.json`` (audit TCP-03).

        Giao diện, Watch, build và thiết lập máy phụ đều sửa sổ đăng ký, có khi từ các
        process khác nhau. Đọc ở đầu thao tác rồi ghi đè cả file ở cuối sẽ xoá mất
        thay đổi của bên kia; ở đây đọc bản MỚI NHẤT và ghi dưới cùng một khoá.
        Trả về đúng giá trị mà ``ham_sua`` trả về.
        """
        return cap_nhat_json(
            self.kho_file, ham_sua, mac_dinh={"dang_dung": "", "danh_sach": []}
        )

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

    def _dau_vet_so_kho_hong(self) -> str:
        """Lời giải thích nếu sổ đăng ký kho TỪNG có rồi hỏng/mất; rỗng nếu không có dấu vết.

        Dấu vết: bản hỏng ``khos.json.hong.*`` (lớp lưu trữ đổi tên khi không đọc được mà
        không có ``.bak``), hoặc ``khos.json`` biến mất trong khi ``khos.json.bak`` còn —
        lớp lưu trữ chỉ tự phục hồi từ ``.bak`` khi file chính HỎNG, không khi file MẤT.
        """
        if glob.glob(glob.escape(self.kho_file) + ".hong.*"):
            return ("Sổ đăng ký kho (khos.json) từng bị hỏng — bản hỏng được giữ ở "
                    "khos.json.hong.*. Tool KHÔNG tự dựng «Kho mặc định» từ data/db.pklz để "
                    "khỏi đối chiếu nhầm kho, và chưa quét hay tạo kho được. Hãy khôi phục sổ "
                    "từ bản hỏng, hoặc nếu chắc chắn muốn dùng data/db.pklz thì chuyển các "
                    "file khos.json.hong.* ra chỗ khác rồi mở lại.")
        if not os.path.exists(self.kho_file) and os.path.isfile(self.kho_file + ".bak"):
            return ("Sổ đăng ký kho (khos.json) bị mất nhưng còn bản sao khos.json.bak. Tool "
                    "KHÔNG tự dựng «Kho mặc định» từ data/db.pklz (và không ghi đè bản sao), "
                    "chưa quét hay tạo kho được. Khi app đã dừng, chép khos.json.bak thành "
                    "khos.json rồi mở lại; nếu chắc chắn muốn bỏ sổ cũ thì chuyển "
                    "khos.json.bak ra chỗ khác.")
        return ""

    def _giu_ban_sao_so_kho(self) -> str:
        """Sổ chính MẤT mà còn ``.bak``: chép ``.bak`` ra tên cố định
        ``khos.json.bak.giu_<thời điểm>`` (một lần cho mỗi nội dung). Người dùng có thể tạo kho
        mới ngay trong trạng thái này, và lần ghi sổ thứ hai sẽ thay ``.bak`` bằng sổ mới —
        bản sao cuối cùng của sổ thật mất theo (phản biện vòng 3). Trả đường dẫn bản giữ."""
        bak = self.kho_file + ".bak"
        if os.path.exists(self.kho_file) or not os.path.isfile(bak):
            return ""
        try:
            with open(bak, "rb") as f:
                noi_dung = f.read()
            for cu in sorted(glob.glob(glob.escape(bak) + ".giu_*")):
                with open(cu, "rb") as f:
                    if f.read() == noi_dung:
                        return cu
            goc = f"{bak}.giu_{time.strftime('%Y%m%d_%H%M%S')}"
            dich, i = goc, 2
            while os.path.exists(dich):
                dich, i = f"{goc}_{i}", i + 1
            with open(dich, "xb") as f:
                f.write(noi_dung)
            return dich
        except OSError:
            LOGGER_SCAN.exception("event=kho.registry_backup_keep_failed")
            return ""

    def _so_kho_vua_hong(self) -> bool:
        """Sổ đăng ký trống vì vừa hỏng/mất (không phải cài mới chưa từng có kho)?"""
        return not getattr(self, "kho_dang_dung", "") and bool(self._dau_vet_so_kho_hong())

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
        # Nâng cấp: đã có db.pklz kiểu cũ mà chưa khai báo kho nào — nhưng KHÔNG khi sổ
        # từng tồn tại rồi hỏng/mất: "sổ trống" lúc đó là sổ bị MẤT, tự dựng «Kho mặc
        # định» từ db.pklz là lặng lẽ đối chiếu nhầm kho (phản biện vòng 2 + 3).
        dau_vet = self._dau_vet_so_kho_hong() if not d["danh_sach"] else ""
        if dau_vet:
            self.canh_bao_khoi_dong.append(dau_vet)
            giu = self._giu_ban_sao_so_kho()
            if giu:
                self.canh_bao_khoi_dong.append(
                    f"Đã giữ một bản sao cố định của sổ cũ: {os.path.basename(giu)} (không "
                    "bao giờ bị ghi đè).")
        elif not d["danh_sach"] and os.path.exists(os.path.join(self.data_dir, "db.pklz")):
            def nang_cap(moi: dict) -> dict:
                # Process khác có thể vừa tạo kho đầu tiên: chỉ nâng cấp khi vẫn rỗng.
                if not moi.get("danh_sach"):
                    moi["dang_dung"] = "Kho mặc định"
                    moi["danh_sach"] = [
                        # id bền: xoá rồi tự tạo lại không được thừa hưởng lịch sử cũ.
                        {"ten": "Kho mặc định", "thu_muc": "", "db": "db.pklz",
                         "id": uuid.uuid4().hex}
                    ]
                return moi

            d = self._sua_khos(nang_cap)
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
        kho = {"ten": ten, "thu_muc": thu_muc.strip('" '),
               "db": f"kho_{self._slug(ten)}.pklz",
               # Định danh BỀN của kho, khác tên hiển thị: lịch sử quét gắn vào đây.
               # Xoá rồi tạo lại kho cùng tên là một kho KHÁC (id khác).
               "id": uuid.uuid4().hex}

        def them(d: dict) -> dict:
            if any(k["ten"] == ten for k in d["danh_sach"]):
                raise RuntimeError(f"Đã có kho tên «{ten}» rồi.")
            d["danh_sach"].append(kho)
            d["dang_dung"] = ten
            return d

        d = self._sua_khos(them)
        self._ap_dung_kho(ten, d)
        return kho

    def use_kho(self, ten: str) -> None:
        def chon(d: dict) -> dict:
            kho = next((k for k in d["danh_sach"] if k["ten"] == ten), None)
            if kho is None:
                raise RuntimeError(f"Không có kho tên «{ten}».")
            # Kiểm TRƯỚC khi ghi sổ: ghi `dang_dung` cho một kho trỏ tới file vân tay
            # không hợp lệ làm mọi lần mở sau lặng lẽ lùi về kho mặc định (phản biện).
            try:
                self._duong_dan_db_kho(kho.get("db"))
            except LoiDuLieu as e:
                raise RuntimeError(
                    f"Kho «{ten}» trỏ tới file vân tay không hợp lệ: {e}") from e
            d["dang_dung"] = ten
            return d

        d = self._sua_khos(chon)
        self._ap_dung_kho(ten, d)

    def update_kho(self, ten: str, thu_muc: str) -> None:
        def sua(d: dict) -> dict:
            for k in d["danh_sach"]:
                if k["ten"] == ten:
                    k["thu_muc"] = thu_muc.strip('" ')
            return d

        d = self._sua_khos(sua)
        self._ap_dung_kho(d.get("dang_dung", ""), d)

    def delete_kho(self, ten: str, xoa_van_tay: bool = True) -> None:
        """Xoá kho khỏi danh sách. KHÔNG bao giờ đụng vào file video/audio gốc.

        Lấy ``data/tool.lock``: xoá file vân tay là thao tác nặng trên kho, không được
        chạy khi build/Watch/sửa metadata đang dùng kho (audit TCP-01). Bận thì ném
        ``DangChayRoi`` để giao diện báo rõ, không xoá gì.
        """
        with KhoaTienTrinh(os.path.join(self.data_dir, "tool.lock"), f"xoá kho «{ten}»"):
            d = self._doc_khos()
            kho = next((k for k in d["danh_sach"] if k["ten"] == ten), None)
            if not kho:
                return
            if xoa_van_tay:
                self._cache_khoa = None
                self._xoa_an_toan(self._duong_dan_db_kho(kho["db"]))

            def bo(d: dict) -> dict:
                d["danh_sach"] = [k for k in d["danh_sach"] if k["ten"] != ten]
                if d.get("dang_dung") == ten:
                    d["dang_dung"] = d["danh_sach"][0]["ten"] if d["danh_sach"] else ""
                return d

            d = self._sua_khos(bo)
            self._ap_dung_kho(d.get("dang_dung", ""), d)

    # =================================================================
    #  NGỮ CẢNH JOB — ghim kho và cấu hình suốt một job (audit TCP-01)
    #
    #  Giao diện chạy build/quét trong thread nền trên CHÍNH Engine mà thanh bên vẫn
    #  sửa trực tiếp: đổi kho gọi `use_kho`, ô tham số gán thẳng vào `self.config`.
    #  Job đọc `self.db_file`/`self.config` ở nhiều thời điểm nên có thể bắt đầu với
    #  kho A rồi ghi kết quả của A đè lên kho B. Mỗi job vì thế chạy trên một BẢN SAO
    #  đã ghim: tên kho, file kho, thư mục kho và một bản sâu của Config được chụp lúc
    #  bắt đầu. Bản sao dùng chung cờ huỷ (bấm Dừng vẫn tới được job) và bộ nhớ client.
    # =================================================================

    def _ban_sao_cho_job(self) -> "Engine":
        """Bản sao Engine ghim cho đúng một job; đã là bản ghim thì trả lại chính nó."""
        if getattr(self, "_la_ban_ghim", False):
            return self
        job = copy.copy(self)
        job.config = copy.deepcopy(self.config)
        job.canh_bao_gop = []
        job.canh_bao_mang = []
        job.chan_doan_quet = ChanDoanQuet()
        job._la_ban_ghim = True
        job._chu_ky_kho_ghim = job._chu_ky_db()
        return job

    def _chu_ky_db(self) -> tuple:
        """Chữ ký file kho đang ghim: đường dẫn, kích thước, mtime."""
        try:
            st_ = os.stat(self.db_file)
            return (os.path.normcase(os.path.abspath(self.db_file)),
                    st_.st_size, st_.st_mtime_ns)
        except OSError:
            return (os.path.normcase(os.path.abspath(self.db_file)), None, None)

    def _kiem_kho_khong_doi(self) -> None:
        """Một lượt quét không được trộn hai phiên bản kho.

        Quét gọi audfprint nhiều lần (từng đoạn, Top-1 hai pha, bù tốc độ). Nếu kho
        được ghi lại giữa hai lần gọi thì nửa lượt dùng kho cũ, nửa dùng kho mới.
        Phát hiện là dừng rõ ràng — không âm thầm trộn.
        """
        ghim = getattr(self, "_chu_ky_kho_ghim", None)
        if ghim is not None and self._chu_ky_db() != ghim:
            raise RuntimeError(
                f"Kho vân tay «{self.kho_dang_dung or os.path.basename(self.db_file)}» "
                "vừa được ghi lại trong lúc quét. Kết quả lượt này không được trộn giữa "
                "hai phiên bản kho — hãy quét lại video này."
            )

    def _nhan_ket_qua_job(self, job: "Engine") -> None:
        """Giữ hợp đồng cũ: sau job, trường kết quả vẫn đọc được trên Engine gốc."""
        if job is self:
            return
        self.chan_doan_quet = job.chan_doan_quet
        self.canh_bao_gop = job.canh_bao_gop
        self.canh_bao_mang = job.canh_bao_mang

    def _danh_tinh_kho(self) -> dict:
        """Kho của lượt quét: định danh bền, tên, phiên bản hiệu lực (audit TCP-07).

        Phiên bản hiệu lực = ``revision`` trong sổ đăng ký (đổi ĐÚNG lúc công bố kho
        mới, xem ``_ghi_phien_ban_sau_cong_bo``) + kích thước file kho. Kích thước là
        lưới an toàn cho kho cũ chưa có ``revision`` hoặc lần cập nhật sổ bị lỗi; nó
        không đổi khi chép kho sang máy phụ, khác ``mtime``. Không băm file kho —
        kho thật hàng trăm MB.

        Không đọc được sổ đăng ký, hay sổ đang trỏ sang file khác file đã ghim, thì
        định danh là RỖNG: kết quả vẫn được lưu nhưng không bao giờ chặn lượt quét sau.
        """
        ten = self.kho_dang_dung
        ky = getattr(self, "_chu_ky_kho_ghim", None) or self._chu_ky_db()
        kich_thuoc = "?" if ky[1] is None else str(ky[1])
        if not ten:
            # Không có sổ đăng ký: file kho mặc định chính là danh tính.
            return {"kho_id": "db:" + os.path.basename(self.db_file).lower(),
                    "kho_ten": "", "kho_phien_ban": f"-:{kich_thuoc}"}
        try:
            muc = next((k for k in self._doc_khos()["danh_sach"] if k.get("ten") == ten),
                       None)
            cung_file = muc is not None and os.path.normcase(
                self._duong_dan_db_kho(muc["db"])) == os.path.normcase(
                os.path.abspath(self.db_file))
        except Exception:  # noqa: BLE001 — sổ hỏng: danh tính không rõ, không chặn gì
            muc, cung_file = None, False
        if muc is None or not cung_file:
            return {"kho_id": "", "kho_ten": ten, "kho_phien_ban": ""}
        return {"kho_id": self._kho_id_cua(muc), "kho_ten": ten,
                "kho_phien_ban": f"{muc.get('revision') or '-'}:{kich_thuoc}"}

    def _gan_danh_tinh(self, kq: "ScanResult") -> None:
        """Gắn kho + chính sách đang ghim vào kết quả (đầu lượt quét)."""
        dt = self._danh_tinh_kho()
        kq.kho_id = dt["kho_id"]
        kq.kho_ten = dt["kho_ten"]
        kq.kho_phien_ban = dt["kho_phien_ban"]
        kq.chinh_sach = chu_ky_chinh_sach(self.config)

    # ---------- hạ tầng ----------

    def _tim_audfprint(self) -> Optional[str]:
        for ten in ("audfprint-master", "audfprint"):
            p = os.path.join(self.root, ten, "audfprint.py")
            if os.path.isfile(p):
                return p
        return None

    def _init_sqlite(self) -> None:
        """Tạo hoặc nâng cấp ``lichsu.db`` (lược đồ có phiên bản — xem ``lich_su.py``).

        Nâng cấp chỉ THÊM cột, sao lưu trước bằng SQLite backup API và chạy một lần;
        các lần mở sau chỉ đọc ``PRAGMA user_version``.
        """
        kq = lich_su.dam_bao_luoc_do(self.sqlite_file)
        if kq["da_nang_cap"]:
            LOGGER_SCAN.info(
                "event=history.schema_upgraded from=%s to=%s backup=%r",
                kq["phien_ban_cu"], kq["phien_ban"], kq["sao_luu"],
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
        if self._so_kho_vua_hong():
            raise SoKhoHong(
                "Sổ đăng ký kho (data\\khos.json) đã hỏng hoặc bị mất — tool không quét và "
                "không tạo kho bằng data\\db.pklz để khỏi đối chiếu nhầm kho. Khôi phục "
                "khos.json (từ bản hỏng khos.json.hong.* hoặc khos.json.bak) khi app đã dừng "
                "rồi mở lại; xem cảnh báo lúc khởi động.")
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
        # FFprobe chỉ đọc header: có TRẦN TỔNG riêng. Treo (ổ mạng, file khoá) thì trả
        # None như "không đọc được thời lượng", không giữ job vô hạn (audit TCP-15).
        r = chay_lenh_media(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            tran_tong_s=TRAN_FFPROBE_S,
        )
        if r.timed_out:
            LOGGER_SCAN.warning("event=ffprobe.timeout path=%s budget_s=%.0f",
                                os.path.basename(path), TRAN_FFPROBE_S)
            return None
        try:
            return float(r.stdout.strip().splitlines()[-1])
        except Exception:
            return None

    @staticmethod
    def do_dai_am_thanh(path: str) -> Optional[float]:
        """Mốc kết thúc của luồng âm thanh (giây) hoặc ``None`` khi không biết chắc.

        ``duration_of`` là độ dài cả file = luồng dài nhất. mp4 có hình dài hơn tiếng thì
        phần đuôi không có âm thanh; lập khúc theo độ dài cả file sẽ báo nhầm phần đó là
        "cắt lỗi" ở MỌI lần quét (phản biện TCP-04).

        mkv/webm để độ dài luồng ở thẻ ``DURATION`` (vòng 2). File có NHIỀU luồng tiếng
        → ``None``: luồng đầu hết sớm không có nghĩa là phần sau không còn tiếng; luồng
        bắt đầu trễ thì mốc kết thúc là ``start_time`` + độ dài (vòng 3). Cùng bộ đọc với
        đồng bộ kênh (``channel.doc_moc_het_tieng``).
        """
        try:
            r = chay_lenh_media([*channel.LENH_FFPROBE_LUONG_TIENG, path],
                                tran_tong_s=TRAN_FFPROBE_S)
            if r.timed_out or r.returncode != 0:
                return None
        except Exception:  # noqa: BLE001
            return None
        return channel.doc_moc_het_tieng(r.stdout)

    def _trong_thu_muc_dem(self, path: str) -> bool:
        """File nằm trong thư mục đệm tải về của tool (được phép bỏ)?"""
        try:
            dem = os.path.abspath(self.dl_dir)
            return os.path.commonpath([dem, os.path.abspath(path)]) == dem
        except ValueError:
            return False

    def _khoang_cua_khuc(self, pv, moc: int, tong: float) -> tuple:
        ten = f"chunk_{int(moc):07d}.wav"
        dai = pv.do_dai_khuc.get(ten, min(float(self.config.chunk_s), tong - moc))
        return (float(moc), min(float(moc) + dai, tong))

    @staticmethod
    def _luot_bu(he_so: float, ho: str) -> str:
        """Khoá của MỘT lượt bù tốc độ — cũng là hậu tố file danh sách/kết quả của nó."""
        return f"k{ma_he_so(he_so)}_{ho}"

    def _vung_hong_bu_toc_do(self, pv, tong: float) -> list:
        """Vùng mà ít nhất một lượt bù tốc độ KHÔNG kiểm được.

        Theo từng lượt: vùng các khúc hỏng trừ đi vùng các khúc chạy được của CHÍNH lượt
        đó — khúc gối nhau phủ lẫn nhau, nên đuôi ngắn hỏng mà khúc trước đã phủ trọn thì
        lượt đó vẫn kiểm đủ (phản biện vòng 2, N2).
        """
        vung: list = []
        for luot in {luot for luot, _ in pv.loi_bu_toc_do}:
            hong = [self._khoang_cua_khuc(pv, moc, tong)
                    for l2, moc in pv.loi_bu_toc_do if l2 == luot]
            chay_duoc = [self._khoang_cua_khuc(pv, moc, tong)
                         for l2, moc in pv.bu_toc_do_ok if l2 == luot]
            vung += tru_khoang(hong, hop_khoang(chay_duoc))
        return hop_khoang(vung)

    def _chay_ffmpeg(self, lenh: list) -> KetQuaLenh:
        """Một lệnh FFmpeg dài (cắt/đổi tốc độ): huỷ được, dừng khi IM LẶNG quá lâu.

        Không đặt hạn chót tổng: cắt một khúc 1 giờ từ file 90 tiếng có thể chậm mà
        vẫn khoẻ — chỉ dừng khi FFmpeg không còn báo tiến độ (audit TCP-15).
        """
        r = chay_lenh_media(
            lenh,
            cancel_event=self.cancel_event,
            theo_doi_tien_do=True,
            im_lang_toi_da_s=IM_LANG_FFMPEG_S,
        )
        if r.cancelled:
            raise Cancelled()
        if r.timed_out:
            LOGGER_SCAN.warning(
                "event=ffmpeg.stalled reason=%s output=%s budget_s=%.0f",
                r.ly_do, os.path.basename(str(lenh[-1])), IM_LANG_FFMPEG_S,
            )
        return r

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

        try:
            ds = self._doc_danh_sach_clip(self.db_file)
        except Exception:
            ds = []
        self._cache_khoa, self._cache_clips = khoa, ds
        return ds

    def _doc_danh_sach_clip(self, path: str) -> list:
        """Danh sách clip của MỘT file kho bất kỳ; ném ``RuntimeError`` nếu không đọc được.

        Cùng loader an toàn với ``db_clips``: đọc trọn vào RAM trong khối ``with`` rồi
        mới unpickle — không bao giờ giữ handle (chốt chặn WinError 32), không dùng
        ``hash_table.HashTable(path)``. File kho chỉ nạp từ ``data_dir`` của chính tool
        (do tool tạo) — pickle không được dùng cho dữ liệu ngoài.
        Dùng để KIỂM kho tạm trước khi công bố (audit TCP-02).
        """
        import gzip
        import pickle

        thu_muc_af = (os.path.dirname(self.audfprint) if self.audfprint
                      else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "audfprint-master"))
        if thu_muc_af not in sys.path:
            sys.path.insert(0, thu_muc_af)
        try:
            with gzip.open(path, "rb") as f:
                raw = f.read()
            with contextlib.redirect_stdout(io.StringIO()):
                ht = pickle.loads(raw, encoding="latin1")
            del raw
        except Exception as e:  # noqa: BLE001 - mọi kiểu hỏng đều là "không đọc được"
            raise RuntimeError(
                f"Không đọc được file vân tay {os.path.basename(path)}: "
                f"{type(e).__name__}"
            ) from e
        ten_ds = getattr(ht, "names", None)
        hpid = getattr(ht, "hashesperid", None)
        if ten_ds is None or hpid is None:
            raise RuntimeError(
                f"Không đọc được file vân tay {os.path.basename(path)}: "
                "không phải kho audfprint."
            )
        ds = []
        for i, ten in enumerate(ten_ds or []):
            if not ten:
                continue
            so_hash = hpid[i] if i < len(hpid) else 0
            ds.append({"ten": os.path.basename(ten), "duong_dan": ten,
                       "so_hash": int(so_hash)})
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
        """Nguồn chỉ thuộc kho active, theo thứ tự xác định; không dùng set last-wins.

        Số ưu tiên NHỎ thắng. ``clips_meta.json`` của thư mục kho là NGUỒN CHUẨN: đồng
        bộ kênh và các công cụ sửa ngày đăng/thời lượng đều ghi vào đó. Snapshot chỉ
        bù trường nguồn chuẩn còn thiếu và thay thế khi thư mục kho không truy cập
        được (ổ mạng/USB). Trước đây snapshot đứng trước nên một lần sửa đã ghi thành
        công không bao giờ tới báo cáo — kể cả khi làm mới snapshot, vì lượt làm mới
        cũng đọc qua resolver ưu tiên snapshot cũ (audit TCP-09). Không dựa vào mtime.
        """
        candidates: list[tuple[str, str, int]] = []
        seen: set[str] = set()

        def add(path: str, kind: str, priority: int) -> None:
            absolute = os.path.abspath(path)
            key = os.path.normcase(absolute)
            if key not in seen:
                seen.add(key)
                candidates.append((absolute, kind, priority))

        if self.kho_thu_muc:
            add(os.path.join(self.kho_thu_muc, "clips_meta.json"), "live", 0)
        if self.kho_dang_dung:
            add(self._metadata_snapshot_path(), "snapshot", 10)

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
        xung_dot = set(resolver.conflicts)
        lech = {c.split(":", 2)[-1] for c in xung_dot if c.startswith("snapshot_lech:")}
        if lech:
            warnings.append(
                f"Snapshot metadata lệch với clips_meta.json ở {len(lech)} clip — báo "
                "cáo dùng clips_meta.json (nguồn chuẩn). Chạy «Khôi phục metadata "
                "offline» để làm mới snapshot."
            )
        con_lai = {c for c in xung_dot if not c.startswith("snapshot_lech:")}
        if con_lai:
            warnings.append(
                f"Phát hiện {len(con_lai)} xung đột metadata; "
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
        # Ghim kho + cấu hình NGAY lúc người dùng bấm: đổi kho/tham số trên thanh bên
        # sau đó không được chạm tới job này (audit TCP-01).
        job = self._ban_sao_cho_job()
        try:
            with KhoaTienTrinh(
                os.path.join(self.data_dir, "tool.lock"),
                "dựng kho vân tay",
            ):
                return job._build_database_da_khoa(
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
        except DangChayRoi as exc:
            # "Bận" là tình huống vận hành bình thường, không phải lỗi lập trình: một dòng
            # nhật ký, không traceback (phản biện vòng 3).
            if tracker.state.status != "failed":
                tracker.failed(f"Không thể hoàn tất tạo vân tay: {exc}", "DangChayRoi")
            raise
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
            self._lam_moi_sau_build(job)

    def _lam_moi_sau_build(self, job: "Engine") -> None:
        """Engine gốc (giao diện) nhìn thấy kết quả build mà không bị đổi kho.

        Chỉ làm mới khi Engine gốc vẫn đang chọn đúng kho của job: file kho có thể đã
        đổi tên (đường lui khi file cũ bị khoá). Đang chọn kho khác thì để nguyên.
        """
        if job is self:
            return
        self._cache_khoa = None
        self._invalidate_metadata_cache()
        if self.kho_dang_dung and self.kho_dang_dung == job.kho_dang_dung:
            with contextlib.suppress(Exception):
                d = self._doc_khos()
                if any(k.get("ten") == self.kho_dang_dung for k in d["danh_sach"]):
                    self._ap_dung_kho(self.kho_dang_dung, d)

    # ---------- công bố kho vân tay (audit TCP-01/TCP-02) ----------

    @staticmethod
    def _khoa_duong_dan(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _clip_huu_ich(self, path: str) -> set:
        """Tập đường dẫn (đã chuẩn hoá) của clip CÓ hash trong một file kho."""
        return {
            self._khoa_duong_dan(c["duong_dan"])
            for c in self._doc_danh_sach_clip(path)
            if int(c.get("so_hash") or 0) > 0
        }

    def _ghi_thu_muc_kho_ghim(self, thumuc: str) -> None:
        """Ghi thư mục nguồn cho ĐÚNG kho đã ghim — không đổi kho đang chọn của ai."""
        if not self.kho_dang_dung:
            return
        ten = self.kho_dang_dung
        moi = thumuc.strip('" ')

        def sua(d: dict) -> None:
            for k in d["danh_sach"]:
                if k["ten"] == ten:
                    k["thu_muc"] = moi

        self._sua_khos(sua)
        if os.path.normcase(moi) != os.path.normcase(self.kho_thu_muc or ""):
            self.kho_thu_muc = moi
            self._invalidate_metadata_cache()

    def _kiem_dich_cong_bo(self) -> None:
        """Ngay trước khi thay file: sổ đăng ký vẫn trỏ kho đã ghim tới đúng file đích."""
        if not self.kho_dang_dung:
            return
        d = self._doc_khos()
        kho = next((k for k in d["danh_sach"] if k["ten"] == self.kho_dang_dung), None)
        if kho is None:
            raise RuntimeError(
                f"Kho «{self.kho_dang_dung}» không còn trong danh sách kho; "
                "không ghi kết quả tạo vân tay để tránh ghi nhầm kho."
            )
        try:
            dich = self._duong_dan_db_kho(kho["db"])
        except LoiDuLieu as e:
            raise RuntimeError(
                f"Kho «{self.kho_dang_dung}» có file vân tay không hợp lệ trong sổ đăng ký; "
                "không ghi kết quả."
            ) from e
        if self._khoa_duong_dan(dich) != self._khoa_duong_dan(self.db_file):
            raise RuntimeError(
                f"Kho «{self.kho_dang_dung}» đã đổi file vân tay trong lúc tạo vân tay "
                f"({os.path.basename(self.db_file)} → {kho['db']}); không ghi kết quả "
                "để tránh ghi nhầm kho. Hãy chạy lại."
            )

    def _kiem_kho_tam(self, db_tam: str, sub: str, cu_huu_ich: set,
                      can_xu_ly: list, *, lam_moi: frozenset = frozenset(),
                      da_go: frozenset = frozenset()) -> tuple:
        """Kho tạm có được phép thay kho đang dùng không? Trả ``(cong_bo, canh_bao)``.

        Tiến trình audfprint thoát mã 0 và file tạm tồn tại KHÔNG chứng minh kho dùng
        được: clip 0 hash vẫn được ghi tên vào bảng (audit TCP-02). Quy tắc:

        * kho tạm phải đọc được bằng loader của dự án;
        * ``new`` mà không clip nào có hash → thất bại, kho cũ nguyên vẹn;
        * ``new`` thay một kho đang có: clip TỪNG có hash mà lần này lỗi → từ chối, không
          âm thầm làm hẹp vùng phủ; clip mới/hỏng sẵn chỉ bị cảnh báo;
        * ``add``: phải còn đủ mọi clip hữu ích của kho cũ (kể cả clip vừa được LÀM MỚI —
          làm mới thất bại là mất clip, bị từ chối), trừ đúng các clip ``da_go`` (bản đã bị
          cách ly) — và các clip đó phải thật sự đã ra khỏi kho; không có clip mới hữu
          ích, không làm mới, không gỡ gì thì không ghi (kho hiện tại giữ nguyên byte).
        """
        tam_huu_ich = self._clip_huu_ich(db_tam)
        da_xu_ly = {self._khoa_duong_dan(p) for p in can_xu_ly}
        ten_ngan = {self._khoa_duong_dan(p): os.path.basename(p) for p in can_xu_ly}

        def vi_du(tap: set) -> str:
            ten = sorted(ten_ngan.get(p, os.path.basename(p)) for p in tap)
            return ", ".join(ten[:10]) + (f" … (+{len(ten) - 10})" if len(ten) > 10 else "")

        canh_bao = []
        if sub == "new":
            if not tam_huu_ich:
                raise RuntimeError(
                    f"Kho mới không có clip nào có vân tay dùng được ({len(can_xu_ly)} "
                    "clip đều lỗi hoặc 0 hash). Giữ nguyên kho cũ."
                )
            mat = cu_huu_ich - tam_huu_ich
            mat_do_loi = mat & da_xu_ly
            if mat_do_loi:
                raise RuntimeError(
                    f"{len(mat_do_loi)} clip từng có vân tay trong kho hiện tại nhưng lần "
                    f"tạo lại này thất bại: {vi_du(mat_do_loi)}. Giữ nguyên kho cũ — kiểm "
                    "tra file nguồn rồi chạy lại, hoặc dùng «Bổ sung» để thêm clip mới mà "
                    "không tạo lại toàn bộ."
                )
            if mat - da_xu_ly:
                canh_bao.append(
                    f"{len(mat - da_xu_ly)} clip của kho cũ không còn trong thư mục nguồn "
                    "nên không có trong kho mới."
                )
            loi_moi = da_xu_ly - tam_huu_ich
            if loi_moi:
                canh_bao.append(
                    f"{len(loi_moi)} clip không tạo được vân tay và không có trong kho: "
                    f"{vi_du(loi_moi)}."
                )
            return True, canh_bao

        chua_go = set(da_go) & tam_huu_ich
        if chua_go:
            raise RuntimeError(
                f"Không gỡ được vân tay của {len(chua_go)} clip đã bị cách ly: "
                f"{vi_du(chua_go)}. Kho hiện tại giữ nguyên."
            )
        thieu = (cu_huu_ich - set(da_go)) - tam_huu_ich
        lam_moi_hong = thieu & set(lam_moi)
        if lam_moi_hong:
            raise RuntimeError(
                f"{len(lam_moi_hong)} clip có file đã thay sau lần tạo kho gần nhất nhưng "
                f"file mới không tạo được vân tay: {vi_du(lam_moi_hong)}. Kho hiện tại giữ "
                "nguyên (vẫn dùng vân tay cũ) — kiểm tra lại các file đó."
            )
        if thieu:
            raise RuntimeError(
                f"Kho tạm thiếu {len(thieu)} clip có vân tay của kho hiện tại; từ chối ghi "
                "để không làm mất vân tay. Kho hiện tại giữ nguyên."
            )
        moi = tam_huu_ich - cu_huu_ich
        loi_moi = da_xu_ly - tam_huu_ich
        if loi_moi:
            canh_bao.append(
                f"{len(loi_moi)} clip không tạo được vân tay: {vi_du(loi_moi)}."
            )
        if not moi and not (set(lam_moi) & tam_huu_ich) and not da_go:
            canh_bao.append(
                "Không có clip mới nào tạo được vân tay; không ghi lại kho — kho hiện tại "
                "giữ nguyên."
            )
            return False, canh_bao
        return True, canh_bao

    # Sai số mtime khi so file clip với file kho: FAT/exFAT chỉ lưu tới 2 giây.
    DUNG_SAI_MTIME_S = 2.0

    def _clip_doi_file_sau_cong_bo(self, files: list, da_co: set) -> set:
        """Khoá các clip có vân tay mà file được sửa SAU khi lần build gần nhất BẮT ĐẦU.

        So với lúc BẮT ĐẦU (``moc_build`` trong sổ đăng ký) chứ không chỉ lúc công bố: file
        bị thay trong lúc build đang chạy có thể đã được đọc ở bản cũ, mà mtime của nó lại
        nhỏ hơn mtime file kho — so với lúc công bố thì không bao giờ được làm mới (phản
        biện vòng 2). Kho cũ chưa có mốc thì lùi về mtime file kho như trước.
        """
        try:
            moc_kho = os.path.getmtime(self.db_file)
        except OSError:
            return set()
        moc_build = self._moc_build_kho_ghim()
        if moc_build:
            moc_kho = min(moc_kho, moc_build)
        doi = set()
        for path in files:
            khoa = self._khoa_duong_dan(path)
            if khoa in da_co:
                with contextlib.suppress(OSError):
                    if os.path.getmtime(path) > moc_kho + self.DUNG_SAI_MTIME_S:
                        doi.add(khoa)
        return doi

    @staticmethod
    def _ma_video_khoa(khoa: str) -> str:
        """Mã video trong tên file của một clip (khoá đã chuẩn hoá); rỗng nếu không có.

        Đọc hậu tố ``[ID]`` (chấp nhận đuôi bản sao Windows) chứ không đòi đủ ngữ pháp
        ``<ngày> - <tiêu đề> [ID]`` — kho cũ/chép tay có tên không có ngày.
        """
        return str(extract_youtube_id(os.path.basename(khoa)) or "").lower()

    def _go_hong_co_ban_thay(self, ung_vien: set, db_tam: str) -> set:
        """Clip đã bị cách ly có BẢN THAY THẾ cùng mã video mang vân tay trong kho tạm."""
        con_lai = self._clip_huu_ich(db_tam) - set(ung_vien)
        ma_co_van_tay = {self._ma_video_khoa(k) for k in con_lai} - {""}
        return {k for k in ung_vien if self._ma_video_khoa(k) in ma_co_van_tay}

    @staticmethod
    def _canh_bao_giu_hong(tap: set, ke_ten: Callable) -> str:
        return (f"Giữ vân tay {len(tap)} clip đã bị cách ly vào {channel.THU_MUC_HONG}/ vì "
                "chưa có bản thay thế cùng mã video có vân tay — chạy lại «Bổ sung» sau khi "
                f"bản thay thế tạo được vân tay: {ke_ten(tap)}.")

    def _go_van_tay_cu(self, db_tam: str, lam_moi: set, ds_cu: list, workspace: str,
                       tracker) -> None:
        """Gỡ vân tay CŨ của clip sắp làm mới hoặc đã bị cách ly khỏi KHO TẠM
        (``audfprint remove``).

        Chỉ đụng kho tạm; lỗi thì dừng job, kho đang dùng giữ nguyên.
        """
        ten_luu = [c["duong_dan"] for c in ds_cu
                   if self._khoa_duong_dan(c["duong_dan"]) in lam_moi]
        if not ten_luu:
            return
        ds_go = os.path.join(workspace, "go_van_tay_cu.txt")
        with open(ds_go, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(ten_luu))
        tracker.phase("validating",
                      f"Đang gỡ vân tay cũ của {len(ten_luu)} clip đã đổi file hoặc đã "
                      "bị cách ly...")
        rc, duoi = self._run_stream(
            self._audfprint_cmd("remove", "--list", ds_go, db_file=db_tam),
            None,
            logger=tracker.logger,
            process_name="audfprint-remove",
        )
        if rc != 0:
            chi_tiet = "\n".join(duoi[-8:]) or "(không có thông báo nào)"
            raise RuntimeError(
                f"Không gỡ được vân tay cũ của {len(ten_luu)} clip đã đổi file hoặc đã bị "
                f"cách ly; kho hiện tại giữ nguyên.\n{chi_tiet}"
            )

    def _ghi_phien_ban_sau_cong_bo(self, *, shifts_kho: int,
                                   cap_nhat_shifts: bool,
                                   moc_build: Optional[float] = None) -> list:
        """Sau khi thay file kho: phiên bản mới (+ id bền, shifts, mốc bắt đầu build) trong
        sổ đăng ký.

        Lỗi ở đây KHÔNG làm job thất bại — kho đã ghi xong; chỉ cảnh báo. Lịch sử quét
        vẫn thấy kho đã đổi nhờ kích thước file là một phần của phiên bản hiệu lực.
        """
        if not self.kho_dang_dung:
            return []
        ten = self.kho_dang_dung

        def sua(d: dict) -> None:
            for k in d["danh_sach"]:
                if k["ten"] == ten:
                    k.setdefault("id", self._kho_id_cua(k))
                    k["revision"] = uuid.uuid4().hex
                    if cap_nhat_shifts:
                        k["shifts"] = shifts_kho
                    if moc_build:
                        k["moc_build"] = round(float(moc_build), 3)
                    break

        try:
            self._sua_khos(sua)
        except Exception as e:  # noqa: BLE001
            LOGGER_SCAN.exception("event=kho.revision_update_failed warehouse=%r", ten)
            return [f"Kho vân tay đã ghi xong nhưng chưa cập nhật được sổ đăng ký kho: {e}"]
        return []

    def _moc_build_kho_ghim(self) -> float:
        """``moc_build`` của kho đang ghim trong sổ đăng ký; 0 nếu chưa có/không đọc được."""
        if not self.kho_dang_dung:
            return 0.0
        try:
            kho = next((k for k in self._doc_khos()["danh_sach"]
                        if k.get("ten") == self.kho_dang_dung), None)
            gia_tri = float((kho or {}).get("moc_build") or 0)
        except (LoiDuLieu, TypeError, ValueError, KeyError):
            return 0.0
        return gia_tri if math.isfinite(gia_tri) and gia_tri > 0 else 0.0

    def _kho_id_cua(self, entry: dict) -> str:
        """Định danh bền của một kho. Kho cũ chưa có ``id`` dùng định danh suy ra từ tên
        (ổn định, không cần ghi lại sổ đăng ký)."""
        return str(entry.get("id") or f"ten:{self._slug(str(entry.get('ten') or ''))}")

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
        # Mốc BẮT ĐẦU đọc file của lượt build này — file sửa sau mốc này có thể đã được đọc
        # ở bản cũ, nên lần bổ sung sau phải làm mới (phản biện vòng 2).
        bat_dau_build = time.time()
        files = liet_ke_media(thumuc, bo_thu_muc_lam_viec=True)
        tracker.set_files(files)
        if not files:
            raise RuntimeError(f"Thư mục không có file media nào: {thumuc}")

        # KHÔNG gọi update_kho: hàm đó áp lại kho "đang chọn" của sổ đăng ký lên Engine,
        # tức có thể đổi job sang kho khác giữa chừng. Chỉ ghi đúng entry đã ghim.
        self._ghi_thu_muc_kho_ghim(thumuc)

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
        # Clip HỮU ÍCH (có hash) của kho hiện tại: để bỏ qua khi bổ sung, và để kiểm
        # kho tạm không làm mất clip đang tốt trước khi thay (audit TCP-02).
        ds_cu: list = []
        if db_da_ton_tai:
            try:
                ds_cu = self._doc_danh_sach_clip(self.db_file)
            except RuntimeError as e:
                if mode != "new":
                    raise RuntimeError(
                        f"{e}. Không bổ sung vào một kho không đọc được — hãy «Tạo mới» "
                        "kho này."
                    ) from e
                canh_bao.append(f"{e}. Kho sẽ được tạo lại từ đầu.")
        cu_huu_ich = {self._khoa_duong_dan(c["duong_dan"]) for c in ds_cu
                      if int(c.get("so_hash") or 0) > 0}
        da_co = cu_huu_ich if mode != "new" else set()
        # Clip ĐÃ có vân tay nhưng FILE bị thay sau lần công bố kho gần nhất (ví dụ đồng
        # bộ kênh vừa tải lại bản tốt cho một file nén dở — audit TCP-10): bỏ qua theo
        # đường dẫn như trước sẽ giữ vân tay của bản hỏng mãi. Gỡ rồi tạo lại.
        lam_moi = self._clip_doi_file_sau_cong_bo(files, da_co) if da_co else set()
        can_xu_ly = []
        for path in files:
            khoa = self._khoa_duong_dan(path)
            if khoa in da_co and khoa not in lam_moi:
                tracker.skipped(path)
            else:
                can_xu_ly.append(path)
        # Clip có vân tay mà file đã VẮNG khỏi thư mục nguồn (phản biện vòng 2 + 3):
        # * có bản cách ly trong `_hong/` của ĐÚNG thư mục chứa nó → ứng viên gỡ, nhưng chỉ
        #   gỡ khi bản THAY THẾ cùng mã video có vân tay trong kho tạm (kiểm sau bước
        #   thêm) — gỡ trước khi bản mới tạo được vân tay là xuất bản một kho không còn vân
        #   tay nào cho video đó;
        # * vắng không rõ lý do (ổ chưa gắn, file chưa tải về…) → GIỮ: gỡ nhầm là mất hàng
        #   giờ tạo lại.
        ten_goc = {self._khoa_duong_dan(c["duong_dan"]): os.path.basename(c["duong_dan"])
                   for c in ds_cu}

        def ke_ten(tap) -> str:
            ds = sorted(ten_goc.get(k, os.path.basename(k)) for k in tap)
            return ", ".join(ds[:10]) + (f" … (+{len(ds) - 10})" if len(ds) > 10 else "")

        ung_vien_go: set = set()
        giu_hong: set = set()
        if da_co:
            goc_kho = self._khoa_duong_dan(thumuc)
            vang = da_co - {self._khoa_duong_dan(p) for p in files}
            hong_theo_thu_muc: dict = {}
            for k in vang:
                thu_muc_k = os.path.dirname(k)
                try:
                    trong_kho = os.path.commonpath([thu_muc_k, goc_kho]) == goc_kho
                except ValueError:
                    trong_kho = False
                if not trong_kho:
                    continue
                if thu_muc_k not in hong_theo_thu_muc:
                    hong_theo_thu_muc[thu_muc_k] = channel.ten_da_cach_ly(thu_muc_k)
                if channel.la_ban_da_cach_ly(os.path.basename(k),
                                             hong_theo_thu_muc[thu_muc_k]):
                    ung_vien_go.add(k)
            # Không có bản thay thế nào (trong kho cũ hoặc trong lượt thêm này) thì khỏi
            # dựng kho tạm: chắc chắn giữ.
            ma_co_the_thay = ({self._ma_video_khoa(k) for k in cu_huu_ich - ung_vien_go}
                              | {self._ma_video_khoa(self._khoa_duong_dan(p))
                                 for p in can_xu_ly}) - {""}
            giu_hong = {k for k in ung_vien_go
                        if self._ma_video_khoa(k) not in ma_co_the_thay}
            ung_vien_go -= giu_hong
            con_vang = vang - ung_vien_go - giu_hong
            if con_vang:
                canh_bao.append(
                    f"{len(con_vang)} clip trong kho vân tay không còn file trong thư mục "
                    "nguồn — giữ nguyên vân tay (ổ chưa gắn, file chưa tải về…?). Dùng «Tạo "
                    f"mới» nếu chắc chắn muốn gỡ: {ke_ten(con_vang)}.")
        if lam_moi:
            ten_lam_moi = sorted(os.path.basename(p) for p in files
                                 if self._khoa_duong_dan(p) in lam_moi)
            canh_bao.append(
                f"Làm mới vân tay {len(lam_moi)} clip có file đã thay sau lần tạo kho gần "
                f"nhất: {', '.join(ten_lam_moi[:10])}"
                + (f" … (+{len(ten_lam_moi) - 10})" if len(ten_lam_moi) > 10 else "") + "."
            )

        if not can_xu_ly and not ung_vien_go:
            if giu_hong:
                canh_bao.append(self._canh_bao_giu_hong(giu_hong, ke_ten))
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
            if lam_moi:
                self._go_van_tay_cu(db_tam, lam_moi, ds_cu, workspace, tracker)

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
        cong_bo = False
        try:
            # Chỉ có clip cần GỠ (đã bị cách ly) mà không có gì để thêm: bỏ bước `add`.
            if can_xu_ly:
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
            # Clip đã bị cách ly: gỡ SAU bước thêm, chỉ khi bản thay thế cùng mã video có
            # vân tay trong kho tạm (phản biện vòng 3).
            go_hong: set = set()
            if ung_vien_go:
                go_hong = self._go_hong_co_ban_thay(ung_vien_go, db_tam)
                if go_hong:
                    self._go_van_tay_cu(db_tam, go_hong, ds_cu, workspace, tracker)
                    canh_bao.append(
                        f"Gỡ vân tay {len(go_hong)} clip đã bị cách ly vào "
                        f"{channel.THU_MUC_HONG}/ (file nghi hỏng; bản thay thế cùng mã video "
                        f"đã có vân tay): {ke_ten(go_hong)}.")
                giu_hong |= ung_vien_go - go_hong
            if giu_hong:
                canh_bao.append(self._canh_bao_giu_hong(giu_hong, ke_ten))
            # Mã thoát 0 + file tạm tồn tại chưa chứng minh kho DÙNG ĐƯỢC (TCP-02).
            cong_bo, canh_bao_kiem = self._kiem_kho_tam(db_tam, sub, cu_huu_ich, can_xu_ly,
                                                        lam_moi=lam_moi,
                                                        da_go=frozenset(go_hong))
            canh_bao.extend(canh_bao_kiem)
            if cong_bo:
                # Sổ đăng ký vẫn trỏ kho đã ghim tới đúng file này? (TCP-01)
                self._kiem_dich_cong_bo()
                tracker.saving(tracker.state.active_subprocess_pid)
                self._cache_khoa = None
                try:
                    os.replace(db_tam, self.db_file)
                except PermissionError:
                    # File cũ đang bị khoá (Windows/diệt virus): công bố sang file MỚI,
                    # trỏ đúng kho đã ghim sang đó. Không bao giờ xoá file cũ trước.
                    ten_moi = (
                        f"kho_{self._slug(self.kho_dang_dung or 'kho')}_"
                        f"{uuid.uuid4().hex[:6]}.pklz"
                    )
                    db_moi = os.path.join(self.data_dir, ten_moi)
                    os.replace(db_tam, db_moi)
                    if self.kho_dang_dung:
                        ten_kho = self.kho_dang_dung

                        def doi_file(d: dict) -> None:
                            for kho in d["danh_sach"]:
                                if kho["ten"] == ten_kho:
                                    kho["db_cu"] = kho["db"]
                                    kho["db"] = ten_moi

                        self._sua_khos(doi_file)
                    self.db_file = db_moi
                    canh_bao.append(
                        "File vân tay cũ đang bị khóa; đã ghi kết quả vào file mới an toàn."
                    )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        if not cong_bo:
            tracker.completed(
                "Không có clip mới nào tạo được vân tay; kho hiện tại giữ nguyên.",
                db_written=False,
            )
            state = tracker.state
            return {
                "so_clip": tong,
                "da_xu_ly": state.processed_count,
                "thanh_cong": 0,
                "bo_qua": state.skipped_count,
                "that_bai": state.failed_count,
                "da_huy": False,
                "loi_file": [*loi_file, *[x["message"] for x in tracker.errors]],
                "giay": state.elapsed_seconds,
                "canh_bao": canh_bao,
                "da_ghi_kho": False,
            }

        # Phiên bản mới cho lịch sử quét (TCP-07). Chỉ đổi metadata shifts khi toàn bộ
        # kho vừa được tạo mới, hoặc khi phần bổ sung dùng đúng shifts cũ. Kho add lệch
        # shifts phải tiếp tục mang metadata cũ để những lượt sau vẫn cảnh báo cho tới
        # khi người dùng chủ động tạo lại.
        canh_bao.extend(self._ghi_phien_ban_sau_cong_bo(
            shifts_kho=shifts_kho,
            cap_nhat_shifts=sub == "new" or shifts_da_luu == shifts_kho,
            moc_build=bat_dau_build,
        ))

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
            "da_ghi_kho": True,
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
        # Sổ phạm vi của lượt quét (nếu có): khúc lỗi KHÔNG được biến mất khỏi trách
        # nhiệm quét — vùng của nó phải được ghi là chưa kiểm (audit TCP-04).
        pv = getattr(self, "_pham_vi", None)
        # Lập khúc theo độ dài ÂM THANH khi luồng tiếng kết thúc trước hình.
        tong_quet = float(tong)
        if pv is not None and pv.het_am_thanh and pv.het_am_thanh < tong_quet:
            tong_quet = float(pv.het_am_thanh)

        buoc = cfg.chunk_s - overlap
        het = tong_quet if den_giay is None else min(den_giay, tong_quet)
        moc = [
            bat_dau
            for bat_dau in range(0, int(tong_quet) + 1, buoc)
            if bat_dau < tong_quet and tu_giay <= bat_dau < het
        ]
        ds = []
        if not moc:
            return ds, tong
        for i, bat_dau in enumerate(moc):
            self._check_cancel()
            out = os.path.join(chunk_dir, f"chunk_{int(bat_dau):07d}.wav")
            ky_vong = min(float(cfg.chunk_s), tong_quet - bat_dau)
            # `-map 0:a:0`: cắt ĐÚNG luồng tiếng đầu tiên — luồng mà `do_dai_am_thanh` đo.
            # Không chỉ định thì FFmpeg tự chọn luồng "tốt nhất" (nhiều kênh hơn), có thể
            # là luồng khác với độ dài khác (phản biện vòng 2).
            lenh = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(bat_dau), "-t", str(cfg.chunk_s), "-i", media,
                    "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "11025", out]
            ok = False
            do = None
            # Thử lại MỘT lần cho lỗi tạm thời (file đang bị khoá, ổ chập chờn). Không thử
            # lại khi FFmpeg treo: lần sau cũng sẽ treo, chỉ tốn thêm một hạn chờ. WAV mà
            # không đọc được header cũng là cắt lỗi — trước đây được coi như đủ độ dài.
            for lan in range(2):
                r = self._chay_ffmpeg(lenh)
                if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024:
                    do = do_dai_wav(out)
                    if do is not None:
                        ok = True
                        break
                LOGGER_SCAN.warning(
                    "event=scan.chunk_failed start=%d attempt=%d rc=%s timed_out=%s err=%s",
                    int(bat_dau), lan + 1, r.returncode, r.timed_out,
                    (r.stderr or "").strip()[-200:],
                )
                if r.timed_out:
                    break
            if ok:
                ds.append(out)
                if pv is not None:
                    thuc = min(do, ky_vong)
                    pv.do_dai_khuc[os.path.basename(out)] = thuc
                    if thuc < ky_vong - 1.0:
                        # Khúc bị cắt ngắn: phần cuối chưa từng được giải mã.
                        pv.loi_cat.append((bat_dau + thuc, bat_dau + ky_vong))
            elif pv is not None:
                pv.loi_cat.append((float(bat_dau), bat_dau + ky_vong))
            self._bao(progress, pct0 + (pct1 - pct0) * (i + 1) / len(moc),
                      f"Đang cắt khúc {i+1}/{len(moc)} (mốc {hhmmss(bat_dau)})...")
        return ds, tong

    def _match_chunks(self, chunks: list, progress: Optional[Callable] = None,
                      pct0: float = 0.60, pct1: float = 0.95,
                      workspace: Optional[str] = None,
                      hau_to: str = "", luot_bu: str = "") -> list:
        """So khớp một nhóm khúc với kho vân tay, trả về danh sách kết quả thô.

        ``luot_bu``: khoá lượt bù tốc độ (``_luot_bu``) khi các khúc là bản đã đổi tốc độ.

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
        # Kho được ghi lại giữa hai lượt khớp của CÙNG một video → dừng, không trộn.
        self._kiem_kho_khong_doi()
        goc = workspace or self.data_dir
        listfile = os.path.join(goc, f"_ds_khuc{hau_to}.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            f.write("\n".join(chunks))
        opfile = os.path.join(goc, f"_raw_match{hau_to}.txt")
        if os.path.exists(opfile):
            os.remove(opfile)

        dem = {"n": 0}
        # Khúc audfprint KHÔNG đọc được: tín hiệu chính là dòng stdout
        # "wavfile2peaks: Error reading <khúc> skipping" (phản biện TCP-04). Dòng NOMATCH
        # "0.0 sec" thì KHÔNG đủ: khúc im lặng cũng ghi y hệt (phản biện vòng 2, N1).
        loi_doc: set = set()

        def on_line(dong: str):
            # ncores > 1: các worker audfprint ghi CHUNG một ống stdout, mỗi `print` là
            # vài lần ghi riêng nên dòng của nhiều khúc XEN nhau — hai lỗi trên một dòng,
            # hoặc lỗi chen giữa dòng "Analyzed <khúc khác>". Lấy MỌI khúc đứng ngay sau
            # cụm "Error reading", không lấy khúc đầu tiên của dòng (phản biện vòng 3).
            for mk_loi in RE_LOI_DOC_KHUC.finditer(dong):
                loi_doc.add(mk_loi.group(1))
            # Với ncores > 1 audfprint in "Analyzed <khúc>" không có "#N".
            so = dong.count("Analyzed")
            if so:
                dem["n"] += so
                self._bao(progress, pct0 + (pct1 - pct0) * min(1.0, dem["n"] / max(
                    1, len(chunks))),
                    f"Đang so khớp vân tay... khúc {min(dem['n'], len(chunks))}/"
                    f"{len(chunks)}")

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
        # Khúc mà audfprint THỰC SỰ đã phân tích: mỗi khúc để lại dòng `Matched …` hoặc
        # `NOMATCH …`. Khúc gửi đi mà vắng mặt (lỗi đọc với --continue-on-error) là
        # vùng CHƯA được so khớp (audit TCP-04).
        da_phan_tich: set = set()
        khong_hash: set = set()
        if os.path.exists(opfile):
            with open(opfile, "r", encoding="utf-8", errors="replace") as f:
                for dong in f:
                    dong_tho += 1
                    dong = dong.strip()
                    mk_bat_ky = RE_TEN_KHUC.search(dong)
                    if mk_bat_ky:
                        da_phan_tich.add(mk_bat_ky.group(0))
                        m_no = (RE_NOMATCH_SO_HASH.search(dong)
                                if dong.startswith("NOMATCH") else None)
                        if m_no and int(m_no.group(1)) == 0:
                            khong_hash.add(mk_bat_ky.group(0))
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
                    # `t_clip` ở trục CLIP GỐC, không nhân hệ số. Trên trục khúc đã
                    # hiệu chỉnh, clip gốc phát đúng tốc độ nên đầu clip (t_clip = 0)
                    # nằm ở t_khuc − t_clip, tức `offset + k·(t_khuc − t_clip)` trên
                    # video = `bat_dau − k·t_clip`. Trừ thẳng `t_clip` (code cũ) lệch
                    # (1 − k)·t_clip giây — 12 s ở ca audit TCP-05. Với k = 1 y hệt cũ.
                    tho.append({"clip": file_clip, "bat_dau": bat_dau,
                                "khop": khop, "t_clip": t_clip, "hash": so_hash,
                                "he_so": he_so,
                                "align": bat_dau - he_so * t_clip})

        # Lớp phòng thủ thứ hai, theo NỘI DUNG khúc chứ không theo stdout: khúc 0 hash mà
        # bộ đọc WAV của tool không đọc được, hoặc đọc được mà CÓ TIẾNG RÕ, thì audfprint
        # chưa từng phân tích nó (lỗi đọc tạm thời lúc đó — bị khoá, FFmpeg con chết…).
        # Khúc im lặng / gần im lặng vẫn là ĐÃ phân tích — âm tính thật (vòng 2 + vòng 3).
        theo_ten = {os.path.basename(k): k for k in chunks}
        for ten in khong_hash - loi_doc:
            duong = theo_ten.get(ten)
            if duong and (do_dai_wav(duong) is None or wav_co_tieng(duong)):
                loi_doc.add(ten)
        da_phan_tich -= loi_doc
        pv = getattr(self, "_pham_vi", None)
        if pv is not None:
            vang = []
            for khuc in chunks:
                ten = os.path.basename(khuc)
                mk = RE_TEN_KHUC.fullmatch(ten)
                if not mk:
                    continue
                if not mk.group(2):
                    # Khúc GỐC: tính độ phủ.
                    if ten not in da_phan_tich:
                        pv.khong_phan_tich.add(ten)
                        vang.append(ten)
                elif ten in da_phan_tich:
                    pv.bu_toc_do_ok.add((luot_bu, int(mk.group(1))))
                else:
                    # Khúc của lượt BÙ TỐC ĐỘ không được phân tích.
                    pv.loi_bu_toc_do.add((luot_bu, int(mk.group(1))))
            if vang:
                LOGGER_SCAN.warning(
                    "event=scan.chunks_not_analyzed count=%d first=%s", len(vang), vang[0])

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

        def he_so(x: dict) -> float:
            return round(float(x.get("he_so", 1.0) or 1.0), 5)

        gop = []
        for x in loc:
            trung = next(
                (
                    g for g in gop
                    if g["clip"] == x["clip"]
                    # Mảnh của hai phép biến đổi tốc độ khác nhau không cùng trục khúc:
                    # không gộp (audit TCP-05). Lượt thường k = 1 vẫn gộp như cũ.
                    and g["he_so"] == he_so(x)
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
                    "he_so": he_so(x),
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
            k = g["he_so"]
            # Mốc đầu clip gốc trên trục VIDEO: `bat_dau − k·t_clip` (xem parser).
            clip_bat_dau_s = max(
                0.0,
                som_nhat["bat_dau"] - k * som_nhat["t_clip"],
            )
            ket_qua.append(Match(
                clip=ten_clip,
                start_s=clip_bat_dau_s,
                end_s=end_s,
                matched_s=do_dai_hop,
                # "Khớp từ giây thứ mấy CỦA CLIP" đo trên trục clip gốc: đổi khoảng cách
                # trên video về trục clip bằng cách chia k. Với k = 1 y hệt công thức cũ
                # (kể cả ca clip bắt đầu trước đầu video và bị kẹp về 0).
                clip_offset_s=(vung_khop_s - clip_bat_dau_s) / k,
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

    @staticmethod
    def _nhan_vung(start_s: float, duration: float) -> str:
        """Nhãn Đầu/Giữa/Cuối của mốc ``start_s`` trong video dài ``duration`` giây.

        p < 1/3 → «Đầu», p < 2/3 → «Giữa», còn lại «Cuối» (điểm ranh giới thuộc vùng SAU).
        Thời lượng không dương thì không có vị trí để nói: trả chuỗi rỗng.
        """
        if not duration or duration <= 0:
            return ""
        p = start_s / duration
        return "Đầu" if p < 1 / 3 else ("Giữa" if p < 2 / 3 else "Cuối")

    def _gan_chi_so(self, ds: list, duration: float) -> None:
        """Tính tỷ lệ vân tay khớp (%) và vùng vị trí cho từng kết quả."""
        tong_hash = self._tong_hash_kho()
        for m in ds:
            goc = tong_hash.get(m.clip, 0)
            m.ty_le = min(100.0, round(100.0 * m.hashes / goc, 1)) if goc else 0.0
            if duration:
                m.vung = self._nhan_vung(m.start_s, duration)

    def _dan_lai_nhan_vung(self, r: ScanResult) -> None:
        """`duration_s` vừa đổi từ độ dài FILE sang độ dài VIDEO thật: dán lại nhãn vùng.

        `_gan_chi_so` đã dán theo file đang xử lý, còn báo cáo đọc `duration_s`. Dán cho MỌI
        ứng viên — cả đoạn bị loại — để một kết quả không mang hai trục thời gian (CLAUDE.md
        mục 13: đổi trường phái sinh thì rà mọi thứ tính từ nó).
        """
        if not r.duration_s:
            return
        for m in (*r.matches, *r.matches_loai):
            m.vung = self._nhan_vung(m.start_s, r.duration_s)

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
        # Trạng thái kho chỉ cần cho ca "audfprint không ra dòng nào": ở đó mô tả
        # chung nêu nghi vấn "sai kho / kho rỗng" mà ta đã biết là không phải, và
        # nghi vấn thừa đó từng khiến người dùng đi kiểm kho thay vì kết luận đúng
        # là clip gốc chưa có trong kho. `db_clips()` có cache theo (đường dẫn,
        # mtime, kích thước) và đã được nạp từ đầu lượt quét nên không tốn thêm I/O.
        if cd.giai_doan_mat == AUDFPRINT_KHONG_RA_MATCH:
            with contextlib.suppress(Exception):
                cd.ten_kho = self.kho_dang_dung
                cd.so_clip_kho = len(self.db_clips())
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
        # `ten_file_an_toan` chỉ lọc ký tự ĐIỀU KHIỂN — nó sinh ra cho log, không phải
        # để dựng đường dẫn. Dùng nó ở đây khiến mọi tiêu đề có dấu hai chấm ghi vào
        # một NTFS Alternate Data Stream: bản ghi biến mất khỏi `glob("*.json")` và để
        # lại file rác 0 byte. Xem `luu_tru.ten_file_hop_le`.
        ten = ten_file_hop_le(f"{ban_ghi['video']}_{int(time.time())}") + ".json"
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
        # Ghi ĐÚNG những khúc đã gửi đi so khớp — đường nhanh Top-1 có thể chỉ gửi khúc
        # đầu; phạm vi không được lấy theo vùng dự kiến (audit TCP-06).
        pv = getattr(self, "_pham_vi", None)

        def gui(ds: list) -> list:
            if pv is not None:
                pv.da_gui.extend(ds)
            return ds

        du_dieu_kien = (
            cfg.top1_tim_nhanh
            and cfg.top_n == 1
            and len(chunks) >= max(2, cfg.top1_khuc_toi_thieu)
        )
        if not du_dieu_kien:
            cd.duong_di = "quet_toan_bo"
            return self._match_chunks(gui(chunks), progress, pct0, pct1,
                                      workspace=workspace)

        # Chia đôi tiến độ: phần đầu cho vùng ưu tiên, phần sau cho quét bù.
        giua = pct0 + (pct1 - pct0) * 0.35
        self._bao(progress, pct0,
                  "Tìm nhanh 1 kết quả đáng tin — đang kiểm tra phần đầu video...")
        dau = self._match_chunks(gui(chunks[:1]), progress, pct0, giua,
                                 workspace=workspace, hau_to="_uu_tien")
        som = self._du_manh_de_dung_som(dau, duration)
        if som is not None:
            if pv is not None:
                pv.dung_som = True
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
        con_lai = self._match_chunks(gui(chunks[1:]), progress, giua, pct1,
                                     workspace=workspace, hau_to="_con_lai")
        return dau + con_lai

    # =================================================================
    #  3c) BÙ VIDEO BỊ ĐỔI TỐC ĐỘ ĐỂ NÉ VÂN TAY
    # =================================================================

    def _gioi_han_tai(self, tong: float) -> Optional[float]:
        """Chỉ tải bao nhiêu giây đầu? ``None`` = tải trọn như cũ.

        Dùng chung ngưỡng và bước với quét tăng dần: phần tải về đúng bằng phần lượt
        quét đầu tiên cần, không thừa không thiếu.

        ``quet_tang_dan`` là CÔNG TẮC TỔNG. Trước đây hàm này chỉ đọc ``tai_mot_phan``,
        mà ``tai_mot_phan`` không có ô nào trên giao diện — nên người dùng bỏ tick
        «Quét tăng dần cho video rất dài» theo đúng hướng dẫn của chính tool
        (app.py, hộp «Đã dừng sớm ở N nguồn») vẫn chỉ tải 3 tiếng đầu của video 40
        tiếng. Lời hứa "muốn quét trọn thì tắt ô này" bị phá ngay ở khâu TẢI, và
        không có dấu hiệu nào cho thấy điều đó.

        Chiều ngược lại vẫn hợp lệ và vẫn giữ được: ``quet_tang_dan`` bật +
        ``tai_mot_phan`` tắt = tải trọn nhưng xử lý tăng dần.
        """
        cfg = self.config
        if not getattr(cfg, "quet_tang_dan", False):
            return None
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

    def _ung_vien_dat(self, tho: list, duration: float) -> list:
        """Các ứng viên đạt tiêu chí chấp nhận. Không đụng chẩn đoán cuối."""
        if not tho:
            return []
        ung_vien = self._merge(tho)
        if not ung_vien:
            return []
        self._gan_chi_so(ung_vien, duration)
        dat, _, _ = loc_chap_nhan(ung_vien, self.config)
        return dat

    def _co_ung_vien_dat(self, tho: list, duration: float) -> bool:
        """Đã có ứng viên nào đạt tiêu chí chấp nhận chưa? Không đụng chẩn đoán cuối."""
        return bool(self._ung_vien_dat(tho, duration))

    def _du_de_dung_som(self, tho: list, duration: float) -> bool:
        """Phần đã quét có đủ để KHÔNG cần quét tiếp không?

        Câu hỏi đúng không phải "đã có ứng viên đạt chuẩn chưa" mà là "chính sách
        chọn lọc hiện tại đã được thoả mãn chưa". Hai câu này chỉ trùng nhau khi
        ``top_n = 1``. Trước đây chỉ hỏi câu đầu, nên đặt ``top_n = 5`` để lấy 5 bằng
        chứng cho hồ sơ khiếu nại thì đoạn đầu tìm được ĐÚNG MỘT ứng viên là vòng lặp
        dừng luôn — mất trắng 4 suất còn lại mà không có một dấu hiệu nào.

        Lưu ý ``Config.top_n`` mặc định là **5**, không phải 1 — nên lỗi này KHÔNG
        phải ca hiếm ở cấu hình lạ mà là hành vi mặc định. Phép đo trong CLAUDE.md
        mục 12 (40 phút xuống 5,5 phút) chạy ở ``top_n = 1`` nên đã không chạm tới nó.

        Điều kiện dừng: đã đủ ``top_n`` ứng viên đạt chuẩn. Nếu còn bật
        ``uu_tien_clip_khac_nhau`` thì phải đủ ``top_n`` clip gốc KHÁC NHAU — năm đoạn
        của cùng một clip chỉ điền được một suất, đếm gộp lại là tự lừa mình.

        VÌ SAO KHÔNG chặn dừng sớm khi ``phan_bo_deu`` bật: đúng là ``_chon_loc`` sinh
        ra để chứng minh vi phạm TRẢI DÀI toàn video, mà dừng ở 3 tiếng đầu thì không
        chứng minh được điều đó. Nhưng chặn hẳn sẽ vô hiệu hoá tính năng ở đúng cấu
        hình mặc định (``phan_bo_deu`` cũng mặc định bật), tức trả giá toàn bộ khoản
        tiết kiệm để đổi lấy một thứ mà báo cáo ĐÃ nói thật: ``_gan_chi_so`` dán nhãn
        vùng theo VIDEO THẬT nên năm đoạn lấy từ 3 tiếng đầu của video 35 tiếng đều
        mang nhãn «Đầu», và ``kq.note`` ghi rõ đã dừng ở đâu. Người dùng nhìn ra ngay,
        và tắt «Quét tăng dần» là quét trọn.
        """
        cfg = self.config
        n = max(1, cfg.top_n)
        dat = self._ung_vien_dat(tho, duration)
        if not dat:
            return False
        if n <= 1:
            return True
        if cfg.uu_tien_clip_khac_nhau:
            return len({m.clip for m in dat}) >= n
        return len(dat) >= n

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
            r = self._chay_ffmpeg(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", khuc,
                 "-vn", "-ac", "1", "-ar", "11025",
                 "-af", bo_loc_ffmpeg(he_so, ho), out])
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1024:
                ra.append(out)
            elif getattr(self, "_pham_vi", None) is not None:
                # Lượt bù tốc độ thiếu khúc này: âm tính của video chưa được kiểm trọn
                # theo chính sách đang bật (phản biện TCP-04).
                self._pham_vi.loi_bu_toc_do.add(
                    (self._luot_bu(he_so, ho), int(mk.group(1))))
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
            # Ghi RÕ vì sao không có gì để thử. Không ghi thì `da_thu_toc_do` rỗng
            # trông y hệt ca "đã thử mà không thấy", và người dùng tin nhầm rằng lượt
            # quét âm tính này đã được kiểm chống né tốc độ — trong khi nó chưa từng
            # chạy một lượt nào. Đây chính là điểm mù đã che mất việc lưới quét mù bị
            # để rỗng suốt nhiều tuần.
            if max(0, cfg.toc_do_toi_da_thu) <= 0:
                cd.ly_do_khong_bu_toc_do = (
                    "Chưa thử bù tốc độ lượt nào: «Số lượt bù tốc độ tối đa» "
                    "(toc_do_toi_da_thu) đang là 0."
                )
            else:
                cd.ly_do_khong_bu_toc_do = (
                    "Chưa thử bù tốc độ lượt nào: không đọc được độ trôi từ các mảnh "
                    f"khớp (cần ≥{cfg.toc_do_min_manh} mảnh của CÙNG một clip gốc), "
                    "mà cả hai lưới quét mù «luoi_tempo» và «luoi_resample» trong "
                    "data/cau_hinh.json đều rỗng. Nghĩa là reup bị ĐỔI CAO ĐỘ sẽ "
                    "không bắt được. Thêm mức vào «luoi_resample» nếu cần — đánh đổi "
                    "là mỗi video không có kết quả sẽ quét lâu hơn khoảng 2,9 lần."
                )
            LOGGER_SCAN.info("event=scan.tempo.skipped reason=%s",
                             "khong_co_phuong_an")
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
            luot = self._luot_bu(he_so, ho)
            ket = self._match_chunks(khuc_moi, progress, p0, p1,
                                     workspace=workspace,
                                     hau_to=f"_{luot}", luot_bu=luot)
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

        Gọi trực tiếp một file = một JOB mới: xoá cờ huỷ đúng một lần rồi chạy trên bản
        Engine đã ghim kho/cấu hình. Gọi từ bên trong một job (batch, quét YouTube) thì
        KHÔNG xoá cờ huỷ — yêu cầu Dừng của batch phải còn nguyên (audit TCP-13).
        """
        if source_type == "file" and not getattr(self, "_la_ban_ghim", False):
            self.cancel_event.clear()
        job = self._ban_sao_cho_job()
        try:
            return job._scan_media(path, label, ref, source_type, progress,
                                   luu_lich_su, pct_start)
        finally:
            self._nhan_ket_qua_job(job)

    def _scan_media(self, path: str, label: Optional[str] = None, ref: str = "",
                    source_type: str = "file", progress: Optional[Callable] = None,
                    luu_lich_su: bool = True, pct_start: float = 0.0) -> ScanResult:
        """Thân của ``scan_media`` — chạy trên bản Engine đã ghim, không đụng cờ huỷ."""
        self.require(can_db=True)
        # Mỗi video là một đơn vị nhất quán: chụp chữ ký kho ở đây và kiểm lại trước mỗi
        # lượt khớp. Giữa hai video của một batch thì kho mới được phép có hiệu lực.
        self._chu_ky_kho_ghim = self._chu_ky_db()
        # Mốc phần trăm cắt-khúc cũ không còn cố định: quét tăng dần chia dải
        # `pct_start..p_match1` cho từng đoạn, mỗi đoạn tự có phần cắt và phần khớp.
        p_match1 = 0.95
        ten = label or os.path.basename(path)
        kq = ScanResult(source_name=ten, source_ref=ref or path)
        self._gan_danh_tinh(kq)
        self.chan_doan_quet = ChanDoanQuet()
        # Sổ phạm vi THẬT của lượt quét này: khúc nào đã gửi đi khớp, khúc nào lỗi.
        pv = self._pham_vi = _PhamViQuet()
        try:
            if not os.path.isfile(path):
                raise RuntimeError(f"Không tìm thấy file: {path}")
            with self.scan_workspace() as ws:
                tong = self.duration_of(path)
                if not tong:
                    raise RuntimeError(f"Không đọc được thời lượng file: {path}")
                kq.duration_s = tong
                tong_am = self.do_dai_am_thanh(path)
                if tong_am and tong_am < tong - DUNG_SAI_PHU_S:
                    pv.het_am_thanh = float(tong_am)
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
                    if len(doan) > 1 and self._du_de_dung_som(tho, tong):
                        if i < len(doan) - 1:
                            pv.dung_som = True
                        break
                if not chunks:
                    raise RuntimeError("Không cắt được khúc nào từ file này.")
                self._chot_pham_vi(kq, tong, da_quet_den)
                # Không có gì đạt chuẩn thì thử bù tốc độ trước khi kết luận là
                # không có. Đây là lúc DUY NHẤT lượt quét phụ được chạy, nên video
                # có kết quả bình thường không tốn thêm giây nào.
                if self.config.quet_da_toc_do and not self._co_ung_vien_dat(tho, tong):
                    tho = tho + self._quet_da_toc_do(
                        chunks, tho, progress, p_match1, p_match1, ws
                    )
            # `_merge`/`_gan_chi_so` đọc tổng hash từ kho: phải là đúng phiên bản đã khớp.
            self._kiem_kho_khong_doi()
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
            kq.dat_muc_tieu = self._du_muc_tieu(kq.matches)
            hong_bu = self._vung_hong_bu_toc_do(pv, tong) if not kq.matches else []
            if hong_bu:
                # Không thấy gì mà lượt bù tốc độ lại không chạy trọn: chưa chứng minh được
                # âm tính theo chính sách đang bật — coi như vùng chưa kiểm (phản biện).
                kq.vung_loi = hop_khoang(list(kq.vung_loi) + hong_bu)
                kq.note = "\n".join(x for x in (
                    kq.note, "Lượt bù tốc độ không chạy trọn: "
                             f"{len(hong_bu)} vùng chưa được kiểm.") if x)
            if kq.vung_loi:
                # Vùng chưa kiểm KHÔNG được biến mất: có bằng chứng thì giữ bằng chứng
                # và ghi rõ chưa quét trọn; KHÔNG có thì đây chưa phải kết luận âm tính
                # — báo lỗi để lịch sử không chặn lượt quét lại (audit TCP-04).
                kq.ly_do_pham_vi = "loi_khuc"
                if kq.matches:
                    tin = (f"Chưa quét trọn video: {mo_ta_pham_vi(kq)}. Bằng chứng chỉ "
                           "nằm trong phần đã so khớp.")
                else:
                    kq.status = "error"
                    tin = (f"Không xử lý được một phần video: {mo_ta_pham_vi(kq)}. Chưa "
                           "thể kết luận video này không chứa clip gốc — hãy quét lại.")
                kq.note = "\n".join([x for x in (kq.note, tin) if x])
                self._bao(progress, p_match1, "⚠️ " + tin)
            elif kq.quet_mot_phan:
                if pv.dung_som:
                    kq.ly_do_pham_vi = "dung_som"
                da_khop = (tong_do_dai(kq.vung_da_khop) if kq.vung_da_khop is not None
                           else kq.pham_vi_quet_s)
                tin = (f"Đã dừng sớm sau khi so khớp {hhmmss(da_khop)}"
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
            kq.ly_do_pham_vi = "huy"
        except Exception as e:
            kq.status, kq.note = "error", ytdlp_chung.giai_thich_loi(e)
        finally:
            shutil.rmtree(self.chunk_dir, ignore_errors=True)
            kq.chan_doan = self._chot_chan_doan(kq)
            self._pham_vi = None
        if luu_lich_su:
            kq.job_id = self.save_job(kq, source_type)
        return kq

    def _chot_pham_vi(self, kq: ScanResult, tong: float, da_quet_den: float) -> None:
        """Tính phạm vi THẬT đã so khớp từ sổ phạm vi của lượt quét (TCP-04/TCP-06).

        Khúc tính là đã khớp khi đã được GỬI đi so khớp và audfprint có báo về nó; độ
        dài lấy theo số đo thật của khúc. Vùng lỗi = vùng cắt/khớp lỗi KHÔNG được khúc
        nào khác phủ. ``pham_vi_quet_s`` = mốc cuối của phần đã khớp — chỉ dùng chia
        vùng chọn lọc, không dùng để khẳng định độ phủ.

        Không có sổ phạm vi (hàm quét bị thay trong test kiểu cũ) thì giữ cách tính cũ
        và để phạm vi là "không biết".
        """
        pv = getattr(self, "_pham_vi", None)
        if pv is None or not pv.da_gui:
            kq.pham_vi_quet_s = da_quet_den
            return
        khoang, loi = [], list(pv.loi_cat)
        for khuc in pv.da_gui:
            ten = os.path.basename(khuc)
            mk = RE_TEN_KHUC.fullmatch(ten)
            if not mk or mk.group(2):
                continue
            a = float(int(mk.group(1)))
            dai = pv.do_dai_khuc.get(ten, min(float(self.config.chunk_s), tong - a))
            if ten in pv.khong_phan_tich:
                loi.append((a, a + dai))
            else:
                khoang.append((a, min(a + dai, tong)))
        if pv.het_am_thanh and pv.het_am_thanh < tong:
            # Sau khi luồng tiếng kết thúc không còn gì để so khớp: đã kiểm, không phải lỗi.
            khoang.append((float(pv.het_am_thanh), float(tong)))
        kq.vung_da_khop = hop_khoang(khoang)
        kq.vung_loi = tru_khoang(loi, kq.vung_da_khop)
        kq.pham_vi_quet_s = max((b for _, b in kq.vung_da_khop), default=0.0)

    def _du_muc_tieu(self, matches: list) -> bool:
        """Chính sách chọn lọc đã thoả chưa: đủ Top-N (và đủ clip khác nhau nếu bật)."""
        n = max(1, int(self.config.top_n))
        if self.config.uu_tien_clip_khac_nhau:
            return len({m.clip for m in matches}) >= n
        return len(matches) >= n

    def scan_youtube(self, url: str, progress: Optional[Callable] = None,
                     luu_lich_su: bool = True) -> ScanResult:
        """Tải audio 1 link YouTube rồi quét.

        Gọi trực tiếp = một JOB mới: xoá cờ huỷ một lần, ghim kho/cấu hình. Bên trong
        batch (``scan_iter``) thì không xoá cờ — trước đây chính dòng xoá cờ ở đây làm
        nút Dừng chỉ dừng được video đang chạy, video kế tiếp lại chạy (audit TCP-13).
        """
        if not getattr(self, "_la_ban_ghim", False):
            self.cancel_event.clear()
        job = self._ban_sao_cho_job()
        try:
            return job._scan_youtube(url, progress, luu_lich_su)
        finally:
            self._nhan_ket_qua_job(job)

    def _scan_youtube(self, url: str, progress: Optional[Callable] = None,
                      luu_lich_su: bool = True) -> ScanResult:
        """Thân của ``scan_youtube`` — chạy trên bản ghim, không đụng cờ huỷ."""
        self.require(can_ytdlp=True, can_db=True)
        self.canh_bao_mang = []
        kq = ScanResult(source_name=url, source_ref=url)
        self._gan_danh_tinh(kq)
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
            can_top_n = max(1, self.config.top_n)
            if gioi_han and len(r.matches) < can_top_n:
                # Phần đầu chưa đủ kết luận cho cả video: phải tải nốt.
                #
                # So với `top_n` chứ không so với 0. Với `top_n = 5`, tìm được 1 đoạn
                # trong 3 tiếng đầu KHÔNG có nghĩa là đã xong: 4 suất còn lại nằm ở
                # phần chưa tải, và điều kiện cũ `not r.matches` khiến chúng mất trắng.
                # Với `top_n = 1` (mặc định) điều kiện này y hệt điều kiện cũ.
                thieu = (f"mới có {len(r.matches)}/{can_top_n} đoạn"
                         if r.matches else "không thấy gì")
                self._bao(progress, 0.40,
                          f"{thieu.capitalize()} trong {hhmmss(gioi_han)} đầu — "
                          "tải nốt phần còn lại để quét trọn...")
                if not self.config.keep_downloads:
                    # Bản tải MỘT PHẦN `<id>__p<giây>` đã quét xong: không giữ đệm thì bỏ
                    # luôn, trước đây nó nằm lại mãi (phản biện vòng 3).
                    with contextlib.suppress(OSError):
                        os.remove(f)
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
                # Nhãn Đầu/Giữa/Cuối cũng tính từ thời lượng: `_gan_chi_so` đã dán theo
                # FILE, nên giờ thứ 1 của video 66 tiếng mang nhãn «Giữa» (1/3 của 3 tiếng).
                self._dan_lai_nhan_vung(r)
                r.pham_vi_quet_s = min(r.pham_vi_quet_s or gioi_han, gioi_han)
                if r.quet_mot_phan and not r.vung_loi:
                    r.ly_do_pham_vi = "gioi_han_tai"
                if r.quet_mot_phan:
                    tin = (f"Chỉ TẢI và quét {hhmmss(r.pham_vi_quet_s)} đầu "
                           f"/{hhmmss(r.duration_s)} — đã đủ bằng chứng nên không tải "
                           "tiếp. Bằng chứng chỉ nằm trong phần đã quét.")
                    r.note = "\n".join([x for x in (r.note, tin) if x])
            # File tải về NGẮN hơn video (yt-dlp bỏ fragment lỗi, file đệm cũ bị cụt): phần
            # thiếu chưa từng được quét — không được thành "quét trọn" (phản biện TCP-04).
            if (r.ly_do_pham_vi != "gioi_han_tai" and r.vung_da_khop is not None
                    and self._thieu_duoi(info.get("duration"), r.duration_s)):
                r, f = self._xu_ly_tai_thieu(url, info, r, f, progress)
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
            kq.ly_do_pham_vi = "huy"
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

    @staticmethod
    def _thieu_duoi(dai_that, dai_file) -> bool:
        """File dài ``dai_file`` có thiếu đuôi so với video dài ``dai_that`` không?"""
        dai_that, dai_file = float(dai_that or 0), float(dai_file or 0)
        return dai_that > 0 and dai_file > 0 and dai_that - dai_file > DUNG_SAI_TAI_THIEU_S

    def _bo_ban_dem(self, video_id: str) -> bool:
        """Bỏ MỌI bản đệm đầy đủ của video. True = không còn bản nào, nên lần tải sau chắc
        chắn là một bản MỚI chứ không phải bản cũ lấy lại từ đệm."""
        con_lai = []
        for p in glob.glob(os.path.join(self.dl_dir, video_id + ".*")):
            if p.endswith((".part", ".ytdl")):
                continue
            try:
                os.remove(p)
            except OSError:
                con_lai.append(p)
        return not con_lai

    def _xu_ly_tai_thieu(self, url: str, info: dict, r: ScanResult, f: str,
                         progress: Optional[Callable]) -> tuple:
        """File tải về ngắn hơn video: trả ``(kết quả, file)`` sau khi đã giải thích được.

        Chỉ một lần tải ĐỘC LẬP thứ hai mới phân biệt được hai nguyên nhân, nên khi chưa có
        bằng chứng nào thì tải lại ngay MỘT lần (phản biện vòng 2):

        * bản mới ĐỦ dài → lần trước bị đứt: quét lại bằng bản mới;
        * bản mới ngắn ĐÚNG bằng lần trước (± ``DUNG_SAI_TAI_LAI_S``) → âm thanh YouTube
          cung cấp thật sự ngắn hơn lengthSeconds: phần sau không có tiếng nào để so
          khớp (như đuôi hình không tiếng của mp4), ghi rõ vào ghi chú. Trước đây ca này
          thành lỗi + bỏ đệm + tải lại ở MỌI lượt, không bao giờ dứt;
        * còn lại (không tải lại được, hoặc lại ngắn với độ dài khác) → phần thiếu là vùng
          LỖI và bỏ bản đệm để lượt sau tải lại (phản biện TCP-04).

        Đã có bằng chứng thì giữ bằng chứng và ghi rõ là chưa quét trọn — không tải lại cả
        video dài chỉ để quét nốt phần đuôi.
        """
        dai_that = float(info.get("duration") or 0)
        dai_file = float(r.duration_s or 0)
        if not r.matches and self._trong_thu_muc_dem(f) and self._bo_ban_dem(info["id"]):
            self._bao(progress, 0.40,
                      f"File tải về chỉ dài {hhmmss(dai_file)}/{hhmmss(dai_that)} — tải lại "
                      "một lần để kiểm...")
            f_moi, dai_moi = None, 0.0
            try:
                f_moi = self.download_audio(url, info["id"], progress)
                dai_moi = float(self.duration_of(f_moi) or 0)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 — giữ kết quả lần đầu, báo vùng lỗi
                LOGGER_SCAN.warning("event=scan.redownload_failed video=%s err=%s",
                                    info["id"], str(e)[:200])
            if f_moi and dai_moi > 0 and not self._thieu_duoi(dai_that, dai_moi):
                r_moi = self.scan_media(f_moi, label=r.source_name, ref=url,
                                        source_type="youtube", progress=progress,
                                        luu_lich_su=False, pct_start=0.40)
                if not self._thieu_duoi(dai_that, r_moi.duration_s):
                    return r_moi, f_moi
                r, f, dai_file = r_moi, f_moi, float(r_moi.duration_s or 0)
            elif f_moi and dai_moi > 0 and abs(dai_moi - dai_file) <= DUNG_SAI_TAI_LAI_S:
                r.vung_da_khop = hop_khoang(list(r.vung_da_khop or [])
                                            + [(dai_file, dai_that)])
                r.duration_s = dai_that
                self._dan_lai_nhan_vung(r)
                # Lý do riêng (dù đã "trọn") để về sau còn tra lại được những video được
                # nhận theo cách này — ví dụ khi nghi một client cắt cụt cố định (vòng 3).
                # Lượt đầu đã có vùng lỗi thì lý do đó quan trọng hơn: không ghi đè.
                if not r.vung_loi:
                    r.ly_do_pham_vi = "am_thanh_ngan_hon"
                tin = (f"Âm thanh YouTube cung cấp chỉ dài {hhmmss(dai_file)}/"
                       f"{hhmmss(dai_that)} — đã tải lại và nhận cùng độ dài, nên phần sau "
                       "không có tiếng để so khớp.")
                r.note = "\n".join(x for x in (r.note, tin) if x)
                return r, f_moi
            elif f_moi:
                f = f_moi
        r.vung_loi = hop_khoang(list(r.vung_loi) + [(dai_file, dai_that)])
        r.duration_s = dai_that
        self._dan_lai_nhan_vung(r)
        r.ly_do_pham_vi = "tai_thieu"
        tin = (f"File tải về chỉ dài {hhmmss(dai_file)}/{hhmmss(dai_that)} — phần cuối "
               "chưa được quét.")
        if not r.matches:
            r.status = "error"
            tin += " Chưa thể kết luận video này không chứa clip gốc — hãy quét lại."
        r.note = "\n".join(x for x in (r.note, tin) if x)
        if self._trong_thu_muc_dem(f):
            # Bỏ bản đệm thiếu để lần quét sau tải lại, không dùng lại file cụt.
            with contextlib.suppress(OSError):
                os.remove(f)
        return r, f

    def scan_iter(
        self,
        nguon: Iterable,
        source_type: str = "youtube",
        progress: Optional[Callable] = None,
        on_video: Optional[Callable] = None,
        *,
        xoa_co_huy: bool = True,
    ):
        """Quét lần lượt nhiều nguồn, **yield từng ScanResult ngay khi xong**.

        Đây là API nền cho streaming result: người dùng thấy kết quả video 1 mà
        không phải chờ video 10. ``scan_many()`` giờ chỉ là ``list(scan_iter(...))``
        nên mọi call site cũ (CLI, Watch, test) giữ nguyên hành vi.

        ``on_video(index, total, ket_qua)`` được gọi ngay sau mỗi video — dùng để
        đẩy Sheets/ghi UI mà không chặn video kế tiếp. Ngoại lệ trong callback được
        nuốt có chủ đích và ghi log: một lỗi ở tầng giao hàng không được phép làm
        hỏng lượt quét đang chạy tốt.

        Cả batch là MỘT job: ghim kho/cấu hình một lần, cờ huỷ xoá đúng một lần lúc bắt
        đầu (``xoa_co_huy=False`` khi người gọi đã tự xoá, ví dụ ``ScanJobController``,
        để một cú bấm Dừng rơi vào khoảng giữa không bị nuốt). Có yêu cầu Dừng thì không
        nhận video mới; kết quả đã xong vẫn được giữ (audit TCP-13).
        """
        nguon = list(nguon)
        tong = len(nguon)
        if xoa_co_huy and not getattr(self, "_la_ban_ghim", False):
            self.cancel_event.clear()
        job = self._ban_sao_cho_job()
        try:
            for i, x in enumerate(nguon, 1):
                if self.cancel_event.is_set():
                    LOGGER_SCAN.info(
                        "event=scan.batch.stopped before_index=%d total=%d", i, tong)
                    break

                def p(pct, msg, i=i):
                    self._bao(progress, (i - 1 + pct) / max(1, tong),
                              f"[{i}/{tong}] {msg}")

                ket_qua = (
                    job.scan_youtube(x, p) if source_type == "youtube"
                    else job.scan_media(x, progress=p)
                )
                if on_video:
                    try:
                        on_video(i, tong, ket_qua)
                    except Exception:  # noqa: BLE001
                        LOGGER_SCAN.exception(
                            "event=scan.on_video_callback_failed index=%d total=%d", i, tong
                        )
                yield ket_qua
        finally:
            self._nhan_ket_qua_job(job)

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
        if not (kq.kho_id or kq.kho_ten or kq.kho_phien_ban):
            # Kết quả dựng tay (công cụ, test): gắn kho đang dùng. Lượt quét thật đã
            # gắn từ đầu lượt nên không đi qua nhánh này.
            self._gan_danh_tinh(kq)
        if not kq.chinh_sach:
            kq.chinh_sach = chu_ky_chinh_sach(self.config)

        def tron(vung):
            return [[round(float(a), 3), round(float(b), 3)] for a, b in vung]

        pham_vi = json.dumps({
            "vung_da_khop": None if kq.vung_da_khop is None else tron(kq.vung_da_khop),
            "vung_loi": tron(kq.vung_loi),
            "ly_do": kq.ly_do_pham_vi,
            "pham_vi_quet_s": round(float(kq.pham_vi_quet_s or 0), 3),
        }, ensure_ascii=False)
        with self._db() as c:
            cur = c.execute(
                "INSERT INTO jobs(created_at, source_type, source_name, source_ref,"
                " duration_s, status, n_matches, note, source_id, kho_id, kho_ten,"
                " kho_phien_ban, chinh_sach, day_du, dat_muc_tieu, pham_vi)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), source_type,
                 kq.source_name, kq.source_ref, kq.duration_s, kq.status,
                 len(kq.matches), kq.note, kq.source_id, kq.kho_id, kq.kho_ten,
                 kq.kho_phien_ban, kq.chinh_sach,
                 1 if (kq.status == "ok" and kq.quet_day_du) else 0,
                 1 if kq.dat_muc_tieu else 0, pham_vi))
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
        """Video đã KIỂM XONG với kho đang dùng — Watch được bỏ qua (audit TCP-07).

        Trước đây truy vấn toàn cục: chỉ cần từng "ok" ở BẤT KỲ kho nào là mọi kho bỏ
        qua video đó, kể cả khi kho kia chưa từng được đối chiếu. Nay, trong cùng
        ``kho_id`` bền:

        * dương tính (status ok, có kết quả): đã thấy vi phạm — vẫn tính, kể cả sau
          khi kho được bổ sung (thấy rồi thì vẫn là thấy; không phải "đã tìm hết");
        * âm tính: chỉ khi đã quét TRỌN video, cùng phiên bản kho và cùng chính sách
          nhận diện. Kho được bổ sung vân tay hay nới ngưỡng thì phải quét lại.

        Lỗi, huỷ, quét dở không chặn lượt quét lại. Lịch sử cũ (``kho_id`` rỗng) không
        chặn kho nào. ``chi_thanh_cong=False``: mọi video đã từng thử với kho này.
        """
        dt = self._danh_tinh_kho()
        if not dt["kho_id"]:
            return set()
        if chi_thanh_cong:
            sql = ("SELECT DISTINCT source_id FROM jobs WHERE source_id IS NOT NULL"
                   " AND source_id != '' AND kho_id = ? AND status = 'ok'"
                   " AND (n_matches > 0 OR (day_du = 1 AND kho_phien_ban != ''"
                   " AND kho_phien_ban = ? AND chinh_sach = ?))")
            tham_so = (dt["kho_id"], dt["kho_phien_ban"], chu_ky_chinh_sach(self.config))
        else:
            sql = ("SELECT DISTINCT source_id FROM jobs WHERE source_id IS NOT NULL"
                   " AND source_id != '' AND kho_id = ?")
            tham_so = (dt["kho_id"],)
        with self._db() as c:
            rows = c.execute(sql, tham_so).fetchall()
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
            # Quét chưa trọn → hậu tố ngay ở cột nguồn (không thêm cột, xem nhan_pham_vi).
            dau = [luc, (kq.source_name or "") + nhan_pham_vi(kq), kq.source_ref]
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
