# -*- coding: utf-8 -*-
"""Bộ ghi «golden master» cho đường quét CŨ (chế độ «mỗi video tự chọn kết quả»).

Vì sao có file này: chế độ «một video gốc chung cho cả lô» phải chen vào đúng những điểm
engine quyết định dừng sớm / tải tiếp / bù tốc độ. Hành vi cũ ở các điểm đó phải giữ
NGUYÊN. Bộ test cũ không đủ để chứng minh điều này — nhiều test thay luôn `_quet_tho`,
`_merge` hay `scan_media` bằng hàm giả nên không chạm tới các nhánh quyết định thật.

Ở đây chỉ giả ở RANH GIỚI TIẾN TRÌNH:
* FFmpeg/FFprobe — `engine.chay_lenh_media` (cắt khúc ghi WAV nhỏ, đo thời lượng);
* audfprint — `Engine._run_stream` (đọc `--list`, ghi `--opfile` đúng định dạng thật);
* yt-dlp — `Engine.youtube_info`, `Engine.download_audio`;
* kho — `Engine.db_clips` (tổng hash từng clip), `Engine.clip_meta` (rỗng).
Phần còn lại chạy THẬT: lưới khúc, parser audfprint, sổ phạm vi, `_merge`, chấp nhận,
chọn lọc, dừng sớm, bù tốc độ, xử lý file tải thiếu, lịch sử SQLite.

Mỗi kịch bản ghi lại: các lần tải (và giới hạn tải một phần), các mốc cắt khúc, từng lần
gọi audfprint (hậu tố + danh sách khúc), các lần đổi tốc độ khúc, thông điệp tiến độ,
`ScanResult` đã chuẩn hoá, chẩn đoán và dòng lịch sử.

Dữ liệu golden sinh trên commit f87cc85 (TRƯỚC khi thêm chế độ mới) — đặt biến môi trường
``TIMCLIP_GHI_GOLDEN=1`` rồi chạy ``tests/test_golden_quet_cu.py``.
"""

from __future__ import annotations

import json
import math
import os
import re
import wave
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional

import engine as engine_module
from engine import Cancelled, Engine
from toc_do_khop import giai_ma_he_so

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
BIEN_GHI_GOLDEN = "TIMCLIP_GHI_GOLDEN"

RE_KHUC = re.compile(r"chunk_(\d+)(?:_k(\d+))?\.wav$")

# Kho giả: tổng số hash của từng clip gốc (dùng cho cận trên khi gộp và cho ty_le).
KHO_MAC_DINH = {
    "A [aaaaaaaaaaa].opus": 20000,
    "B [bbbbbbbbbbb].opus": 30000,
    "C [ccccccccccc].opus": 25000,
    "D [ddddddddddd].opus": 25000,
    "E [eeeeeeeeeee].opus": 25000,
    "F [fffffffffff].opus": 25000,
}

# Cấu hình thu nhỏ trục thời gian để mỗi kịch bản chạy trong mili giây mà vẫn đi đúng các
# nhánh của video nhiều giờ: khúc 200 s, gối 60 s (bước 140 s); quét tăng dần từ 900 s,
# mỗi đoạn 720 s; tải một phần 720 s đầu.
CAU_HINH_GOC = {
    "chunk_s": 200,
    "overlap_s": 60,
    "overlap_max_s": 60,
    "quet_tang_dan_tu_gio": 0.25,
    "quet_tang_dan_buoc_gio": 0.2,
    "ncores": 1,
}


@dataclass(frozen=True)
class Dat:
    """Một lần clip gốc xuất hiện trong video: [bat_dau, bat_dau + dai) theo giây video."""
    clip: str
    bat_dau: float
    dai: float
    mat_do: float = 20.0      # hash khớp trên mỗi giây
    toc_do: float = 1.0       # video phát nhanh gấp toc_do lần bản gốc
    troi: bool = False        # có để lại mảnh khớp yếu trôi theo độ lệch tốc độ không


@dataclass
class KichBan:
    ten: str
    nguon: str = "file"                 # "file" | "youtube"
    tong_s: float = 600.0               # thời lượng THẬT của video
    cau_hinh: dict = field(default_factory=dict)
    dat: tuple = ()
    loi_cat: frozenset = frozenset()          # mốc khúc cắt lỗi (mọi lần thử)
    khong_phan_tich: frozenset = frozenset()  # mốc khúc audfprint không báo gì
    loi_bien_doi: frozenset = frozenset()     # mốc khúc đổi tốc độ lỗi
    tai: tuple = ()                     # độ dài từng lần tải TRỌN (mặc định = tong_s)
    huy_khi_tai_lan: int = 0            # huỷ trong lần gọi download_audio thứ n (1-based)
    kho_doi_sau_lan_khop: int = 0       # ghi lại file kho sau lần gọi audfprint thứ n
    loi_audfprint_lan: int = 0          # lần gọi audfprint thứ n trả mã lỗi
    ten_file: str = "video_vi_pham.mp4"
    kho: dict = field(default_factory=lambda: dict(KHO_MAC_DINH))


def _ghi_wav(path: str, giay: float) -> None:
    """WAV im lặng có header đúng độ dài, tần số mẫu thấp để file nhỏ.

    `_cut_chunks` coi khúc < 1 KB là cắt lỗi, nên khúc ngắn dùng tần số cao hơn.
    """
    giay = max(0.0, float(giay))
    tan_so = 8 if giay >= 70 else max(8, math.ceil(600 / max(giay, 0.5)))
    so_khung = int(round(giay * tan_so))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tan_so)
        w.writeframes(b"\x00\x00" * so_khung)


def _kq_lenh(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr,
                           cancelled=False, timed_out=False, ly_do="")


def _so(x, chu_so: int = 3):
    return None if x is None else round(float(x), chu_so)


def _khoang(ds) -> Optional[list]:
    if ds is None:
        return None
    return [[_so(a), _so(b)] for a, b in ds]


def _match(m) -> dict:
    return {
        "clip": m.clip, "start_s": _so(m.start_s), "end_s": _so(m.end_s),
        "matched_s": _so(m.matched_s), "clip_offset_s": _so(m.clip_offset_s),
        "hashes": int(m.hashes), "confidence": m.confidence, "ty_le": _so(m.ty_le),
        "vung": m.vung, "clip_bat_dau_s": _so(m.clip_bat_dau_s),
        "vung_khop_s": _so(m.vung_khop_s),
    }


class MoiTruongGia:
    """Toàn bộ thế giới bên ngoài engine cho MỘT kịch bản, kèm nhật ký lời gọi."""

    def __init__(self, kb: KichBan, eng: Engine, goc_tmp: str):
        self.kb = kb
        self.eng = eng
        self.goc_tmp = goc_tmp
        self.nhat_ky: list = []
        self.thoi_luong: dict = {}       # đường dẫn chuẩn hoá -> thời lượng file
        self.so_lan_tai_tron = 0
        self.so_lan_goi_tai = 0
        self.so_lan_khop = 0

    # ---------- tiện ích ----------
    @staticmethod
    def _khoa(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _rut_gon(self, text: str) -> str:
        """Bỏ đường dẫn tạm (đổi theo lần chạy) khỏi chuỗi để so sánh được."""
        if not isinstance(text, str):
            return text
        for goc in {self.goc_tmp, self.goc_tmp.replace("\\", "/"),
                    os.path.normcase(self.goc_tmp)}:
            text = text.replace(goc, "<TMP>")
        return text

    # ---------- FFmpeg / FFprobe ----------
    def chay_lenh_media(self, lenh, **_kw):
        lenh = [str(x) for x in lenh]
        if lenh[0] == "ffprobe":
            path = lenh[-1]
            if "format=duration" in lenh:
                dai = self.thoi_luong.get(self._khoa(path))
                return _kq_lenh(stdout="" if dai is None else f"{dai}\n")
            return _kq_lenh(stdout="")          # luồng tiếng: không biết -> None
        if "-af" in lenh:                         # đổi tốc độ một khúc đã cắt
            vao, ra = lenh[lenh.index("-i") + 1], lenh[-1]
            mk = RE_KHUC.search(os.path.basename(vao))
            moc = int(mk.group(1)) if mk else -1
            self.nhat_ky.append(["bien_doi", os.path.basename(ra)])
            if moc in self.kb.loi_bien_doi:
                return _kq_lenh(returncode=1, stderr="lỗi đổi tốc độ giả")
            with open(vao, "rb") as f, open(ra, "wb") as g:
                g.write(f.read())
            return _kq_lenh()
        if "-ss" in lenh:                         # cắt khúc
            moc = int(float(lenh[lenh.index("-ss") + 1]))
            vao = lenh[lenh.index("-i") + 1]
            self.nhat_ky.append(["cat", moc])
            if moc in self.kb.loi_cat:
                return _kq_lenh(returncode=1, stderr="lỗi giải mã giả")
            tong = float(self.thoi_luong.get(self._khoa(vao), 0.0))
            dai = min(float(self.eng.config.chunk_s), tong - moc)
            _ghi_wav(lenh[-1], dai)
            return _kq_lenh()
        raise AssertionError(f"Lệnh media lạ trong kịch bản: {lenh[:4]}")

    # ---------- audfprint ----------
    def _dong_cua_khuc(self, path: str) -> list:
        ten = os.path.basename(path)
        mk = RE_KHUC.search(ten)
        if not mk:
            return []
        moc = float(int(mk.group(1)))
        he_so = giai_ma_he_so(mk.group(2))
        bien_doi = mk.group(2) is not None
        # Độ dài khúc đọc từ chính file WAV (header do FFmpeg giả ghi) — khúc đổi tốc độ là
        # bản sao của khúc gốc nên cùng độ dài trên trục khúc gốc.
        dai_khuc = float(engine_module.do_dai_wav(path) or 0.0)
        dong = []
        for d in self.kb.dat:
            a, b = max(d.bat_dau, moc), min(d.bat_dau + d.dai, moc + dai_khuc)
            if b - a < 1.0:
                continue
            binh_thuong = abs(d.toc_do - 1.0) < 1e-9
            if binh_thuong and bien_doi:
                continue
            if not binh_thuong and bien_doi and abs(he_so * d.toc_do - 1.0) > 0.003:
                continue
            if not binh_thuong and not bien_doi:
                if not d.troi:
                    continue
                # Mảnh yếu, trôi theo độ lệch tốc độ: đủ để ước lượng, không đủ để nhận.
                v = a
                while v + 5.0 <= b:
                    t_clip = (v - d.bat_dau) * d.toc_do
                    dong.append(
                        f"Matched 5.0 s starting at {v - moc:.1f} s in {path} to time "
                        f"{t_clip:.1f} s in D:/Kho/{d.clip} with 20 of 40 common hashes "
                        "at rank 0")
                    v += 30.0
                continue
            so_hash = int(round(d.mat_do * (b - a)))
            t_khuc = (a - moc) / he_so
            khop = (b - a) / he_so
            t_clip = (a - d.bat_dau) * (d.toc_do if bien_doi else 1.0)
            dong.append(
                f"Matched {khop:.1f} s starting at {t_khuc:.1f} s in {path} to time "
                f"{t_clip:.1f} s in D:/Kho/{d.clip} with {so_hash} of {2 * so_hash} "
                "common hashes at rank 0")
        return dong

    def run_stream(self, lenh, on_line=None, **_kw):
        lenh = [str(x) for x in lenh]
        self.so_lan_khop += 1
        listfile = lenh[lenh.index("--list") + 1]
        opfile = lenh[lenh.index("--opfile") + 1]
        with open(listfile, encoding="utf-8") as f:
            khuc = [x for x in f.read().split("\n") if x]
        hau_to = os.path.basename(opfile)[len("_raw_match"):-len(".txt")]
        self.nhat_ky.append(["khop", hau_to, [os.path.basename(k) for k in khuc]])
        if self.kb.loi_audfprint_lan == self.so_lan_khop:
            return 1, ["Traceback giả", "lỗi audfprint giả"]
        if self.kb.kho_doi_sau_lan_khop == self.so_lan_khop:
            with open(self.eng.db_file, "ab") as f:
                f.write(b"kho-moi")
        ra = []
        for i, k in enumerate(khuc, 1):
            mk = RE_KHUC.search(os.path.basename(k))
            moc = int(mk.group(1)) if mk else -1
            if mk and mk.group(2) is None and moc in self.kb.khong_phan_tich:
                continue
            if on_line:
                on_line(f"Analyzed #{i} {k}")
            dong = self._dong_cua_khuc(k)
            ra.extend(dong or [f"NOMATCH {k} 99.9 sec 812 raw hashes"])
        with open(opfile, "w", encoding="utf-8") as f:
            f.write("\n".join(ra) + ("\n" if ra else ""))
        return 0, []

    # ---------- yt-dlp ----------
    def youtube_info(self, url):
        self.nhat_ky.append(["info", url])
        return {
            "id": "vidvipham01", "title": "Video vi phạm thử", "duration": self.kb.tong_s,
            "uploader": "Kênh thử", "channel": "Kênh thử", "channel_id": "UCthu",
            "channel_url": "https://www.youtube.com/channel/UCthu",
            "upload_date": "20260101", "upload_date_raw": "20260101",
            "publication_date_source": "upload_date", "publication_date_confidence": "cao",
        }

    def download_audio(self, url, video_id, progress=None, gioi_han_giay=None):
        self.so_lan_goi_tai += 1
        self.nhat_ky.append(["tai", None if gioi_han_giay is None else _so(gioi_han_giay)])
        if self.kb.huy_khi_tai_lan == self.so_lan_goi_tai:
            self.eng.cancel_event.set()
            raise Cancelled()
        if gioi_han_giay:
            path = os.path.join(self.eng.dl_dir, f"{video_id}__p{int(gioi_han_giay)}.m4a")
            dai = min(float(gioi_han_giay), float(self.kb.tong_s))
        else:
            path = os.path.join(self.eng.dl_dir, f"{video_id}.m4a")
            if os.path.exists(path):
                self.nhat_ky.append(["tai_tu_dem"])
                return path
            self.so_lan_tai_tron += 1
            ds = list(self.kb.tai) or [self.kb.tong_s]
            dai = float(ds[min(self.so_lan_tai_tron, len(ds)) - 1])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x")
        self.thoi_luong[self._khoa(path)] = dai
        return path

    # ---------- lắp vào engine ----------
    def lap(self, monkeypatch) -> None:
        e = self.eng
        e.require = lambda *a, **k: None
        e.clip_meta = lambda: {}
        e.db_clips = lambda bo_cache=False: [
            {"ten": ten, "duong_dan": f"D:/Kho/{ten}", "so_hash": so}
            for ten, so in self.kb.kho.items()]
        e.youtube_info = self.youtube_info
        e.download_audio = self.download_audio
        e._run_stream = self.run_stream
        # Chỉ thay hàm I/O. KHÔNG bọc phương thức của engine trên instance: lượt quét chạy
        # trên BẢN SAO đã ghim (`_ban_sao_cho_job`), hàm bọc giữ tham chiếu engine gốc sẽ
        # ghi sổ phạm vi nhầm chỗ.
        monkeypatch.setattr(engine_module, "chay_lenh_media", self.chay_lenh_media)


def tao_engine(kb: KichBan, tmp_path) -> Engine:
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    for khoa, gia_tri in {**CAU_HINH_GOC, **kb.cau_hinh}.items():
        setattr(e.config, khoa, gia_tri)
    return e


def chuan_hoa_ket_qua(kq, rut_gon) -> dict:
    cd = kq.chan_doan.thanh_dict() if kq.chan_doan is not None else None
    if cd is not None:
        cd = json.loads(json.dumps(cd, ensure_ascii=False, default=str))
        cd = _lam_tron(cd)
    return {
        "source_name": kq.source_name, "source_ref": rut_gon(kq.source_ref),
        "source_id": kq.source_id, "duration_s": _so(kq.duration_s),
        "status": kq.status, "note": rut_gon(kq.note),
        "matches": [_match(m) for m in kq.matches],
        "matches_loai": [_match(m) for m in kq.matches_loai],
        "so_dat_nguong": kq.so_dat_nguong, "pham_vi_quet_s": _so(kq.pham_vi_quet_s),
        "vung_da_khop": _khoang(kq.vung_da_khop), "vung_loi": _khoang(kq.vung_loi),
        "ly_do_pham_vi": kq.ly_do_pham_vi, "dat_muc_tieu": kq.dat_muc_tieu,
        "quet_day_du": kq.quet_day_du, "quet_mot_phan": kq.quet_mot_phan,
        "kho_id": kq.kho_id, "kho_ten": kq.kho_ten, "kho_phien_ban": kq.kho_phien_ban,
        "chinh_sach": kq.chinh_sach, "channel_name": kq.channel_name,
        "channel_id": kq.channel_id, "channel_url": kq.channel_url,
        "upload_date": kq.upload_date, "job_id": kq.job_id, "chan_doan": cd,
    }


def _lam_tron(x):
    if isinstance(x, float):
        return round(x, 3)
    if isinstance(x, list):
        return [_lam_tron(y) for y in x]
    if isinstance(x, dict):
        return {k: _lam_tron(v) for k, v in x.items()}
    return x


def chay(kb: KichBan, tmp_path, monkeypatch, muc_tieu=None, luu_lich_su=True,
         info=None) -> tuple:
    """Chạy một kịch bản trên engine THẬT với thế giới giả.

    Trả ``(ScanResult, engine, môi trường giả, thông điệp tiến độ)``. ``muc_tieu``/``info``
    chỉ được truyền khi khác ``None`` — lời gọi kiểu cũ giữ y nguyên.
    """
    e = tao_engine(kb, tmp_path)
    mt = MoiTruongGia(kb, e, str(tmp_path))
    mt.lap(monkeypatch)
    tien_do: list = []

    def progress(pct, msg):
        tien_do.append([_so(pct), mt._rut_gon(msg)])

    them = {}
    if muc_tieu is not None:
        them["muc_tieu"] = muc_tieu
    if kb.nguon == "youtube":
        if info is not None:
            them["info"] = info
        kq = e.scan_youtube("https://youtu.be/vidvipham01", progress=progress,
                            luu_lich_su=luu_lich_su, **them)
    else:
        media = tmp_path / kb.ten_file
        media.write_bytes(b"x")
        mt.thoi_luong[mt._khoa(str(media))] = float(kb.tong_s)
        kq = e.scan_media(str(media), progress=progress, luu_lich_su=luu_lich_su, **them)
    return kq, e, mt, tien_do


def chay_kich_ban(kb: KichBan, tmp_path, monkeypatch) -> dict:
    """Chạy một kịch bản kiểu CŨ; trả bản ghi để so golden."""
    kq, e, mt, tien_do = chay(kb, tmp_path, monkeypatch)
    with e._db() as c:
        jobs = [dict(r) for r in c.execute("SELECT * FROM jobs ORDER BY id").fetchall()]
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM matches ORDER BY job_id, id").fetchall()]
    for j in jobs:
        j.pop("created_at", None)
        j["note"] = mt._rut_gon(j.get("note"))
        j["source_ref"] = mt._rut_gon(j.get("source_ref"))
    return _lam_tron({
        "nhat_ky": mt.nhat_ky,
        "tien_do": tien_do,
        "ket_qua": chuan_hoa_ket_qua(kq, mt._rut_gon),
        "lich_su": {"jobs": jobs, "matches": rows},
    })


# =====================================================================
#  Ma trận kịch bản — phủ HAI nhánh của mọi điểm quyết định cũ
# =====================================================================

_B = "B [bbbbbbbbbbb].opus"
_C = "C [ccccccccccc].opus"
_D = "D [ddddddddddd].opus"
_E = "E [eeeeeeeeeee].opus"
_F = "F [fffffffffff].opus"
_A = "A [aaaaaaaaaaa].opus"

KICH_BAN = [
    # --- YouTube, video "dài" (3000 s > ngưỡng quét tăng dần 900 s) ---
    KichBan("yt_dai_top1_thay_trong_phan_tai_dau", "youtube", 3000,
            {"top_n": 1}, (Dat(_B, 100, 300),)),
    KichBan("yt_dai_top1_thay_muon_phai_tai_not", "youtube", 3000,
            {"top_n": 1}, (Dat(_B, 2300, 300),)),
    KichBan("yt_dai_top5_can_5_clip_khac_nhau", "youtube", 3000,
            {"top_n": 5, "quet_da_toc_do": False},
            (Dat(_B, 100, 100), Dat(_C, 300, 100), Dat(_D, 500, 100),
             Dat(_E, 1000, 100), Dat(_F, 1800, 100))),
    KichBan("yt_top5_nam_doan_ba_clip_trong_phan_tai_dau", "youtube", 3000,
            {"top_n": 5, "quet_da_toc_do": False},
            (Dat(_B, 10, 80), Dat(_B, 300, 80), Dat(_C, 150, 80), Dat(_C, 450, 80),
             Dat(_D, 600, 80))),
    KichBan("yt_top5_khong_uu_tien_khac_nhau", "youtube", 3000,
            {"top_n": 5, "uu_tien_clip_khac_nhau": False, "quet_da_toc_do": False},
            (Dat(_B, 10, 80), Dat(_B, 300, 80), Dat(_C, 150, 80), Dat(_C, 450, 80),
             Dat(_D, 600, 80))),
    KichBan("yt_tai_mot_phan_tat", "youtube", 3000,
            {"top_n": 1, "tai_mot_phan": False, "quet_da_toc_do": False},
            (Dat(_B, 2300, 300),)),
    KichBan("yt_quet_tang_dan_tat", "youtube", 3000,
            {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
            (Dat(_B, 2300, 300),)),
    KichBan("yt_file_ngan_khong_bang_chung_tai_lai_van_ngan", "youtube", 3000,
            {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
            (), tai=(2500, 2500)),
    KichBan("yt_file_ngan_co_bang_chung", "youtube", 3000,
            {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
            (Dat(_B, 100, 300),), tai=(2500, 2500)),
    KichBan("yt_file_ngan_tai_lai_du", "youtube", 3000,
            {"top_n": 1, "quet_tang_dan": False, "quet_da_toc_do": False},
            (Dat(_B, 2800, 150),), tai=(2500, 3000)),
    KichBan("yt_huy_khi_tai_lan_hai", "youtube", 3000,
            {"top_n": 1, "quet_da_toc_do": False}, (Dat(_B, 2300, 300),),
            huy_khi_tai_lan=2),
    KichBan("yt_khong_giu_dem", "youtube", 3000,
            {"top_n": 1, "keep_downloads": False, "quet_da_toc_do": False},
            (Dat(_B, 2300, 300),)),
    # --- File trên máy ---
    KichBan("file_ngan_top1_khuc_dau_manh", "file", 600, {"top_n": 1},
            (Dat(_B, 10, 180, mat_do=30.0),)),
    KichBan("file_ngan_top1_khuc_dau_yeu", "file", 600, {"top_n": 1},
            (Dat(_B, 10, 60),)),
    KichBan("file_ngan_top5", "file", 600, {"top_n": 5},
            (Dat(_B, 10, 180, mat_do=30.0), Dat(_C, 350, 100))),
    KichBan("file_bu_toc_do_theo_do_troi", "file", 600, {"top_n": 1},
            (Dat(_A, 50, 400, toc_do=1.03, troi=True),)),
    KichBan("file_bu_toc_do_theo_luoi", "file", 600, {"top_n": 1},
            (Dat(_A, 50, 400, toc_do=1.02),)),
    KichBan("file_bu_toc_do_luoi_rong", "file", 600,
            {"top_n": 1, "luoi_resample": [], "luoi_tempo": []},
            (Dat(_A, 50, 400, toc_do=1.02),)),
    KichBan("file_bu_toc_do_bien_doi_hong", "file", 600, {"top_n": 1},
            (Dat(_A, 50, 400, toc_do=1.5),), loi_bien_doi=frozenset({140})),
    KichBan("file_B_dat_chuan_canh_A_doi_toc_do", "file", 600, {"top_n": 1},
            (Dat(_B, 10, 60), Dat(_A, 300, 250, toc_do=1.02, troi=True))),
    KichBan("file_khuc_loi_khong_bang_chung", "file", 600,
            {"top_n": 1, "quet_da_toc_do": False}, (), loi_cat=frozenset({140})),
    KichBan("file_khuc_loi_co_bang_chung", "file", 600,
            {"top_n": 1, "quet_da_toc_do": False}, (Dat(_B, 10, 60),),
            loi_cat=frozenset({280})),
    KichBan("file_khuc_khong_duoc_phan_tich", "file", 600,
            {"top_n": 1, "quet_da_toc_do": False}, (),
            khong_phan_tich=frozenset({140})),
    KichBan("file_kho_doi_giua_luot", "file", 3000,
            {"top_n": 1, "quet_da_toc_do": False}, (Dat(_B, 2300, 300),),
            kho_doi_sau_lan_khop=1),
    KichBan("file_tu_khop_chinh_no", "file", 600, {"top_n": 1},
            (Dat(_B, 10, 180),), ten_file=_B),
    KichBan("file_dai_khong_thay_gi_quet_het", "file", 3000,
            {"top_n": 1, "quet_da_toc_do": False}, ()),
    # Đoạn đầu có 5 đoạn khớp nhưng chỉ 3 clip: luật dừng giữa các đoạn đếm clip KHÁC
    # NHAU nên phải quét tiếp tới khi đủ 5 clip (đoạn 3).
    KichBan("file_dai_top5_nam_doan_ba_clip_doan_dau", "file", 3000,
            {"top_n": 5, "quet_da_toc_do": False},
            (Dat(_B, 10, 80), Dat(_B, 300, 80), Dat(_C, 150, 80), Dat(_C, 450, 80),
             Dat(_D, 600, 80), Dat(_E, 1000, 80), Dat(_F, 1800, 80))),
    KichBan("file_loi_audfprint", "file", 600, {"top_n": 1}, (Dat(_B, 10, 60),),
            loi_audfprint_lan=1),
]
