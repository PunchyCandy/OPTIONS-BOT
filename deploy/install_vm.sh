#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/options-bot"
SERVICE_USER="optionsbot"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this installer with sudo."
  exit 1
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'venv' \
  ./ "${APP_DIR}/"

python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "Created ${APP_DIR}/.env. Edit it with your Alpaca paper credentials before starting the service."
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"

cp "${APP_DIR}/deploy/options-bot.service" /etc/systemd/system/options-bot.service
systemctl daemon-reload
systemctl enable options-bot.service

echo "Installed options-bot."
echo "Next:"
echo "  sudo nano ${APP_DIR}/.env"
echo "  sudo systemctl start options-bot"
echo "  sudo journalctl -u options-bot -f"
