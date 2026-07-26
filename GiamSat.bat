@echo off
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY exit /b 1

%PY% cli.py watch --log --sheet ""
set "EXIT_CODE=%errorlevel%"
exit /b %EXIT_CODE%
