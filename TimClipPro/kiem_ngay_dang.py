# -*- coding: utf-8 -*-
"""Audit và sửa ngày đăng trong clips_meta.json của một kho clip gốc.

Mặc định **chỉ đọc**. Chỉ ghi khi có ``--apply``.

Vì sao cần công cụ này
======================
Metadata cũ được ghi bằng ``upload_date`` của yt-dlp — là ngày theo lịch **UTC**.
Với người dùng ở ``Asia/Ho_Chi_Minh``, video phát hành từ 17:00 UTC trở đi đã
sang ngày hôm sau, nên ngày lưu bị lệch một ngày. Xem
``docs/PUBLICATION_DATE_ARCHITECTURE.md``.

Giới hạn quan trọng của repair offline
=====================================
Entry cũ **chỉ lưu chuỗi ``YYYYMMDD``**, không lưu epoch. Không có giờ thì
không thể biết video phát hành lúc 09:00 hay 20:00 UTC, tức **không thể** biết
ngày giờ Việt Nam có lệch hay không. Vì vậy ``--repair-offline`` chỉ sửa được
entry đã lưu sẵn ``timestamp``/``release_timestamp``; phần còn lại bắt buộc
``--repair-network``. Công cụ này tuyệt đối không đoán.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field

from channel import ChannelSync
from clip_metadata import extract_youtube_id, filename_fallback_parts
from publication_date import (
    MUI_GIO_MAC_DINH,
    TRUONG_EPOCH,
    format_publication_date,
    ngay_tu_chuoi,
    resolve_publication_date,
)

# Chỉ nguồn suy từ epoch mới đủ chắc để khỏi hỏi lại YouTube.
TRUONG_DO_TIN_CAY_CAO = frozenset(TRUONG_EPOCH)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


@dataclass
class ThongKe:
    tong: int = 0
    co_provenance: int = 0          # đã có publication_date + nguồn
    chi_upload_date: int = 0        # schema cũ, không biết giờ
    co_epoch_luu_san: int = 0       # sửa được offline
    thieu_ngay: int = 0
    can_xem_lai: list = field(default_factory=list)
    se_doi: list = field(default_factory=list)
    mo_ho: list = field(default_factory=list)


def _doc_meta(kho: str) -> tuple[ChannelSync, dict]:
    cs = ChannelSync(kho)
    return cs, cs.load_meta()


def audit(kho: str, mui_gio: str) -> ThongKe:
    _cs, meta = _doc_meta(kho)
    tk = ThongKe(tong=len(meta))

    for ten, entry in meta.items():
        if not isinstance(entry, dict):
            tk.mo_ho.append((ten, "entry không phải object"))
            continue

        co_epoch = any(
            isinstance(entry.get(k), (int, float)) and entry.get(k)
            for k in ("release_timestamp", "timestamp")
        )
        if co_epoch:
            tk.co_epoch_luu_san += 1
        if entry.get("publication_date_source"):
            tk.co_provenance += 1

        ngay_luu = ngay_tu_chuoi(entry.get("publication_date") or entry.get("upload_date"))
        if ngay_luu is None:
            tk.thieu_ngay += 1
            continue
        if not co_epoch and not entry.get("publication_date_source"):
            tk.chi_upload_date += 1

        ket_qua = resolve_publication_date(entry, mui_gio)
        if ket_qua.date and ket_qua.date != ngay_luu:
            tk.se_doi.append((ten, ngay_luu, ket_qua.date, ket_qua.source_field))

        ngay_ten_file = ngay_tu_chuoi(str(filename_fallback_parts(ten).get("upload_date") or ""))
        if ngay_ten_file and ngay_ten_file != ngay_luu:
            tk.can_xem_lai.append((ten, "ngày trong tên file khác ngày metadata"))

    return tk


def in_audit(kho: str, tk: ThongKe, mui_gio: str) -> None:
    print(f"Kho:                          {kho}")
    print(f"Múi giờ hiển thị:             {mui_gio}")
    print(f"Tổng clip:                    {tk.tong}")
    print(f"Đã có nguồn gốc ngày:         {tk.co_provenance}")
    print(f"Chỉ có upload_date (cũ):      {tk.chi_upload_date}")
    print(f"Có epoch lưu sẵn:             {tk.co_epoch_luu_san}")
    print(f"Thiếu ngày:                   {tk.thieu_ngay}")
    print(f"Sẽ đổi nếu repair:            {len(tk.se_doi)}")
    print(f"Cần xem lại:                  {len(tk.can_xem_lai)}")
    print(f"Mơ hồ:                        {len(tk.mo_ho)}")

    if tk.se_doi:
        print("\nVí dụ record sẽ đổi:")
        for ten, cu, moi, nguon in tk.se_doi[:10]:
            print(f"  {format_publication_date(cu)} -> {format_publication_date(moi)}"
                  f"  [{nguon}]  {ten[:58]}")

    if tk.chi_upload_date:
        print(
            f"\nLƯU Ý: {tk.chi_upload_date} clip chỉ có upload_date (không có giờ) nên "
            "KHÔNG thể biết ngày giờ Việt Nam có lệch hay không nếu chỉ dùng dữ liệu "
            "đã lưu. Muốn chắc chắn phải chạy --repair-network."
        )


def _fetcher_mac_dinh(video_id: str, timeout: int = 30) -> dict:
    return ChannelSync.lay_info_video(video_id, timeout)


def repair(
    kho: str,
    mui_gio: str,
    dung_mang: bool,
    apply: bool,
    gioi_han: int,
    fetcher=None,
    nghi_giay: float = 0.0,
    progress=None,
    dung_sau_n_loi: int = 25,
) -> dict:
    """Sửa ngày đăng. ``nghi_giay`` giãn nhịp gọi mạng để tránh bị chặn bot.

    ``dung_sau_n_loi``: gặp bấy nhiêu lỗi LIÊN TIẾP thì dừng sớm. YouTube chặn
    chống bot sẽ làm mọi request sau đó đều hỏng; cố chạy tiếp chỉ tốn thời gian
    và khiến bị chặn nặng hơn. Entry lỗi không bị ghi gì nên lần chạy sau tiếp
    tục được từ chỗ dở.
    """
    cs, meta = _doc_meta(kho)
    fetcher = fetcher or _fetcher_mac_dinh

    khong_doi = da_doi = bo_qua = that_bai = 0
    loi_lien_tiep = 0
    dung_som = False
    loi: list[str] = []
    thay_doi: list[tuple] = []
    da_xu_ly = 0

    for ten, entry in list(meta.items()):
        if gioi_han and da_xu_ly >= gioi_han:
            break
        if not isinstance(entry, dict):
            bo_qua += 1
            continue

        nguon_du_lieu = dict(entry)
        # Chỉ bỏ qua khi đã có nguồn ĐỘ TIN CẬY CAO (suy từ epoch). Nếu chỉ dựa
        # trên upload_date thì vẫn phải hỏi lại: chuỗi YYYYMMDD không có giờ nên
        # không thể biết ngày giờ Việt Nam có lệch hay không. Nếu không, một lượt
        # repair offline chạy trước sẽ vô tình khoá luôn những entry cần sửa nhất.
        da_chac_chan = entry.get("publication_date_source") in TRUONG_DO_TIN_CAY_CAO
        if dung_mang and not da_chac_chan:
            video_id = str(entry.get("id") or "") or (extract_youtube_id(ten) or "")
            if not video_id:
                bo_qua += 1
                continue
            da_xu_ly += 1
            if nghi_giay > 0 and da_xu_ly > 1:
                time.sleep(nghi_giay)
            if progress:
                progress(da_xu_ly, ten)
            try:
                nguon_du_lieu = fetcher(video_id)
            except Exception as e:  # noqa: BLE001
                that_bai += 1
                loi_lien_tiep += 1
                loi.append(f"{ten}: {type(e).__name__}: {str(e)[:160]}")
                if loi_lien_tiep >= dung_sau_n_loi:
                    dung_som = True
                    break
                continue
            loi_lien_tiep = 0
        else:
            da_xu_ly += 1

        ket_qua = resolve_publication_date(nguon_du_lieu, mui_gio)
        if ket_qua.date is None:
            bo_qua += 1
            continue

        ngay_cu = ngay_tu_chuoi(entry.get("publication_date") or entry.get("upload_date"))
        if ngay_cu == ket_qua.date and da_chac_chan:
            khong_doi += 1
            continue

        if ngay_cu != ket_qua.date:
            thay_doi.append((ten, ngay_cu, ket_qua.date, ket_qua.source_field))
            da_doi += 1
        else:
            khong_doi += 1

        entry["publication_date"] = ket_qua.yyyymmdd
        entry["publication_date_source"] = ket_qua.source_field or ""
        entry["upload_date"] = ket_qua.yyyymmdd     # tương thích bản đọc cũ
        for k in ("timestamp", "release_timestamp"):
            if isinstance(nguon_du_lieu.get(k), (int, float)) and nguon_du_lieu.get(k):
                entry[k] = nguon_du_lieu[k]

    if apply and (da_doi or khong_doi):
        goc = os.path.join(kho, "clips_meta.json")
        if os.path.isfile(goc):
            bk = f"{goc}.truoc_ngay_dang_{time.strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(goc, bk)
            print(f"Đã sao lưu -> {bk}")
        cs.save_meta(meta)      # ghi nguyên tử qua luu_tru.ghi_json_an_toan

    return {
        "khong_doi": khong_doi,
        "da_doi": da_doi,
        "bo_qua": bo_qua,
        "that_bai": that_bai,
        "loi": loi,
        "thay_doi": thay_doi,
        "da_ghi": bool(apply),
        "dung_som": dung_som,
        "con_lai": max(0, len(meta) - da_xu_ly),
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Audit/sửa ngày đăng trong clips_meta.json (mặc định chỉ đọc)."
    )
    p.add_argument("--kho", required=True, help="Thư mục kho clip gốc.")
    p.add_argument("--mui-gio", default=MUI_GIO_MAC_DINH)
    p.add_argument("--audit", action="store_true", help="Chỉ thống kê, không ghi.")
    p.add_argument("--repair-offline", action="store_true",
                   help="Chỉ dùng dữ liệu đã lưu, không gọi mạng.")
    p.add_argument("--repair-network", action="store_true",
                   help="Hỏi lại YouTube cho clip chưa có nguồn gốc ngày.")
    p.add_argument("--apply", action="store_true",
                   help="Thực sự ghi. Thiếu cờ này là dry-run.")
    p.add_argument("--limit", type=int, default=0, help="Chỉ xử lý N clip đầu (0 = tất cả).")
    p.add_argument("--nghi", type=float, default=1.5,
                   help="Giây nghỉ giữa hai lần gọi mạng. Quá nhanh sẽ bị YouTube "
                        "chặn chống bot. Mặc định 1.5.")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    if not os.path.isdir(a.kho):
        p.error(f"Không thấy thư mục kho: {a.kho}")
    if a.repair_offline and a.repair_network:
        p.error("Chọn một trong --repair-offline hoặc --repair-network.")
    if a.apply and not (a.repair_offline or a.repair_network):
        p.error("--apply chỉ hợp lệ cùng một chế độ repair.")
    if not (a.audit or a.repair_offline or a.repair_network):
        a.audit = True

    if a.audit:
        tk = audit(a.kho, a.mui_gio)
        if a.json:
            print(json.dumps({
                "tong": tk.tong, "co_provenance": tk.co_provenance,
                "chi_upload_date": tk.chi_upload_date,
                "co_epoch_luu_san": tk.co_epoch_luu_san,
                "thieu_ngay": tk.thieu_ngay, "se_doi": len(tk.se_doi),
                "can_xem_lai": len(tk.can_xem_lai), "mo_ho": len(tk.mo_ho),
            }, ensure_ascii=False, indent=2))
        else:
            in_audit(a.kho, tk, a.mui_gio)
        return 0

    che_do = "APPLY" if a.apply else "DRY-RUN"
    mang = "CÓ gọi mạng" if a.repair_network else "KHÔNG gọi mạng"
    print(f"Chế độ: {che_do} | {mang} | kho: {a.kho}")

    def bao(so, ten):
        if so % 25 == 0 or so == 1:
            print(f"  [{so}] {ten[:60]}", flush=True)

    kq = repair(
        a.kho, a.mui_gio, a.repair_network, a.apply, a.limit,
        nghi_giay=a.nghi if a.repair_network else 0.0,
        progress=bao if a.repair_network else None,
    )
    print(f"\nKhông đổi:  {kq['khong_doi']}")
    print(f"Sẽ đổi/đã đổi: {kq['da_doi']}")
    print(f"Bỏ qua:     {kq['bo_qua']}")
    print(f"Thất bại:   {kq['that_bai']}")
    print(f"Đã ghi:     {kq['da_ghi']}")
    if kq["dung_som"]:
        print(
            f"\nDỪNG SỚM: quá nhiều lỗi liên tiếp — nhiều khả năng YouTube đang chặn "
            f"chống bot. Còn {kq['con_lai']} clip chưa xử lý.\n"
            f"Hãy chờ 30–60 phút rồi chạy lại đúng lệnh này: clip đã sửa sẽ được bỏ "
            f"qua, chạy tiếp từ chỗ dở. Cân nhắc tăng --nghi."
        )
    for ten, cu, moi, nguon in kq["thay_doi"][:15]:
        print(f"  {format_publication_date(cu) or '(trống)'} -> "
              f"{format_publication_date(moi)}  [{nguon}]  {ten[:56]}")
    for e in kq["loi"][:10]:
        print(f"  LỖI: {e}")
    if not a.apply:
        print("\nDry-run: chưa ghi gì. Thêm --apply để thực sự cập nhật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
