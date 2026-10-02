# -*- coding: utf-8 -*-
"""Đồng bộ kênh chỉ coi một video là ĐÃ CÓ khi file audio đã được xác nhận (TCP-10).

Bản cũ cho FFmpeg ghi thẳng vào tên file cuối trong kho. Nén lỗi để lại file rỗng/dở,
và lượt sync sau thấy "có file .opus mang mã video" là bỏ qua vĩnh viễn — thiếu
nguồn gốc, hoặc đưa file hỏng vào vân tay.

Nay: nén vào file tạm riêng của lượt chạy → kiểm (mã thoát, ffprobe, độ dài so với
nguồn) → đổi tên nguyên tử sang tên cuối → metadata → ``downloaded.txt``. File trên đĩa
chưa được xác nhận thì kiểm lại; hỏng thì báo, tải lại, và CHỈ chuyển bản cũ vào
``_hong/`` sau khi bản mới tải thành công — không bao giờ tự xoá.

FFmpeg/FFprobe là thật (thư mục ``bin`` trong PATH); ca lỗi thay đúng một lệnh nén.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import wave
from pathlib import Path

import pytest

import channel
import engine as engine_module
import process_runner
from channel import ChannelSync, VideoInfo
from process_runner import KetQuaLenh

can_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="cần ffmpeg/ffprobe trong PATH")

VID = "abcdefghijk"
DAI = 6.0
TEN = f"20260101 - Video {VID} [{VID}].opus"


def _wav(path, giay: float, sr: int = 16000) -> None:
    n = int(giay * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(
            struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / sr)))
            for i in range(n)))


def _cs(tmp_path, video_ids=(VID,)):
    cs = ChannelSync(str(tmp_path / "kho"))
    ds = [VideoInfo(v, f"Video {v}", "20260101", DAI, f"https://youtu.be/{v}")
          for v in video_ids]
    cs.list_channel = lambda *a, **k: list(ds)
    cs.so_lan_tai = 0

    def tai(url, rieng):
        cs.so_lan_tai += 1
        vid = url.rsplit("/", 1)[-1]
        os.makedirs(cs.tmp_dir, exist_ok=True)
        _wav(os.path.join(cs.tmp_dir, f"{vid}.wav"), DAI)
        return {"id": vid, "title": f"Video {vid}", "upload_date": "20260101",
                "duration": DAI}

    cs._tai_thu_tung_client = tai
    return cs


def _opus_trong_kho(cs) -> list:
    return sorted(f for f in os.listdir(cs.dest) if f.lower().endswith(".opus"))


def _ffmpeg_gia(hanh_vi):
    """Thay đúng lệnh NÉN; ffprobe và mọi lệnh khác vẫn chạy thật."""
    def chay(lenh, **kw):
        if os.path.basename(lenh[0]).lower().startswith("ffmpeg"):
            return hanh_vi(lenh, kw)
        return process_runner.chay_lenh_media(lenh, **kw)
    return chay


def _kq(rc=0, **kw):
    return KetQuaLenh(returncode=rc, stdout="", stderr=kw.pop("stderr", ""), **kw)


@can_ffmpeg
def test_nen_loi_de_lai_file_0_byte_thi_lan_sau_van_tai_lai(tmp_path, monkeypatch):
    cs = _cs(tmp_path)

    def rong_roi_loi(lenh, kw):
        Path(lenh[-1]).write_bytes(b"")
        return _kq(1, stderr="Conversion failed!")

    monkeypatch.setattr(channel, "chay_lenh_media", _ffmpeg_gia(rong_roi_loi))
    r1 = cs.sync("kenh")
    assert r1["moi"] == 0 and len(r1["loi"]) == 1
    assert _opus_trong_kho(cs) == [], "file nén dở không được nằm trong kho"
    assert cs.load_meta() == {} and cs.done_ids() == set()

    monkeypatch.setattr(channel, "chay_lenh_media", process_runner.chay_lenh_media)
    r2 = cs.sync("kenh")
    assert r2["moi"] == 1 and r2["loi"] == []
    assert cs.so_lan_tai == 2, "lần sau phải tải lại"
    assert _opus_trong_kho(cs) == [TEN]
    assert channel.do_dai_media(os.path.join(cs.dest, TEN)) == pytest.approx(DAI, abs=0.2)
    assert VID in cs.done_ids() and TEN in cs.load_meta()


@can_ffmpeg
@pytest.mark.parametrize("ca", ["rac_ma_thoat_0", "cat_ngan_ma_thoat_0", "het_dia"])
def test_file_nen_khong_qua_kiem_tra_thi_khong_cong_bo(tmp_path, monkeypatch, ca):
    cs = _cs(tmp_path)

    def hanh_vi(lenh, kw):
        if ca == "rac_ma_thoat_0":
            Path(lenh[-1]).write_bytes(os.urandom(4096))
            return _kq(0)
        if ca == "cat_ngan_ma_thoat_0":
            # Bản nén hợp lệ nhưng chỉ dài 1 giây trong khi nguồn dài 6 giây.
            return process_runner.chay_lenh_media(lenh[:-1] + ["-t", "1", lenh[-1]], **kw)
        process_runner.chay_lenh_media(lenh, **kw)
        du_lieu = Path(lenh[-1]).read_bytes()
        Path(lenh[-1]).write_bytes(du_lieu[: len(du_lieu) // 3])
        return _kq(1, stderr="av_interleaved_write_frame(): No space left on device")

    monkeypatch.setattr(channel, "chay_lenh_media", _ffmpeg_gia(hanh_vi))
    r = cs.sync("kenh")

    assert r["moi"] == 0 and len(r["loi"]) == 1, r
    assert _opus_trong_kho(cs) == []
    assert cs.load_meta() == {} and cs.done_ids() == set()
    assert not any(Path(cs.dest, "_tam").rglob("*.opus")), "phải dọn file tạm của lượt này"


@can_ffmpeg
def test_huy_khi_dang_nen_thi_don_file_tam_va_khong_cong_bo(tmp_path, monkeypatch):
    cs = _cs(tmp_path)

    def bi_huy(lenh, kw):
        Path(lenh[-1]).write_bytes(b"OggS" + os.urandom(2000))
        return _kq(-1, cancelled=True)

    monkeypatch.setattr(channel, "chay_lenh_media", _ffmpeg_gia(bi_huy))
    r = cs.sync("kenh", cancel_check=lambda: cs.so_lan_tai > 0)

    assert r["da_huy"] is True and r["moi"] == 0
    assert _opus_trong_kho(cs) == []
    assert not any(Path(cs.dest, "_tam").rglob("*.opus"))


@can_ffmpeg
def test_ghi_metadata_loi_sau_khi_cong_bo_thi_lan_sau_doi_soat_tai_cho(tmp_path, monkeypatch):
    cs = _cs(tmp_path)
    goc = cs.cap_nhat_meta

    def hong(*a, **k):
        raise OSError("đĩa đầy khi ghi clips_meta.json")

    monkeypatch.setattr(cs, "cap_nhat_meta", hong)
    r1 = cs.sync("kenh")
    assert r1["moi"] == 0 and len(r1["loi"]) == 1
    assert _opus_trong_kho(cs) == [TEN], "file đã kiểm và công bố thì giữ lại"

    monkeypatch.setattr(cs, "cap_nhat_meta", goc)
    r2 = cs.sync("kenh")

    assert cs.so_lan_tai == 1, "đối soát tại chỗ, không gọi lại YouTube"
    assert r2["da_doi_soat"] == 1
    muc = cs.load_meta()[TEN]
    assert muc["id"] == VID and muc["url"] == f"https://youtu.be/{VID}"
    assert muc["duration_media"] == pytest.approx(DAI, abs=0.2)
    assert VID in cs.done_ids()


@can_ffmpeg
@pytest.mark.parametrize("noi_dung", [b"", b"x" * 5000], ids=["rong", "rac"])
def test_file_hong_tu_ban_cu_bi_bao_tai_lai_va_ban_cu_vao_hong(tmp_path, noi_dung):
    cs = _cs(tmp_path)
    Path(cs.dest, TEN).write_bytes(noi_dung)            # sót lại từ lần nén lỗi cũ

    r = cs.sync("kenh")

    assert any(TEN in dong for dong in r["nghi_hong"]), r
    assert cs.so_lan_tai == 1 and r["moi"] == 1
    assert _opus_trong_kho(cs) == [TEN]
    assert channel.do_dai_media(os.path.join(cs.dest, TEN)) == pytest.approx(DAI, abs=0.2)
    hong = list(Path(cs.dest, "_hong").iterdir())
    assert len(hong) == 1 and hong[0].read_bytes() == noi_dung, "bản cũ giữ nguyên, không xoá"


def test_file_hong_ma_tai_lai_that_bai_thi_giu_nguyen_tai_cho(tmp_path):
    cs = _cs(tmp_path)
    Path(cs.dest, TEN).write_bytes(b"")

    def loi_mang(url, rieng):
        cs.so_lan_tai += 1
        raise RuntimeError("HTTP Error 403: Forbidden")

    cs._tai_thu_tung_client = loi_mang
    r = cs.sync("kenh")

    assert cs.so_lan_tai == 1 and len(r["loi"]) == 1
    assert any(TEN in dong for dong in r["nghi_hong"])
    assert Path(cs.dest, TEN).is_file(), "không tự xoá file nghi hỏng"
    assert not Path(cs.dest, "_hong").exists()


@can_ffmpeg
def test_chay_lai_khong_tai_trung_khong_nhan_doi(tmp_path):
    cs = _cs(tmp_path)
    cs.sync("kenh")
    r = cs.sync("kenh")

    assert cs.so_lan_tai == 1 and r["moi"] == 0 and r["bo_qua"] == 1
    assert _opus_trong_kho(cs) == [TEN]
    assert Path(cs.archive).read_text(encoding="utf-8").split() == ["youtube", VID]
    assert list(cs.load_meta()) == [TEN]


def test_file_da_xac_nhan_khong_bi_probe_lai(tmp_path, monkeypatch):
    # "Đã xác nhận" = có dấu `xac_nhan_tep` đúng kích thước (chỉ được ghi sau khi kiểm).
    # Bản trước của test dựng "archive + metadata" — hai sổ mà nút «Dựng lại danh sách
    # đã tải» và «Vá metadata» tạo được cho cả file hỏng, nên không còn là bằng chứng.
    cs = _cs(tmp_path, video_ids=())
    Path(cs.dest, TEN).write_bytes(b"x" * 4096)
    cs._mark_done(VID)
    cs.cap_nhat_meta({TEN: {"id": VID, "xac_nhan_tep": {"kich_thuoc": 4096}}})
    goi = []
    monkeypatch.setattr(channel, "chay_lenh_media",
                        lambda lenh, **kw: goi.append(lenh) or _kq(0))

    tep = cs.kiem_tep_tren_dia()

    assert VID in tep["hop_le"] and not tep["nghi_hong"]
    assert goi == [], "kho lớn đã xác nhận không được ffprobe lại mỗi lượt"


def test_liet_ke_media_bo_qua_thu_muc_tam_va_hong(tmp_path):
    kho = tmp_path / "kho"
    (kho / "_tam" / "luot1").mkdir(parents=True)
    (kho / "_hong").mkdir()
    (kho / "a [aaaaaaaaaaa].opus").write_bytes(b"x")
    (kho / "_tam" / "luot1" / "bbbbbbbbbbb.dang_nen.opus").write_bytes(b"x")
    (kho / "_tam" / "ccccccccccc.webm").write_bytes(b"x")
    (kho / "_hong" / "20260101_000000__d [ddddddddddd].opus").write_bytes(b"x")

    assert [os.path.basename(p) for p in engine_module.liet_ke_media(
        str(kho), bo_thu_muc_lam_viec=True)] == ["a [aaaaaaaaaaa].opus"]


def test_sync_chi_don_thu_muc_tam_cua_chinh_minh(tmp_path):
    a = _cs(tmp_path, video_ids=())
    b = _cs(tmp_path, video_ids=())
    os.makedirs(a.tmp_dir, exist_ok=True)
    dang_nen = Path(a.tmp_dir, "xxxxxxxxxxx.dang_nen.opus")
    dang_nen.write_bytes(b"OggS")

    b.list_channel = lambda *x, **k: [VideoInfo(VID, "V", "20260101", DAI, "u")]
    b._tai_thu_tung_client = lambda url, rieng: (_ for _ in ()).throw(RuntimeError("403"))
    b.sync("kenh")

    assert dang_nen.is_file(), "lượt sync khác không được xoá file tạm của lượt đang chạy"


def test_kiem_tra_thieu_coi_file_hong_la_con_thieu(tmp_path):
    cs = _cs(tmp_path)
    Path(cs.dest, TEN).write_bytes(b"")

    r = cs.kiem_tra_thieu("kenh")

    assert [v.id for v in r["thieu"]] == [VID] and r["co_roi"] == 0
    assert any(TEN in dong for dong in r["nghi_hong"])


def test_metadata_cu_khoa_la_duong_dan_day_du_van_duoc_tin_khong_tao_trung(tmp_path,
                                                                          monkeypatch):
    """Kho cũ: clips_meta.json dùng ĐƯỜNG DẪN làm khoá (định dạng resolver vẫn hỗ trợ).

    Không được coi file là lạ rồi đối soát thêm một entry khoá theo tên file — entry mới
    nghèo dữ liệu hơn sẽ thắng ở bước khớp tên chính xác của resolver.
    """
    cs = _cs(tmp_path, video_ids=())
    Path(cs.dest, TEN).write_bytes(b"x" * 4096)
    khoa_cu = rf"D:\Kho cu\{TEN}"
    cs.cap_nhat_meta({khoa_cu: {"id": VID, "title": "Tiêu đề chính thức đầy đủ",
                                "xac_nhan_tep": {"kich_thuoc": 4096}}})
    goi = []
    monkeypatch.setattr(channel, "chay_lenh_media",
                        lambda lenh, **kw: goi.append(lenh) or _kq(0))

    tep = cs.kiem_tep_tren_dia()

    assert VID in tep["hop_le"] and not tep["can_doi_soat"] and goi == []


@can_ffmpeg
def test_doi_soat_cap_nhat_dung_entry_khoa_cu_khong_tao_entry_moi(tmp_path):
    cs = _cs(tmp_path)
    nguon = tmp_path / "nguon.wav"
    _wav(nguon, DAI)
    process_runner.chay_lenh_media(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(nguon),
         "-c:a", "libopus", "-b:a", "64k", os.path.join(cs.dest, TEN)])
    khoa_cu = rf"D:\Kho cu\{TEN}"
    cs.cap_nhat_meta({khoa_cu: {"id": VID, "title": "Tiêu đề chính thức đầy đủ"}})
    # Không có dòng archive -> phải kiểm bằng ffprobe rồi đối soát.

    r = cs.sync("kenh")

    meta = cs.load_meta()
    assert list(meta) == [khoa_cu], "không được đẻ thêm entry khoá theo tên file"
    assert meta[khoa_cu]["title"] == "Tiêu đề chính thức đầy đủ"
    assert meta[khoa_cu]["xac_nhan_tep"]["kich_thuoc"] == os.path.getsize(
        os.path.join(cs.dest, TEN))
    assert r["da_doi_soat"] == 1 and VID in cs.done_ids()
    assert cs.so_lan_tai == 0, "file tốt có sẵn: không tải lại"


# ---------------------------------------------------------------------------
#  Phản biện độc lập (TCP-10)
# ---------------------------------------------------------------------------

def _opus_that(path, giay=DAI):
    nguon = Path(str(path) + ".nguon.wav")
    _wav(nguon, DAI)
    process_runner.chay_lenh_media(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(nguon),
         "-t", str(giay), "-c:a", "libopus", "-b:a", "64k", str(path)])
    nguon.unlink()


@can_ffmpeg
def test_nut_bao_tri_khong_bien_file_hong_thanh_tin_cay(tmp_path):
    """«Dựng lại danh sách đã tải» + «Vá metadata» tạo đủ archive + metadata cho file 0 byte."""
    cs = _cs(tmp_path)
    Path(cs.dest, TEN).write_bytes(b"")
    cs.sua_archive()
    cs.cap_nhat_meta({TEN: {"id": VID, "title": "Video"}}, chi_khi_chua_co=True)

    r = cs.sync("kenh")

    assert cs.so_lan_tai == 1 and r["moi"] == 1
    assert channel.do_dai_media(os.path.join(cs.dest, TEN)) == pytest.approx(DAI, abs=0.2)
    assert any(TEN in dong for dong in r["nghi_hong"])


@can_ffmpeg
def test_file_cat_cut_khong_co_trong_danh_sach_kenh_van_bi_bat_nho_metadata(tmp_path):
    cs = _cs(tmp_path, video_ids=("zzzzzzzzzzz",))
    _opus_that(Path(cs.dest, TEN), giay=1)                      # 1 s của video 6 s
    cs.cap_nhat_meta({TEN: {"id": VID, "duration": DAI}})

    r = cs.sync("kenh")

    assert any(TEN in dong for dong in r["nghi_hong"]), r
    assert "xac_nhan_tep" not in cs.load_meta()[TEN]


@can_ffmpeg
def test_khong_co_do_dai_tham_chieu_thi_khong_dong_dau(tmp_path):
    cs = _cs(tmp_path, video_ids=("zzzzzzzzzzz",))
    _opus_that(Path(cs.dest, TEN))

    tep = cs.kiem_tep_tren_dia({})
    cs._doi_soat(tep["can_doi_soat"])

    assert VID in tep["hop_le"]
    assert "xac_nhan_tep" not in cs.load_meta().get(TEN, {}), \
        "không có độ dài tham chiếu thì không được đóng dấu vĩnh viễn"


@can_ffmpeg
def test_doi_ten_vao_kho_that_bai_thi_hoan_nguyen(tmp_path, monkeypatch):
    cs = _cs(tmp_path)
    Path(cs.dest, TEN).write_bytes(b"x" * 3000)              # bản cũ hỏng, cùng tên

    def bi_giu(tam, dich, so_lan=10):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(channel, "_dat_vao_kho", bi_giu)
    r1 = cs.sync("kenh")

    assert len(r1["loi"]) == 1 and r1["da_cach_ly"] == []
    assert Path(cs.dest, TEN).read_bytes() == b"x" * 3000, "bản cũ phải còn nguyên tại chỗ"
    assert not any(Path(cs.dest, "_hong").glob("*")) if Path(cs.dest, "_hong").exists() \
        else True

    monkeypatch.undo()
    r2 = cs.sync("kenh")
    assert r2["moi"] == 1 and cs.so_lan_tai == 2
    assert [p.read_bytes() for p in Path(cs.dest, "_hong").iterdir()] == [b"x" * 3000]


@can_ffmpeg
def test_danh_sach_kenh_trung_ma_chi_tai_mot_lan(tmp_path):
    cs = _cs(tmp_path)
    v = cs.list_channel()[0]
    cs.list_channel = lambda *a, **k: [v, v]

    r = cs.sync("kenh")

    assert cs.so_lan_tai == 1 and r["moi"] == 1 and r["da_cach_ly"] == []
    assert Path(cs.archive).read_text(encoding="utf-8").split() == ["youtube", VID]
    assert not Path(cs.dest, "_hong").exists()


def test_hai_luot_dong_bo_cung_kho_thi_luot_sau_bi_tu_choi(tmp_path):
    from khoa import DangChayRoi, KhoaTienTrinh
    cs = _cs(tmp_path)
    with KhoaTienTrinh(os.path.join(cs.dest, channel.TEN_KHOA_DONG_BO), "đồng bộ khác"):
        with pytest.raises(DangChayRoi):
            cs.sync("kenh")
    assert cs.so_lan_tai == 0


@can_ffmpeg
def test_ban_da_xac_nhan_vua_xuat_hien_thi_khong_bi_cach_ly(tmp_path):
    """Lượt khác vừa đặt bản ĐÃ KIỂM vào đúng tên trong lúc lượt này đang tải."""
    cs = _cs(tmp_path)
    tai_goc = cs._tai_thu_tung_client

    def tai_va_bi_chen(url, rieng):
        kq = tai_goc(url, rieng)
        _opus_that(Path(cs.dest, TEN))
        cs.cap_nhat_meta({TEN: {"id": VID, "xac_nhan_tep": {
            "kich_thuoc": os.path.getsize(os.path.join(cs.dest, TEN)), "do_dai": DAI}}})
        return kq

    cs._tai_thu_tung_client = tai_va_bi_chen
    r = cs.sync("kenh")

    assert r["moi"] == 1 and r["da_cach_ly"] == [] and not Path(cs.dest, "_hong").exists()
    assert _opus_trong_kho(cs) == [TEN]


def test_danh_sach_video_trong_kho_bo_qua_tam_va_hong(tmp_path):
    import danh_sach_video
    kho = tmp_path / "kho"
    (kho / "_tam" / "luot").mkdir(parents=True)
    (kho / "_hong").mkdir()
    (kho / TEN).write_bytes(b"x")
    (kho / "_hong" / f"260101-000000_{TEN}").write_bytes(b"x")
    (kho / "_tam" / "luot" / f"{VID}.ab12cd34.dang_nen.opus").write_bytes(b"x")

    kq = danh_sach_video.liet_ke_kho("SML", str(kho))

    assert [d.ten_file for d in kq.dong] == [TEN]


@can_ffmpeg
def test_doi_soat_loi_khong_chan_ca_luot_dong_bo(tmp_path, monkeypatch):
    cs = _cs(tmp_path, video_ids=(VID, "bbbbbbbbbbb"))
    ten_b = "20260101 - Video bbbbbbbbbbb [bbbbbbbbbbb].opus"
    _opus_that(Path(cs.dest, ten_b))                       # file tốt, chưa có dấu
    goc = channel.cap_nhat_json
    lan = []

    def hong_lan_dau(*a, **k):
        lan.append(1)
        if len(lan) == 1:
            raise OSError("ổ đĩa đầy")
        return goc(*a, **k)

    monkeypatch.setattr(channel, "cap_nhat_json", hong_lan_dau)
    r = cs.sync("kenh")

    assert any("đối soát" in dong.lower() for dong in r["loi"]), r["loi"]
    assert r["moi"] == 1 and cs.so_lan_tai == 1, "video còn thiếu vẫn phải được tải"


def test_ten_trong_hong_rut_gon_khi_duong_dan_qua_dai(tmp_path, monkeypatch):
    cs = _cs(tmp_path, video_ids=())
    Path(cs.dest, TEN).write_bytes(b"x")
    monkeypatch.setattr(channel, "DO_DAI_DUONG_DAN_TOI_DA", 10)

    moi = cs._luu_vao_hong(os.path.join(cs.dest, TEN), VID, giu_ban_goc=False)

    assert os.path.basename(moi).endswith(f"_{VID}.opus") and TEN not in moi
    assert Path(moi).read_bytes() == b"x" and not Path(cs.dest, TEN).exists()


@can_ffmpeg
def test_kiem_file_tren_dia_bao_tien_do_va_dung_duoc(tmp_path):
    cs = _cs(tmp_path, video_ids=(VID, "bbbbbbbbbbb", "ccccccccccc"))
    for v in ("bbbbbbbbbbb", "ccccccccccc"):
        _opus_that(Path(cs.dest, f"20260101 - Video {v} [{v}].opus"))
    tien_do = []

    r = cs.sync("kenh", progress=lambda pct, msg: tien_do.append(msg),
                cancel_check=lambda: any("Kiểm file" in m for m in tien_do))

    assert any("Kiểm file" in m for m in tien_do)
    assert r["da_huy"] is True and cs.so_lan_tai == 0
