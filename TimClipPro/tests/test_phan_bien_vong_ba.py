# -*- coding: utf-8 -*-
"""Phát hiện của vòng phản biện 3 — kiểm lại các bản sửa ở ``test_phan_bien_vong_hai.py``.

Mỗi test khoá đúng một phát hiện đã được reviewer tái hiện; mã phát hiện (V3-…) ở ghi chú.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import channel
from channel import ChannelSync, VideoInfo
from engine import Engine

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


def _mp4_hinh_dai_hon_tieng(path, hinh_s: float, tieng_s: float) -> None:
    """Video tiến trình kiểu client `android` (format 18): hình dài hơn tiếng."""
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"color=c=black:s=64x64:r=5:d={hinh_s}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={tieng_s}",
                    "-c:v", "mpeg4", "-q:v", "31", "-c:a", "aac", "-b:a", "32k",
                    str(path)], check=True)


def _kenh_ytdlp(tmp_path, dai_youtube, cac_lan_tai, *, dang="wav"):
    """ChannelSync với hàm tải giả theo ĐÚNG hai quy tắc của yt-dlp mà code dựa vào:
    ghi vào `outtmpl`, và file đích đã tồn tại thì KHÔNG tải lại (không ghi đè).

    Lần tải thật thứ i ra nguồn dài `cac_lan_tai[i]` giây (`(hình, tiếng)` khi dang="mp4").
    """
    cs = ChannelSync(str(tmp_path / "kho"))
    ds = [VideoInfo(VID, f"Video {VID}", "20260101", float(dai_youtube),
                    f"https://youtu.be/{VID}")]
    cs.list_channel = lambda *a, **k: list(ds)
    cs.so_lan_goi = 0
    cs.so_lan_tai = 0

    def tai(url, rieng):
        cs.so_lan_goi += 1
        vid = url.rsplit("/", 1)[-1]
        dich = rieng["outtmpl"].replace("%(id)s", vid).replace("%(ext)s", dang)
        os.makedirs(os.path.dirname(dich), exist_ok=True)
        if not os.path.exists(dich):
            dai = cac_lan_tai[min(cs.so_lan_tai, len(cac_lan_tai) - 1)]
            cs.so_lan_tai += 1
            if dang == "mp4":
                _mp4_hinh_dai_hon_tieng(dich, *dai)
            else:
                _wav_tieng(dich, dai)
        return {"id": vid, "title": f"Video {vid}", "upload_date": "20260101",
                "duration": float(dai_youtube)}

    cs._tai_thu_tung_client = tai
    return cs


# ---------------------------------------------------------------------------
#  V3-B1 — lần tải lại kiểm chứng phải là bản MỚI thật sự
# ---------------------------------------------------------------------------

@can_ffmpeg
def test_kenh_khong_xoa_duoc_nguon_thi_lan_tai_lai_van_la_ban_moi(tmp_path, monkeypatch):
    """Nguồn vừa tải bị phần mềm khác giữ (WinError 32) nên không xoá được; yt-dlp thấy file
    cũ thì KHÔNG tải lại. "Lần tải thứ hai" khi đó chính là file cụt cũ → bị đóng dấu
    "âm thanh ngắn thật" và tin vĩnh viễn. Lần tải lại phải vào chỗ MỚI."""
    cs = _kenh_ytdlp(tmp_path, 15.0, [6.0, 15.0])
    xoa_goc = os.remove

    def khong_xoa_nguon(p, *a, **k):
        p = str(p)
        if os.path.basename(p).startswith(VID + ".") and p.endswith(".wav"):
            raise PermissionError(32, "Tiến trình khác đang giữ file")
        return xoa_goc(p, *a, **k)

    monkeypatch.setattr(channel.os, "remove", khong_xoa_nguon)

    r = cs.sync("kenh")

    assert r["moi"] == 1 and cs.so_lan_tai == 2, (r, cs.so_lan_tai)
    dau = cs.load_meta()[TEN]["xac_nhan_tep"]
    assert not dau.get("am_thanh_ngan_hon_youtube"), dau
    assert dau["do_dai"] == pytest.approx(15.0, abs=0.3)


# ---------------------------------------------------------------------------
#  V3-B2 — nguồn là VIDEO (client android): đo LUỒNG TIẾNG, không đo luồng dài nhất
# ---------------------------------------------------------------------------

@can_ffmpeg
def test_kenh_nguon_video_tieng_ngan_hon_hinh_van_duoc_nhan_sau_hai_lan_tai(tmp_path):
    cs = _kenh_ytdlp(tmp_path, 15.0, [(15.0, 12.0), (15.0, 12.0)], dang="mp4")

    r1 = cs.sync("kenh")

    assert r1["moi"] == 1 and r1["loi"] == [] and cs.so_lan_tai == 2, (r1, cs.so_lan_tai)
    assert cs.load_meta()[TEN]["xac_nhan_tep"].get("am_thanh_ngan_hon_youtube")

    r2 = cs.sync("kenh")

    assert cs.so_lan_tai == 2 and r2["bo_qua"] == 1, r2


# ---------------------------------------------------------------------------
#  V3-B (hợp lý) — dấu "ngắn thật" không được rò sang lượt đồng bộ sau
# ---------------------------------------------------------------------------

@can_ffmpeg
def test_kenh_dau_ngan_that_khong_ro_sang_luot_sau(tmp_path):
    cs = _kenh_ytdlp(tmp_path, 15.0, [15.0])
    cs._ngan_hon_youtube.add(VID)               # sót lại từ một lượt trước trên CÙNG đối tượng

    cs.sync("kenh")

    assert not cs.load_meta()[TEN]["xac_nhan_tep"].get("am_thanh_ngan_hon_youtube")


# ---------------------------------------------------------------------------
#  V3-B8 — đối soát chỉ đếm thay đổi THẬT
# ---------------------------------------------------------------------------

@can_ffmpeg
def test_doi_soat_khong_bao_lai_file_khong_doi_o_moi_luot(tmp_path):
    import process_runner

    cs = _kenh_ytdlp(tmp_path, 6.0, [6.0])
    cs.list_channel = lambda *a, **k: [VideoInfo("zzzzzzzzzzz", "Khac", "20260101", 6.0,
                                                 "https://youtu.be/zzzzzzzzzzz")]
    nguon = tmp_path / "nguon.wav"
    _wav_tieng(nguon, 6.0)
    process_runner.chay_lenh_media(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(nguon),
         "-c:a", "libopus", "-b:a", "64k", os.path.join(cs.dest, TEN)])

    r1 = cs.sync("kenh")
    r2 = cs.sync("kenh")

    assert r1["da_doi_soat"] == 1 and r2["da_doi_soat"] == 0, (r1["da_doi_soat"],
                                                                 r2["da_doi_soat"])


# ---------------------------------------------------------------------------
#  V3-B9 — seed metadata: mã video của mục cũ đọc cả từ KHOÁ và URL
# ---------------------------------------------------------------------------

def test_seed_metadata_nhan_ma_tu_url_cua_muc_cu_khong_co_id(tmp_path):
    cs = ChannelSync(str(tmp_path / "kho"))
    ban_sao = f"20260101 - Video {VID} [{VID}] (1).opus"
    for ten in (TEN, ban_sao):
        (Path(cs.dest) / ten).write_bytes(b"x")
    cs.save_meta({"cu.opus": {"title": "Tiêu đề thật", "url": f"https://youtu.be/{VID}"}})

    _, them = cs.seed_meta_tu_dia()

    assert them == 0


def test_seed_metadata_nhan_ma_tu_khoa_cua_muc_cu_khong_co_id(tmp_path):
    cs = ChannelSync(str(tmp_path / "kho"))
    ban_sao = f"20260101 - Video {VID} [{VID}] - Copy.opus"
    (Path(cs.dest) / ban_sao).write_bytes(b"x")
    cs.save_meta({TEN: {"title": "Tiêu đề thật"}})

    _, them = cs.seed_meta_tu_dia()

    assert them == 0


# ---------------------------------------------------------------------------
#  V3-B3/B4 — sổ kho hỏng hoặc mất (còn .bak): CHẶN quét và tạo kho, không chỉ Watch
# ---------------------------------------------------------------------------

def _data_kho(tmp_path, noi_dung=None, *, bak=None):
    from kho_gia import ghi_kho

    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    if noi_dung is not None:
        (data / "khos.json").write_text(noi_dung, encoding="utf-8")
    if bak is not None:
        (data / "khos.json.bak").write_text(json.dumps(bak), encoding="utf-8")
    ghi_kho(data / "db.pklz", [("x.opus", 5)])          # kho mặc định kiểu cũ CÓ tồn tại
    return data


_SO_SML = {"dang_dung": "SML", "danh_sach": [
    {"ten": "SML", "thu_muc": "", "db": "kho_sml.pklz", "id": "s"}]}


def _sha(p) -> str:
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.mark.parametrize("ca", ["hong", "mat_con_bak"])
def test_so_kho_hong_thi_quet_va_tao_kho_deu_bi_chan(tmp_path, ca):
    data = (_data_kho(tmp_path, '{"dang_dung": "SML", "danh_sach": [') if ca == "hong"
            else _data_kho(tmp_path, None, bak=_SO_SML))
    truoc = _sha(data / "db.pklz")
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    nguon = tmp_path / "nguon"
    nguon.mkdir()
    (nguon / "a.wav").write_bytes(b"x")

    assert e.kho_dang_dung == "" and e.canh_bao_khoi_dong, e.canh_bao_khoi_dong
    with pytest.raises(RuntimeError, match="khos.json"):
        e.require(can_db=True)
    with pytest.raises(RuntimeError, match="khos.json"):
        e.build_database(str(nguon), "add")
    # Cả lô sẽ hỏng như nhau nên dừng ngay ở đầu lô, không chạy từng video rồi báo lỗi.
    with pytest.raises(RuntimeError, match="khos.json"):
        e.scan_media(str(nguon / "a.wav"))
    assert _sha(data / "db.pklz") == truoc, "không được ghi vào data/db.pklz"


def test_so_kho_mat_con_bak_thi_watch_dung_va_giu_nguyen_bak(tmp_path, monkeypatch):
    from engine import ScanResult
    from watch import MucTheoDoi, WatchList, chay_giam_sat

    data = _data_kho(tmp_path, None, bak=_SO_SML)
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    dem = {"liet_ke": 0, "quet": 0}

    def lister(url, limit=None):
        dem["liet_ke"] += 1
        return [SimpleNamespace(id="vid00000001", title="V", url="https://youtu.be/x")]

    def quet(url, progress=None):
        dem["quet"] += 1
        return ScanResult(source_name=url)

    monkeypatch.setattr(e, "scan_youtube", quet)
    bc = chay_giam_sat(e, WatchList(muc=[MucTheoDoi("kenh", "k")]), lister=lister)

    assert dem == {"liet_ke": 0, "quet": 0} and bc.loi, bc.loi
    assert json.loads((data / "khos.json.bak").read_text(encoding="utf-8")) == _SO_SML


# ---------------------------------------------------------------------------
#  V3-B6 — "bận" là mã thoát 2 ở MỌI lệnh CLI, kể cả watch; build bận không in traceback
# ---------------------------------------------------------------------------

def test_watch_khoa_dang_bi_giu_thi_bao_cao_ghi_ban(tmp_path):
    from khoa import KhoaTienTrinh
    from watch import MucTheoDoi, WatchList, chay_giam_sat

    eng = SimpleNamespace(data_dir=str(tmp_path))
    with KhoaTienTrinh(os.path.join(str(tmp_path), "tool.lock"), "lượt khác"):
        bc = chay_giam_sat(eng, WatchList(muc=[MucTheoDoi("kenh", "k")]),
                           lister=lambda url, limit=None: [])

    assert bc.ban and bc.loi, (bc.ban, bc.loi)


def test_cli_watch_ban_thi_thoat_ma_2(monkeypatch, tmp_path, capsys):
    import cli
    from watch import BaoCao, MucTheoDoi, WatchList

    class _EngineGia:
        def __init__(self):
            self.config = SimpleNamespace(ncores=1)
            self.data_dir = str(tmp_path)
            self.canh_bao_khoi_dong = []

    class _DungGia:
        def __init__(self, *a, **k):
            pass

        def bat_tin_hieu(self):
            pass

        def don_file_dung(self):
            pass

    monkeypatch.setattr("sys.argv", ["cli.py", "watch"])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    monkeypatch.setattr(cli, "YeuCauDung", _DungGia)
    monkeypatch.setattr(cli.watch, "doc_watchlist",
                        lambda p: WatchList(muc=[MucTheoDoi("kenh", "k")]))
    monkeypatch.setattr(cli.watch, "chay_giam_sat", lambda *a, **k: BaoCao(
        loi=["Đã có tiến trình khác đang chạy. Thông tin khóa: pid=1"], ban=True))

    with pytest.raises(SystemExit) as thoat:
        cli.main()

    assert thoat.value.code == 2


def test_build_khi_kho_dang_ban_khong_ghi_traceback(tmp_path):
    from khoa import DangChayRoi, KhoaTienTrinh

    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    nguon = tmp_path / "nguon"
    nguon.mkdir()
    with KhoaTienTrinh(os.path.join(e.data_dir, "tool.lock"), "lượt khác"):
        with pytest.raises(DangChayRoi):
            e.build_database(str(nguon), "add")

    nhat_ky = (tmp_path / "out" / "fingerprint.log").read_text(encoding="utf-8")
    assert "Traceback" not in nhat_ky and "DangChayRoi" in nhat_ky, nhat_ky[-800:]


# ---------------------------------------------------------------------------
#  V3-B3/B10 — CLI in cảnh báo khởi động và cảnh báo của build
# ---------------------------------------------------------------------------

def _cli_gia(monkeypatch, argv, **them):
    import cli

    class _EngineGia:
        def __init__(self):
            self.config = SimpleNamespace(ncores=1)
            self.data_dir = ""
            self.kho_dang_dung = ""
            self.canh_bao_khoi_dong = them.get("canh_bao_khoi_dong", [])

        def va_metadata_thieu(self, progress=None):
            return {"da_va": 0, "tong": 0, "bo_qua": 0, "loi": []}

        def build_database(self, *a, **k):
            return {"so_clip": 1, "da_xu_ly": 1, "thanh_cong": 0, "bo_qua": 1,
                    "that_bai": 0, "da_huy": False, "giay": 0.1,
                    "canh_bao": them.get("canh_bao_build", [])}

    monkeypatch.setattr("sys.argv", ["cli.py", *argv])
    monkeypatch.setattr(cli, "Engine", _EngineGia)
    return cli


def test_cli_in_canh_bao_khoi_dong_ra_stderr(monkeypatch, capsys):
    cli = _cli_gia(monkeypatch, ["vametak"], canh_bao_khoi_dong=[
        "Sổ đăng ký kho (khos.json) từng bị hỏng — bản hỏng được giữ ở khos.json.hong.*."])

    cli.main()

    assert "khos.json" in capsys.readouterr().err


def test_cli_themclip_in_canh_bao_cua_build(monkeypatch, capsys, tmp_path):
    cli = _cli_gia(monkeypatch, ["themclip", str(tmp_path)], canh_bao_build=[
        "Gỡ vân tay 1 clip đã bị cách ly vào _hong/ (file nghi hỏng): Ten cu [abc].opus."])

    cli.main()

    assert "Gỡ vân tay 1 clip" in capsys.readouterr().out


# ---------------------------------------------------------------------------
#  V3 kiểm lại (reviewer B) — N1: dọn file tải dở ở MỌI thư mục của lượt (kể cả lan2_*)
# ---------------------------------------------------------------------------

def test_doi_client_don_file_tai_do_ca_trong_thu_muc_tai_lai(tmp_path, monkeypatch):
    """`.part` của client vừa chết ở `lan2_*` mà còn lại thì client sau (continuedl) nối byte
    của luồng MỚI vào luồng CŨ — đúng mối nguy hàm dọn này sinh ra để chặn."""
    cs = ChannelSync(str(tmp_path / "kho"))
    lan2 = Path(cs.tmp_dir) / "lan2_abcd1234"
    lan2.mkdir(parents=True)
    do_dang = lan2 / f"{VID}.webm.part"

    def thu_gia(clients, chay, opts, *, truoc_khi_thu_lai=None, **kw):
        do_dang.write_bytes(b"byte cua client 1")       # client 1 chết giữa chừng
        truoc_khi_thu_lai()                             # trước khi thử client 2
        assert not do_dang.exists(), "file tải dở của client trước phải bị dọn"
        return {}

    monkeypatch.setattr(channel, "thu_tung_client", thu_gia)

    cs._tai_thu_tung_client(f"https://youtu.be/{VID}",
                            {"outtmpl": str(lan2 / "%(id)s.%(ext)s")})


# ---------------------------------------------------------------------------
#  V3 kiểm lại (reviewer B) — N2: sổ kho mất-còn-.bak — bản sao không được bị đè mất
# ---------------------------------------------------------------------------

def test_so_kho_mat_con_bak_giu_mot_ban_sao_khong_bi_ghi_de(tmp_path):
    data = _data_kho(tmp_path, None, bak=_SO_SML)
    e = Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))
    giu = list(data.glob("khos.json.bak.giu_*"))
    assert len(giu) == 1 and json.loads(giu[0].read_text(encoding="utf-8")) == _SO_SML

    # Người dùng tạo kho mới ngay trong trạng thái này rồi sổ được ghi thêm lần nữa: .bak
    # thường bị thay — bản giữ riêng thì không.
    e.add_kho("Moi", str(tmp_path / "nguon"))
    e.update_kho("Moi", str(tmp_path / "nguon2"))
    Engine(root=str(tmp_path), data_dir=str(data), out_dir=str(tmp_path / "out"))

    assert [json.loads(p.read_text(encoding="utf-8")) for p in
            data.glob("khos.json.bak.giu_*")] == [_SO_SML]
