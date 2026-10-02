# -*- coding: utf-8 -*-
"""Phát hiện của vòng phản biện độc lập sau khi sửa TCP-01…16 (brief §19).

Mỗi test khoá đúng một phát hiện đã được kiểm lại trên code, ghi mã phát hiện ở tên.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine as engine_module
import lich_su
from clip_metadata import extract_youtube_id
from engine import Engine, ScanResult
from kho_gia import ghi_kho
from watch import MucTheoDoi, WatchList, chay_giam_sat

SR = 11025
can_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="cần ffmpeg/ffprobe trong PATH")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _ghi_wav(path, giay: float) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"\x00\x00" * int(giay * SR))


def _eng(tmp_path, chunk_s=100):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.chunk_s = chunk_s
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    e.config.top_n = 1
    e._overlap_thuc_te = lambda *a, **k: 0
    e.db_clips = lambda **k: [{"ten": "goc.opus", "duong_dan": "goc.opus",
                               "so_hash": 20000}]
    return e


def _kq(rc=0):
    return SimpleNamespace(returncode=rc, stdout="", stderr="", cancelled=False,
                           timed_out=False, ly_do="")


def _ffmpeg_cat(tong: float, chunk_s: float, rac=(), bien_doi_loi=False):
    """Cắt khúc giả: WAV thật; khúc trong `rac` ra file KHÔNG phải WAV (>1 KB)."""
    def chay(lenh, **kw):
        if "-af" in lenh:                                   # lượt bù tốc độ
            if bien_doi_loi:
                return _kq(1)
            _ghi_wav(lenh[-1], 100.0)
            return _kq(0)
        bat_dau = int(float(lenh[lenh.index("-ss") + 1]))
        if bat_dau in rac:
            Path(lenh[-1]).write_bytes(b"khong phai wav " * 200)
        else:
            _ghi_wav(lenh[-1], min(chunk_s, tong - bat_dau))
        return _kq(0)
    return chay


def _audfprint_nomatch(loi_doc=()):
    """audfprint giả: mỗi khúc một dòng NOMATCH. Khúc trong `loi_doc` mô phỏng đúng
    audfprint THẬT khi không đọc được file (--continue-on-error): stdout in
    "wavfile2peaks: Error reading <khúc> skipping" rồi opfile ghi "0.0 sec 0 raw hashes".

    (Bản đầu chỉ ghi "0.0 sec" mà không có dòng lỗi — nhưng khúc IM LẶNG cũng ghi y hệt,
    nên test cũ đã khoá nhầm một tiền đề sai; xem test_phan_bien_vong_hai.py, N1.)
    """
    def chay(lenh, on_line=None, **kw):
        ds = [p for p in Path(lenh[lenh.index("--list") + 1])
              .read_text(encoding="utf-8").splitlines() if p]
        with open(lenh[lenh.index("--opfile") + 1], "w", encoding="utf-8") as f:
            for p in ds:
                ten = os.path.basename(p)
                if any(ten.startswith(f"chunk_{x:07d}") for x in loi_doc):
                    if on_line:
                        on_line(f"wavfile2peaks: Error reading {p} skipping")
                    f.write(f"NOMATCH {p} 0.0 sec 0 raw hashes\n")
                else:
                    f.write(f"NOMATCH {p} 100.0 sec 0 raw hashes\n")
        return 0, []
    return chay


# ---------------------------------------------------------------------------
#  R3-1 — khúc audfprint không đọc được KHÔNG được tính là đã khớp
# ---------------------------------------------------------------------------

def test_khuc_audfprint_loi_doc_la_chua_phan_tich(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat(300, 100))
    e._run_stream = _audfprint_nomatch(loi_doc=(100,))
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 200.0)], (kq.status, kq.vung_loi)
    assert not kq.quet_day_du


def test_khuc_wav_khong_doc_duoc_header_la_cat_loi(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat(300, 100, rac=(100,)))
    e._run_stream = _audfprint_nomatch()
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 200.0)], (kq.status, kq.vung_loi)


@pytest.mark.slow
def test_audfprint_that_khuc_hong_sau_khi_cat_khong_thanh_am_tinh(tmp_path):
    """audfprint THẬT với --continue-on-error: khúc hỏng ra `NOMATCH … 0.0 sec`."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("cần ffmpeg trong PATH")
    from conftest import _ghi_wav as ghi, _giai_dieu

    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    e = Engine(root=goc, data_dir=str(tmp_path / "data"), out_dir=str(tmp_path / "out"))
    kho = tmp_path / "kho"
    kho.mkdir()
    ghi(kho / "ref.wav", _giai_dieu(30, seed=71, sr=22050), 22050)
    e.add_kho("A", str(kho))
    e.build_database(str(kho), "new")
    e.config.chunk_s = 200
    e.config.overlap_max_s = 60
    e.config.overlap_s = 60
    e.config.min_hash_floor = 50
    e.config.quet_da_toc_do = False
    video = tmp_path / "video.wav"
    ghi(video, _giai_dieu(300, seed=72, sr=22050), 22050)
    cat_goc = e._cut_chunks

    def cat_roi_lam_hong(*a, **k):
        ds, tong = cat_goc(*a, **k)
        for khuc in ds:
            if os.path.basename(khuc).startswith("chunk_0000140"):
                Path(khuc).write_bytes(b"RIFF" + b"\x00" * 4000)   # hỏng sau khi cắt
        return ds, tong

    e._cut_chunks = cat_roi_lam_hong
    kq = e.scan_media(str(video))

    assert not kq.quet_day_du and kq.vung_loi, (kq.status, kq.vung_da_khop, kq.vung_loi)
    assert kq.status == "error"


# ---------------------------------------------------------------------------
#  R3-2 — âm thanh ngắn hơn hình KHÔNG phải vùng lỗi
# ---------------------------------------------------------------------------

@can_ffmpeg
def test_am_thanh_ngan_hon_hinh_khong_bi_bao_loi(tmp_path):
    media = tmp_path / "video.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=64x64:r=5:d=200",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=190",
                    "-c:v", "mpeg4", "-q:v", "31", "-c:a", "aac", "-b:a", "32k",
                    str(media)], check=True)
    e = _eng(tmp_path)
    e._match_chunks = lambda chunks, *a, **k: []

    kq = e.scan_media(str(media))

    assert kq.status == "ok" and kq.vung_loi == [], (kq.status, kq.vung_loi, kq.note)
    assert kq.quet_day_du


# ---------------------------------------------------------------------------
#  R1-1 / R3-3 — file tải về ngắn hơn video không phải "quét trọn"
# ---------------------------------------------------------------------------

def test_file_tai_ve_ngan_hon_video_khong_phai_quet_tron(tmp_path, monkeypatch):
    """Tải đứt: mỗi lần tải ra một độ dài KHÁC (lần tải lại kiểm chứng ở vòng 2 cũng cụt).

    Bản đầu cho hàm tải giả trả mãi CÙNG một file 300 s — nay đó là đúng dấu hiệu của
    âm thanh YouTube thật sự ngắn hơn (test_phan_bien_vong_hai.py), nên đổi hàm tải giả
    cho giống tải đứt thật; khẳng định giữ nguyên.
    """
    e = _eng(tmp_path)
    os.makedirs(e.dl_dir, exist_ok=True)
    tep = Path(e.dl_dir) / "abcdefghijk.wav"
    e.youtube_info = lambda url: {"title": "Video", "id": "abcdefghijk", "channel": "",
                                  "channel_id": "", "channel_url": "", "upload_date": "",
                                  "duration": 600.0}
    cac_lan = iter([300.0, 420.0])
    hien = {}

    def tai(url, vid, progress=None, gioi_han_giay=None):
        hien["dai"] = next(cac_lan)
        _ghi_wav(tep, hien["dai"])
        return str(tep)

    e.download_audio = tai
    e.duration_of = lambda p: hien["dai"]
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat(300, 100))
    e._match_chunks = lambda chunks, *a, **k: []

    kq = e.scan_youtube("https://youtu.be/abcdefghijk")

    assert kq.duration_s == 600.0 and kq.vung_loi == [(300.0, 600.0)], (kq.duration_s,
                                                                        kq.vung_loi)
    assert kq.status == "error" and not kq.quet_day_du
    assert "abcdefghijk" not in e.ids_da_quet()
    assert not tep.exists(), "file đệm thiếu đuôi phải bị bỏ để lần sau tải lại"


# ---------------------------------------------------------------------------
#  R3-4 — day_du của dòng lỗi
# ---------------------------------------------------------------------------

def test_dong_loi_khong_duoc_ghi_la_quet_tron(tmp_path):
    e = _eng(tmp_path)
    e.save_job(ScanResult(source_name="Lỗi giữa chừng", source_id="vidloi00001",
                          status="error", duration_s=300.0,
                          vung_da_khop=[(0.0, 300.0)]), "youtube")
    assert e.list_jobs()[0]["day_du"] == 0


# ---------------------------------------------------------------------------
#  R1-5 — lượt bù tốc độ chạy lỗi: âm tính chưa chứng minh được
# ---------------------------------------------------------------------------

def test_bu_toc_do_bien_doi_loi_thi_am_tinh_chua_ket_luan(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.config.quet_da_toc_do = True
    e.config.luoi_resample = [1.02]
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media",
                        _ffmpeg_cat(300, 100, bien_doi_loi=True))
    e._run_stream = _audfprint_nomatch()
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "error" and not kq.quet_day_du, (kq.status, kq.vung_loi, kq.note)


def test_bu_toc_do_chay_tron_thi_van_la_am_tinh_tron(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.config.quet_da_toc_do = True
    e.config.luoi_resample = [1.02]
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_cat(300, 100))
    e._run_stream = _audfprint_nomatch()
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")

    kq = e.scan_media(str(media))

    assert kq.status == "ok" and kq.quet_day_du


# ---------------------------------------------------------------------------
#  R1-2 / R1-3 — sổ đăng ký kho và Watch fail-closed
# ---------------------------------------------------------------------------

def _so_dang_ky(tmp_path, danh_sach, dang_dung):
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "khos.json").write_text(json.dumps(
        {"dang_dung": dang_dung, "danh_sach": danh_sach}, ensure_ascii=False),
        encoding="utf-8")
    return data


def test_use_kho_tro_toi_file_van_tay_khong_hop_le_khong_ghi_so(tmp_path):
    data = _so_dang_ky(tmp_path, [
        {"ten": "A", "thu_muc": "", "db": "kho_a.pklz", "id": "a"},
        {"ten": "SML", "thu_muc": "", "db": r"C:\may_khac\kho_sml.pklz", "id": "s"},
    ], "A")
    ghi_kho(data / "kho_a.pklz", [("x.opus", 5)])
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    truoc = _sha(data / "khos.json")

    with pytest.raises(Exception):
        e.use_kho("SML")

    assert _sha(data / "khos.json") == truoc and e.kho_dang_dung == "A"


def _dem_watch(e, monkeypatch):
    dem = {"liet_ke": 0, "quet": 0}

    def lister(url, limit=None):
        dem["liet_ke"] += 1
        return [SimpleNamespace(id="vid00000001", title="V", url="https://youtu.be/x")]

    def quet(url, progress=None):
        dem["quet"] += 1
        return ScanResult(source_name=url)

    monkeypatch.setattr(e, "scan_youtube", quet)
    monkeypatch.setattr(e, "export_csv_ngang", lambda ket: "x.csv")
    return dem, lister


def test_watch_khong_chi_dinh_kho_ma_kho_dang_chon_hong_thi_dung(tmp_path, monkeypatch):
    data = _so_dang_ky(tmp_path, [
        {"ten": "SML", "thu_muc": "", "db": r"C:\may_khac\kho_sml.pklz", "id": "s"},
    ], "SML")
    ghi_kho(data / "db.pklz", [("x.opus", 5)])          # kho mặc định kiểu cũ CÓ tồn tại
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    dem, lister = _dem_watch(e, monkeypatch)

    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")]), lister=lister)

    assert dem == {"liet_ke": 0, "quet": 0}, "không được lặng lẽ quét bằng data/db.pklz"
    assert bc.quet_moi == 0 and any("dừng" in x.lower() for x in bc.loi), bc.loi


def test_watch_kho_chi_dinh_chua_co_van_tay_thi_dung_truoc_khi_liet_ke(tmp_path,
                                                                        monkeypatch):
    _so_dang_ky(tmp_path, [{"ten": "B", "thu_muc": "", "db": "kho_b.pklz", "id": "b"}], "B")
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    dem, lister = _dem_watch(e, monkeypatch)

    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")], kho="B"), lister=lister)

    assert dem == {"liet_ke": 0, "quet": 0}
    assert any("vân tay" in x.lower() for x in bc.loi), bc.loi


# ---------------------------------------------------------------------------
#  R1-4 — định danh bền cho kho tự tạo và gói máy phụ
# ---------------------------------------------------------------------------

def test_kho_mac_dinh_tu_tao_co_id_rieng(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    ghi_kho(data / "db.pklz", [("x.opus", 5)])
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    kho = e._doc_khos()["danh_sach"][0]
    assert kho["ten"] == "Kho mặc định" and len(str(kho.get("id") or "")) == 32


def test_goi_may_phu_mang_id_va_phien_ban_kho(tmp_path):
    import dong_goi_may_chay as dgmc
    goc = tmp_path / "duan"
    (goc / "data").mkdir(parents=True)
    (goc / "data" / "kho_a.pklz").write_bytes(b"x" * 100)
    (goc / "data" / "khos.json").write_text(json.dumps({
        "dang_dung": "A", "danh_sach": [{"ten": "A", "thu_muc": "D:/x", "db": "kho_a.pklz",
                                         "id": "abc123", "revision": "r9"}]}),
        encoding="utf-8")

    khos = json.loads(dgmc.noi_dung_sinh_them(["A"], goc=str(goc))["data/khos.json"])

    assert khos["danh_sach"][0]["id"] == "abc123"
    assert khos["danh_sach"][0]["revision"] == "r9"


# ---------------------------------------------------------------------------
#  R1-6 — không hạ phiên bản lược đồ
# ---------------------------------------------------------------------------

def test_khong_ha_user_version_cua_db_moi_hon(tmp_path):
    db = tmp_path / "lichsu.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE jobs(id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT)")
    c.execute("PRAGMA user_version = 7")
    c.commit()
    c.close()

    lich_su.dam_bao_luoc_do(str(db))

    c = sqlite3.connect(db)
    try:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 7
        assert "kho_id" in [r[1] for r in c.execute("PRAGMA table_info(jobs)")]
    finally:
        c.close()


# ---------------------------------------------------------------------------
#  R1-7 — công cụ chẩn đoán metadata chỉ lấy lịch sử của kho đang xem
# ---------------------------------------------------------------------------

def test_chan_doan_metadata_lay_lich_su_dung_kho(tmp_path):
    import kiem_metadata_kho as kmk
    e = _eng(tmp_path)
    e.add_kho("A", str(tmp_path))
    e.add_kho("B", str(tmp_path))
    e.use_kho("A")
    e.save_job(ScanResult(source_name="A", source_id="vid00000001", duration_s=10.0,
                          vung_da_khop=[(0.0, 10.0)]), "youtube")
    e.use_kho("B")
    e.save_job(ScanResult(source_name="B", source_id="vid00000001", duration_s=10.0,
                          vung_da_khop=[(0.0, 10.0)]), "youtube")
    kho_a = next(k for k in e._doc_khos()["danh_sach"] if k["ten"] == "A")["id"]

    kq = kmk._history_matches(e.sqlite_file, "vid00000001", kho_id=kho_a)

    assert kq["job"]["source_name"] == "A"


# ---------------------------------------------------------------------------
#  R3-6 — ngữ pháp tên file: bản sao do Windows đặt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ten", [
    "20260101 - Tiêu đề [abcdefghijk] (1).opus",
    "20260101 - Tiêu đề [abcdefghijk] - Copy.opus",
    "20260101 - Tiêu đề [abcdefghijk] - Copy (2).opus",
    "20260101 - Tiêu đề [abcdefghijk] - Bản sao.opus",
    "Tiêu đề [abcdefghijk].f251.webm",
    "Tiêu đề [abcdefghijk] .opus",
])
def test_ma_video_doc_duoc_tu_ban_sao_windows(ten):
    assert extract_youtube_id(ten) == "abcdefghijk"


# ---------------------------------------------------------------------------
#  R3-7 — snapshot lệch MÃ VIDEO với nguồn chuẩn vẫn hội tụ; .bak của live là nguồn chuẩn
# ---------------------------------------------------------------------------

def _eng_meta(tmp_path, monkeypatch, ten):
    kho = tmp_path / "Kho"
    data = _so_dang_ky(tmp_path, [{"ten": "SML", "thu_muc": str(kho), "db": "kho.pklz"}],
                       "SML")
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    monkeypatch.setattr(e, "db_clips", lambda bo_cache=False: [
        {"ten": ten, "duong_dan": str(kho / ten)}])
    Path(e.db_file).write_bytes(b"marker")
    return e, kho


def _meta(vid, title="T", **them):
    return {"id": vid, "title": title, "url": f"https://youtu.be/{vid}",
            "upload_date": "20260101", "duration": 60.0, **them}


def test_snapshot_lech_ma_video_voi_nguon_chuan_thi_hoi_tu(tmp_path, monkeypatch):
    ten = "Clip không mang mã.opus"
    e, kho = _eng_meta(tmp_path, monkeypatch, ten)
    kho.mkdir()
    (kho / "clips_meta.json").write_text(json.dumps({ten: _meta("BBBBBBBBBBB")}),
                                         encoding="utf-8")
    e.khoi_phuc_metadata_offline(dry_run=False)               # snapshot giữ mã B
    (kho / "clips_meta.json").write_text(json.dumps({ten: _meta("AAAAAAAAAAA")}),
                                         encoding="utf-8")   # người dùng sửa đúng mã

    r = e.clip_metadata_resolver().resolve(ten)
    assert r.status == "complete" and r.video_id == "AAAAAAAAAAA", r.warnings
    assert any("lệch" in w for w in e.canh_bao_metadata), e.canh_bao_metadata

    e.khoi_phuc_metadata_offline(dry_run=False)
    snap = json.loads(Path(e._metadata_snapshot_path()).read_text(encoding="utf-8"))
    assert snap["clips"][ten]["id"] == "AAAAAAAAAAA"


def test_ban_sao_bak_cua_nguon_chuan_khac_snapshot_la_lech_khong_phai_xung_dot(
        tmp_path, monkeypatch):
    ten = "20260101 - Clip [AAAAAAAAAAA].opus"
    e, kho = _eng_meta(tmp_path, monkeypatch, ten)
    kho.mkdir()
    (kho / "clips_meta.json").write_text(json.dumps({ten: _meta("AAAAAAAAAAA", "Cũ")}),
                                         encoding="utf-8")
    e.khoi_phuc_metadata_offline(dry_run=False)
    (kho / "clips_meta.json.bak").write_text(
        json.dumps({ten: _meta("AAAAAAAAAAA", "Mới")}), encoding="utf-8")
    (kho / "clips_meta.json").write_text("{hỏng", encoding="utf-8")

    r = e.clip_metadata_resolver().resolve(ten)

    assert r.title == "Mới"
    assert any("lệch" in w for w in e.canh_bao_metadata)
    assert not any("xung đột" in w for w in e.canh_bao_metadata), e.canh_bao_metadata
