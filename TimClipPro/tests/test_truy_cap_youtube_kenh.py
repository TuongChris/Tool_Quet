# -*- coding: utf-8 -*-
"""Cầu dao + phân loại trên đường KÊNH: liệt kê, đồng bộ, vá metadata, sửa ngày đăng.

ChannelSync, kho trên đĩa và clips_meta.json là thật; yt-dlp là bản giả theo kịch bản
(`tests/ytdlp_gia.py`). Không mạng, không FFmpeg (lượt tải đầu đã bị chặn).
"""

import hashlib
import json
import os

import pytest
import yt_dlp

import kiem_ngay_dang
import truy_cap_youtube as t
from channel import ChannelSync
from ytdlp_gia import BOT, R429, YdlKichBan, info_mau


def _ma(i: int) -> str:
    return f"vid{i:08d}"


def _danh_sach(ids):
    return {"_type": "playlist", "id": "UCkenh", "entries": [
        {"id": m, "title": f"Video {m}", "url": f"https://www.youtube.com/watch?v={m}",
         "duration": 600.0} for m in ids]}


@pytest.fixture()
def nghi_ngan(monkeypatch):
    for k in ("metadata", "listing"):
        monkeypatch.setitem(t.NGAN_SACH, k, t.NganSach(cho_tam_thoi=(0.01,), cho_429=(0.01,)))


def _vá(monkeypatch, ydl):
    monkeypatch.setattr(yt_dlp, "YoutubeDL", ydl)
    return ydl


def _sha(p) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ---------------------------------------------------------------- đồng bộ kênh

def test_dong_bo_kenh_bi_bot_check_o_video_dau_thi_dung_khong_dung_file_cu(
        tmp_path, monkeypatch, nghi_ngan):
    kho = tmp_path / "kho"
    kho.mkdir()
    cu = []
    for i in range(5):
        p = kho / f"20240101 - Clip cu {i} [old{i:08d}].opus"
        p.write_bytes(b"opus cu " + bytes([i]))
        cu.append(p)
    (kho / "downloaded.txt").write_text("".join(f"youtube old{i:08d}\n" for i in range(5)),
                                        encoding="utf-8")
    truoc = {p.name: (_sha(p), os.path.getmtime(p)) for p in cu}
    archive = _sha(kho / "downloaded.txt")
    ydl = _vá(monkeypatch, YdlKichBan(tai={"*": BOT},
                                      liet_ke=lambda _p, _u: _danh_sach([_ma(i) for i in range(10)])))
    r = ChannelSync(str(kho)).sync("https://www.youtube.com/@kenh")
    assert ydl.dem("liet_ke") == 1 and ydl.dem("tai") == 1, "không tải tiếp sau khi cầu dao mở"
    assert r["moi"] == 0 and "Đã dừng yêu cầu mới tới YouTube" in r["chan_youtube"]
    assert any("Đã dừng yêu cầu mới tới YouTube" in x for x in r["loi"])
    assert r["youtube"]["bot_challenges"] == 1
    assert r["youtube"]["skipped_by_breaker"] == 0, "vòng đồng bộ tự dừng, không thử tiếp"
    assert {p.name: (_sha(p), os.path.getmtime(p)) for p in cu} == truoc
    assert _sha(kho / "downloaded.txt") == archive


def test_tai_clip_bi_bot_check_khong_doi_client(tmp_path, monkeypatch, nghi_ngan):
    ydl = _vá(monkeypatch, YdlKichBan(tai={"*": BOT}))
    cs = ChannelSync(str(tmp_path), player_clients=["android", "", "tv", "ios"])
    with pytest.raises(RuntimeError) as ei:
        cs._tai_thu_tung_client("https://youtu.be/vid00000001", dict(
            format="ba/b", outtmpl=str(tmp_path / "%(id)s.%(ext)s")))
    assert ydl.dem("tai") == 1
    assert t.phan_loai_loi(ei.value).category == t.BOT_CHALLENGE


# ---------------------------------------------------------------- liệt kê kênh

def test_liet_ke_kenh_bi_429_khong_tra_danh_sach_rong(tmp_path, monkeypatch, nghi_ngan):
    """`ignoreerrors=True` nuốt lỗi và trả None — trước đây thành "Kiểm tra lại link kênh"."""
    def liet_ke(phien, url):
        phien.opts["logger"].error(R429.format(id="UCkenh"))
        return None

    ydl = _vá(monkeypatch, YdlKichBan(liet_ke=liet_ke))
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        ChannelSync.list_channel("https://www.youtube.com/@kenh")
    assert ei.value.that_bai.category == t.RATE_LIMITED
    assert ydl.dem("liet_ke") == 2, "429: thử lại đúng một lần"
    with pytest.raises(t.LoiTruyCapYouTube):
        ChannelSync(str(tmp_path)).sync("https://www.youtube.com/@kenh")


def test_liet_ke_kenh_tra_ve_tab_thi_bao_ro_khong_coi_la_video(monkeypatch, nghi_ngan):
    """`/channel/UC…` thiếu `/videos`: yt-dlp trả các TAB, id = id kênh (Tier 2)."""
    kenh = "UC" + "x" * 22
    tab = {"_type": "playlist", "id": kenh, "entries": [
        {"id": kenh, "title": f"Kênh - {ten}", "url": f"https://www.youtube.com/channel/{kenh}/{ten}"}
        for ten in ("videos", "shorts", "streams")]}
    _vá(monkeypatch, YdlKichBan(liet_ke=lambda _p, _u: tab))
    with pytest.raises(t.LoiTruyCapYouTube) as ei:
        ChannelSync.list_channel(f"https://www.youtube.com/channel/{kenh}")
    assert ei.value.that_bai.category == t.INVALID_INPUT
    assert "/videos" in str(ei.value)


def test_liet_ke_kenh_bo_muc_khong_phai_video(monkeypatch, nghi_ngan):
    ds = _danh_sach([_ma(1), _ma(2)])
    ds["entries"].append({"id": "UC" + "y" * 22, "title": "tab lạ",
                          "url": "https://www.youtube.com/channel/UCy/shorts"})
    _vá(monkeypatch, YdlKichBan(liet_ke=lambda _p, _u: ds))
    assert [v.id for v in ChannelSync.list_channel("https://www.youtube.com/@kenh")] == [
        _ma(1), _ma(2)]


def test_liet_ke_lay_ngay_dang_dung_khi_bi_bot_check(monkeypatch, nghi_ngan):
    ids = [_ma(i) for i in range(6)]
    ydl = _vá(monkeypatch, YdlKichBan(info={"*": BOT}, liet_ke=lambda _p, _u: _danh_sach(ids)))
    p = t.PhienYouTube()
    ds = ChannelSync.list_channel("https://www.youtube.com/@kenh", lay_ngay_dang=True,
                                  phien_youtube=p)
    assert [v.id for v in ds] == ids and all(not v.upload_date for v in ds)
    assert ydl.dem("info") == 1, "một request mỗi video — phải dừng ngay khi bị chặn"
    assert p.tom_tat()["skipped_by_breaker"] == 0 and p.tom_tat()["listing_requests"] == 1


# ---------------------------------------------------------------- vá metadata

def test_va_metadata_dung_khi_bi_bot_check(tmp_path, monkeypatch, nghi_ngan):
    meta = {f"00000000 - Clip {i} [{_ma(i)}].opus": {"id": _ma(i), "title": f"Clip {i}",
                                                     "upload_date": "", "duration": None}
            for i in range(5)}
    (tmp_path / "clips_meta.json").write_text(json.dumps(meta, ensure_ascii=False),
                                              encoding="utf-8")
    ydl = _vá(monkeypatch, YdlKichBan(info={"*": BOT}))
    cs = ChannelSync(str(tmp_path))
    r = cs.va_metadata()
    assert ydl.dem("info") == 1
    assert r["da_va"] == 0 and cs.phien.mo
    assert any("Đã dừng yêu cầu mới tới YouTube" in x for x in r["loi"])
    assert cs.phien.tom_tat()["skipped_by_breaker"] == 0
    assert json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8")) == meta


def test_va_metadata_video_bi_go_van_chay_tiep(tmp_path, monkeypatch, nghi_ngan):
    meta = {f"00000000 - Clip {i} [{_ma(i)}].opus": {"id": _ma(i), "title": f"Clip {i}",
                                                     "upload_date": "", "duration": None}
            for i in range(3)}
    (tmp_path / "clips_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    ydl = _vá(monkeypatch, YdlKichBan(info={_ma(0): "ERROR: [youtube] {id}: Video unavailable"}))
    cs = ChannelSync(str(tmp_path))
    r = cs.va_metadata()
    assert ydl.dem("info") == 3 and r["da_va"] == 2 and not cs.phien.mo


# ---------------------------------------------------------------- sửa ngày đăng (CLI riêng)

def test_sua_ngay_dang_qua_mang_dung_ngay_khi_bi_bot_check(tmp_path, monkeypatch, nghi_ngan):
    meta = {f"20240101 - Clip {i} [{_ma(i)}].opus": {"id": _ma(i), "upload_date": "20240101",
                                                     "duration": 100.0} for i in range(30)}
    (tmp_path / "clips_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    ydl = _vá(monkeypatch, YdlKichBan(info={"*": BOT}))
    kq = kiem_ngay_dang.repair(str(tmp_path), "Asia/Ho_Chi_Minh", dung_mang=True, apply=False,
                               gioi_han=0)
    assert ydl.dem("info") == 1, "trước đây chạy tới 25 lỗi liên tiếp mới dừng"
    assert kq["dung_som"] and "Đã dừng yêu cầu mới tới YouTube" in kq["chan_youtube"]
    assert kq["that_bai"] == 1 and kq["youtube"]["skipped_by_breaker"] == 0


def test_sua_ngay_dang_dung_cau_hinh_mang_cua_nguoi_dung(tmp_path, monkeypatch, nghi_ngan):
    """Trước đây fetcher mặc định bỏ qua cookie + nhịp người dùng đặt (CLAUDE.md mục 9)."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "cau_hinh.json").write_text(json.dumps({"network_timeout_s": 77,
                                                    "ytdlp_sleep_requests_s": 2.5}),
                                        encoding="utf-8")
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(data))
    ydl = _vá(monkeypatch, YdlKichBan(info={"*": lambda _p, m: info_mau(m)}))
    kiem_ngay_dang._fetcher_mac_dinh(_ma(1))
    assert ydl.opts[-1]["socket_timeout"] == 77
    assert ydl.opts[-1]["sleep_interval_requests"] == 2.5
