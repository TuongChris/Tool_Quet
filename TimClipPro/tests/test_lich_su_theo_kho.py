# -*- coding: utf-8 -*-
"""Lịch sử quét phải gắn với KHO đã dùng (audit TCP-07).

* Video đã quét ở kho A không được làm kho B bỏ qua — kể cả khi A đã thấy vi phạm.
* Âm tính cũ của kho A hết giá trị khi kho A được bổ sung vân tay, hoặc khi chính sách
  nhận diện đổi. Dương tính vẫn là "đã thấy" (không phải "đã tìm hết").
* Âm tính chưa quét trọn, lỗi, huỷ không chặn lượt quét lại.
* Lịch sử cũ (chưa có cột kho) là "chưa rõ kho": không chặn kho nào, không bị xoá,
  không bị gán cho kho đang dùng.

SQLite THẬT trong thư mục tạm. Quét đi qua ``scan_youtube`` thật; chỉ thay ba điểm
chạm bên ngoài: lấy thông tin video, tải audio, FFmpeg/audfprint.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

import engine as engine_module
from engine import Engine, Match, ScanResult
from kho_gia import ghi_kho

SR = 11025

# Đúng DDL của lichsu.db do bản 4b7e5bd tạo ra (engine.py:872–889 của bản audit).
DDL_CU = [
    """CREATE TABLE jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT, source_type TEXT, source_name TEXT, source_ref TEXT,
        duration_s REAL, status TEXT, n_matches INTEGER, note TEXT,
        source_id TEXT DEFAULT '')""",
    """CREATE TABLE matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER,
        clip TEXT, start_s REAL, end_s REAL, matched_s REAL,
        clip_offset_s REAL, hashes INTEGER, confidence TEXT)""",
    "CREATE INDEX idx_jobs_source_id ON jobs(source_id)",
    "CREATE INDEX idx_matches_job_id ON matches(job_id)",
]


def _sha(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _tao_lichsu_cu(path, so_dong: int = 3) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    for lenh in DDL_CU:
        con.execute(lenh)
    for i in range(so_dong):
        cur = con.execute(
            "INSERT INTO jobs(created_at, source_type, source_name, source_ref,"
            " duration_s, status, n_matches, note, source_id)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            ("2026-09-01 10:00:00", "youtube", f"Video cũ {i}", f"u{i}", 300.0,
             "ok", i % 2, "", f"cu{i}"))
        if i % 2:
            con.execute("INSERT INTO matches(job_id, clip, start_s, end_s, matched_s,"
                        " clip_offset_s, hashes, confidence) VALUES(?,?,?,?,?,?,?,?)",
                        (cur.lastrowid, "goc.opus", 10.0, 70.0, 60.0, 0.0, 9000, "x"))
    con.commit()
    con.close()


def _eng(tmp_path) -> Engine:
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e.config.chunk_s = 100
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    e.config.top_n = 1
    e._overlap_thuc_te = lambda *a, **k: 0
    e.db_clips = lambda **k: [{"ten": "goc.opus", "duong_dan": "goc.opus",
                               "so_hash": 20000}]
    return e


def _kho(e, tmp_path, ten, so_hash=9) -> None:
    thu_muc = tmp_path / f"nguon_{ten}"
    thu_muc.mkdir(exist_ok=True)
    e.add_kho(ten, str(thu_muc))
    ghi_kho(e.db_file, [(str(thu_muc / "goc.opus"), so_hash)])


def _ghi_wav(path, giay: float) -> None:
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"\x00\x00" * int(giay * SR))


def _quet(e, tmp_path, monkeypatch, vid, *, khop=False, tong=300.0) -> ScanResult:
    """Quét một link qua ``scan_youtube`` thật; audfprint trả mảnh khớp hoặc không."""
    media = tmp_path / f"{vid}.wav"
    media.write_bytes(b"x")
    e.youtube_info = lambda url: {
        "title": f"Video {vid}", "id": vid, "channel": "", "channel_id": "",
        "channel_url": "", "upload_date": "", "duration": tong}
    e.download_audio = lambda url, video_id, progress=None, gioi_han_giay=None: str(media)
    e.duration_of = lambda p: tong

    def ffmpeg(lenh, **kw):
        bat_dau = int(float(lenh[lenh.index("-ss") + 1]))
        _ghi_wav(lenh[-1], min(100.0, tong - bat_dau))
        return SimpleNamespace(returncode=0, stdout="", stderr="", cancelled=False,
                               timed_out=False, ly_do="")

    monkeypatch.setattr(engine_module, "chay_lenh_media", ffmpeg)
    manh = [{"clip": "goc.opus", "bat_dau": 40.0, "khop": 60.0, "t_clip": 0.0,
             "hash": 9000, "align": 40.0}]
    e._match_chunks = lambda chunks, *a, **k: list(manh) if khop else []
    return e.scan_youtube(f"https://youtu.be/{vid}")


def _hang(e, vid) -> dict:
    con = sqlite3.connect(e.sqlite_file)
    con.row_factory = sqlite3.Row
    try:
        return dict(con.execute("SELECT * FROM jobs WHERE source_id=? ORDER BY id DESC",
                                (vid,)).fetchone())
    finally:
        con.close()


# ---------------------------------------------------------------------------
#  Kho A → kho B
# ---------------------------------------------------------------------------

def test_am_tinh_o_kho_A_khong_lam_kho_B_bo_qua(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    _kho(e, tmp_path, "B")
    e.use_kho("A")
    kq = _quet(e, tmp_path, monkeypatch, "abcdefghijk")
    assert kq.status == "ok" and not kq.matches and kq.quet_day_du

    assert "abcdefghijk" in e.ids_da_quet(), "cùng kho, cùng phiên bản: được bỏ qua"
    e.use_kho("B")
    assert "abcdefghijk" not in e.ids_da_quet(), \
        "video chưa từng được kiểm với kho B — không được bỏ qua"


def test_duong_tinh_o_kho_A_cung_khong_lam_kho_B_bo_qua(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    _kho(e, tmp_path, "B")
    e.use_kho("A")
    kq = _quet(e, tmp_path, monkeypatch, "duongtinhA1", khop=True)
    assert kq.matches

    assert "duongtinhA1" in e.ids_da_quet()
    e.use_kho("B")
    assert "duongtinhA1" not in e.ids_da_quet()


def test_lich_su_ghi_kho_phien_ban_chinh_sach_va_pham_vi(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    _quet(e, tmp_path, monkeypatch, "vid00000001")

    h = _hang(e, "vid00000001")
    kho_a = next(k for k in e._doc_khos()["danh_sach"] if k["ten"] == "A")
    assert h["kho_id"] == kho_a["id"]
    assert h["kho_ten"] == "A"
    assert h["kho_phien_ban"] and h["chinh_sach"]
    assert h["day_du"] == 1
    pham_vi = json.loads(h["pham_vi"])
    assert pham_vi["vung_da_khop"] == [[0.0, 300.0]]
    assert pham_vi["vung_loi"] == []


# ---------------------------------------------------------------------------
#  Kho được bổ sung / chính sách đổi / phạm vi
# ---------------------------------------------------------------------------

def test_kho_duoc_bo_sung_thi_am_tinh_cu_phai_quet_lai_duong_tinh_van_giu(
        tmp_path, monkeypatch):
    from test_kho_build_an_toan import runner_gia

    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    _quet(e, tmp_path, monkeypatch, "amtinh00001")
    _quet(e, tmp_path, monkeypatch, "duongtinh01", khop=True)
    assert {"amtinh00001", "duongtinh01"} <= e.ids_da_quet()

    nguon = tmp_path / "nguon_A"
    (nguon / "clip_moi.opus").write_bytes(b"audio")
    e._cap_nhat_snapshot_sau_build = lambda *a: []
    e._run_stream = runner_gia(e, {"clip_moi.opus": 9})
    kq_build = e.build_database(str(nguon), mode="add")
    assert kq_build.get("da_ghi_kho") is True

    ids = e.ids_da_quet()
    assert "amtinh00001" not in ids, "âm tính cũ không còn đúng với kho đã bổ sung"
    assert "duongtinh01" in ids, "dương tính vẫn là bằng chứng đã thấy"


def test_doi_chinh_sach_nhan_dien_thi_am_tinh_cu_phai_quet_lai(tmp_path, monkeypatch):
    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    _quet(e, tmp_path, monkeypatch, "chinhsach01")
    assert "chinhsach01" in e.ids_da_quet()

    e.config.top_n = 3               # chỉ đổi cách CHỌN kết quả, không đổi nhận diện
    assert "chinhsach01" in e.ids_da_quet()

    e.config.min_hash_floor = 500    # nới ngưỡng chấp nhận: âm tính cũ chưa chứng minh gì
    assert "chinhsach01" not in e.ids_da_quet()


def test_am_tinh_chua_quet_tron_khong_chan_quet_lai(tmp_path):
    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    e.save_job(ScanResult(source_name="Một phần", source_id="motphan0001",
                          duration_s=300.0, vung_da_khop=[(0.0, 100.0)]), "youtube")
    e.save_job(ScanResult(source_name="Không rõ phạm vi", source_id="khongro0001",
                          duration_s=300.0), "youtube")
    e.save_job(ScanResult(source_name="Lỗi", source_id="loi00000001", status="error",
                          duration_s=300.0, vung_da_khop=[(0.0, 300.0)]), "youtube")

    ids = e.ids_da_quet()
    assert "motphan0001" not in ids
    assert "khongro0001" not in ids
    assert "loi00000001" not in ids


def test_duong_tinh_mot_phan_van_la_da_thay(tmp_path):
    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")
    m = Match(clip="goc.opus", start_s=10, end_s=70, matched_s=60, clip_offset_s=0,
              hashes=9000, confidence="x")
    e.save_job(ScanResult(source_name="Dừng sớm", source_id="dungsom0001",
                          duration_s=40000.0, vung_da_khop=[(0.0, 10800.0)],
                          matches=[m], ly_do_pham_vi="dung_som"), "youtube")
    assert "dungsom0001" in e.ids_da_quet()


# ---------------------------------------------------------------------------
#  Lịch sử cũ và nâng cấp lược đồ
# ---------------------------------------------------------------------------

def test_lich_su_cu_khong_ro_kho_khong_chan_kho_nao_va_khong_mat(tmp_path):
    data = tmp_path / "data"
    _tao_lichsu_cu(str(data / "lichsu.db"), so_dong=4)

    e = _eng(tmp_path)
    _kho(e, tmp_path, "A")

    assert not ({"cu0", "cu1", "cu2", "cu3"} & e.ids_da_quet()), \
        "lịch sử cũ không biết kho: không được chặn kho nào"
    jobs = e.list_jobs()
    assert sorted(j["source_id"] for j in jobs) == ["cu0", "cu1", "cu2", "cu3"]
    assert all(j["kho_id"] == "" for j in jobs), "không được gán cho kho đang dùng"
    assert len(e.job_matches(next(j["id"] for j in jobs if j["source_id"] == "cu1"))) == 1


def test_nang_cap_luoc_do_co_sao_luu_va_chay_lai_khong_doi_gi(tmp_path):
    import lich_su

    db = str(tmp_path / "data" / "lichsu.db")
    _tao_lichsu_cu(db, so_dong=5)

    kq = lich_su.dam_bao_luoc_do(db)

    assert kq["da_nang_cap"] is True
    bak = kq["sao_luu"]
    assert bak and os.path.isfile(bak)
    con = sqlite3.connect(bak)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 5
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
    finally:
        con.close()
    tt = lich_su.thong_ke(db)
    assert tt["phien_ban"] == lich_su.PHIEN_BAN and tt["so_dong"] == 5
    assert tt["so_dong_chua_ro_kho"] == 5 and tt["can_nang_cap"] is False

    truoc = _sha(db)
    kq2 = lich_su.dam_bao_luoc_do(db)
    assert kq2["da_nang_cap"] is False and not kq2["sao_luu"]
    assert _sha(db) == truoc, "chạy lại không được ghi gì"
    assert len([f for f in os.listdir(tmp_path / "data") if f.endswith(".bak")]) == 1


def test_kiem_tra_thu_khong_ghi_gi(tmp_path):
    import lich_su

    db = str(tmp_path / "lichsu.db")
    _tao_lichsu_cu(db, so_dong=3)
    truoc = _sha(db)

    tt = lich_su.thong_ke(db)

    assert tt["can_nang_cap"] is True and tt["phien_ban"] == 0
    assert tt["so_dong"] == 3 and tt["so_dong_chua_ro_kho"] == 3
    assert set(tt["cot_se_them"]) >= {"kho_id", "kho_phien_ban", "chinh_sach", "day_du"}
    assert _sha(db) == truoc
    assert os.listdir(tmp_path) == ["lichsu.db"]


def test_khoi_phuc_tu_ban_sao_luu_roi_nang_cap_lai(tmp_path):
    import lich_su

    db = str(tmp_path / "lichsu.db")
    _tao_lichsu_cu(db, so_dong=4)
    bak = lich_su.dam_bao_luoc_do(db)["sao_luu"]

    ban_sao = str(tmp_path / "khoi_phuc.db")
    lich_su.khoi_phuc(bak, ban_sao)

    tt = lich_su.thong_ke(ban_sao)
    assert tt["phien_ban"] == 0 and tt["so_dong"] == 4 and tt["can_nang_cap"] is True
    assert lich_su.dam_bao_luoc_do(ban_sao)["da_nang_cap"] is True
    assert lich_su.thong_ke(ban_sao)["so_dong"] == 4


def test_khoi_phuc_khong_ghi_de_db_dang_co_neu_chua_cho_phep(tmp_path):
    import lich_su

    db = str(tmp_path / "lichsu.db")
    _tao_lichsu_cu(db, so_dong=2)
    bak = lich_su.dam_bao_luoc_do(db)["sao_luu"]
    truoc = _sha(db)

    with pytest.raises(FileExistsError):
        lich_su.khoi_phuc(bak, db)
    assert _sha(db) == truoc


def test_db_moi_tao_thang_phien_ban_moi_khong_can_sao_luu(tmp_path):
    import lich_su

    e = _eng(tmp_path)
    tt = lich_su.thong_ke(e.sqlite_file)
    assert tt["phien_ban"] == lich_su.PHIEN_BAN and tt["can_nang_cap"] is False
    assert not [f for f in os.listdir(tmp_path / "data") if f.endswith(".bak")]


def test_hai_tien_trinh_nang_cap_cung_luc_khong_hong_khong_nhan_doi(tmp_path):
    db = str(tmp_path / "lichsu.db")
    _tao_lichsu_cu(db, so_dong=6)
    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ma = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {goc!r})
        import lich_su
        while time.time() < float(sys.argv[1]):
            time.sleep(0.005)
        print(lich_su.dam_bao_luoc_do({db!r})["da_nang_cap"])
    """)
    import time
    moc = str(time.time() + 1.5)
    ps = [subprocess.Popen([sys.executable, "-c", ma, moc], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True) for _ in range(2)]
    ra = [p.communicate(timeout=120) for p in ps]

    assert all(p.returncode == 0 for p in ps), ra
    assert sorted(o.strip() for o, _ in ra) == ["False", "True"], ra
    con = sqlite3.connect(db)
    try:
        cot = [r[1] for r in con.execute("PRAGMA table_info(jobs)")]
        assert cot.count("kho_id") == 1
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 6
    finally:
        con.close()
    assert len([f for f in os.listdir(tmp_path) if f.endswith(".bak")]) == 1


def test_mo_ta_lich_su_cu_la_chua_ro_can_ra_soat():
    import lich_su

    cu = {"kho_id": "", "kho_ten": "", "day_du": None, "pham_vi": "", "status": "ok"}
    assert "chưa rõ" in lich_su.mo_ta_kho(cu).lower()
    assert "chưa rõ" in lich_su.mo_ta_pham_vi(cu).lower()
    moi = {"kho_id": "x", "kho_ten": "SML", "day_du": 0, "status": "ok",
           "pham_vi": json.dumps({"vung_da_khop": [[0, 10800]], "vung_loi": [],
                                  "ly_do": "dung_som"}), "duration_s": 40000.0}
    assert lich_su.mo_ta_kho(moi) == "SML"
    assert "một phần" in lich_su.mo_ta_pham_vi(moi).lower()
    tron = {**moi, "day_du": 1, "pham_vi": json.dumps(
        {"vung_da_khop": [[0, 40000]], "vung_loi": [], "ly_do": ""})}
    assert "trọn" in lich_su.mo_ta_pham_vi(tron).lower()
