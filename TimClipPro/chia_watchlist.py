# -*- coding: utf-8 -*-
"""chia_watchlist.py — Chia watchlist thành N phần cho N máy chạy song song.

VÌ SAO CẦN

`watch` lọc video đã quét bằng `Engine.ids_da_quet()`, mà hàm đó đọc `lichsu.db`
**cục bộ của từng máy**. Chép nguyên một watchlist sang N máy thì cả N máy cùng
tải và quét đúng những video giống nhau — tốn N lần băng thông và CPU.

Cách rẻ nhất và không cần sửa code là chia danh sách trước: mỗi máy một phần riêng.

    python chia_watchlist.py --so-may 3
    python chia_watchlist.py --so-may 3 --nguon watchlist.json --tien-to may

Sinh ra `watchlist.may1.json`, `watchlist.may2.json`, ... Chép mỗi file sang đúng
một máy rồi đổi tên thành `watchlist.json`, hoặc trỏ thẳng bằng
`cli.py watch --file watchlist.may2.json`.

Chia luân phiên (round-robin) chứ không cắt khối, để các mục nặng/nhẹ rải đều.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from luu_tru import doc_json_an_toan

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def chia_muc(muc: list, so_may: int) -> list[list]:
    """Chia luân phiên; giữ nguyên thứ tự tương đối trong mỗi phần."""
    if so_may < 1:
        raise ValueError("so_may phải >= 1")
    phan: list[list] = [[] for _ in range(so_may)]
    for i, m in enumerate(muc):
        phan[i % so_may].append(m)
    return phan


def chia_watchlist(du_lieu: dict, so_may: int) -> list[dict]:
    """Trả về N watchlist, mỗi cái giữ nguyên `kho` và `gioi_han_moi_lan`."""
    muc = [m for m in du_lieu.get("muc", []) if isinstance(m, dict)]
    bat = [m for m in muc if m.get("bat", True)]
    tat = [m for m in muc if not m.get("bat", True)]
    # Chỉ chia các mục đang BẬT; mục đã tắt giữ nguyên ở phần đầu để không mất.
    ra = []
    for i, phan in enumerate(chia_muc(bat, so_may)):
        d = dict(du_lieu)
        d["muc"] = phan + (tat if i == 0 else [])
        ra.append(d)
    return ra


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--so-may", type=int, required=True, help="Chia cho mấy máy")
    ap.add_argument("--nguon", default="watchlist.json")
    ap.add_argument("--tien-to", default="may",
                    help="Tiền tố tên file ra: watchlist.<tien-to>N.json")
    ap.add_argument("--that-su", action="store_true",
                    help="Ghi file thật; không có cờ này thì chỉ in ra")
    args = ap.parse_args()

    if args.so_may < 1:
        print("[X] --so-may phải >= 1")
        return 1
    if not os.path.isfile(args.nguon):
        print(f"[X] Không thấy {args.nguon}")
        return 1

    du_lieu = doc_json_an_toan(args.nguon, {})
    if not isinstance(du_lieu, dict) or not du_lieu.get("muc"):
        print(f"[X] {args.nguon} không có mục nào")
        return 1

    phan = chia_watchlist(du_lieu, args.so_may)
    tong_bat = sum(1 for m in du_lieu["muc"]
                   if isinstance(m, dict) and m.get("bat", True))
    print(f"Nguồn: {args.nguon} — {len(du_lieu['muc'])} mục "
          f"({tong_bat} đang bật), kho «{du_lieu.get('kho', '')}»\n")

    for i, d in enumerate(phan, 1):
        ten = f"watchlist.{args.tien_to}{i}.json"
        so_bat = sum(1 for m in d["muc"] if m.get("bat", True))
        print(f"  {ten:<26} {len(d['muc'])} mục ({so_bat} bật)")
        for m in d["muc"][:4]:
            print(f"      - {(m.get('ghi_chu') or m.get('url', ''))[:60]}")
        if len(d["muc"]) > 4:
            print(f"      ... và {len(d['muc']) - 4} mục nữa")
        if args.that_su:
            with open(ten, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

    if args.that_su:
        print(f"\n[OK] Đã ghi {len(phan)} file.")
    else:
        print("\n[thử] chưa ghi gì — thêm --that-su để tạo file thật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
