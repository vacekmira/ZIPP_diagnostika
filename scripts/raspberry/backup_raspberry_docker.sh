#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Spusťte pomocí sudo."; exit 1; fi
SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
docker compose --env-file /etc/zipp-diagnostics/docker.env -f "$SOURCE_DIR/docker-compose.yml" run --rm app python -m scripts.backup
