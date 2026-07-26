# -*- coding: utf-8 -*-
"""Mô hình dữ liệu và lưu trữ danh sách nguồn YouTube cần theo dõi."""

from dataclasses import asdict, dataclass, field
import os
import re
from typing import Any, Callable, Optional

import bang_ngang
from channel import ChannelSync
from don_dep import don_kho_dem
from khoa import DangChayRoi, KhoaTienTrinh
from luu_tru import doc_json_an_toan, ghi_json_an_toan
from sheets import SheetsExporter


@dataclass
class MucTheoDoi:
    loai: str
    url: str
    ghi_chu: str = ""
    bat: bool = True


@dataclass
class WatchList:
    muc: list = field(default_factory=list)
    kho: str = ""
    gioi_han_moi_lan: int = 20


@dataclass
class UngVien:
    video_id: str
    url: str
    tieu_de: str = ""
    nguon: str = ""


@dataclass
class BaoCao:
    tong_ung_vien: int = 0
    da_quet_truoc: int = 0
    quet_moi: int = 0
    nguon_co_vi_pham: int = 0
    tong_bang_chung: int = 0
    da_don_file: int = 0
    da_don_gb: float = 0.0
    csv_path: str = ""
    sheets_ok: bool = False
    sheets_so_dong: int = 0
    sheets_note: str = ""
    loi: list = field(default_factory=list)

    def tom_tat(self) -> str:
        """Trả về bản tóm tắt nhiều dòng, tiếng Việt, để in ra console hoặc gửi email."""
        loi_csv = any(
            dong.startswith("Không xuất được CSV:")
            for dong in self.loi
        )
        if self.csv_path:
            trang_thai_csv = self.csv_path
        elif loi_csv:
            trang_thai_csv = "Lỗi (xem chi tiết bên dưới)"
        else:
            trang_thai_csv = "Không có dữ liệu để ghi"

        if self.sheets_ok:
            trang_thai_sheets = (
                f"Đã ghi {self.sheets_so_dong} dòng"
                if self.sheets_so_dong > 0
                else "Không có dữ liệu để ghi"
            )
        else:
            trang_thai_sheets = self.sheets_note or "Không sử dụng"

        cac_dong = [
            f"Tổng ứng viên: {self.tong_ung_vien}",
            f"Đã quét trước: {self.da_quet_truoc}",
            f"Quét mới: {self.quet_moi}",
            f"Nguồn có vi phạm: {self.nguon_co_vi_pham}",
            f"Tổng bằng chứng: {self.tong_bang_chung}",
            (
                f"Đã dọn kho đệm: {self.da_don_file} file "
                f"({self.da_don_gb:.3f} GB)"
            ),
            f"File CSV: {trang_thai_csv}",
            f"Google Sheets: {trang_thai_sheets}",
        ]
        if self.loi:
            cac_dong.append("Lỗi:")
            cac_dong.extend(f"- {dong}" for dong in self.loi)
        return "\n".join(cac_dong)


_MAU_ID_YOUTUBE = (
    re.compile(
        r"^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{6,20})(?=$|[?&#/])",
        re.IGNORECASE,
    ),
    re.compile(
        r"^https?://(?:www\.)?youtube\.com/watch\?"
        r"(?:[^&#]+&)*v=([A-Za-z0-9_-]{6,20})(?=$|[&#])",
        re.IGNORECASE,
    ),
    re.compile(
        r"^https?://(?:www\.)?youtube\.com/shorts/"
        r"([A-Za-z0-9_-]{6,20})(?=$|[?&#/])",
        re.IGNORECASE,
    ),
)


def lay_id_youtube(url: str) -> str:
    """Tách ID video từ URL YouTube. Trả về "" nếu không nhận dạng được."""
    for mau in _MAU_ID_YOUTUBE:
        ket_qua = mau.search(url.strip())
        if ket_qua:
            return ket_qua.group(1)
    return ""


def doc_watchlist(path: str) -> WatchList:
    """Đọc watchlist.json; file hỏng không phục hồi được sẽ ném LoiDuLieu."""
    du_lieu = doc_json_an_toan(path, {})

    if not isinstance(du_lieu, dict):
        return WatchList()

    du_lieu_muc = du_lieu.get("muc", [])
    if not isinstance(du_lieu_muc, list):
        du_lieu_muc = []

    cac_muc = []
    for muc in du_lieu_muc:
        if not isinstance(muc, dict):
            continue
        loai = muc.get("loai")
        url = muc.get("url")
        if loai not in {"kenh", "link"} or not isinstance(url, str) or not url.strip():
            continue
        ghi_chu = muc.get("ghi_chu", "")
        bat = muc.get("bat", True)
        cac_muc.append(MucTheoDoi(
            loai=loai,
            url=url,
            ghi_chu=ghi_chu if isinstance(ghi_chu, str) else "",
            bat=bat if isinstance(bat, bool) else True,
        ))

    kho = du_lieu.get("kho", "")
    gioi_han = du_lieu.get("gioi_han_moi_lan", 20)
    return WatchList(
        muc=cac_muc,
        kho=kho if isinstance(kho, str) else "",
        gioi_han_moi_lan=(
            gioi_han
            if isinstance(gioi_han, int) and not isinstance(gioi_han, bool)
            else 20
        ),
    )


def ghi_watchlist(wl: WatchList, path: str) -> None:
    """Ghi watchlist.json, encoding utf-8, ensure_ascii=False, indent=2."""
    du_lieu = {
        "muc": [asdict(muc) for muc in wl.muc],
        "kho": wl.kho,
        "gioi_han_moi_lan": wl.gioi_han_moi_lan,
    }
    ghi_json_an_toan(path, du_lieu)


def id_da_quet(engine: Any, chi_thanh_cong: bool = True) -> set:
    """Trả về set các video_id đã quét, đọc từ lịch sử SQLite."""
    ket_qua = set()
    for job in engine.list_jobs(limit=100000):
        if chi_thanh_cong and job.get("status") != "ok":
            continue
        video_id = job.get("source_id")
        if video_id:
            ket_qua.add(video_id)
    return ket_qua


def loc_can_quet(ung_vien: list, da_quet: set, gioi_han: int = 0) -> list:
    """Lọc ra các ứng viên CHƯA quét. Hàm thuần — không chạm engine, không I/O."""
    ket_qua = []
    da_gap = set()
    for muc in ung_vien:
        video_id = muc.video_id
        if not video_id or video_id in da_quet or video_id in da_gap:
            continue
        da_gap.add(video_id)
        ket_qua.append(muc)
        if gioi_han > 0 and len(ket_qua) >= gioi_han:
            break
    return ket_qua


def lay_ung_vien(
    wl: WatchList,
    lister: Optional[Callable] = None,
    gioi_han_kenh: int = 50,
) -> tuple:
    """
    Mở rộng watchlist thành danh sách ứng viên.
    lister: hàm (url, limit) -> list[VideoInfo]. None thì dùng ChannelSync.list_channel.
    Trả về (danh_sach_ung_vien, danh_sach_loi).
    danh_sach_loi: list[str], mỗi phần tử là một dòng mô tả lỗi.
    """
    if lister is None:
        lister = ChannelSync.list_channel

    ung_vien = []
    loi = []
    for muc in wl.muc:
        if not muc.bat:
            continue

        if muc.loai == "link":
            video_id = lay_id_youtube(muc.url)
            if not video_id:
                loi.append(f"Không nhận dạng được ID video YouTube từ URL: {muc.url}")
                continue
            ung_vien.append(UngVien(
                video_id=video_id,
                url=muc.url,
                tieu_de="",
                nguon=muc.url,
            ))
            continue

        if muc.loai == "kenh":
            try:
                video_trong_kenh = lister(muc.url, gioi_han_kenh)
            except Exception as e:  # noqa: BLE001
                loi.append(f"Không lấy được video từ kênh {muc.url}: {e}")
                continue
            for video in video_trong_kenh:
                ung_vien.append(UngVien(
                    video_id=video.id,
                    url=video.url,
                    tieu_de=getattr(video, "title", "") or "",
                    nguon=muc.url,
                ))

    return ung_vien, loi


def chay_giam_sat(
    engine: Any,
    wl: WatchList,
    progress: Optional[Callable] = None,
    lister: Optional[Callable] = None,
    sheet_link: str = "",
    dang_ngang: bool = True,
) -> BaoCao:
    """Chạy một lượt giám sát đầy đủ."""
    try:
        with KhoaTienTrinh(
            os.path.join(engine.data_dir, "giamsat.lock"),
            "giám sát",
        ):
            return _chay_giam_sat_da_khoa(
                engine,
                wl,
                progress=progress,
                lister=lister,
                sheet_link=sheet_link,
                dang_ngang=dang_ngang,
            )
    except DangChayRoi as e:
        return BaoCao(loi=[str(e)])


def _chay_giam_sat_da_khoa(
    engine: Any,
    wl: WatchList,
    progress: Optional[Callable] = None,
    lister: Optional[Callable] = None,
    sheet_link: str = "",
    dang_ngang: bool = True,
) -> BaoCao:
    """Thực hiện lượt giám sát sau khi caller đã giữ khóa liên tiến trình."""
    bao_cao = BaoCao()
    try:
        return _thuc_hien_giam_sat(
            engine,
            wl,
            bao_cao,
            progress=progress,
            lister=lister,
            sheet_link=sheet_link,
            dang_ngang=dang_ngang,
        )
    finally:
        try:
            ket_qua_don = don_kho_dem(
                engine.dl_dir,
                max_gb=engine.config.dem_max_gb,
                max_ngay=engine.config.dem_max_ngay,
            )
            bao_cao.da_don_file = ket_qua_don["xoa_file"]
            bao_cao.da_don_gb = ket_qua_don["xoa_gb"]
            bao_cao.loi.extend(
                f"Dọn kho đệm: {dong}"
                for dong in ket_qua_don["loi"]
            )
        except Exception as e:  # noqa: BLE001
            bao_cao.loi.append(f"Không dọn được kho đệm: {e}")


def _thuc_hien_giam_sat(
    engine: Any,
    wl: WatchList,
    bao_cao: BaoCao,
    progress: Optional[Callable] = None,
    lister: Optional[Callable] = None,
    sheet_link: str = "",
    dang_ngang: bool = True,
) -> BaoCao:
    """Quét nguồn, xuất CSV và đẩy Sheets trong một lượt giám sát."""
    if wl.kho:
        try:
            engine.use_kho(wl.kho)
        except Exception as e:  # noqa: BLE001
            bao_cao.loi.append(f"Không dùng được kho «{wl.kho}»: {e}")

    ung_vien, loi = lay_ung_vien(wl, lister=lister)
    bao_cao.loi.extend(loi)
    da_quet = id_da_quet(engine)
    can_quet = loc_can_quet(ung_vien, da_quet, wl.gioi_han_moi_lan)
    bao_cao.tong_ung_vien = len(ung_vien)
    bao_cao.da_quet_truoc = len(ung_vien) - len(can_quet)

    ket_qua = []
    tong_can_quet = len(can_quet)
    for i, ung_vien_moi in enumerate(can_quet):
        def bao_tien_do(pct: float, msg: str, i: int = i) -> None:
            if progress is not None:
                progress(
                    (i + pct) / tong_can_quet,
                    f"[{i + 1}/{tong_can_quet}] {msg}",
                )

        bao_cao.quet_moi += 1
        try:
            ket_qua_quet = engine.scan_youtube(
                ung_vien_moi.url,
                progress=bao_tien_do,
            )
        except Exception as e:  # noqa: BLE001
            bao_cao.loi.append(
                f"Không quét được {ung_vien_moi.url}: {e}"
            )
            continue

        ket_qua.append(ket_qua_quet)
        if ket_qua_quet.matches:
            bao_cao.nguon_co_vi_pham += 1
            bao_cao.tong_bang_chung += len(ket_qua_quet.matches)
        if ket_qua_quet.status != "ok":
            ten_nguon = (
                ket_qua_quet.source_name
                or ung_vien_moi.tieu_de
                or ung_vien_moi.url
            )
            bao_cao.loi.append(f"{ten_nguon}: {ket_qua_quet.note}")

    if ket_qua:
        try:
            bao_cao.csv_path = (
                engine.export_csv_ngang(ket_qua)
                if dang_ngang
                else engine.export_csv(ket_qua)
            )
        except Exception as e:  # noqa: BLE001
            bao_cao.loi.append(f"Không xuất được CSV: {e}")

    if sheet_link:
        try:
            sheets = SheetsExporter(sheet=sheet_link)
            if not sheets.san_sang():
                bao_cao.sheets_note = (
                    sheets.thieu_gi() or "Google Sheets chưa sẵn sàng."
                )
            else:
                if dang_ngang:
                    header = bang_ngang.HEADER_NGANG
                    rows = engine.to_rows_ngang(ket_qua)
                else:
                    header = engine.HEADER
                    rows = engine.to_rows(ket_qua)
                bao_cao.sheets_so_dong = sheets.append(header, rows)
                bao_cao.sheets_ok = True
        except Exception as e:  # noqa: BLE001
            bao_cao.sheets_note = f"Lỗi ghi Google Sheets: {e}"

    return bao_cao
