# -*- coding: utf-8 -*-
"""Ghi song song console và file log, đồng thời quản lý thời hạn lưu log."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from typing import IO, Optional


# Các dòng yt-dlp in THẲNG ra sys.stderr (không qua logger nên cờ `quiet` không chặn
# được) mà nội dung chính là bí mật. Điển hình:
#     WARNING: skipping cookie file entry due to invalid length 1: '.youtube.com ... __Secure-1PSID <giá trị>'
# Chỉ một dòng cookies.txt sai định dạng — hay gặp khi mở bằng Notepad làm TAB thành
# dấu cách — là giá trị phiên đăng nhập bị ghi vào ketqua/giamsat_*.log, file giữ 30
# ngày nằm chung thư mục với CSV mà người dùng hay nén gửi đi khi nhờ hỗ trợ.
# `ytdlp_chung.kiem_tra_file_cookie()` đã chặn từ đầu nguồn; đây là lớp thứ hai, phòng
# khi yt-dlp thêm cảnh báo tương tự hoặc file bị đổi giữa chừng.
TIEN_TO_CAN_CHE = (
    "WARNING: skipping cookie file entry",
    "WARNING: Failed to parse cookie",
)
THAY_THE = "[đã ẩn: dòng này chứa nội dung cookie]"


def che_bi_mat(noi_dung: str) -> str:
    """Thay các dòng chứa bí mật bằng ghi chú, giữ nguyên phần còn lại.

    Cắt theo từng dòng chứ không bỏ cả khối, để thông tin chẩn đoán khác không mất.
    """
    if not any(t in noi_dung for t in TIEN_TO_CAN_CHE):
        return noi_dung
    ra = []
    for dong in noi_dung.splitlines(keepends=True):
        if any(t in dong for t in TIEN_TO_CAN_CHE):
            ra.append(THAY_THE + ("\n" if dong.endswith("\n") else ""))
        else:
            ra.append(dong)
    return "".join(ra)


class _GhiSongSong:
    def __init__(self, man_hinh: IO[str], file_log: IO[str]) -> None:
        self.man_hinh = man_hinh
        self.file_log = file_log
        self._da_bao_loi = False

    @property
    def encoding(self) -> Optional[str]:
        return getattr(self.man_hinh, "encoding", None)

    def write(self, noi_dung: str) -> int:
        noi_dung = che_bi_mat(noi_dung)
        ket_qua = self.man_hinh.write(noi_dung)
        try:
            self.file_log.write(noi_dung)
        except OSError as e:
            if not self._da_bao_loi:
                self._da_bao_loi = True
                self.man_hinh.write(
                    f"\n[Cảnh báo] Không ghi tiếp được file nhật ký: {e}\n"
                )
        return ket_qua if isinstance(ket_qua, int) else len(noi_dung)

    def flush(self) -> None:
        self.man_hinh.flush()
        try:
            self.file_log.flush()
        except OSError:
            pass

    def isatty(self) -> bool:
        return bool(
            getattr(self.man_hinh, "isatty", lambda: False)()
        )


_STDOUT_GOC: Optional[IO[str]] = None
_STDERR_GOC: Optional[IO[str]] = None
_FILE_LOG: Optional[IO[str]] = None


def _don_log_cu(
    thu_muc: str,
    ten: str,
    giu_ngay: int,
    bay_gio: datetime,
) -> None:
    if giu_ngay <= 0:
        return
    tien_to = ten + "_"
    try:
        entries = list(os.scandir(thu_muc))
    except OSError as e:
        print(f"[Cảnh báo] Không quét được thư mục nhật ký: {e}", file=sys.stderr)
        return

    for entry in entries:
        if (
            not entry.is_file(follow_symlinks=False)
            or not entry.name.startswith(tien_to)
            or not entry.name.endswith(".log")
        ):
            continue
        chuoi_ngay = entry.name[len(tien_to):-4]
        try:
            ngay_file = datetime.strptime(chuoi_ngay, "%Y-%m-%d").date()
        except ValueError:
            continue
        if bay_gio.date() - ngay_file <= timedelta(days=giu_ngay):
            continue
        try:
            os.remove(entry.path)
        except OSError as e:
            print(
                f"[Cảnh báo] Không xóa được nhật ký cũ {entry.path}: {e}",
                file=sys.stderr,
            )


def mo_nhat_ky(
    thu_muc: str,
    ten: str = "giamsat",
    giu_ngay: int = 30,
) -> str:
    """Bật ghi song song ra màn hình và file log theo ngày, đồng thời dọn log cũ."""
    dong_nhat_ky()
    bay_gio = datetime.now()
    thu_muc_log = os.path.abspath(thu_muc)
    path = os.path.join(
        thu_muc_log,
        f"{ten}_{bay_gio.strftime('%Y-%m-%d')}.log",
    )
    try:
        os.makedirs(thu_muc_log, exist_ok=True)
    except OSError as e:
        print(f"[Cảnh báo] Không tạo được thư mục nhật ký: {e}", file=sys.stderr)
        return path

    _don_log_cu(thu_muc_log, ten, giu_ngay, bay_gio)
    try:
        file_log = open(path, "a", encoding="utf-8")
    except OSError as e:
        print(f"[Cảnh báo] Không mở được file nhật ký {path}: {e}", file=sys.stderr)
        return path

    global _STDOUT_GOC, _STDERR_GOC, _FILE_LOG
    _STDOUT_GOC = sys.stdout
    _STDERR_GOC = sys.stderr
    _FILE_LOG = file_log
    sys.stdout = _GhiSongSong(_STDOUT_GOC, file_log)
    sys.stderr = _GhiSongSong(_STDERR_GOC, file_log)
    return path


def dong_nhat_ky() -> None:
    """Khôi phục stdout/stderr về ban đầu và đóng file log."""
    global _STDOUT_GOC, _STDERR_GOC, _FILE_LOG
    if _STDOUT_GOC is None and _STDERR_GOC is None and _FILE_LOG is None:
        return

    stdout_goc = _STDOUT_GOC
    stderr_goc = _STDERR_GOC
    file_log = _FILE_LOG
    _STDOUT_GOC = None
    _STDERR_GOC = None
    _FILE_LOG = None
    if stdout_goc is not None:
        sys.stdout = stdout_goc
    if stderr_goc is not None:
        sys.stderr = stderr_goc
    if file_log is not None:
        try:
            file_log.flush()
        except OSError:
            pass
        try:
            file_log.close()
        except OSError as e:
            print(
                f"[Cảnh báo] Không đóng sạch được file nhật ký: {e}",
                file=sys.stderr,
            )
