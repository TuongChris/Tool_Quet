@echo off
cd /d "%~dp0"

if not exist "ketqua" mkdir "ketqua"

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY exit /b 1

%PY% cli.py watch >> "ketqua\giamsat_%date:~-4%%date:~3,2%%date:~0,2%.log" 2>&1
exit /b %errorlevel%
