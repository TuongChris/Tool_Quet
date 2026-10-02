# -*- coding: utf-8 -*-
"""Kho vân tay ``.pklz`` HỢP LỆ cho test — ``HashTable`` thật của audfprint, rất nhỏ.

Từ khi Engine kiểm kho tạm trước khi công bố (audit TCP-02), một file "kho" chứa
chuỗi rác không còn được chấp nhận. Các audfprint giả trong test dùng helper này để
ghi đúng định dạng thật, giữ nguyên ý nghĩa của test.

``pickle`` ở đây chỉ chạm file do CHÍNH test ghi trong thư mục tạm.
"""

import gzip
import os
import pickle
import sys
from pathlib import Path

_THU_MUC_AUDFPRINT = str(Path(__file__).resolve().parents[1] / "audfprint-master")
if _THU_MUC_AUDFPRINT not in sys.path:
    sys.path.insert(0, _THU_MUC_AUDFPRINT)

import hash_table  # noqa: E402


def _bang_moi():
    return hash_table.HashTable(hashbits=4, depth=2, maxtime=16)


def _ghi(ht, path) -> bytes:
    with gzip.open(path, "wb") as f:
        pickle.dump(ht, f)
    return Path(path).read_bytes()


def ghi_kho(path, muc) -> bytes:
    """``muc`` = [(tên/đường dẫn clip, số hash)]; 0 hash = clip không tạo được vân tay."""
    ht = _bang_moi()
    for ten, so in muc:
        ht.store(str(ten), [(t % 16, t % 16) for t in range(int(so))])
    return _ghi(ht, path)


def ghi_kho_tu_lenh(command, so_hash: int = 5, loi=()) -> bytes:
    """Ghi kho tạm theo đúng lệnh build mà Engine gửi (``--dbase``, ``--list``,
    ``new``/``add``). Clip trong ``loi`` (tên hoặc đường dẫn) nhận 0 hash."""
    db = command[command.index("--dbase") + 1]
    ds = [p for p in Path(command[command.index("--list") + 1])
          .read_text(encoding="utf-8").splitlines() if p]
    sub = next((x for x in command if x in ("new", "add")), "new")
    if sub == "add" and os.path.exists(db):
        with gzip.open(db, "rb") as f:
            ht = pickle.load(f)
    else:
        ht = _bang_moi()
    loi = set(loi)
    for p in ds:
        n = 0 if (p in loi or os.path.basename(p) in loi) else so_hash
        ht.store(p, [(t % 16, t % 16) for t in range(n)])
    return _ghi(ht, db)


MA_GHI_KHO_TRONG_PROCESS_CON = r'''
import gzip as _gzip, pickle as _pickle, sys as _sys
_sys.path.insert(0, {thu_muc_audfprint!r})
import hash_table as _hash_table
def _ghi_kho_hop_le(db_file, cac_file, so_hash=5):
    ht = _hash_table.HashTable(hashbits=4, depth=2, maxtime=16)
    for p in cac_file:
        ht.store(p, [(t % 16, t % 16) for t in range(so_hash)])
    with _gzip.open(db_file, "wb") as fh:
        _pickle.dump(ht, fh)
'''


def ma_ghi_kho_cho_process_con() -> str:
    """Đoạn mã chèn vào audfprint giả chạy ở PROCESS CON: định nghĩa
    ``_ghi_kho_hop_le(db_file, cac_file, so_hash=5)``."""
    return MA_GHI_KHO_TRONG_PROCESS_CON.format(thu_muc_audfprint=_THU_MUC_AUDFPRINT)
