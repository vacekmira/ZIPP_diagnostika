@echo off
setlocal
cd /d "%~dp0\..\.."
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo CHYBA: Python 3.10 nebo novejsi nebyl nalezen.
  echo Nainstalujte Python z python.org a zaskrtnete Add Python to PATH.
  pause
  exit /b 1
)
if not exist .venv %PY% -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
if errorlevel 1 goto :error
set "DATA_ROOT=%LOCALAPPDATA%\ZippDiagnostics"
if not exist "%DATA_ROOT%\db" mkdir "%DATA_ROOT%\db"
if not exist "%DATA_ROOT%\backups" mkdir "%DATA_ROOT%\backups"
if not exist .env (
  >.env echo APP_HOST=127.0.0.1
  >>.env echo APP_PORT=8000
  >>.env echo DATABASE_PATH=%DATA_ROOT%\db\zipp.sqlite3
  >>.env echo BACKUP_PATH=%DATA_ROOT%\backups
  >>.env echo PUBLIC_URL=
  >>.env echo DEBUG=false
  >>.env echo BACKUP_RETENTION=30
)
alembic upgrade head
if errorlevel 1 goto :error
echo.
echo Instalace dokoncena. Spustte START.bat.
pause
exit /b 0
:error
echo CHYBA: Instalace nebyla dokoncena. Existujici data nebyla smazana.
pause
exit /b 1
