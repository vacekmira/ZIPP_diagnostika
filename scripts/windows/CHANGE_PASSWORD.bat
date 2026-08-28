@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist .venv\Scripts\python.exe (
  echo Aplikace neni nainstalovana. Nejprve spustte INSTALL.bat.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m app.cli check-schema
if errorlevel 1 goto :error
python -m app.cli change-password
if errorlevel 1 goto :error
echo Hotovo. Vsichni klienti se musi prihlasit novym heslem.
pause
exit /b 0
:error
echo CHYBA: Heslo nebylo zmeneno.
pause
exit /b 1
