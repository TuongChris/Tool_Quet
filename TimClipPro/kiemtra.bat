@echo off
REM ============================================================
REM  KIEM TRA - chay 1 lenh, copy toan bo ket qua gui lai cho AI
REM  Day la buoc 3 trong vong lap: Spec -> Code -> KIEM TRA -> Fix
REM
REM  Ma thoat: 0 = ca 3 buoc deu dat; khac 0 = co buoc that bai.
REM  Day la CONG KIEM THU: dung duoc trong script/Task Scheduler.
REM
REM  KIEMTRA_PY        (tuy chon) interpreter CO pytest, vi du:
REM                    set KIEMTRA_PY="C:\duong dan\python.exe"
REM                    .venv cua app KHONG cai pytest (requirements-dev.txt).
REM  KIEMTRA_KHONG_DUNG (tuy chon) dat bat ky gia tri -> khong "pause" o cuoi.
REM
REM  Khong dung khoi ngoac ( ) quanh %PY%: duong dan co "(x86)" se pha cu phap.
REM ============================================================
setlocal
cd /d "%~dp0"
set "PY="
if defined KIEMTRA_PY set "PY=%KIEMTRA_PY%"
if not defined PY if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY set "PY=python"
set "LOI=0"
echo Interpreter: %PY%
echo.

echo ===== 1/3: Import sach =====
%PY% -c "import engine, channel, sheets, cli; print('  [OK] Tat ca module import duoc')"
if errorlevel 1 goto :loi_import
goto :buoc_2
:loi_import
echo   [X] LOI IMPORT
set "LOI=1"

:buoc_2
echo.
echo ===== 2/3: Test tu dong =====
%PY% -c "import pytest" >nul 2>nul
if errorlevel 1 goto :thieu_pytest
%PY% -m pytest -q
if errorlevel 1 goto :test_hong
echo   [OK] Test tu dong dat
goto :buoc_3
:thieu_pytest
echo   [X] THIEU PYTEST trong interpreter: %PY%
echo       Dat KIEMTRA_PY tro toi Python co pytest, hoac cai requirements-dev.txt.
set "LOI=1"
goto :buoc_3
:test_hong
echo   [X] CO TEST THAT BAI
set "LOI=1"

:buoc_3
echo.
echo ===== 3/3: Giao dien co render loi khong =====
%PY% -c "import sys; from streamlit.testing.v1 import AppTest; at=AppTest.from_file('app.py',default_timeout=120).run(); e=[str(x.value) for x in at.exception]; print('  [OK] Giao dien sach' if not e else '  [X] LOI GIAO DIEN: '+str(e)); sys.exit(1 if e else 0)"
if errorlevel 1 goto :ui_hong
goto :tong_ket
:ui_hong
echo   [X] GIAO DIEN KHONG DAT
set "LOI=1"

:tong_ket
echo.
echo ============================================================
if "%LOI%"=="0" goto :dat
echo  KET QUA: KHONG DAT - co dong [X] o tren.
echo  Copy TOAN BO man hinh nay gui cho AI.
goto :ket_thuc
:dat
echo  KET QUA: DAT - ca 3 buoc deu qua.
:ket_thuc
echo ============================================================
if not defined KIEMTRA_KHONG_DUNG pause
exit /b %LOI%
