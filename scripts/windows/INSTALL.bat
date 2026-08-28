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
  >>.env echo SESSION_COOKIE_SECURE=false
  >>.env echo SESSION_MAX_AGE=604800
)
python -m app.cli ensure-session-secret --env .env
if errorlevel 1 goto :error
if exist "%DATA_ROOT%\db\zipp.sqlite3" (
  echo Vytvarim povinnou zalohu pred migraci...
  python -m scripts.backup --prefix preinstall
  if errorlevel 1 goto :error
)
alembic upgrade head
if errorlevel 1 goto :error
python -m app.cli ensure-password
if errorlevel 1 goto :error
python -m app.cli check-schema
if errorlevel 1 goto :error
echo.
echo Instalace Alpha 2 dokoncena. Spustte START.bat.
pause
exit /b 0
:error
echo CHYBA: Instalace nebyla dokoncena. Existujici data ani zalohy nebyly smazany.
pause
exit /b 1
