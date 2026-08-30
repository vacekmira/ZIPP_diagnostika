#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Spusťte pomocí sudo."; exit 1; fi

SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE=/etc/zipp-diagnostics/docker.env
compose() { docker compose --env-file "$ENV_FILE" -f "$SOURCE_DIR/docker-compose.yml" "$@"; }

cd "$SOURCE_DIR"
echo "Vytvářím povinnou a ověřenou předaktualizační zálohu..."
compose run --rm app python -m scripts.backup --prefix preupdate
git pull --ff-only
compose build app
compose stop app
if ! compose run --rm app alembic upgrade head; then
  echo "CHYBA: Migrace selhala. Aplikace zůstala zastavená; databáze a záloha jsou zachované."
  exit 1
fi
compose run --rm app python -m app.cli ensure-password
compose run --rm app python -m app.cli check-schema
compose up -d app
if grep -Eq '^CLOUDFLARE_TUNNEL_TOKEN=.+$' "$ENV_FILE"; then
  compose --profile cloudflare up -d
fi
for _ in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:8000/health >/dev/null; then
    compose exec -T app python -c "import sqlite3; from app.config import get_settings; c=sqlite3.connect(get_settings().database_path); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; print('Databáze: ok')"
    echo "Aktualizace Alpha 4 dokončena."
    exit 0
  fi
  sleep 1
done
compose logs --tail=100 app
echo "CHYBA: Aktualizovaná aplikace neprošla health checkem. Záloha zůstala zachována."
exit 1
