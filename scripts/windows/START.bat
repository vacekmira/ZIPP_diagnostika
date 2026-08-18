@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist .venv\Scripts\python.exe (
  echo Aplikace neni nainstalovana. Nejprve spustte INSTALL.bat.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
alembic upgrade head
if errorlevel 1 (
  echo CHYBA: Databazovou migraci se nepodarilo dokoncit.
  pause
  exit /b 1
)
echo ZIPP Diagnostika bezi na http://127.0.0.1:8000
echo Toto okno ponechte otevrene. Ukonceni: Ctrl+C.
start "" powershell -NoProfile -WindowStyle Hidden -Command "$url='http://127.0.0.1:8000'; for($i=0;$i -lt 40;$i++){try{Invoke-WebRequest -UseBasicParsing ($url + '/health') | Out-Null; Start-Process $url; break}catch{Start-Sleep -Milliseconds 250}}"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
