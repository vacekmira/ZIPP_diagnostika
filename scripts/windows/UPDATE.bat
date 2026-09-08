@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist .venv\Scripts\python.exe (
  echo Aplikace neni nainstalovana. Spustte INSTALL.bat.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
echo Vytvarim povinnou a overenou predaktualizacni zalohu...
python -m scripts.backup --prefix preupdate
if errorlevel 1 goto :error
where git >nul 2>nul
if errorlevel 1 (
  echo CHYBA: Git nebyl nalezen. Kod aktualizujte z noveho release balicku a spustte tento skript znovu.
  goto :error
)
git pull --ff-only
if errorlevel 1 goto :error
python -m pip install -e ".[test]"
if errorlevel 1 goto :error
python -m app.cli ensure-session-secret --env .env
if errorlevel 1 goto :error
alembic upgrade head
if errorlevel 1 goto :error
python -m app.cli ensure-password
if errorlevel 1 goto :error
python -m app.cli check-schema
if errorlevel 1 goto :error
python -c "from app.main import health; result=health(); assert result['status']=='ok'; print('Health check:', result)"
if errorlevel 1 goto :error
echo Aktualizace na Alpha 9, migrace a kontrola databaze byly dokonceny. Spustte START.bat.
pause
exit /b 0
:error
echo CHYBA: Aktualizace byla zastavena. Databaze ani zaloha nebyly smazany.
pause
exit /b 1
