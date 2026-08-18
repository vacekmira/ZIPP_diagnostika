#!/usr/bin/env bash
set -euo pipefail
cd /opt/zipp-diagnostics/current
set -a; source /etc/zipp-diagnostics/app.env; set +a
/opt/zipp-diagnostics/venv/bin/python -m scripts.backup
