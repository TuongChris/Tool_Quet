# -*- coding: utf-8 -*-
"""Mô hình dữ liệu và lưu trữ danh sách nguồn YouTube cần theo dõi."""

import contextlib
from dataclasses import asdict, dataclass, field
import os
import re
from typing import Any, Callable, Optional

import bang_ngang
from channel import ChannelSync
from don_dep import don_job_quet, don_kho_dem
from khoa import DangChayRoi, KhoaTienTrinh
from luu_tru import doc_json_an_toan, ghi_json_an_toan
from sheets import SheetsExporter
from truy_cap_youtube import PhienYouTube
from ytdlp_chung import giai_thich_loi


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
    # Lượt không chạy vì một tác vụ khác đang giữ `tool.lock` — "bận", không phải lỗi
    # (CLI thoát mã 2 để lịch chạy phân biệt được; phản biện vòng 3).
    ban: bool = False
    # YouTube chặn truy cập (bot-check, 429, đăng nhập/403 lặp lại…): cầu dao đã mở và lượt
    # DỪNG gửi request. Video chưa quét KHÔNG được tính là đã quét (CLI thoát mã 3).
    chan_youtube: str = ""
    chua_quet_do_chan: int = 0
    youtube: dict = field(default_factory=dict)      # số đo truy cập YouTube của lượt

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
        if self.chan_youtube:
            cac_dong.append(f"Chưa quét vì YouTube chặn truy cập: {self.chua_quet_do_chan}")
            cac_dong.append(f"YouTube: {self.chan_youtube}")
        if self.youtube.get("youtube_operations"):
            so = self.youtube
            cac_dong.append(
                f"Truy cập YouTube: {so.get('youtube_operations', 0)} thao tác, "
                f"{so.get('retries', 0)} lần thử lại, bot-check {so.get('bot_challenges', 0)}, "
                f"429 {so.get('rate_limited', 0)}, 403 {so.get('http_403', 0)}, "
                f"cần đăng nhập {so.get('auth_failures', 0)}")
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
    lay_ids = getattr(engine, "ids_da_quet", None)
    if callable(lay_ids):
        return lay_ids(chi_thanh_cong=chi_thanh_cong)

    ket_qua = set()
    for job in engine.list_jobs(limit=100_000):
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
    phien: Optional[PhienYouTube] = None,
) -> tuple:
    """
    Mở rộng watchlist thành danh sách ứng viên.
    lister: hàm (url, limit) -> list[VideoInfo]. None thì dùng ChannelSync.list_channel.
    Trả về (danh_sach_ung_vien, danh_sach_loi).
    danh_sach_loi: list[str], mỗi phần tử là một dòng mô tả lỗi.

    ``phien``: phiên YouTube của lượt Watch — liệt kê một kênh bị chặn/429 thì không hỏi tiếp
    các kênh còn lại.
    """
    if lister is None:
        lister = ChannelSync.list_channel

    ung_vien = []
    loi = []
    bo_qua_kenh = 0
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
            if phien is not None and phien.mo:
                bo_qua_kenh += 1
                continue
            try:
                video_trong_kenh = lister(muc.url, gioi_han_kenh)
            except Exception as e:  # noqa: BLE001
                if phien is not None:
                    phien.ghi_loi(e, "listing")
                loi.append(f"Không lấy được video từ kênh {muc.url}: {giai_thich_loi(e)}")
                continue
            for video in video_trong_kenh:
                ung_vien.append(UngVien(
                    video_id=video.id,
                    url=video.url,
                    tieu_de=getattr(video, "title", "") or "",
                    nguon=muc.url,
                ))

    if bo_qua_kenh:
        loi.append(f"Chưa liệt kê {bo_qua_kenh} kênh: {phien.thong_bao_dung()}")
    return ung_vien, loi


@contextlib.contextmanager
def _mo_phien(engine: Any):
    """Một phiên YouTube cho cả lượt Watch: mọi ``scan_youtube`` (mỗi video một job) dùng chung
    một cầu dao. Engine giả trong test không có phiên thì dùng phiên cục bộ."""
    mo = getattr(engine, "mo_phien_youtube", None)
    if callable(mo):
        with mo() as phien:
            if isinstance(phien, PhienYouTube):
                yield phien
                return
    yield PhienYouTube()


def _la_loi_youtube(kq: Any) -> bool:
    """Kết quả hỏng vì YouTube (bị chặn, cần đăng nhập, gỡ, mạng…): không phải kết quả quét."""
    return getattr(kq, "loi_truy_cap", None) is not None


def _lister_theo_cau_hinh(engine: Any) -> Callable:
    """`(url, limit) -> list[VideoInfo]` mang theo cookie và nhịp tải của engine.

    Giữ đúng chữ ký hai đối số mà `mo_rong_watchlist` mong đợi để test vẫn thay được
    bằng bản giả.
    """
    lay_cau_hinh = getattr(engine, "cau_hinh_mang", None)
    cau_hinh = lay_cau_hinh() if callable(lay_cau_hinh) else None

    def lister(url: str, limit: Optional[int] = None) -> list:
        return ChannelSync.list_channel(url, limit, cau_hinh_mang=cau_hinh)

    return lister


def chay_giam_sat(
    engine: Any,
    wl: WatchList,
    progress: Optional[Callable] = None,
    lister: Optional[Callable] = None,
    sheet_link: str = "",
    dang_ngang: bool = True,
    dung_lai: Any = None,
    quet_lai: bool = False,
) -> BaoCao:
    """Chạy một lượt giám sát đầy đủ.

    ``quet_lai=True``: quét lại cả video lịch sử nói đã kiểm xong với kho này (ví dụ
    sau khi nghi kết quả cũ). Không xoá lịch sử — lượt mới chỉ thêm dòng.
    """
    # Vòng giám sát chạy lặp lại theo lịch nên là nơi tích luỹ nguy cơ bị YouTube coi
    # là bot cao nhất. `mo_rong_watchlist` mặc định dùng `ChannelSync.list_channel`
    # trần, tức mất cookie và mất nhịp người dùng đã đặt; dựng sẵn lister mang cấu
    # hình của engine ngay tại đây — chỗ gần nhất còn nhìn thấy `engine`.
    if lister is None:
        lister = _lister_theo_cau_hinh(engine)
    try:
        with KhoaTienTrinh(
            os.path.join(engine.data_dir, "tool.lock"),
            "giám sát",
        ), _mo_phien(engine) as phien:
            return _chay_giam_sat_da_khoa(
                engine,
                wl,
                progress=progress,
                lister=lister,
                sheet_link=sheet_link,
                dang_ngang=dang_ngang,
                dung_lai=dung_lai,
                quet_lai=quet_lai,
                phien=phien,
            )
    except DangChayRoi as e:
        return BaoCao(loi=[str(e)], ban=True)


def _chay_giam_sat_da_khoa(
    engine: Any,
    wl: WatchList,
    progress: Optional[Callable] = None,
    lister: Optional[Callable] = None,
    sheet_link: str = "",
    dang_ngang: bool = True,
    dung_lai: Any = None,
    quet_lai: bool = False,
    phien: Optional[PhienYouTube] = None,
) -> BaoCao:
    """Thực hiện lượt giám sát sau khi caller đã giữ khóa liên tiến trình."""
    bao_cao = BaoCao()
    phien = phien if phien is not None else PhienYouTube()
    try:
        return _thuc_hien_giam_sat(
            engine,
            wl,
            bao_cao,
            progress=progress,
            lister=lister,
            sheet_link=sheet_link,
            dang_ngang=dang_ngang,
            dung_lai=dung_lai,
            quet_lai=quet_lai,
            phien=phien,
        )
    finally:
        bao_cao.youtube = phien.tom_tat()
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

        # Máy chạy watch theo lịch là nơi rác job tích luỹ nhanh nhất: quét liên
        # tục hàng đêm, và mỗi lượt bị ngắt giữa chừng để lại vài GB chunk WAV.
        # Bọc riêng try để lỗi ở đây không nuốt mất kết quả dọn kho đệm ở trên.
        try:
            ket_qua_job = don_job_quet(
                os.path.join(engine.data_dir, "scan_jobs"),
                max_ngay=engine.config.dem_max_ngay,
            )
            bao_cao.da_don_gb += ket_qua_job["xoa_gb"]
            bao_cao.loi.extend(
                f"Dọn thư mục job: {dong}"
                for dong in ket_qua_job["loi"]
            )
        except Exception as e:  # noqa: BLE001
            bao_cao.loi.append(f"Không dọn được thư mục job: {e}")


def _db_theo_so(engine: Any, ten: str) -> str:
    """File vân tay của kho ``ten`` theo sổ đăng ký — CHỈ ĐỌC; rỗng nếu không tra được
    (khi đó ``use_kho`` tự báo lỗi đúng nguyên nhân mà không ghi gì)."""
    doc_so = getattr(engine, "_doc_khos", None)
    duong_dan = getattr(engine, "_duong_dan_db_kho", None)
    if not (callable(doc_so) and callable(duong_dan)):
        return ""
    try:
        kho = next((k for k in doc_so().get("danh_sach", []) if k.get("ten") == ten), None)
        return duong_dan(kho.get("db")) if kho else ""
    except Exception:  # noqa: BLE001
        return ""


def _kho_khong_dung_duoc(engine: Any, wl: WatchList) -> str:
    """Lý do KHÔNG được quét lượt này; chuỗi rỗng = kho dùng được.

    * Watchlist chỉ định kho: phải mở được ĐÚNG kho đó và kho đã có vân tay.
    * Không chỉ định: dùng kho đang chọn trong sổ đăng ký — nhưng Engine lặng lẽ lùi về
      ``data/db.pklz`` khi sổ hỏng hoặc kho đang chọn không mở được; quét như vậy là đối
      chiếu nhầm kho (phản biện TCP-08). So sổ với kho Engine đang mở để phát hiện.
    """
    if wl.kho:
        # Kiểm file vân tay TRƯỚC khi `use_kho` ghi «kho đang dùng» vào sổ: lượt bị dừng
        # không được đổi kho mà giao diện đang chọn (phản biện vòng 2).
        db = _db_theo_so(engine, wl.kho)
        if db and not os.path.isfile(db):
            return (f"Kho «{wl.kho}» chưa có vân tay ({os.path.basename(db)} chưa được "
                    "tạo) — hãy tạo kho trước.")
        try:
            engine.use_kho(wl.kho)
        except Exception as e:  # noqa: BLE001
            return f"Không dùng được kho «{wl.kho}»: {str(e).rstrip('. ')}."
        dang_mo = getattr(engine, "kho_dang_dung", wl.kho)
        if dang_mo != wl.kho:
            return f"Không dùng được kho «{wl.kho}» (đang mở «{dang_mo}»)."
        db = getattr(engine, "db_file", "")
        if db and not os.path.isfile(db):
            return (f"Kho «{wl.kho}» chưa có vân tay ({os.path.basename(db)} chưa được "
                    "tạo) — hãy tạo kho trước.")
        return ""
    doc_so = getattr(engine, "_doc_khos", None)
    if not callable(doc_so):
        return ""
    try:
        so = doc_so()
    except Exception as e:  # noqa: BLE001
        return f"Không đọc được sổ đăng ký kho: {str(e).rstrip('. ')}."
    if not so.get("danh_sach"):
        # Sổ trống. Chưa từng tạo kho (cài mới) thì không có kho nào để nhầm — lượt quét
        # tự báo thiếu kho vân tay như cũ. Nhưng sổ trống vì vừa HỎNG hoặc MẤT (còn
        # khos.json.hong.* / khos.json.bak) thì Engine đang lùi về data/db.pklz: quét như
        # vậy là đối chiếu nhầm kho (phản biện vòng 2 + 3).
        vua_hong = getattr(engine, "_so_kho_vua_hong", None)
        if not (callable(vua_hong) and vua_hong()):
            return ""
        chi_tiet = " ".join(getattr(engine, "canh_bao_khoi_dong", None) or [])
        return ("Sổ đăng ký kho đã hỏng — không có kho nào dùng được."
                + (f" {chi_tiet}" if chi_tiet else ""))
    yeu_cau = so.get("dang_dung") or ""
    dang_mo = getattr(engine, "kho_dang_dung", "")
    if not yeu_cau or dang_mo != yeu_cau:
        return (f"Kho đang chọn trong sổ đăng ký («{yeu_cau or 'trống'}») không mở được — "
                f"Engine đang dùng «{dang_mo or 'kho mặc định data/db.pklz'}».")
    db = getattr(engine, "db_file", "")
    if db and not os.path.isfile(db):
        return (f"Kho «{yeu_cau}» chưa có vân tay ({os.path.basename(db)} chưa được tạo) — "
                "hãy tạo kho trước.")
    return ""


def _thuc_hien_giam_sat(
    engine: Any,
    wl: WatchList,
    bao_cao: BaoCao,
    progress: Optional[Callable] = None,
    lister: Optional[Callable] = None,
    sheet_link: str = "",
    dang_ngang: bool = True,
    dung_lai: Any = None,
    quet_lai: bool = False,
    phien: Optional[PhienYouTube] = None,
) -> BaoCao:
    """Quét nguồn, xuất CSV và đẩy Sheets trong một lượt giám sát.

    Một phiên YouTube cho cả lượt: bị nghi là bot / 429 / đòi đăng nhập lặp lại thì DỪNG phần
    mạng — video chưa quét không được tính là đã quét (không lịch sử, không CSV, không Sheets)
    và lượt sau quét lại. Kết quả hỏng vì YouTube không bao giờ thành dòng trên Sheets.
    """
    if phien is None:
        phien = PhienYouTube()
    # Kho không dùng được thì DỪNG cả lượt trước mọi thao tác (audit TCP-08). Trước đây
    # chỉ ghi một dòng lỗi rồi quét tiếp bằng kho đang chọn từ trước: đối chiếu sai kho,
    # xuất CSV và đẩy Sheets như thể đúng kho.
    ly_do = _kho_khong_dung_duoc(engine, wl)
    if ly_do:
        bao_cao.loi.append(
            f"{ly_do} Đã dừng lượt giám sát: không liệt kê, không tải, không quét, không "
            "xuất CSV hay Google Sheets — để không quét nhầm bằng kho khác."
        )
        return bao_cao

    ung_vien, loi = lay_ung_vien(wl, lister=lister, phien=phien)
    bao_cao.loi.extend(loi)
    # Lịch sử chỉ tính video đã kiểm XONG với đúng kho này (audit TCP-07).
    da_quet = set() if quet_lai else id_da_quet(engine)
    can_quet = loc_can_quet(ung_vien, da_quet, wl.gioi_han_moi_lan)
    bao_cao.tong_ung_vien = len(ung_vien)
    bao_cao.da_quet_truoc = len(ung_vien) - len(can_quet)

    ket_qua = []
    tong_can_quet = len(can_quet)
    ghi_tung_phan = bool(
        getattr(engine.config, "ghi_tung_phan", True)
    )
    sheets = None
    da_kiem_tra_sheets = False
    da_day_sheets: set[int] = set()

    def khoi_tao_sheets():
        nonlocal sheets, da_kiem_tra_sheets
        if da_kiem_tra_sheets or not sheet_link:
            return sheets
        da_kiem_tra_sheets = True
        try:
            ung_dung_sheets = SheetsExporter(sheet=sheet_link)
            if not ung_dung_sheets.san_sang():
                bao_cao.sheets_note = (
                    ung_dung_sheets.thieu_gi()
                    or "Google Sheets chưa sẵn sàng."
                )
                return None
            sheets = ung_dung_sheets
            bao_cao.sheets_ok = True
            return sheets
        except Exception as e:  # noqa: BLE001
            bao_cao.sheets_note = f"Lỗi kết nối Google Sheets: {e}"
            return None

    def chuyen_dong_sheets(ds: list) -> tuple[list, list]:
        if dang_ngang:
            return bang_ngang.HEADER_NGANG, engine.to_rows_ngang(ds)
        return engine.HEADER, engine.to_rows(ds)

    def day_tung_phan(kq: Any) -> None:
        ung_dung_sheets = khoi_tao_sheets()
        if ung_dung_sheets is None:
            return
        header, rows = chuyen_dong_sheets([kq])
        if not rows:
            da_day_sheets.add(id(kq))
            return
        try:
            so_dong = ung_dung_sheets.append(header, rows)
            bao_cao.sheets_so_dong += so_dong
            if so_dong > 0:
                da_day_sheets.add(id(kq))
        except Exception as e:  # noqa: BLE001
            ten_nguon = kq.source_name or kq.source_ref or "(không rõ nguồn)"
            bao_cao.loi.append(
                f"Không ghi được kết quả từng phần lên Google Sheets "
                f"cho {ten_nguon}: {e}"
            )

    def dung_neu_duoc_yeu_cau(so_con_lai: int) -> bool:
        if dung_lai is None or not dung_lai.can_dung():
            return False
        bao_cao.loi.append(
            "Đã dừng theo yêu cầu; "
            f"còn {so_con_lai} video chưa quét."
        )
        return True

    for i, ung_vien_moi in enumerate(can_quet):
        if dung_neu_duoc_yeu_cau(tong_can_quet - i):
            break
        if phien.mo:
            # Cầu dao mở: KHÔNG chạy tiếp hàng chục video vào đúng bức tường đó. Video còn lại
            # không vào lịch sử/CSV/Sheets — lượt Watch sau quét lại chúng.
            bao_cao.chua_quet_do_chan = tong_can_quet - i
            bao_cao.chan_youtube = phien.thong_bao_dung()
            bao_cao.loi.append(
                f"{bao_cao.chan_youtube} Còn {tong_can_quet - i} video chưa quét.")
            break

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
            phien.ghi_loi(e, "scan")
            bao_cao.loi.append(
                f"Không quét được {ung_vien_moi.url}: {giai_thich_loi(e)}"
            )
            if dung_neu_duoc_yeu_cau(tong_can_quet - i - 1):
                break
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
        # Lỗi YouTube (bị chặn, cần đăng nhập, gỡ, mạng) không phải kết quả quét: không đẩy
        # dòng "(LỖI…)" lên Sheets — giao diện cũng chỉ đẩy kết quả `ok` (app.py).
        if sheet_link and ghi_tung_phan and not _la_loi_youtube(ket_qua_quet):
            day_tung_phan(ket_qua_quet)
        if dung_neu_duoc_yeu_cau(tong_can_quet - i - 1):
            break

    if phien.mo and not bao_cao.chan_youtube:
        # Cầu dao mở ở chính video cuối: vẫn phải nói rõ lượt này đã bị YouTube chặn.
        bao_cao.chan_youtube = phien.thong_bao_dung()

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
            ung_dung_sheets = khoi_tao_sheets()
            if ung_dung_sheets is not None:
                hop_le = [kq for kq in ket_qua if not _la_loi_youtube(kq)]
                chua_day = (
                    [kq for kq in hop_le if id(kq) not in da_day_sheets]
                    if ghi_tung_phan
                    else hop_le
                )
                if chua_day or not ghi_tung_phan:
                    header, rows = chuyen_dong_sheets(chua_day)
                    if rows or not ghi_tung_phan:
                        bao_cao.sheets_so_dong += ung_dung_sheets.append(
                            header,
                            rows,
                        )
        except Exception as e:  # noqa: BLE001
            bao_cao.sheets_ok = False
            bao_cao.sheets_note = f"Lỗi ghi Google Sheets: {e}"

    return bao_cao
