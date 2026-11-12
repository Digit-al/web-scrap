#!/usr/bin/env bash
# mcp-scraping — installation userland (sans root, sans systemd).
# Usage : ./install.sh [--cron]
#   --cron : ajoute une entrée @reboot au crontab de l'utilisateur.
set -euo pipefail
cd "$(dirname "$0")"

CRON=0
[[ "${1:-}" == "--cron" ]] && CRON=1

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 introuvable dans le PATH." >&2
  exit 1
fi

echo "→ Création du venv (.venv)…"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "→ Configuration créée : ./.env (éditez-la au besoin)"
fi
mkdir -p logs

echo
echo "✅ mcp-scraping installé (userland) dans : $(pwd)"
echo "   Démarrer : ./run.sh start"
echo "   Arrêter  : ./run.sh stop"
echo "   Statut   : ./run.sh status"
echo "   Logs     : ./run.sh logs"
echo "   Config   : ./.env   (puis ./run.sh restart)"

if [[ $CRON -eq 1 ]]; then
  CRON_LINE="@reboot cd $(pwd) && ./run.sh start >> logs/cron.log 2>&1"
  (crontab -l 2>/dev/null || true) | { grep -vF 'mcp-scraping' || true; echo "$CRON_LINE"; } | crontab -
  echo "   Autodémarage : entrée @reboot ajoutée au crontab."
fi
