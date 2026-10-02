# -*- coding: utf-8 -*-
"""Job tạo/bổ sung vân tay phải ghi ĐÚNG kho đã chọn lúc bắt đầu (TCP-01) và không
bao giờ thay một kho tốt bằng kho không dùng được (TCP-02).

Kho ``.pklz`` ở đây là ``HashTable`` thật của audfprint (nhỏ) trong thư mục tạm.
Subprocess build được thay bằng hàm giả phát đúng event JSON mà wrapper thật phát,
nên mọi logic công bố của Engine chạy thật.
"""

import gzip
import json
import os
import pickle
import sys
from pathlib import Path

import pytest

from engine import Engine
from khoa import DangChayRoi

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audfprint-master"))
import hash_table  # noqa: E402

PREFIX = "TIMCLIP_FINGERPRINT_EVENT "

# `pickle` chỉ dùng trên file `.pklz` do CHÍNH test này vừa ghi trong thư mục tạm —
# đó là định dạng kho của audfprint. Không bao giờ nạp file từ nguồn ngoài.


def ghi_ht(path, muc) -> None:
    """``muc``: [(tên, số_hash)] — số_hash = 0 mô phỏng clip không tạo được hash."""
    ht = hash_table.HashTable(hashbits=4, depth=2, maxtime=16)
    for ten, so in muc:
        ht.store(str(ten), [(t % 16, t % 16) for t in range(so)])
    with gzip.open(path, "wb") as f:
        pickle.dump(ht, f)


def doc_ht(path) -> dict:
    with gzip.open(path, "rb") as f:
        ht = pickle.load(f)
    return {os.path.basename(n): int(h) for n, h in zip(ht.names, ht.hashesperid)}


def _eng(tmp_path) -> Engine:
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e._cap_nhat_snapshot_sau_build = lambda *a: []
    return e


def _thu_muc(tmp_path, ten, files) -> Path:
    d = tmp_path / ten
    d.mkdir(exist_ok=True)
    for f in files:
        (d / f).write_bytes(b"audio")
    return d


def runner_gia(e, so_hash: dict, *, truoc_khi_ghi=None, ghi_rac=False):
    """Giả lập audfprint build: ``so_hash[tên file] = số hash`` (0 = thất bại)."""
    def chay(lenh, on_line=None, **kw):
        sub = lenh[4]
        db = lenh[lenh.index("--dbase") + 1]
        ds = Path(lenh[lenh.index("--list") + 1]).read_text(encoding="utf-8").split("\n")
        ds = [p for p in ds if p]
        if truoc_khi_ghi:
            truoc_khi_ghi()
        if ghi_rac:
            Path(db).write_bytes(b"day khong phai pickle")
            return 0, []
        muc = []
        if sub == "add":
            with gzip.open(db, "rb") as f:
                cu = pickle.load(f)
            muc = [(n, int(h)) for n, h in zip(cu.names, cu.hashesperid)]
        for p in ds:
            n = so_hash.get(os.path.basename(p), 0)
            on_line(PREFIX + json.dumps({"event": "clip_started", "file": p}))
            on_line(PREFIX + json.dumps({
                "event": "clip_finished", "file": p,
                "status": "success" if n else "failed",
                "category": "" if n else "zero_hashes"}))
            muc.append((p, n))
        ghi_ht(db, muc)
        return 0, []
    return chay


def _kho(e, tmp_path, ten, files, cu):
    nguon = _thu_muc(tmp_path, f"nguon_{ten}", files)
    e.add_kho(ten, str(nguon))
    if cu is not None:
        ghi_ht(e.db_file, [(str(nguon / n), h) for n, h in cu])
    return nguon, Path(e.db_file)


# ---------------------------------------------------------------------------
#  TCP-01 — job ghim vào kho lúc bắt đầu
# ---------------------------------------------------------------------------

def test_doi_kho_giua_build_khong_ghi_sang_kho_khac(tmp_path):
    e = _eng(tmp_path)
    nguon_a, db_a = _kho(e, tmp_path, "A", ["refA.opus"], [("cuA.opus", 5)])
    _, db_b = _kho(e, tmp_path, "B", ["refB.opus"], [("cuB.opus", 5)])
    e.use_kho("A")
    b_truoc = db_b.read_bytes()
    # Thanh bên đổi sang B trong lúc subprocess build của A đang chạy.
    e._run_stream = runner_gia(e, {"refA.opus": 7}, truoc_khi_ghi=lambda: e.use_kho("B"))

    e.build_database(str(nguon_a), mode="new")

    assert db_b.read_bytes() == b_truoc, "kho B bị ghi đè bằng kết quả của A"
    assert doc_ht(db_a) == {"refA.opus": 7}


def test_xoa_kho_dang_build_bi_tu_choi_va_kho_con_nguyen(tmp_path):
    e = _eng(tmp_path)
    nguon_a, db_a = _kho(e, tmp_path, "A", ["refA.opus"], [("cuA.opus", 5)])
    loi = []

    def xoa_giua_chung():
        try:
            e.delete_kho("A")
        except DangChayRoi as exc:
            loi.append(exc)

    e._run_stream = runner_gia(e, {"refA.opus": 7}, truoc_khi_ghi=xoa_giua_chung)
    e.build_database(str(nguon_a), mode="new")

    assert loi, "xoá kho trong lúc build phải bị từ chối"
    assert any(k["ten"] == "A" for k in e.list_khos())
    assert doc_ht(db_a) == {"refA.opus": 7}


def test_so_dang_ky_doi_file_dich_giua_build_thi_khong_cong_bo(tmp_path):
    e = _eng(tmp_path)
    nguon_a, db_a = _kho(e, tmp_path, "A", ["refA.opus"], [("cuA.opus", 5)])
    a_truoc = db_a.read_bytes()

    def doi_file_dich():
        from luu_tru import cap_nhat_json

        def sua(d):
            for k in d["danh_sach"]:
                if k["ten"] == "A":
                    k["db"] = "kho_khac_hoan_toan.pklz"
        cap_nhat_json(e.kho_file, sua)

    e._run_stream = runner_gia(e, {"refA.opus": 7}, truoc_khi_ghi=doi_file_dich)
    with pytest.raises(RuntimeError, match="(?i)đổi|thay đổi|không còn"):
        e.build_database(str(nguon_a), mode="new")

    assert db_a.read_bytes() == a_truoc
    assert not (Path(e.data_dir) / "kho_khac_hoan_toan.pklz").exists()


def test_doi_cau_hinh_giua_quet_khong_doi_ket_qua_cua_job(tmp_path):
    e = _eng(tmp_path)
    e.config.top_n = 1
    e.config.quet_da_toc_do = False
    e.config.top1_tim_nhanh = False
    e.duration_of = lambda p: 600.0
    e.db_clips = lambda **k: [{"ten": "goc.opus", "duong_dan": "goc.opus",
                               "so_hash": 20000}]
    media = tmp_path / "q.wav"
    media.write_bytes(b"x")
    e._cut_chunks = lambda *a, **k: ([str(tmp_path / "chunk_0000000.wav")], 600.0)

    def khop(chunks, *a, **k):
        # Người dùng kéo thanh trượt giữa lúc job đang chạy.
        e.config.min_hash_floor = 10_000_000
        e.config.top_n = 7
        return [{"clip": "goc.opus", "bat_dau": 10.0, "khop": 300.0,
                 "t_clip": 0.0, "hash": 9000, "align": 10.0}]

    e._match_chunks = khop
    kq = e.scan_media(str(media))

    assert kq.status == "ok"
    assert len(kq.matches) == 1, "cấu hình đổi giữa chừng đã làm đổi kết quả của job"


def test_doi_kho_giua_quet_cac_lan_khop_van_dung_kho_cu(tmp_path):
    e = _eng(tmp_path)
    _, db_a = _kho(e, tmp_path, "A", [], [("goc.opus", 9)])
    _kho(e, tmp_path, "B", [], [("khac.opus", 9)])
    e.use_kho("A")
    e.config.quet_da_toc_do = False
    e.config.top_n = 1
    e.config.top1_tim_nhanh = True
    e.config.top1_khuc_toi_thieu = 2
    e.duration_of = lambda p: 9000.0
    media = tmp_path / "q.wav"
    media.write_bytes(b"x")
    e._cut_chunks = lambda *a, **k: (
        [str(tmp_path / f"chunk_{m:07d}.wav") for m in (0, 3000, 6000)], 9000.0)
    db_da_dung = []

    def chay(lenh, on_line=None, **kw):
        db_da_dung.append(os.path.normcase(lenh[lenh.index("--dbase") + 1]))
        if len(db_da_dung) == 1:
            e.use_kho("B")      # thanh bên đổi kho giữa hai lượt khớp
        Path(lenh[lenh.index("--opfile") + 1]).write_text("", encoding="utf-8")
        return 0, []

    e._run_stream = chay
    e.scan_media(str(media))

    assert len(db_da_dung) == 2
    assert set(db_da_dung) == {os.path.normcase(str(db_a))}


def test_kho_bi_ghi_lai_giua_hai_luot_khop_thi_bao_loi_khong_tron(tmp_path):
    e = _eng(tmp_path)
    _, db_a = _kho(e, tmp_path, "A", [], [("goc.opus", 9)])
    e.config.quet_da_toc_do = False
    e.config.top_n = 1
    e.config.top1_tim_nhanh = True
    e.config.top1_khuc_toi_thieu = 2
    e.duration_of = lambda p: 9000.0
    media = tmp_path / "q.wav"
    media.write_bytes(b"x")
    e._cut_chunks = lambda *a, **k: (
        [str(tmp_path / f"chunk_{m:07d}.wav") for m in (0, 3000, 6000)], 9000.0)
    goi = []

    def chay(lenh, on_line=None, **kw):
        goi.append(1)
        if len(goi) == 1:
            ghi_ht(db_a, [("goc.opus", 9), ("moi.opus", 4)])   # build khác vừa công bố
        Path(lenh[lenh.index("--opfile") + 1]).write_text("", encoding="utf-8")
        return 0, []

    e._run_stream = chay
    kq = e.scan_media(str(media))

    assert kq.status == "error"
    assert "quét lại" in kq.note


# ---------------------------------------------------------------------------
#  TCP-02 — kiểm kho tạm trước khi công bố
# ---------------------------------------------------------------------------

def test_build_moi_khong_clip_nao_co_hash_thi_giu_kho_tot(tmp_path):
    e = _eng(tmp_path)
    nguon, db = _kho(e, tmp_path, "A", ["silent.opus"], [("tot.opus", 9)])
    truoc = db.read_bytes()
    e._run_stream = runner_gia(e, {"silent.opus": 0})

    with pytest.raises(RuntimeError, match="(?i)không có clip nào"):
        e.build_database(str(nguon), mode="new")

    assert db.read_bytes() == truoc


def test_bo_sung_ma_moi_clip_moi_deu_loi_thi_khong_ghi_kho(tmp_path):
    e = _eng(tmp_path)
    nguon, db = _kho(e, tmp_path, "A", ["moi.opus"], [("tot.opus", 9)])
    truoc = db.read_bytes()
    e._run_stream = runner_gia(e, {"moi.opus": 0})

    r = e.build_database(str(nguon), mode="add")

    assert db.read_bytes() == truoc
    assert r["thanh_cong"] == 0 and r["that_bai"] == 1
    assert any("không" in c and "ghi" in c for c in r.get("canh_bao", []))


def test_build_moi_lam_mat_clip_tung_co_hash_bi_tu_choi(tmp_path):
    e = _eng(tmp_path)
    nguon = _thu_muc(tmp_path, "nguon_A", ["a.opus", "b.opus"])
    e.add_kho("A", str(nguon))
    ghi_ht(e.db_file, [(str(nguon / "a.opus"), 9), (str(nguon / "b.opus"), 9)])
    truoc = Path(e.db_file).read_bytes()
    e._run_stream = runner_gia(e, {"a.opus": 9, "b.opus": 0})

    with pytest.raises(RuntimeError, match="b.opus"):
        e.build_database(str(nguon), mode="new")

    assert Path(e.db_file).read_bytes() == truoc


def test_build_moi_chi_clip_moi_bi_loi_thi_van_cong_bo_kem_canh_bao(tmp_path):
    e = _eng(tmp_path)
    nguon = _thu_muc(tmp_path, "nguon_A", ["a.opus", "c_moi.opus"])
    e.add_kho("A", str(nguon))
    ghi_ht(e.db_file, [(str(nguon / "a.opus"), 9)])
    e._run_stream = runner_gia(e, {"a.opus": 9, "c_moi.opus": 0})

    r = e.build_database(str(nguon), mode="new")

    assert doc_ht(e.db_file) == {"a.opus": 9, "c_moi.opus": 0}
    assert r["that_bai"] == 1
    assert any("c_moi.opus" in c for c in r.get("canh_bao", []))


def test_kho_tam_khong_doc_duoc_bi_tu_choi(tmp_path):
    e = _eng(tmp_path)
    nguon, db = _kho(e, tmp_path, "A", ["a.opus"], [("tot.opus", 9)])
    truoc = db.read_bytes()
    e._run_stream = runner_gia(e, {"a.opus": 9}, ghi_rac=True)

    with pytest.raises(RuntimeError, match="(?i)không đọc được"):
        e.build_database(str(nguon), mode="new")

    assert db.read_bytes() == truoc


def test_cong_bo_thanh_cong_doi_phien_ban_kho(tmp_path):
    e = _eng(tmp_path)
    nguon, db = _kho(e, tmp_path, "A", ["a.opus"], [("cu.opus", 9)])

    def phien_ban():
        return next(k for k in e._doc_khos()["danh_sach"] if k["ten"] == "A").get("revision")

    truoc = phien_ban()
    e._run_stream = runner_gia(e, {"a.opus": 9})
    e.build_database(str(nguon), mode="new")
    sau = phien_ban()

    assert sau and sau != truoc
    assert next(k for k in e._doc_khos()["danh_sach"] if k["ten"] == "A").get("id")
