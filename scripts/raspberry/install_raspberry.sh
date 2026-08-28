#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Spusťte pomocí sudo."; exit 1; fi
SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
apt-get update
apt-get install -y fonts-dejavu-core
id zipp >/dev/null 2>&1 || useradd --system --home /var/lib/zipp-diagnostics --shell /usr/sbin/nologin zipp
install -d -o zipp -g zipp /var/lib/zipp-diagnostics/db /var/lib/zipp-diagnostics/backups
install -d /opt/zipp-diagnostics /etc/zipp-diagnostics
ln -sfn "$SOURCE_DIR" /opt/zipp-diagnostics/current
python3 -m venv /opt/zipp-diagnostics/venv
/opt/zipp-diagnostics/venv/bin/pip install --upgrade pip
/opt/zipp-diagnostics/venv/bin/pip install "$SOURCE_DIR"
if [[ ! -f /etc/zipp-diagnostics/app.env ]]; then
  install -m 640 -o root -g zipp "$SOURCE_DIR/.env.example" /etc/zipp-diagnostics/app.env
  sed -i 's#DATABASE_PATH=.*#DATABASE_PATH=/var/lib/zipp-diagnostics/db/zipp.sqlite3#' /etc/zipp-diagnostics/app.env
  sed -i 's#BACKUP_PATH=.*#BACKUP_PATH=/var/lib/zipp-diagnostics/backups#' /etc/zipp-diagnostics/app.env
fi
cd "$SOURCE_DIR"
set -a; source /etc/zipp-diagnostics/app.env; set +a
/opt/zipp-diagnostics/venv/bin/alembic upgrade head
install -m 644 deployment/systemd/zipp-diagnostics.service /etc/systemd/system/zipp-diagnostics.service
systemctl daemon-reload
systemctl enable --now zipp-diagnostics
sleep 2
curl --fail http://127.0.0.1:8000/health
echo "Instalace dokončena. Stav: systemctl status zipp-diagnostics"
