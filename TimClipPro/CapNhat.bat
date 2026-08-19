@echo off
REM ============================================================
REM  CAPNHAT.BAT - lay ban moi nhat tu GitHub theo TAG phien ban
REM
REM  Cach dung:
REM     CapNhat.bat                 -> len ban moi nhat
REM     CapNhat.bat --kiem-tra      -> chi xem, khong doi gi
REM     CapNhat.bat --ban v2.1      -> ve dung mot ban cu (lui phien ban)
REM
REM  KHONG bao gio ghi de du lieu cua ban: kho van tay, cau hinh,
REM  watchlist va google_key.json deu nam ngoai git.
REM ============================================================
cd /d "%~dp0"
title TimClip Pro - cap nhat

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
    echo [LOI] Chua cai Python. Hay chay cai_dat.bat truoc.
    pause
    exit /b 1
)

%PY% cap_nhat.py %*
set "MA=%errorlevel%"

REM Ma thoat 11 = da cap nhat VA danh sach thu vien co thay doi.
REM Khong cai lai thi may se chay ma moi bang thu vien cu - loi rat kho tim.
if "%MA%"=="11" (
    echo.
    echo ===== Cai lai thu vien =====
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [CANH BAO] Cai thu vien that bai. Tool co the khong chay dung.
        echo            Kiem tra mang roi chay lai CapNhat.bat
        pause
        exit /b 1
    )
)

echo.
echo Xong.
if "%~1"=="" pause
exit /b 0
