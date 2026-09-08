#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Spusťte pomocí sudo."; exit 1; fi
cd /opt/zipp-diagnostics/current
set -a; source /etc/zipp-diagnostics/app.env; set +a
/opt/zipp-diagnostics/venv/bin/python -m scripts.backup --prefix preupdate
git pull --ff-only
/opt/zipp-diagnostics/venv/bin/pip install .
systemctl stop zipp-diagnostics
/opt/zipp-diagnostics/venv/bin/alembic upgrade head
systemctl start zipp-diagnostics
sleep 3
curl --fail http://127.0.0.1:8000/health
echo "Aktualizace Alpha 9 dokončena. Zálohy: /var/lib/zipp-diagnostics/backups"
