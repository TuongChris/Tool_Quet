# -*- coding: utf-8 -*-
"""«Bổ sung clip mới vào kho» phải LÀM MỚI vân tay của clip đã đổi file (audit TCP-10).

Đồng bộ kênh nay tải lại file hỏng/nén dở và đặt bản tốt vào ĐÚNG tên cũ. Chế độ bổ sung
bỏ qua clip theo đường dẫn nếu clip đã có hash, nên một file bị cắt cụt từng tạo được vài
hash sẽ giữ vân tay cũ mãi. Clip có file sửa đổi SAU lần công bố kho gần nhất được gỡ khỏi
kho tạm (``audfprint remove``) rồi tạo vân tay lại; kho tạm vẫn phải qua ``_kiem_kho_tam``.
"""

import gzip
import json
import os
import pickle
import shutil
import sys
import time
from pathlib import Path

import pytest

from engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "audfprint-master"))
import hash_table  # noqa: E402

PREFIX = "TIMCLIP_FINGERPRINT_EVENT "

# `pickle` chỉ dùng trên file `.pklz` do CHÍNH test này ghi trong thư mục tạm.


def _ghi(path, muc):
    ht = hash_table.HashTable(hashbits=4, depth=2, maxtime=16)
    for ten, so in muc:
        ht.store(str(ten), [(t % 16, t % 16) for t in range(so)])
    with gzip.open(path, "wb") as f:
        pickle.dump(ht, f)


def _doc(path) -> dict:
    with gzip.open(path, "rb") as f:
        ht = pickle.load(f)
    return {os.path.basename(n): int(h) for n, h in zip(ht.names, ht.hashesperid) if n}


def _eng(tmp_path):
    e = Engine(root=str(tmp_path), data_dir=str(tmp_path / "data"),
               out_dir=str(tmp_path / "out"))
    e.require = lambda *a, **k: None
    e._cap_nhat_snapshot_sau_build = lambda *a: []
    return e


def _runner(so_hash: dict, lenh_da_chay: list):
    """audfprint giả: `remove` dùng HashTable.remove THẬT; build ghi đúng event."""
    def chay(lenh, on_line=None, **kw):
        db = lenh[lenh.index("--dbase") + 1]
        ds = [p for p in Path(lenh[lenh.index("--list") + 1])
              .read_text(encoding="utf-8").splitlines() if p]
        # Ghi lại lúc chạy: thư mục làm việc của job bị dọn khi build xong.
        lenh_da_chay.append((list(lenh), ds))
        with gzip.open(db, "rb") as f:
            ht = pickle.load(f) if os.path.getsize(db) else None
        if lenh[3] == "remove":
            for ten in ds:
                ht.remove(ten)
        else:
            for p in ds:
                n = so_hash.get(os.path.basename(p), 0)
                on_line(PREFIX + json.dumps({"event": "clip_started", "file": p}))
                on_line(PREFIX + json.dumps({
                    "event": "clip_finished", "file": p,
                    "status": "success" if n else "failed",
                    "category": "" if n else "zero_hashes"}))
                ht.store(p, [(t % 16, t % 16) for t in range(n)])
        with gzip.open(db, "wb") as f:
            pickle.dump(ht, f)
        return 0, []
    return chay


def _kho(e, tmp_path):
    nguon = tmp_path / "nguon"
    nguon.mkdir()
    for ten in ("a.opus", "b.opus"):
        (nguon / ten).write_bytes(b"audio")
    e.add_kho("A", str(nguon))
    _ghi(e.db_file, [(str(nguon / "a.opus"), 3), (str(nguon / "b.opus"), 9)])
    moc = time.time() - 100
    os.utime(e.db_file, (moc, moc))
    for ten in ("a.opus", "b.opus"):
        os.utime(nguon / ten, (moc - 50, moc - 50))
    return nguon


def test_clip_doi_file_sau_lan_cong_bo_duoc_go_va_tao_van_tay_lai(tmp_path):
    e = _eng(tmp_path)
    nguon = _kho(e, tmp_path)
    (nguon / "a.opus").write_bytes(b"audio day du hon")      # sync vừa thay bản tốt
    lenh = []
    e._run_stream = _runner({"a.opus": 12, "b.opus": 9}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert kq.get("da_ghi_kho") is True
    assert len(lenh) == 2 and lenh[0][0][3] == "remove" and lenh[1][0][4] == "add",         "gỡ vân tay cũ TRƯỚC, rồi mới bổ sung"
    assert lenh[0][1] == [str(nguon / "a.opus")], "chỉ gỡ đúng clip đổi file"
    assert lenh[1][1] == [str(nguon / "a.opus")], "chỉ tạo lại đúng clip đổi file"
    assert _doc(e.db_file) == {"a.opus": 12, "b.opus": 9}, "b không đổi file: giữ nguyên"


def test_clip_doi_file_ma_tao_lai_that_bai_thi_kho_cu_giu_nguyen(tmp_path):
    e = _eng(tmp_path)
    nguon = _kho(e, tmp_path)
    truoc = Path(e.db_file).read_bytes()
    (nguon / "a.opus").write_bytes(b"van hong")
    e._run_stream = _runner({"a.opus": 0, "b.opus": 9}, [])

    with pytest.raises(RuntimeError):
        e.build_database(str(nguon), "add")

    assert Path(e.db_file).read_bytes() == truoc, "kho tốt không bị thay bằng kho mất clip"


def test_khong_clip_nao_doi_file_thi_khong_go_gi(tmp_path):
    e = _eng(tmp_path)
    nguon = _kho(e, tmp_path)
    lenh = []
    e._run_stream = _runner({"a.opus": 3, "b.opus": 9}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert lenh == [] and kq.get("da_ghi_kho") is not True


@pytest.mark.slow
def test_audio_that_clip_cat_cut_duoc_thay_ban_day_du(tmp_path):
    """audfprint THẬT: clip bị cắt còn 10 s được thay bằng bản 30 s rồi «Bổ sung»."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("cần ffmpeg trong PATH")
    from conftest import _ghi_wav, _giai_dieu

    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    e = Engine(root=goc, data_dir=str(tmp_path / "data"), out_dir=str(tmp_path / "out"))
    nguon = tmp_path / "nguon"
    nguon.mkdir()
    a = _giai_dieu(30, seed=31, sr=22050)
    _ghi_wav(nguon / "a.wav", a[: 10 * 22050], 22050)
    _ghi_wav(nguon / "b.wav", _giai_dieu(30, seed=32, sr=22050), 22050)
    e.add_kho("A", str(nguon))
    e.build_database(str(nguon), "new")
    truoc = {c["ten"]: c["so_hash"] for c in e.db_clips(bo_cache=True)}

    time.sleep(1.1)
    _ghi_wav(nguon / "a.wav", a, 22050)
    kq = e.build_database(str(nguon), "add")
    sau = {c["ten"]: c["so_hash"] for c in e.db_clips(bo_cache=True)}

    assert kq.get("da_ghi_kho") is True
    assert sorted(sau) == ["a.wav", "b.wav"], "không nhân đôi, không mất clip"
    assert sau["a.wav"] > 2 * truoc["a.wav"], (truoc, sau)
    assert sau["b.wav"] == truoc["b.wav"]


# ---------------------------------------------------------------------------
#  Phản biện vòng 2: mốc BẮT ĐẦU build; clip đã bị cách ly vào `_hong/`
# ---------------------------------------------------------------------------

def _dat_moc_build(e, moc: float) -> None:
    def sua(d):
        for k in d["danh_sach"]:
            if k["ten"] == e.kho_dang_dung:
                k["moc_build"] = moc
    e._sua_khos(sua)


def test_file_thay_trong_luc_build_duoc_lam_moi_o_lan_bo_sung_sau(tmp_path):
    """Lần build trước bắt đầu lúc T, công bố lúc T+30; file a bị thay lúc T+20 (sau khi
    build đã đọc nó). So với giờ CÔNG BỐ thì a "cũ hơn kho" và không bao giờ được làm mới."""
    e = _eng(tmp_path)
    nguon = _kho(e, tmp_path)
    moc_cong_bo = os.path.getmtime(e.db_file)
    _dat_moc_build(e, moc_cong_bo - 30)
    os.utime(nguon / "a.opus", (moc_cong_bo - 10, moc_cong_bo - 10))
    lenh = []
    e._run_stream = _runner({"a.opus": 12, "b.opus": 9}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert lenh and lenh[0][0][3] == "remove" and lenh[0][1] == [str(nguon / "a.opus")], lenh
    assert kq.get("da_ghi_kho") is True and _doc(e.db_file) == {"a.opus": 12, "b.opus": 9}


def test_build_ghi_moc_bat_dau_vao_so_kho(tmp_path):
    e = _eng(tmp_path)
    nguon = _kho(e, tmp_path)
    (nguon / "c.opus").write_bytes(b"audio")
    e._run_stream = _runner({"c.opus": 4}, [])
    truoc = time.time()

    e.build_database(str(nguon), "add")

    kho = next(k for k in e._doc_khos()["danh_sach"] if k["ten"] == "A")
    assert truoc - 1 <= kho["moc_build"] <= os.path.getmtime(e.db_file) + 1, kho


def test_clip_bien_mat_khong_ro_ly_do_thi_giu_van_tay_va_canh_bao(tmp_path):
    """File vắng mà KHÔNG có bản cách ly (ổ chưa gắn, OneDrive chưa tải về…): gỡ vân tay
    là mất hàng giờ tạo lại — giữ nguyên, chỉ cảnh báo."""
    e = _eng(tmp_path)
    nguon = _kho(e, tmp_path)
    truoc = Path(e.db_file).read_bytes()
    (nguon / "b.opus").unlink()
    lenh = []
    e._run_stream = _runner({"a.opus": 3}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert lenh == [] and Path(e.db_file).read_bytes() == truoc
    assert any("không còn file" in c for c in kq["canh_bao"]), kq["canh_bao"]


# ---------------------------------------------------------------------------
#  Clip đã bị đồng bộ kênh cách ly vào `_hong/` (phản biện vòng 2 + vòng 3)
#
#  Đồng bộ kênh chỉ cách ly bản cũ khi đã có bản THAY THẾ cùng mã video (tải lại, tiêu đề
#  đổi → tên mới). Vân tay bản cũ chỉ được gỡ khi bản thay thế CÓ vân tay trong kho tạm —
#  gỡ trước khi bản mới tạo được vân tay là xuất bản một kho không còn vân tay nào cho
#  video đó (vòng 3, reviewer B).
# ---------------------------------------------------------------------------

CU = "20260101 - Ten cu [abcdefghijk].opus"
MOI = "20260101 - Ten moi [abcdefghijk].opus"
KHAC = "20260101 - Khac [zzzzzzzzzzz].opus"


def _kho_doi_ten(e, tmp_path, *, thu_muc_con="", cu=CU, moi=MOI):
    """Kho có `cu` (9 hash) + KHAC (5). Đồng bộ kênh vừa tải bản `moi` (tiêu đề đổi) và chuyển
    `cu` vào `_hong/` của ĐÚNG thư mục chứa nó."""
    CU, MOI = cu, moi  # noqa: N806 — giữ tên như các test dùng
    nguon = tmp_path / "nguon"
    noi = nguon / thu_muc_con if thu_muc_con else nguon
    noi.mkdir(parents=True)
    for ten in (CU, KHAC):
        (noi / ten).write_bytes(b"audio")
    e.add_kho("A", str(nguon))
    _ghi(e.db_file, [(str(noi / CU), 9), (str(noi / KHAC), 5)])
    moc = time.time() - 100
    os.utime(e.db_file, (moc, moc))
    for ten in (CU, KHAC):
        os.utime(noi / ten, (moc - 50, moc - 50))
    (noi / "_hong").mkdir()
    os.replace(noi / CU, noi / "_hong" / f"260101-120000_{CU}")
    (noi / MOI).write_bytes(b"audio moi")
    return nguon, noi


@pytest.mark.parametrize("cu,moi", [
    (CU, MOI),
    # Tên không theo đủ ngữ pháp bộ tải (không có ngày), và bản thay thế là bản sao Windows.
    ("Ten cu [abcdefghijk].opus", "Ten moi [abcdefghijk] (1).opus"),
], ids=["co_ngay", "khong_ngay_ban_sao"])
def test_clip_da_bi_cach_ly_duoc_go_khi_ban_thay_the_co_van_tay(tmp_path, cu, moi):
    e = _eng(tmp_path)
    nguon, noi = _kho_doi_ten(e, tmp_path, cu=cu, moi=moi)
    lenh = []
    e._run_stream = _runner({moi: 7}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert lenh[0][0][4] == "add" and lenh[0][1] == [str(noi / moi)], lenh
    assert lenh[1][0][3] == "remove" and lenh[1][1] == [str(noi / cu)], lenh
    assert kq.get("da_ghi_kho") is True and _doc(e.db_file) == {moi: 7, KHAC: 5}
    assert any(cu in c for c in kq["canh_bao"]), kq["canh_bao"]


def test_ban_thay_the_khong_tao_duoc_van_tay_thi_giu_van_tay_cu(tmp_path):
    e = _eng(tmp_path)
    nguon, noi = _kho_doi_ten(e, tmp_path)
    truoc = Path(e.db_file).read_bytes()
    lenh = []
    e._run_stream = _runner({MOI: 0}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert all(x[0][3] != "remove" for x in lenh), lenh
    assert Path(e.db_file).read_bytes() == truoc, "kho tốt không được thay"
    assert any("chưa có bản thay thế" in c for c in kq["canh_bao"]), kq["canh_bao"]


def test_clip_da_cach_ly_khong_co_ban_thay_the_thi_giu_van_tay(tmp_path):
    e = _eng(tmp_path)
    nguon, noi = _kho_doi_ten(e, tmp_path)
    (noi / MOI).unlink()
    truoc = Path(e.db_file).read_bytes()
    lenh = []
    e._run_stream = _runner({}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert lenh == [] and Path(e.db_file).read_bytes() == truoc
    assert any("chưa có bản thay thế" in c for c in kq["canh_bao"]), kq["canh_bao"]



def test_clip_vang_khong_bi_cach_ly_du_co_ban_thay_the_van_giu_van_tay(tmp_path):
    """Bản cũ biến mất mà KHÔNG có bản trong `_hong/` (người dùng xoá tay, ổ chưa đồng bộ…):
    không có bằng chứng nó hỏng — giữ vân tay dù đã có bản thay thế cùng mã."""
    e = _eng(tmp_path)
    nguon, noi = _kho_doi_ten(e, tmp_path)
    for f in (noi / "_hong").iterdir():
        f.unlink()
    lenh = []
    e._run_stream = _runner({MOI: 7}, lenh)

    kq = e.build_database(str(nguon), "add")

    assert all(x[0][3] != "remove" for x in lenh), lenh
    assert _doc(e.db_file) == {CU: 9, MOI: 7, KHAC: 5}
    assert any("không còn file" in c for c in kq["canh_bao"]), kq["canh_bao"]

def test_clip_da_cach_ly_trong_thu_muc_con_cung_duoc_go(tmp_path):
    """Kho dựng từ thư mục cha, mỗi kênh một thư mục con có `_hong/` riêng."""
    e = _eng(tmp_path)
    nguon, noi = _kho_doi_ten(e, tmp_path, thu_muc_con="kenh1")
    e._run_stream = _runner({MOI: 7}, [])

    kq = e.build_database(str(nguon), "add")

    assert kq.get("da_ghi_kho") is True and _doc(e.db_file) == {MOI: 7, KHAC: 5}


@pytest.mark.slow
def test_audio_that_clip_bi_cach_ly_duoc_go_khong_can_buoc_them(tmp_path):
    """audfprint THẬT: bản thay thế (tiêu đề mới, cùng mã video) đã có vân tay từ trước; bản
    cũ bị đồng bộ kênh chuyển vào `_hong/`. «Bổ sung» chỉ GỠ (không có gì để thêm) — kho
    còn a và bản thay thế, số hash giữ nguyên."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("cần ffmpeg trong PATH")
    from conftest import _ghi_wav, _giai_dieu

    goc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    e = Engine(root=goc, data_dir=str(tmp_path / "data"), out_dir=str(tmp_path / "out"))
    nguon = tmp_path / "nguon"
    nguon.mkdir()
    cu, moi = "Ten cu [abcdefghijk].wav", "Ten moi [abcdefghijk].wav"
    _ghi_wav(nguon / "a.wav", _giai_dieu(30, seed=41, sr=22050), 22050)
    _ghi_wav(nguon / cu, _giai_dieu(30, seed=42, sr=22050), 22050)
    _ghi_wav(nguon / moi, _giai_dieu(30, seed=43, sr=22050), 22050)
    e.add_kho("A", str(nguon))
    e.build_database(str(nguon), "new")
    truoc = {c["ten"]: c["so_hash"] for c in e.db_clips(bo_cache=True)}
    (nguon / "_hong").mkdir()
    os.replace(nguon / cu, nguon / "_hong" / f"261002-090000_{cu}")

    kq = e.build_database(str(nguon), "add")
    sau = {c["ten"]: c["so_hash"] for c in e.db_clips(bo_cache=True)}

    assert kq.get("da_ghi_kho") is True, kq
    assert sau == {"a.wav": truoc["a.wav"], moi: truoc[moi]}, (truoc, sau)
