# -*- coding: utf-8 -*-
"""Khóa liên tiến trình dựa trên cơ chế khóa file của hệ điều hành."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import IO, Optional


class DangChayRoi(Exception):
    """Đã có tiến trình khác đang giữ khóa."""


def _lay_khoa_windows(f: IO[str]) -> None:
    import msvcrt

    f.seek(0)
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)


def _nha_khoa_windows(f: IO[str]) -> None:
    import msvcrt

    f.seek(0)
    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def _lay_khoa_posix(f: IO[str]) -> None:
    import fcntl

    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _nha_khoa_posix(f: IO[str]) -> None:
    import fcntl

    fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class KhoaTienTrinh:
    """Context manager giữ khóa độc quyền giữa các tiến trình."""

    def __init__(self, path: str, ten: str = ""):
        self.path = os.path.abspath(path)
        self.ten = ten
        self._file: Optional[IO[str]] = None
        self._thong_tin = ""

    @property
    def thong_tin_chu_khoa(self) -> str:
        """Mô tả tiến trình đang giữ khóa để đưa vào thông báo lỗi."""
        if self._thong_tin.strip():
            return self._thong_tin.strip()
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                f.seek(1)
                thong_tin = f.read().strip()
        except OSError:
            return "Không đọc được thông tin tiến trình đang giữ khóa."
        return thong_tin or "Không có thông tin tiến trình đang giữ khóa."

    def __enter__(self) -> "KhoaTienTrinh":
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        f = open(self.path, "a+", encoding="utf-8")
        self._file = f
        try:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            f.seek(1)
            thong_tin_truoc_khi_khoa = f.read().strip()
        except BaseException:
            f.close()
            self._file = None
            raise
        try:
            if sys.platform.startswith("win"):
                _lay_khoa_windows(f)
            else:
                _lay_khoa_posix(f)
        except OSError as e:
            self._thong_tin = thong_tin_truoc_khi_khoa
            f.close()
            self._file = None
            raise DangChayRoi(
                "Đã có tiến trình khác đang chạy. "
                f"Thông tin khóa: {self.thong_tin_chu_khoa}"
            ) from e

        try:
            self._thong_tin = (
                f"PID: {os.getpid()}\n"
                f"Thời điểm: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Tác vụ: {self.ten or 'không ghi tên'}"
            )
            f.seek(1)
            f.truncate(1)
            f.write(self._thong_tin + "\n")
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *a) -> None:
        f = self._file
        self._file = None
        if f is None:
            return
        try:
            try:
                if sys.platform.startswith("win"):
                    _nha_khoa_windows(f)
                else:
                    _nha_khoa_posix(f)
            except OSError:
                pass
        finally:
            f.close()
