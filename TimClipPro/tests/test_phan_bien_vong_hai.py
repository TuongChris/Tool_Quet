# -*- coding: utf-8 -*-
"""Phát hiện của lượt KIỂM LẠI (vòng phản biện thứ hai) sau các bản sửa ở
``test_phan_bien_doc_lap.py``. Mỗi test khoá đúng một phát hiện, mã ở tên/ghi chú.
"""

from __future__ import annotations

import os
import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import engine as engine_module
from engine import Engine

SR = 11025


def _ghi_wav(path, giay: float) -> None:
    """WAV im lặng tuyệt đối (mọi mẫu bằng 0) — đọc được, không có vân tay."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"\x00\x00" * int(giay * SR))


def _eng(tmp_path, chunk_s=100, overlap=0):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.chunk_s = chunk_s
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    e.config.top_n = 1
    e._overlap_thuc_te = lambda *a, **k: overlap
    e.db_clips = lambda **k: [{"ten": "goc.opus", "duong_dan": "goc.opus",
                               "so_hash": 20000}]
    return e


def _kq(rc=0):
    return SimpleNamespace(returncode=rc, stdout="", stderr="", cancelled=False,
                           timed_out=False, ly_do="")


def _ffmpeg_gia(tong: float, chunk_s: float, bien_doi_loi=()):
    """Cắt khúc giả ra WAV thật; lượt bù tốc độ hỏng ở các TÊN khúc trong `bien_doi_loi`."""
    def chay(lenh, **kw):
        out = lenh[-1]
        if "-af" in lenh:                                   # lượt bù tốc độ
            if os.path.basename(out) in bien_doi_loi:
                return _kq(1)
            _ghi_wav(out, chunk_s)
            return _kq(0)
        bat_dau = int(float(lenh[lenh.index("-ss") + 1]))
        _ghi_wav(out, min(chunk_s, tong - bat_dau))
        return _kq(0)
    return chay


def _audfprint_gia(loi_doc=(), im_lang=()):
    """audfprint giả, đúng hành vi của bản THẬT (audfprint_analyze.wavfile2peaks):

    * khúc không đọc được → stdout "wavfile2peaks: Error reading <khúc> skipping" RỒI
      vẫn ghi dòng ``NOMATCH <khúc> 0.0 sec 0 raw hashes`` vào opfile;
    * khúc đọc được nhưng KHÔNG có vân tay (im lặng) → cũng ``NOMATCH … 0.0 sec`` vì
      audfprint lấy "độ dài" từ mốc hash cuối — nhưng KHÔNG có dòng lỗi nào.
    """
    def thuoc(ten, ds):
        return any(ten.startswith(f"chunk_{x:07d}") for x in ds)

    def chay(lenh, on_line=None, **kw):
        ds = [p for p in Path(lenh[lenh.index("--list") + 1])
              .read_text(encoding="utf-8").splitlines() if p]
        with open(lenh[lenh.index("--opfile") + 1], "w", encoding="utf-8") as f:
            for p in ds:
                ten = os.path.basename(p)
                if thuoc(ten, loi_doc):
                    if on_line:
                        on_line(f"wavfile2peaks: Error reading {p} skipping")
                    f.write(f"NOMATCH {p} 0.0 sec 0 raw hashes\n")
                elif thuoc(ten, im_lang):
                    f.write(f"NOMATCH {p} 0.0 sec 0 raw hashes\n")
                else:
                    f.write(f"NOMATCH {p} 99.9 sec 812 raw hashes\n")
        return 0, []
    return chay


def _media(tmp_path):
    media = tmp_path / "q.mp4"
    media.write_bytes(b"x")
    return str(media)


# ---------------------------------------------------------------------------
#  V2-N1 — khúc IM LẶNG không phải lỗi đọc (hồi quy do chính bản sửa R3-1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bu_toc_do", [False, True])
def test_khuc_im_lang_la_da_phan_tich_khong_phai_loi(tmp_path, monkeypatch, bu_toc_do):
    """Video bị tắt tiếng (một phần) là ÂM TÍNH THẬT: không được thành lỗi vĩnh viễn."""
    e = _eng(tmp_path)
    e.config.quet_da_toc_do = bu_toc_do
    e.config.luoi_tempo = []
    e.config.luoi_resample = [0.98, 1.02]
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100))
    e._run_stream = _audfprint_gia(im_lang=(200,))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "ok", (kq.status, kq.vung_loi, kq.note)
    assert kq.vung_loi == [] and kq.quet_day_du
    assert e.list_jobs()[0]["day_du"] == 1


def test_khuc_audfprint_bao_loi_doc_la_chua_phan_tich(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100))
    e._run_stream = _audfprint_gia(loi_doc=(100,))

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 200.0)], (kq.status, kq.vung_loi)
    assert not kq.quet_day_du


def test_khuc_hong_truoc_khi_khop_bi_bat_ca_khi_mat_dong_loi_stdout(tmp_path, monkeypatch):
    """Lớp phòng thủ thứ hai: dòng lỗi stdout lạc mất nhưng khúc 0 hash KHÔNG đọc được
    bằng bộ đọc WAV của chính tool → vẫn là chưa phân tích, không thành âm tính."""
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(300, 100))
    gia = _audfprint_gia(im_lang=(100,))         # 0.0 sec, KHÔNG có dòng lỗi

    def hong_roi_khop(lenh, on_line=None, **kw):
        for p in Path(lenh[lenh.index("--list") + 1]).read_text(
                encoding="utf-8").splitlines():
            if os.path.basename(p) == "chunk_0000100.wav":
                Path(p).write_bytes(os.urandom(64000))      # hỏng sau khi cắt
        return gia(lenh, on_line=on_line, **kw)

    e._run_stream = hong_roi_khop

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "error" and kq.vung_loi == [(100.0, 200.0)], (kq.status, kq.vung_loi)


# ---------------------------------------------------------------------------
#  V2-N2 — lượt bù tốc độ: tính THEO TỪNG LƯỢT và trừ phần khúc gối đã phủ
# ---------------------------------------------------------------------------

def test_bu_toc_do_hong_o_mot_he_so_khong_bi_he_so_khac_che_mat(tmp_path, monkeypatch):
    """Hệ số 1/0.98 hỏng ở khúc 100, hệ số 1/1.02 chạy được: khúc 100 vẫn CHƯA được
    kiểm ở hệ số 1/0.98 → âm tính chưa chứng minh được theo chính sách đang bật."""
    e = _eng(tmp_path)
    e.config.quet_da_toc_do = True
    e.config.luoi_tempo = []
    e.config.luoi_resample = [0.98, 1.02]
    e.config.toc_do_toi_da_thu = 4
    e.duration_of = lambda p: 300.0
    ma = engine_module.ma_he_so(1.0 / 0.98)
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(
        300, 100, bien_doi_loi=(f"chunk_0000100_k{ma}.wav",)))
    e._run_stream = _audfprint_gia()

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "error" and not kq.quet_day_du, (kq.status, kq.vung_loi, kq.note)
    assert kq.vung_loi == [(100.0, 200.0)]


def test_bu_toc_do_hong_o_khuc_da_duoc_khuc_goi_phu_thi_van_tron(tmp_path, monkeypatch):
    """Khúc đuôi [250, 300) nằm trọn trong khúc gối [200, 300) của CÙNG lượt: lượt đó
    vẫn đã kiểm toàn bộ vùng — không phải lỗi."""
    e = _eng(tmp_path, chunk_s=100, overlap=50)
    e.config.quet_da_toc_do = True
    e.config.luoi_tempo = []
    e.config.luoi_resample = [1.02]
    e.duration_of = lambda p: 300.0
    ma = engine_module.ma_he_so(1.0 / 1.02)
    monkeypatch.setattr(engine_module, "chay_lenh_media", _ffmpeg_gia(
        300, 100, bien_doi_loi=(f"chunk_0000250_k{ma}.wav",)))
    e._run_stream = _audfprint_gia()

    kq = e.scan_media(_media(tmp_path))

    assert kq.status == "ok" and kq.quet_day_du, (kq.status, kq.vung_loi, kq.note)


# ---------------------------------------------------------------------------
#  V2-N1/N2 với audfprint + FFmpeg THẬT
# ---------------------------------------------------------------------------

def _eng_that(tmp_path):
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
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    return e, ghi, _giai_dieu


@pytest.mark.slow
def test_audfprint_that_video_tat_tieng_hoan_toan_la_am_tinh_tron(tmp_path):
    e, ghi, _ = _eng_that(tmp_path)
    video = tmp_path / "tat_tieng.wav"
    ghi(video, np.zeros(22050 * 300), 22050)

    kq = e.scan_media(str(video))

    assert kq.status == "ok" and kq.quet_day_du, (kq.status, kq.vung_loi, kq.note)
    assert kq.vung_loi == []


@pytest.mark.slow
def test_audfprint_that_duoi_im_lang_va_bu_toc_do_van_la_am_tinh_tron(tmp_path):
    """Âm tính thật có 30 giây cuối im lặng, bật lượt bù tốc độ theo lưới cao độ."""
    e, ghi, giai_dieu = _eng_that(tmp_path)
    e.config.quet_da_toc_do = True
    e.config.luoi_tempo = []
    e.config.luoi_resample = [0.98, 1.02]
    e.config.toc_do_toi_da_thu = 2
    tin_hieu = giai_dieu(300, seed=79, sr=22050)
    tin_hieu[int(270 * 22050):] = 0.0
    video = tmp_path / "duoi_im_lang.wav"
    ghi(video, tin_hieu, 22050)

    kq = e.scan_media(str(video))

    assert kq.chan_doan.da_thu_toc_do, "lượt bù tốc độ phải thực sự chạy"
    assert kq.status == "ok" and kq.quet_day_du, (kq.status, kq.vung_loi, kq.note)


# ---------------------------------------------------------------------------
#  V2-3 — file tải về ngắn hơn video: tải lại MỘT lần để biết vì sao
# ---------------------------------------------------------------------------

def _yt(tmp_path, dai_that, cac_lan_tai, khop=False):
    """Quét YouTube với tải/quét giả. Mỗi lần tải ra một file MỚI có độ dài kế tiếp."""
    from engine import Match, ScanResult

    e = _eng(tmp_path)
    e.config.quet_tang_dan = False
    e.config.keep_downloads = True
    os.makedirs(e.dl_dir, exist_ok=True)
    e.youtube_info = lambda url: {"title": "Video", "id": "abcdefghijk", "channel": "",
                                  "channel_id": "", "channel_url": "", "upload_date": "",
                                  "duration": float(dai_that)}
    dem = {"tai": 0, "quet": 0}
    do_dai: dict = {}

    def tai(url, vid, progress=None, gioi_han_giay=None):
        tep = os.path.join(e.dl_dir, f"{vid}.webm")
        assert not os.path.exists(tep), "lần tải lại phải ra bản MỚI, không dùng lại bản đệm"
        do_dai[tep] = float(cac_lan_tai[dem["tai"]])
        dem["tai"] += 1
        Path(tep).write_bytes(b"x" * 64)
        return tep

    def quet(path, **kw):
        dem["quet"] += 1
        dai = do_dai[path]
        kq = ScanResult(source_name="Video", duration_s=dai, vung_da_khop=[(0.0, dai)])
        if khop:
            kq.matches = [Match(clip="goc.opus", start_s=10.0, end_s=70.0,
                                matched_s=60.0, clip_offset_s=0.0, hashes=900,
                                confidence="Cao")]
        return kq

    e.download_audio = tai
    e.duration_of = lambda p: do_dai.get(p)
    e.scan_media = quet
    return e, dem


def test_am_thanh_youtube_ngan_that_su_tai_lai_cung_do_dai_thi_chap_nhan(tmp_path):
    """Âm thanh YouTube cung cấp ngắn hơn lengthSeconds: lần nào tải cũng như nhau.
    Trước đây: lỗi + xoá đệm + tải lại ở MỌI lượt Watch, không bao giờ kết thúc."""
    e, dem = _yt(tmp_path, 600, [580, 580])

    kq = e.scan_youtube("https://youtu.be/abcdefghijk")

    assert kq.status == "ok" and kq.quet_day_du, (kq.status, kq.vung_loi, kq.note)
    assert kq.duration_s == 600.0 and dem == {"tai": 2, "quet": 1}
    assert "cùng độ dài" in kq.note
    assert "abcdefghijk" in e.ids_da_quet()


def test_tai_thieu_lan_sau_du_dai_thi_quet_lai_bang_ban_moi(tmp_path):
    e, dem = _yt(tmp_path, 600, [300, 600])

    kq = e.scan_youtube("https://youtu.be/abcdefghijk")

    assert kq.status == "ok" and kq.quet_day_du and kq.duration_s == 600.0
    assert dem == {"tai": 2, "quet": 2}


def test_tai_thieu_hai_lan_khac_do_dai_van_la_loi(tmp_path):
    e, dem = _yt(tmp_path, 600, [300, 420])

    kq = e.scan_youtube("https://youtu.be/abcdefghijk")

    assert kq.status == "error" and not kq.quet_day_du
    assert kq.vung_loi == [(300.0, 600.0)] and kq.duration_s == 600.0
    assert "abcdefghijk" not in e.ids_da_quet()
    assert not os.path.exists(os.path.join(e.dl_dir, "abcdefghijk.webm")), \
        "bản đệm thiếu đuôi phải bị bỏ để lần sau tải lại"


def test_thieu_60_giay_tren_video_10_tieng_van_bi_phat_hien(tmp_path):
    """Dung sai cũ max(5 s, 0,2%) cho video 10 tiếng là 72 s: thiếu 60 s vẫn "quét trọn"."""
    e, dem = _yt(tmp_path, 36000, [35940, 36000])

    kq = e.scan_youtube("https://youtu.be/abcdefghijk")

    assert dem["tai"] == 2, "thiếu 60 s đuôi phải bị phát hiện và tải lại"
    assert kq.status == "ok" and kq.quet_day_du and kq.duration_s == 36000.0


def test_tai_thieu_ma_da_co_bang_chung_thi_khong_tai_lai(tmp_path):
    e, dem = _yt(tmp_path, 600, [300], khop=True)

    kq = e.scan_youtube("https://youtu.be/abcdefghijk")

    assert dem["tai"] == 1 and kq.status == "ok" and kq.matches
    assert kq.vung_loi == [(300.0, 600.0)] and not kq.quet_day_du


# ---------------------------------------------------------------------------
#  V2-3 (kênh) — nguồn ngắn hơn lengthSeconds; V2-4 — không tự tham chiếu
# ---------------------------------------------------------------------------

can_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="cần ffmpeg/ffprobe trong PATH")
VID = "abcdefghijk"
TEN = f"20260101 - Video {VID} [{VID}].opus"


def _wav_tieng(path, giay: float, sr: int = 16000) -> None:
    t = np.arange(int(giay * sr)) / sr
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).tobytes())


def _kenh(tmp_path, dai_youtube, cac_lan_tai, ds_ids=(VID,)):
    """ChannelSync với tải giả: lần thứ i tải ra nguồn dài `cac_lan_tai[i]` giây."""
    from channel import ChannelSync, VideoInfo

    cs = ChannelSync(str(tmp_path / "kho"))
    ds = [VideoInfo(v, f"Video {v}", "20260101", float(dai_youtube),
                    f"https://youtu.be/{v}") for v in ds_ids]
    cs.list_channel = lambda *a, **k: list(ds)
    cs.so_lan_tai = 0

    def tai(url, rieng):
        # Ghi đúng `outtmpl` như yt-dlp thật (vòng 3: lần tải lại đi vào thư mục MỚI).
        vid = url.rsplit("/", 1)[-1]
        dai = cac_lan_tai[min(cs.so_lan_tai, len(cac_lan_tai) - 1)]
        cs.so_lan_tai += 1
        dich = rieng["outtmpl"].replace("%(id)s", vid).replace("%(ext)s", "wav")
        os.makedirs(os.path.dirname(dich), exist_ok=True)
        _wav_tieng(dich, dai)
        return {"id": vid, "title": f"Video {vid}", "upload_date": "20260101",
                "duration": float(dai_youtube)}

    cs._tai_thu_tung_client = tai
    return cs


@can_ffmpeg
def test_kenh_am_thanh_ngan_that_su_tai_lai_cung_do_dai_thi_nhan_va_khong_tai_nua(tmp_path):
    """Short 15 s mà tiếng dừng ở giây 12: trước đây lỗi + tải lại ở MỌI lượt đồng bộ."""
    cs = _kenh(tmp_path, 15.0, [12.0, 12.0])

    r1 = cs.sync("kenh")

    assert r1["moi"] == 1 and r1["loi"] == [], r1
    assert cs.so_lan_tai == 2, "phải tải lại MỘT lần để xác nhận độ dài"
    dau = cs.load_meta()[TEN]["xac_nhan_tep"]
    assert dau.get("am_thanh_ngan_hon_youtube"), dau

    r2 = cs.sync("kenh")

    assert cs.so_lan_tai == 2 and r2["bo_qua"] == 1 and r2["loi"] == [], r2


@can_ffmpeg
def test_kenh_nguon_tai_dut_hai_lan_khac_do_dai_thi_khong_cong_bo(tmp_path):
    cs = _kenh(tmp_path, 15.0, [6.0, 9.0])

    r = cs.sync("kenh")

    assert r["moi"] == 0 and len(r["loi"]) == 1 and cs.so_lan_tai == 2, r
    assert not os.path.exists(os.path.join(cs.dest, TEN))


@can_ffmpeg
def test_kenh_nguon_tai_dut_lan_sau_du_thi_cong_bo_ban_du(tmp_path):
    cs = _kenh(tmp_path, 15.0, [6.0, 15.0])

    r = cs.sync("kenh")

    assert r["moi"] == 1 and r["loi"] == [] and cs.so_lan_tai == 2, r
    dau = cs.load_meta()[TEN]["xac_nhan_tep"]
    assert not dau.get("am_thanh_ngan_hon_youtube")
    assert dau["do_dai"] == pytest.approx(15.0, abs=0.2)


@can_ffmpeg
def test_kenh_file_cut_khong_duoc_tu_lay_chinh_no_lam_tham_chieu(tmp_path):
    """File 1 s của video 6 s, kênh không liệt kê nó (danh sách giới hạn / tab khác):
    lượt 1 từng ghi `duration_media` đo từ CHÍNH file chưa xác nhận, lượt 2 dùng nó làm
    "tham chiếu" rồi đóng dấu — file cụt thành tin cậy vĩnh viễn (phản biện TCP-10)."""
    from channel import do_dai_media

    cs = _kenh(tmp_path, 6.0, [6.0], ds_ids=("zzzzzzzzzzz",))
    os.makedirs(cs.dest, exist_ok=True)
    nguon = tmp_path / "nguon.wav"
    _wav_tieng(nguon, 1.0)
    import process_runner
    process_runner.chay_lenh_media(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(nguon),
         "-c:a", "libopus", "-b:a", "64k", os.path.join(cs.dest, TEN)])
    assert do_dai_media(os.path.join(cs.dest, TEN)) == pytest.approx(1.0, abs=0.2)

    for _ in range(2):
        cs.sync("kenh")

    muc = cs.load_meta().get(TEN, {})
    assert "xac_nhan_tep" not in muc, muc
    assert "duration_media" not in muc, "số đo của file chưa kiểm không được thành metadata"


# ---------------------------------------------------------------------------
#  V2-5 / V2-6 — Watch với sổ đăng ký kho hỏng / kho chỉ định chưa có vân tay
# ---------------------------------------------------------------------------

def _data_kho(tmp_path, noi_dung: str | None, *, db_pklz=True):
    import json  # noqa: F401 — dùng trong các test gọi hàm này
    from kho_gia import ghi_kho

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    if noi_dung is not None:
        (data / "khos.json").write_text(noi_dung, encoding="utf-8")
    if db_pklz:
        ghi_kho(data / "db.pklz", [("x.opus", 5)])    # kho mặc định kiểu cũ CÓ tồn tại
    return data


def _dem_watch(e, monkeypatch):
    from engine import ScanResult

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


def test_watch_so_kho_hong_khong_co_ban_sao_thi_dung(tmp_path, monkeypatch):
    """khos.json hỏng, không có .bak: Engine lùi về data/db.pklz — Watch không được quét."""
    from watch import MucTheoDoi, WatchList, chay_giam_sat

    data = _data_kho(tmp_path, '{"dang_dung": "SML", "danh_sach": [')
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    dem, lister = _dem_watch(e, monkeypatch)

    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")]), lister=lister)

    assert dem == {"liet_ke": 0, "quet": 0}, "không được lặng lẽ quét bằng data/db.pklz"
    assert any("dừng" in x.lower() for x in bc.loi), bc.loi


def test_so_kho_tung_hong_thi_lan_mo_sau_khong_tu_dung_kho_mac_dinh(tmp_path, monkeypatch):
    """Lần mở đầu đã đổi tên sổ hỏng thành khos.json.hong.*; lần mở SAU không được tự
    "nâng cấp" db.pklz thành «Kho mặc định» như thể chưa từng có sổ — và Watch dừng."""
    from watch import MucTheoDoi, WatchList, chay_giam_sat

    data = _data_kho(tmp_path, '{"dang_dung": "SML", "danh_sach": [')
    Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    assert list(data.glob("khos.json.hong.*")), "sổ hỏng phải được giữ lại để điều tra"

    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))

    assert e.kho_dang_dung == "" and e.canh_bao_khoi_dong, e.canh_bao_khoi_dong
    dem, lister = _dem_watch(e, monkeypatch)
    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")]), lister=lister)
    assert dem == {"liet_ke": 0, "quet": 0} and bc.loi


def test_kho_kieu_cu_chua_tung_co_so_van_tu_nang_cap(tmp_path):
    data = _data_kho(tmp_path, None)

    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))

    assert e.kho_dang_dung == "Kho mặc định"


def test_watch_kho_chi_dinh_chua_co_van_tay_khong_doi_kho_dang_dung(tmp_path, monkeypatch):
    import json

    from kho_gia import ghi_kho
    from watch import MucTheoDoi, WatchList, chay_giam_sat

    data = _data_kho(tmp_path, json.dumps({"dang_dung": "A", "danh_sach": [
        {"ten": "A", "thu_muc": "", "db": "kho_a.pklz", "id": "a"},
        {"ten": "B", "thu_muc": "", "db": "kho_b.pklz", "id": "b"},
    ]}), db_pklz=False)
    ghi_kho(data / "kho_a.pklz", [("x.opus", 5)])
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    dem, lister = _dem_watch(e, monkeypatch)

    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")], kho="B"), lister=lister)

    assert dem == {"liet_ke": 0, "quet": 0} and any("vân tay" in x for x in bc.loi), bc.loi
    so = json.loads((data / "khos.json").read_text(encoding="utf-8"))
    assert so["dang_dung"] == "A", "lượt bị dừng không được đổi kho đang dùng của giao diện"


# ---------------------------------------------------------------------------
#  V2-7 — mkv/webm: độ dài LUỒNG tiếng nằm ở thẻ DURATION; cắt khúc đúng luồng a:0
# ---------------------------------------------------------------------------

def _video_tieng_ngan(path, vcodec: str, acodec: str) -> None:
    import subprocess

    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=64x64:r=5:d=200",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=190",
                    "-c:v", vcodec, "-b:v", "50k", "-c:a", acodec, "-b:a", "32k",
                    str(path)], check=True)


@can_ffmpeg
@pytest.mark.parametrize("duoi,vcodec,acodec", [("mkv", "mpeg4", "aac"),
                                                ("webm", "libvpx", "libopus")])
def test_do_dai_am_thanh_doc_duoc_mkv_webm(tmp_path, duoi, vcodec, acodec):
    media = tmp_path / f"video.{duoi}"
    _video_tieng_ngan(media, vcodec, acodec)

    assert Engine.do_dai_am_thanh(str(media)) == pytest.approx(190.0, abs=0.5)


@can_ffmpeg
def test_mkv_am_thanh_ngan_hon_hinh_khong_bi_bao_loi(tmp_path):
    media = tmp_path / "video.mkv"
    _video_tieng_ngan(media, "mpeg4", "aac")
    e = _eng(tmp_path)
    e._match_chunks = lambda chunks, *a, **k: []

    kq = e.scan_media(str(media))

    assert kq.status == "ok" and kq.vung_loi == [], (kq.status, kq.vung_loi, kq.note)
    assert kq.quet_day_du


def test_cat_khuc_lay_dung_luong_tieng_dau_tien(tmp_path, monkeypatch):
    """Độ dài tiếng đo ở luồng a:0 thì phải cắt đúng luồng a:0 — FFmpeg tự chọn luồng
    "tốt nhất" (nhiều kênh hơn) khi không chỉ định, có thể là luồng khác hẳn."""
    e = _eng(tmp_path)
    e.duration_of = lambda p: 300.0
    lenh_cat = []
    gia = _ffmpeg_gia(300, 100)

    def chay(lenh, **kw):
        if "-ss" in lenh:
            lenh_cat.append(list(lenh))
        return gia(lenh, **kw)

    monkeypatch.setattr(engine_module, "chay_lenh_media", chay)
    e._run_stream = _audfprint_gia()

    e.scan_media(_media(tmp_path))

    assert lenh_cat and all(
        "-map" in lenh and lenh[lenh.index("-map") + 1] == "0:a:0" for lenh in lenh_cat)


# ---------------------------------------------------------------------------
#  V2-9 — lời khuyên "chưa quét trọn" khi Top-1 dừng sớm BÊN TRONG quét tăng dần
# ---------------------------------------------------------------------------

def _kq_mot_phan(ly_do, duong_di, gio):
    return SimpleNamespace(vung_loi=[], ly_do_pham_vi=ly_do, duration_s=gio * 3600.0,
                           chan_doan=SimpleNamespace(duong_di=duong_di))


_CFG = SimpleNamespace(quet_tang_dan=True, quet_tang_dan_tu_gio=10)


@pytest.mark.parametrize("ly_do", ["gioi_han_tai", "dung_som"])
def test_top1_dung_som_trong_quet_tang_dan_goi_y_ca_hai(ly_do):
    """Chỉ tắt «tìm nhanh» thì video 40 tiếng vẫn dừng ở đoạn đầu của quét tăng dần."""
    from scan_ui import goi_y_quet_mot_phan

    goi_y = goi_y_quet_mot_phan([_kq_mot_phan(ly_do, "dung_som_vung_dau", 40)], _CFG)

    assert any("Top-1" in g for g in goi_y) and any("Quét tăng dần" in g for g in goi_y), \
        goi_y


def test_top1_dung_som_video_ngan_chi_goi_y_top1():
    from scan_ui import goi_y_quet_mot_phan

    goi_y = goi_y_quet_mot_phan([_kq_mot_phan("dung_som", "dung_som_vung_dau", 1)], _CFG)

    assert any("Top-1" in g for g in goi_y)
    assert not any("Quét tăng dần" in g for g in goi_y), "tắt quét tăng dần không giúp gì"


# ---------------------------------------------------------------------------
#  V2-9 — CLI: kho đang bận thì báo gọn, mã thoát riêng, không traceback
# ---------------------------------------------------------------------------

def test_cli_kenh_kho_dang_dong_bo_thi_bao_ban_khong_traceback(monkeypatch, capsys,
                                                                tmp_path):
    import cli
    from khoa import DangChayRoi

    class _EngineGia:
        def __init__(self):
            self.config = SimpleNamespace(ncores=1, ytdlp_player_clients=["android"])

        def cau_hinh_mang(self):
            return None

    class _ChannelSyncBan:
        def __init__(self, kho, **kw):
            pass

        def sync(self, *a, **k):
            raise DangChayRoi("Đã có tiến trình khác đang chạy. Thông tin khóa: pid=1234")

    monkeypatch.setattr("sys.argv", ["cli.py", "kenh", "https://youtube.com/@k",
                                     "--kho", str(tmp_path)])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    monkeypatch.setattr(cli, "ChannelSync", _ChannelSyncBan)

    with pytest.raises(SystemExit) as thoat:
        cli.main()

    assert thoat.value.code == 2
    loi = capsys.readouterr().err
    assert "đang chạy" in loi and "Traceback" not in loi


# ---------------------------------------------------------------------------
#  V2-9 — `_hong`: bản chép dở không được nằm lại; metadata không nhân đôi mã video
# ---------------------------------------------------------------------------

def test_chep_vao_hong_that_bai_giua_chung_khong_de_lai_ban_do(tmp_path, monkeypatch):
    import channel
    from channel import ChannelSync

    cs = ChannelSync(str(tmp_path / "kho"))
    goc = Path(cs.dest) / TEN
    goc.write_bytes(b"x" * 3_000_000)

    def khong_link(*a, **k):
        raise OSError("ổ không hỗ trợ hard link")

    def het_dia(nguon, ra, *a, **k):
        ra.write(nguon.read(1_000_000))
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(channel.os, "link", khong_link)
    monkeypatch.setattr(channel.shutil, "copyfileobj", het_dia)

    with pytest.raises(OSError):
        cs._luu_vao_hong(str(goc), VID, giu_ban_goc=True)

    assert goc.read_bytes() == b"x" * 3_000_000, "bản gốc nguyên vẹn"
    assert not list(Path(cs.thu_muc_hong).glob("*")), "không để lại bản chép dở"


def test_seed_metadata_khong_tao_muc_cho_ban_sao_cung_ma_video(tmp_path):
    from channel import ChannelSync

    cs = ChannelSync(str(tmp_path / "kho"))
    ban_sao = f"20260101 - Video {VID} [{VID}] (1).opus"
    for ten in (TEN, ban_sao):
        (Path(cs.dest) / ten).write_bytes(b"x")

    meta, them = cs.seed_meta_tu_dia()

    assert them == 1 and TEN in meta and ban_sao not in meta, sorted(meta)


def test_seed_metadata_bo_qua_ban_sao_khi_ban_chinh_da_co_muc(tmp_path):
    from channel import ChannelSync

    cs = ChannelSync(str(tmp_path / "kho"))
    ban_sao = f"20260101 - Video {VID} [{VID}] - Copy.opus"
    (Path(cs.dest) / TEN).write_bytes(b"x")
    (Path(cs.dest) / ban_sao).write_bytes(b"x")
    cs.save_meta({TEN: {"id": VID, "title": "Tiêu đề thật", "duration": 6}})

    meta, them = cs.seed_meta_tu_dia()

    assert them == 0 and ban_sao not in meta


@can_ffmpeg
def test_kenh_duration_media_cua_cong_cu_bao_tri_khong_thanh_tham_chieu(tmp_path):
    """«kiem_thoi_luong --sua» ghi `duration_media` đo từ CHÍNH file (cụt) vào metadata —
    số đo đó không được dùng làm thước đo để đóng dấu tin cậy cho chính file ấy."""
    import process_runner

    cs = _kenh(tmp_path, 6.0, [6.0], ds_ids=("zzzzzzzzzzz",))
    nguon = tmp_path / "nguon.wav"
    _wav_tieng(nguon, 1.0)
    process_runner.chay_lenh_media(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(nguon),
         "-c:a", "libopus", "-b:a", "64k", os.path.join(cs.dest, TEN)])
    cs.save_meta({TEN: {"id": VID, "title": "Video", "duration": None,
                        "duration_media": 1.0}})

    cs.sync("kenh")

    assert "xac_nhan_tep" not in cs.load_meta()[TEN], cs.load_meta()[TEN]
