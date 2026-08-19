@echo off
REM ============================================================
REM  CHAY TOOL - double-click file nay de mo TimClip Pro
REM  Trinh duyet se tu mo tai http://localhost:8501
REM  Dong cua so den nay = tat tool.
REM ============================================================
cd /d "%~dp0"
title TimClip Pro - dang chay (dong cua so nay de tat tool)

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
    echo [LOI] Chua cai Python. Hay chay cai_dat.bat truoc.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo [CANH BAO] Dang dung Python he thong. Nen chay cai_dat.bat de tao .venv rieng.
)

REM Tu cap nhat truoc khi mo. Loi o day KHONG duoc chan tool chay:
REM cap_nhat.py luon thoat 0 khi bo qua/that bai, chi tra 10-11 khi DA doi ban.
REM
REM Vi sao phai khoi dong lai: git checkout co the thay chinh file .bat nay, ma cmd
REM doc file lenh theo vi tri byte trong luc chay -> doi giua chung la chay loan.
REM Da cap nhat thi mo lai chinh minh roi thoat, khong chay tiep bang noi dung cu.
if not "%~1"=="--da-cap-nhat" (
    echo.
    echo   Dang kiem tra ban moi...
    %PY% cap_nhat.py
    if errorlevel 11 %PY% -m pip install -r requirements.txt
    if errorlevel 10 (
        echo   Da cap nhat - dang mo lai...
        start "" "%~f0" --da-cap-nhat
        exit /b 0
    )
)

echo.
echo   TimClip Pro dang khoi dong...
echo   Trinh duyet se tu mo. Neu khong, hay vao: http://localhost:8501
echo.
%PY% -m streamlit run app.py --browser.gatherUsageStats=false --server.port=8501
pause
