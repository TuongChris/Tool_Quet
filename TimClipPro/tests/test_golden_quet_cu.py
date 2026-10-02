# -*- coding: utf-8 -*-
"""Hành vi CŨ của đường quét phải giữ nguyên từng bước (golden master).

Dữ liệu trong ``tests/golden/`` được sinh trên commit f87cc85 — trước khi thêm chế độ
«một video gốc chung cho cả lô». Chế độ mới chen vào đúng các điểm quyết định dừng sớm /
tải tiếp / bù tốc độ, nên đây là lưới an toàn chính: nhánh cũ (không truyền mục tiêu) phải
cho ra CÙNG chuỗi lời gọi tải, cắt khúc, so khớp, đổi tốc độ, CÙNG thông điệp tiến độ, CÙNG
kết quả, chẩn đoán và dòng lịch sử.

Sinh lại (chỉ khi hành vi cũ được CỐ Ý đổi, kèm lý do): ``TIMCLIP_GHI_GOLDEN=1``.
"""

import json
import os

import pytest

from golden_quet import BIEN_GHI_GOLDEN, GOLDEN_DIR, KICH_BAN, chay_kich_ban


@pytest.mark.parametrize("kb", KICH_BAN, ids=[k.ten for k in KICH_BAN])
def test_hanh_vi_quet_cu_khop_golden(kb, tmp_path, monkeypatch):
    ghi = chay_kich_ban(kb, tmp_path, monkeypatch)
    duong = os.path.join(GOLDEN_DIR, f"{kb.ten}.json")
    if os.environ.get(BIEN_GHI_GOLDEN) == "1":
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(duong, "w", encoding="utf-8", newline="\n") as f:
            json.dump(ghi, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        pytest.skip("đã ghi golden")
    with open(duong, encoding="utf-8") as f:
        mong_doi = json.load(f)
    assert ghi == mong_doi


def test_moi_kich_ban_golden_deu_co_file():
    """Thêm kịch bản mà quên sinh golden thì phải đỏ, không được lặng lẽ bỏ qua."""
    co = {os.path.splitext(x)[0] for x in os.listdir(GOLDEN_DIR) if x.endswith(".json")}
    assert {k.ten for k in KICH_BAN} == co
