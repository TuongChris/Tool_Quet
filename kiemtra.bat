@echo off
REM ============================================================
REM  KIEM TRA - chay 1 lenh, copy toan bo ket qua gui lai cho AI
REM  Day la buoc 3 trong vong lap: Spec -> Code -> KIEM TRA -> Fix
REM ============================================================
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY set "PY=python"

echo ===== 1/3: Import sach =====
%PY% -c "import engine, channel, sheets, cli; print('  [OK] Tat ca module import duoc')" || echo   [X] LOI IMPORT

echo.
echo ===== 2/3: Test tu dong =====
%PY% -m pytest -q

echo.
echo ===== 3/3: Giao dien co render loi khong =====
%PY% -c "from streamlit.testing.v1 import AppTest; at=AppTest.from_file('app.py',default_timeout=120).run(); e=[str(x.value) for x in at.exception]; print('  [OK] Giao dien sach' if not e else '  [X] LOI GIAO DIEN: '+str(e))"

echo.
echo ============================================================
echo  Xong. Neu co dong [X], copy TOAN BO man hinh nay gui cho AI.
echo ============================================================
pause
