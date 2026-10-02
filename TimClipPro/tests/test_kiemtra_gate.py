# -*- coding: utf-8 -*-
"""``kiemtra.bat`` là CỔNG KIỂM THỬ: thất bại ở bất kỳ bước nào phải thành mã thoát
khác 0 (audit TCP-16). Chạy thật qua ``cmd.exe`` trên một dự án giả, đường dẫn có
dấu cách — không chỉ tìm chữ ``[X]`` trong output.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="kiemtra.bat chỉ chạy trên Windows")

GOC = Path(__file__).resolve().parents[1]


def _du_an_gia(tmp_path, *, loi_import=False, test_hong=False, ui_hong=False) -> Path:
    du_an = tmp_path / "du an co dau cach"
    (du_an / "tests").mkdir(parents=True)
    shutil.copyfile(GOC / "kiemtra.bat", du_an / "kiemtra.bat")
    for ten in ("engine", "channel", "sheets", "cli"):
        (du_an / f"{ten}.py").write_text("X = 1\n", encoding="utf-8")
    if loi_import:
        (du_an / "engine.py").write_text(
            "raise ImportError('hong gia lap')\n", encoding="utf-8")
    (du_an / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (du_an / "tests" / "test_mau.py").write_text(
        "def test_mau():\n    assert " + ("False" if test_hong else "True") + "\n",
        encoding="utf-8")
    (du_an / "app.py").write_text(
        "import streamlit as st\n"
        + ("raise RuntimeError('giao dien hong gia lap')\n" if ui_hong
           else "st.write('ok')\n"),
        encoding="utf-8")
    return du_an


def _chay(du_an: Path, py: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["KIEMTRA_PY"] = py if py is not None else f'"{sys.executable}"'
    env["KIEMTRA_KHONG_DUNG"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        ["cmd.exe", "/d", "/c", str(du_an / "kiemtra.bat")],
        cwd=du_an, env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600,
    )


def test_tat_ca_dat_thi_ma_thoat_0(tmp_path):
    r = _chay(_du_an_gia(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[OK] Tat ca module import duoc" in r.stdout
    assert "[OK] Test tu dong dat" in r.stdout
    assert "[OK] Giao dien sach" in r.stdout


@pytest.mark.parametrize("hong", ["loi_import", "test_hong", "ui_hong"])
def test_mot_buoc_hong_thi_ma_thoat_khac_0(tmp_path, hong):
    r = _chay(_du_an_gia(tmp_path, **{hong: True}))
    assert r.returncode != 0, r.stdout + r.stderr
    assert "[X]" in r.stdout


def test_thieu_pytest_la_loi_khong_duoc_bo_qua(tmp_path):
    # `-I -S` bỏ cả PYTHONPATH lẫn site-packages: cùng interpreter nhưng không có
    # pytest/streamlit — đúng tình trạng `.venv` của app (không cài pytest).
    r = _chay(_du_an_gia(tmp_path), py=f'"{sys.executable}" -I -S')
    assert r.returncode != 0, r.stdout + r.stderr
    assert "THIEU PYTEST" in r.stdout
