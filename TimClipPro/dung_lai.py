# -*- coding: utf-8 -*-
"""Gom tín hiệu dừng từ hệ điều hành, Engine và file điều khiển."""

from __future__ import annotations

import os
import signal
from typing import Any


class YeuCauDung:
    """Gom mọi nguồn tín hiệu dừng về một chỗ."""

    def __init__(self, engine: Any = None, file_dung: str = "") -> None:
        self.engine = engine
        self.file_dung = file_dung
        self._da_dat = False
        self._so_tin_hieu = 0

    def bat_tin_hieu(self) -> None:
        """Đăng ký Ctrl+C và SIGTERM; tín hiệu đầu chỉ đặt cờ dừng."""
        def handler(signum, frame):
            self._so_tin_hieu += 1
            if self._so_tin_hieu >= 2:
                raise KeyboardInterrupt
            self.dat()

        signal.signal(signal.SIGINT, handler)
        sigterm = getattr(signal, "SIGTERM", None)
        if sigterm is not None:
            signal.signal(sigterm, handler)

    def can_dung(self) -> bool:
        """Kiểm cờ nội bộ, cờ Engine, rồi file dừng theo thứ tự chi phí."""
        if self._da_dat:
            return True
        cancel_event = getattr(self.engine, "cancel_event", None)
        if cancel_event is not None and cancel_event.is_set():
            return True
        return bool(self.file_dung and os.path.exists(self.file_dung))

    def dat(self) -> None:
        """Đặt cờ nội bộ và chuyển yêu cầu xuống Engine nếu có."""
        self._da_dat = True
        cancel_event = getattr(self.engine, "cancel_event", None)
        if cancel_event is not None:
            cancel_event.set()

    def don_file_dung(self) -> None:
        """Xóa file dừng nếu có để lượt sau không bị dừng oan."""
        if not self.file_dung:
            return
        try:
            os.remove(self.file_dung)
        except FileNotFoundError:
            pass
