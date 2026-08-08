@echo off
REM ============================================================
REM  CHAYMAYPHU.BAT - chay giam sat tu dong tren may phu
REM  Dung cho Task Scheduler. Khong mo giao dien, ghi log ra file.
REM
REM  Tham so tuy chon: ten file watchlist
REM     ChayMayPhu.bat                        -> watchlist.json
REM     ChayMayPhu.bat watchlist.may2.json    -> file chi dinh
REM ============================================================
cd /d "%~dp0"

set "WL=%~1"
if "%WL%"=="" set "WL=watchlist.json"

if not exist "%WL%" (
    echo [LOI] Khong thay %WL%. Xem docs\TRIEN_KHAI_MAY_PHU.md
    exit /b 1
)

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
    echo [LOI] Chua cai Python. Chay cai_dat.bat truoc.
    exit /b 1
)

REM Chi bat Google Sheets khi that su co khoa tren may nay.
REM Khoa KHONG nam trong goi - phai tu chep sang bang kenh rieng.
set "THAM_SO=--log --file "%WL%""
if exist "google_key.json" (
    if defined SHEET_LINK (
        set "THAM_SO=%THAM_SO% --sheet "%SHEET_LINK%""
    )
)

echo [%date% %time%] Bat dau giam sat voi %WL%
%PY% cli.py watch %THAM_SO%
set "EXIT_CODE=%errorlevel%"
echo [%date% %time%] Ket thuc, ma thoat %EXIT_CODE%
exit /b %EXIT_CODE%
