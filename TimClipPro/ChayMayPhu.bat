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

REM May phu chay khong nguoi truc nen phai tu lay ban moi. cap_nhat.py dat
REM GIT_TERMINAL_PROMPT=0 va BatchMode=yes nen khong bao gio treo cho nhap mat khau.
REM
REM Da cap nhat thi THOAT ngay, bo qua luot giam sat nay: git checkout co the vua thay
REM chinh file .bat dang chay, ma cmd doc file theo vi tri byte -> chay tiep se loan.
REM Task Scheduler se goi lai theo lich va luot sau chay bang ma moi.
%PY% cap_nhat.py
if errorlevel 11 %PY% -m pip install -r requirements.txt
if errorlevel 10 (
    echo [%date% %time%] Da cap nhat ban moi - bo qua luot nay, luot sau chay ma moi.
    exit /b 0
)

echo [%date% %time%] Bat dau giam sat voi %WL%
%PY% cli.py watch %THAM_SO%
set "EXIT_CODE=%errorlevel%"
echo [%date% %time%] Ket thuc, ma thoat %EXIT_CODE%
exit /b %EXIT_CODE%
