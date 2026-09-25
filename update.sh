#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

AUTO_UPDATER="/opt/traffic-analyzer/auto_update.py"
if [[ -f "$AUTO_UPDATER" ]]; then
  exec /usr/bin/python3 "$AUTO_UPDATER" --manual
fi

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$BASE_DIR/auto_update.py" ]]; then
  exec /usr/bin/python3 "$BASE_DIR/auto_update.py" --manual
fi

echo "ERRO: auto_update.py não encontrado. Reinstale o Traffic Analyzer." >&2
exit 1
