@echo off
REM ============================================================
REM  CAI_DAT.BAT - chay 1 lan duy nhat
REM  Yeu cau: da cai Python tu python.org (tick "Add to PATH")
REM ============================================================
cd /d "%~dp0"

echo.
echo ===== BUOC 1/4: Kiem tra Python =====
set "BOOT_PY="
py -3.12 --version >nul 2>nul && set "BOOT_PY=py -3.12"
if not defined BOOT_PY py -3 --version >nul 2>nul && set "BOOT_PY=py -3"
if not defined BOOT_PY python --version >nul 2>nul && set "BOOT_PY=python"
if not defined BOOT_PY (
    echo [LOI] Chua cai Python hoac chua tick "Add python.exe to PATH".
    echo       Hay cai Python 3.12 64-bit tu: https://www.python.org/downloads/
    pause
    exit /b 1
)
%BOOT_PY% --version

if not exist ".venv\Scripts\python.exe" (
    echo Dang tao moi truong ao .venv rieng cho du an...
    %BOOT_PY% -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong tao duoc .venv.
        pause
        exit /b 1
    )
)
set "PY=.venv\Scripts\python.exe"
%PY% --version

echo.
echo ===== BUOC 2/4: Cai thu vien Python =====
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [LOI] Cai thu vien that bai. Kiem tra mang roi chay lai.
    pause
    exit /b 1
)

echo.
echo ===== BUOC 3/4: Kiem tra audfprint =====
if exist "audfprint-master\audfprint.py" (
    echo Da co san - bo qua.
) else (
    curl -L -o audfprint.zip https://github.com/dpwe/audfprint/archive/refs/heads/master.zip
    tar -xf audfprint.zip
    del audfprint.zip
)

echo.
echo ===== BUOC 4/4: FFmpeg =====
if not exist "bin" mkdir bin
if exist "bin\ffmpeg.exe" (
    echo Da co san bin\ffmpeg.exe - bo qua.
    goto :kiemtra
)
where ffmpeg >nul 2>nul && (echo He thong da co ffmpeg tren PATH. & goto :kiemtra)
echo Dang tai FFmpeg (~100MB), cho mot chut...
curl -L -o ffmpeg.zip https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
tar -xf ffmpeg.zip
for /d %%D in (ffmpeg-*essentials_build) do (
    copy /y "%%D\bin\ffmpeg.exe"  "bin\" >nul
    copy /y "%%D\bin\ffprobe.exe" "bin\" >nul
    rmdir /s /q "%%D"
)
del ffmpeg.zip
if not exist "bin\ffmpeg.exe" (
    echo [CANH BAO] Tai FFmpeg tu dong that bai.
    echo Neu ban da cai VDF truoc do, hay COPY ffmpeg.exe + ffprobe.exe tu thu muc VDF vao bin\
)

:kiemtra
echo.
echo ===== KIEM TRA TONG THE =====
%PY% -c "import numpy,scipy,docopt,joblib,streamlit,pandas,yt_dlp; print('  [OK] Thu vien Python')" || echo   [X] Thu vien Python
if exist "audfprint-master\audfprint.py" (echo   [OK] audfprint) else (echo   [X] audfprint)
if exist "bin\ffmpeg.exe" (echo   [OK] ffmpeg) else (where ffmpeg >nul 2>nul && echo   [OK] ffmpeg ^(PATH^) || echo   [X] ffmpeg)
echo.
echo CAI DAT XONG! Tiep theo: double-click ChayTool.bat
echo.
pause
