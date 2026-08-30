#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Spusťte pomocí sudo."; exit 1; fi

SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE=/etc/zipp-diagnostics/docker.env
DATA_ROOT=/var/lib/zipp-diagnostics

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker.io docker-compose-plugin
fi
if ! docker compose version >/dev/null 2>&1; then
  apt-get update
  apt-get install -y docker-compose-plugin
fi
systemctl enable --now docker

install -d -m 750 /etc/zipp-diagnostics
install -d -m 750 "$DATA_ROOT/db" "$DATA_ROOT/backups"
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 600 "$SOURCE_DIR/.env.docker.example" "$ENV_FILE"
fi
python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import secrets, sys
path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
found = False
for index, line in enumerate(lines):
    if line.startswith("SESSION_SECRET="):
        found = True
        if not line.partition("=")[2].strip():
            lines[index] = "SESSION_SECRET=" + secrets.token_urlsafe(48)
if not found:
    lines.append("SESSION_SECRET=" + secrets.token_urlsafe(48))
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

compose() { docker compose --env-file "$ENV_FILE" -f "$SOURCE_DIR/docker-compose.yml" "$@"; }
compose build app
if systemctl is-active --quiet zipp-diagnostics.service; then
  echo "Zastavuji původní nativní Alpha 1 službu před migrací..."
  systemctl stop zipp-diagnostics.service
fi
if [[ -f "$DATA_ROOT/db/zipp.sqlite3" ]]; then
  echo "Vytvářím povinnou zálohu před migrací..."
  compose run --rm app python -m scripts.backup --prefix preinstall
fi
compose run --rm app alembic upgrade head
compose run --rm app python -m app.cli ensure-password
compose run --rm app python -m app.cli check-schema
compose up -d app
if grep -Eq '^CLOUDFLARE_TUNNEL_TOKEN=.+$' "$ENV_FILE"; then
  compose --profile cloudflare up -d
fi
for _ in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8000/health >/dev/null; then
    compose exec -T app python -c "import sqlite3; from app.config import get_settings; c=sqlite3.connect(get_settings().database_path); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; print('Databáze: ok')"
    echo "Docker instalace Alpha 4 dokončena: http://127.0.0.1:8000"
    exit 0
  fi
  sleep 1
done
compose logs --tail=100 app
echo "CHYBA: Aplikace neprošla health checkem. Data ani zálohy nebyly smazány."
exit 1
