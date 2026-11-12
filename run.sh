#!/usr/bin/env bash
# mcp-scraping — contrôle userland (nohup, sans root, sans systemd).
# Usage : ./run.sh {start|stop|restart|status|logs|install}
set -euo pipefail
cd "$(dirname "$0")"

PID_FILE=.mcp-scraping.pid
LOG_DIR=logs
LOG_FILE="$LOG_DIR/mcp-scraping.log"
ENV_FILE=.env

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ENV_FILE"
    set +a
  fi
}

pid_alive() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
  load_env
  if pid_alive; then
    echo "Déjà en cours (PID $(cat "$PID_FILE"))."
    return 0
  fi
  if [[ ! -x .venv/bin/python ]]; then
    echo "venv absent : lancez d'abord ./install.sh" >&2
    exit 1
  fi
  mkdir -p "$LOG_DIR"
  nohup .venv/bin/python server.py >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 2
  if pid_alive; then
    echo "mcp-scraping démarré (PID $(cat "$PID_FILE"), port ${MCP_PORT:-8000})."
  else
    echo "Échec du démarrage, fin du log :" >&2
    tail -5 "$LOG_FILE" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
}

stop() {
  if pid_alive; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    echo "Arrêté (PID $(cat "$PID_FILE"))."
  else
    echo "Pas en cours."
  fi
  rm -f "$PID_FILE"
}

status() {
  load_env
  if pid_alive; then
    echo "En cours (PID $(cat "$PID_FILE"))."
    echo -n "Health : "
    curl -s -m 3 "http://127.0.0.1:${MCP_PORT:-8000}/health" || echo "KO"
    echo
  else
    echo "Pas en cours."
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; start ;;
  status)  status ;;
  logs)    tail -n 50 -f "$LOG_FILE" ;;
  install) exec bash install.sh "${@:2}" ;;
  *)
    echo "Usage : $0 {start|stop|restart|status|logs|install}" >&2
    exit 1
    ;;
esac
