@echo off
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY exit /b 1

%PY% cli.py watch --log --sheet "https://docs.google.com/spreadsheets/d/13iM9C9PwC6VxNGWZfWhz_MBk4U9lRPtG6uFZvsuOE20/edit?usp=sharing"
set "EXIT_CODE=%errorlevel%"
exit /b %EXIT_CODE%
