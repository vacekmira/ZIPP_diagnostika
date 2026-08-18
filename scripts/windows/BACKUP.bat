@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist .venv\Scripts\python.exe (
  echo Aplikace neni nainstalovana.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m scripts.backup
pause
