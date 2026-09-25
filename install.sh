#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Execute como root: sudo bash install.sh"
  exit 1
fi

VERSION="1.23.0"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/traffic-analyzer"
ENV_FILE="/etc/traffic-analyzer.env"
MAP_ENV_FILE="/etc/traffic-analyzer-map.env"
STATE_DIR="/var/lib/traffic-analyzer"
SERVICE_USER="traffic-analyzer"
SERVICE_GROUP="traffic-analyzer"
UPDATE_SETTINGS_FILE="$STATE_DIR/update-settings.json"
UPDATE_STATUS_FILE="$STATE_DIR/update-status.json"
LAST_INSTALL_FILE="$STATE_DIR/last-install.json"

LEGACY_APP_DIR="/opt/meshmonitor-route-discovery"
LEGACY_ENV_FILE="/etc/meshmonitor-route-discovery.env"
LEGACY_MAP_ENV_FILE="/etc/meshmonitor-route-map.env"
LEGACY_STATE_DIR="/var/lib/meshmonitor-route-discovery"

# Apenas informativo: mantem a instalacao portavel para qualquer conta Linux.
INVOKING_USER="${SUDO_USER:-${USER:-root}}"
if getent passwd "$INVOKING_USER" >/dev/null 2>&1; then
  USER_HOME="$(getent passwd "$INVOKING_USER" | cut -d: -f6)"
else
  USER_HOME="${HOME:-/root}"
fi

append_if_missing() {
  local file="$1" key="$2" value="$3"
  if ! grep -qE "^${key}=" "$file" 2>/dev/null; then
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

# Usuario dedicado para o servidor web/arquivo SQLite.
if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_GROUP" --home-dir /nonexistent --shell /usr/sbin/nologin "$SERVICE_USER"
fi

PREVIOUS_VERSION="$(cat "$APP_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
install -d -m 0755 "$APP_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$STATE_DIR"
install -m 0755 "$BASE_DIR/traffic_analyzer.py" "$APP_DIR/traffic_analyzer.py"
install -m 0755 "$BASE_DIR/traffic_analyzer_web.py" "$APP_DIR/traffic_analyzer_web.py"
install -m 0755 "$BASE_DIR/auto_update.py" "$APP_DIR/auto_update.py"
install -m 0644 "$BASE_DIR/VERSION" "$APP_DIR/VERSION"
install -m 0644 "$BASE_DIR/README.md" "$APP_DIR/README.md"
install -m 0644 "$BASE_DIR/CHANGELOG.md" "$APP_DIR/CHANGELOG.md"
install -m 0755 "$BASE_DIR/update.sh" /usr/local/sbin/traffic-analyzer-update

# Migracao/atualizacao para Traffic Analyzer v1.23.0.
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$LEGACY_ENV_FILE" ]]; then
    cp "$LEGACY_ENV_FILE" "$ENV_FILE"
    echo "Configuracao antiga migrada de $LEGACY_ENV_FILE"
  else
    cp "$BASE_DIR/traffic-analyzer.env.example" "$ENV_FILE"
  fi
fi

# Atualiza caminhos legados, preservando token/source/cooldowns do usuario.
sed -i 's#/var/lib/meshmonitor-route-discovery/state.json#/var/lib/traffic-analyzer/state.json#g' "$ENV_FILE"
sed -i 's#/var/lib/meshmonitor-route-discovery/topology.json#/var/lib/traffic-analyzer/topology.json#g' "$ENV_FILE"
append_if_missing "$ENV_FILE" "TOPOLOGY_LOOKBACK_HOURS" "0"
append_if_missing "$ENV_FILE" "TRACEROUTE_LIMIT" "5000"
append_if_missing "$ENV_FILE" "STATE_FILE" "$STATE_DIR/state.json"
append_if_missing "$ENV_FILE" "TOPOLOGY_FILE" "$STATE_DIR/topology.json"
append_if_missing "$ENV_FILE" "TRAFFIC_ARCHIVE_DB" "$STATE_DIR/traffic.db"
append_if_missing "$ENV_FILE" "ARCHIVE_POLL_SECONDS" "2"
append_if_missing "$ENV_FILE" "ARCHIVE_PAGE_SIZE" "500"
append_if_missing "$ENV_FILE" "ARCHIVE_OVERLAP_MS" "10000"
append_if_missing "$ENV_FILE" "ARCHIVE_RETENTION_DAYS" "0"
if grep -q '^TOPOLOGY_LOOKBACK_HOURS=24$' "$ENV_FILE"; then
  sed -i 's/^TOPOLOGY_LOOKBACK_HOURS=24$/TOPOLOGY_LOOKBACK_HOURS=0/' "$ENV_FILE"
fi
if grep -q '^TRACEROUTE_LIMIT=500$' "$ENV_FILE"; then
  sed -i 's/^TRACEROUTE_LIMIT=500$/TRACEROUTE_LIMIT=5000/' "$ENV_FILE"
fi
chmod 0600 "$ENV_FILE"

if [[ ! -f "$MAP_ENV_FILE" ]]; then
  if [[ -f "$LEGACY_MAP_ENV_FILE" ]]; then
    cp "$LEGACY_MAP_ENV_FILE" "$MAP_ENV_FILE"
  else
    cp "$BASE_DIR/traffic-analyzer-map.env.example" "$MAP_ENV_FILE"
  fi
fi
sed -i 's#MAP_TITLE=MeshMonitor - Topologia RF observada#MAP_TITLE=Traffic Analyzer - MeshMonitor - por Alex, PT2VHF#g' "$MAP_ENV_FILE" || true
sed -i 's#MAP_TITLE=Traffic Analyzer - MeshMonitor$#MAP_TITLE=Traffic Analyzer - MeshMonitor - por Alex, PT2VHF#g' "$MAP_ENV_FILE" || true
sed -i 's#/var/lib/meshmonitor-route-discovery/topology.json#/var/lib/traffic-analyzer/topology.json#g' "$MAP_ENV_FILE"
append_if_missing "$MAP_ENV_FILE" "MAP_TITLE" "Traffic Analyzer - MeshMonitor - por Alex, PT2VHF"
append_if_missing "$MAP_ENV_FILE" "TOPOLOGY_FILE" "$STATE_DIR/topology.json"
chmod 0644 "$MAP_ENV_FILE"

# Preserva estado/topologia ja coletados, se existirem.
if [[ -d "$LEGACY_STATE_DIR" ]]; then
  for f in state.json topology.json; do
    if [[ -f "$LEGACY_STATE_DIR/$f" && ! -f "$STATE_DIR/$f" ]]; then
      cp "$LEGACY_STATE_DIR/$f" "$STATE_DIR/$f"
    fi
  done
fi

# Permissoes: o web service escreve apenas o arquivo historico no STATE_DIR.
chown "$SERVICE_USER:$SERVICE_GROUP" "$STATE_DIR"
chmod 0750 "$STATE_DIR"
[[ -f "$STATE_DIR/state.json" ]] && { chown root:root "$STATE_DIR/state.json"; chmod 0600 "$STATE_DIR/state.json"; } || true
[[ -f "$STATE_DIR/topology.json" ]] && { chown root:root "$STATE_DIR/topology.json"; chmod 0644 "$STATE_DIR/topology.json"; } || true
for f in "$STATE_DIR/traffic.db" "$STATE_DIR/traffic.db-wal" "$STATE_DIR/traffic.db-shm"; do
  [[ -e "$f" ]] && chown "$SERVICE_USER:$SERVICE_GROUP" "$f" || true
done

if [[ ! -f "$UPDATE_SETTINGS_FILE" ]]; then
  printf '%s\n' '{"enabled": false, "rollbackEnabled": true}' > "$UPDATE_SETTINGS_FILE"
fi
if [[ ! -f "$UPDATE_STATUS_FILE" ]]; then
  printf '%s\n' '{"state": "idle"}' > "$UPDATE_STATUS_FILE"
fi
chown "$SERVICE_USER:$SERVICE_GROUP" "$UPDATE_SETTINGS_FILE" "$UPDATE_STATUS_FILE"
chmod 0640 "$UPDATE_SETTINGS_FILE" "$UPDATE_STATUS_FILE"

install -m 0644 "$BASE_DIR/traffic-analyzer.service" /etc/systemd/system/
install -m 0644 "$BASE_DIR/traffic-analyzer.timer" /etc/systemd/system/
install -m 0644 "$BASE_DIR/traffic-analyzer-map.service" /etc/systemd/system/
install -m 0644 "$BASE_DIR/traffic-analyzer-auto-update.service" /etc/systemd/system/
install -m 0644 "$BASE_DIR/traffic-analyzer-auto-update.path" /etc/systemd/system/

# Evita dois servicos executando consultas ou disputando a porta 8788.
systemctl disable --now meshmonitor-route-discovery.timer 2>/dev/null || true
systemctl stop meshmonitor-route-discovery.service 2>/dev/null || true
systemctl disable --now meshmonitor-route-map.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now traffic-analyzer.timer
systemctl enable --now traffic-analyzer-auto-update.path

# Gera topology.json sem transmitir NodeInfo durante a atualizacao.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
if /usr/bin/python3 "$APP_DIR/traffic_analyzer.py" --topology-only; then
  echo "Topologia inicial atualizada."
else
  echo "AVISO: nao foi possivel gerar a topologia agora. O timer tentara novamente." >&2
fi
[[ -f "$STATE_DIR/topology.json" ]] && { chown root:root "$STATE_DIR/topology.json"; chmod 0644 "$STATE_DIR/topology.json"; } || true

python3 - "$LAST_INSTALL_FILE" "$PREVIOUS_VERSION" "$VERSION" <<'PY'
import json, sys, time
path, previous, current = sys.argv[1:4]
with open(path, "w", encoding="utf-8") as f:
    json.dump({"previousVersion": previous, "currentVersion": current, "installedAtMs": int(time.time()*1000)}, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
chown "$SERVICE_USER:$SERVICE_GROUP" "$LAST_INSTALL_FILE"
chmod 0640 "$LAST_INSTALL_FILE"

systemctl enable --now traffic-analyzer-map.service
systemctl restart traffic-analyzer-map.service

cat <<MSG

============================================================
 Traffic Analyzer v${VERSION}
 Instalacao/atualizacao concluida
============================================================

Usuario que iniciou a instalacao: ${INVOKING_USER}
Home corrente: ${USER_HOME}

Configuracao:
  ${ENV_FILE}

Dados persistentes:
  ${STATE_DIR}
  ${STATE_DIR}/traffic.db

Aplicacao:
  ${APP_DIR}

Interface web:
  http://IP_DO_SERVIDOR:8788/

Atualização futura pelo GitHub:
  traffic-analyzer-update

O token, MM_SOURCE, estado, topologia, cooldowns e traffic.db sao preservados nas atualizacoes.
Os servicos antigos meshmonitor-route-* sao desativados para evitar duplicidade.

------------------------------------------------------------
 Status do agendador
------------------------------------------------------------
MSG

# O usuario pediu que os dois status sejam executados automaticamente ao final.
set +e
systemctl status traffic-analyzer.timer --no-pager
TIMER_STATUS=$?

echo
printf '%s\n' '------------------------------------------------------------' ' Status da interface web' '------------------------------------------------------------'
systemctl status traffic-analyzer-map.service --no-pager
MAP_STATUS=$?
set -e

echo
printf '%s\n' '============================================================'
if [[ $TIMER_STATUS -eq 0 && $MAP_STATUS -eq 0 ]]; then
  echo " Traffic Analyzer esta pronto."
else
  echo " ATENCAO: um dos servicos nao esta ativo. Consulte os logs abaixo."
fi
printf '%s\n' '============================================================'
echo
echo "Logs:"
echo "  journalctl -u traffic-analyzer.service -n 50 --no-pager"
echo "  journalctl -u traffic-analyzer-map.service -n 50 --no-pager"
echo "  journalctl -u traffic-analyzer-auto-update.service -n 80 --no-pager"

if [[ $TIMER_STATUS -ne 0 || $MAP_STATUS -ne 0 ]]; then
  exit 1
fi
