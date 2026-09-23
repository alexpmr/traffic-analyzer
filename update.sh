#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

REPO_URL="${TA_REPO_URL:-https://github.com/alexpmr/traffic-analyzer.git}"
CHECKOUT_DIR="${TA_CHECKOUT_DIR:-/opt/traffic-analyzer-source}"
BRANCH="${TA_BRANCH:-main}"

echo "Traffic Analyzer - atualização pelo GitHub"
echo "Repositório: $REPO_URL"
echo "Branch: $BRANCH"

if [[ ! -d "$CHECKOUT_DIR/.git" ]]; then
  rm -rf "$CHECKOUT_DIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$CHECKOUT_DIR"
else
  git -C "$CHECKOUT_DIR" remote set-url origin "$REPO_URL"
  git -C "$CHECKOUT_DIR" fetch --prune origin "$BRANCH"
  git -C "$CHECKOUT_DIR" reset --hard "origin/$BRANCH"
  git -C "$CHECKOUT_DIR" clean -fd
fi

NEW_VERSION="$(cat "$CHECKOUT_DIR/VERSION" 2>/dev/null || echo desconhecida)"
echo "Versão obtida: $NEW_VERSION"
bash "$CHECKOUT_DIR/install.sh"
