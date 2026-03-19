#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON="$ROOT_DIR/.venv/bin/python"
CELERY="$ROOT_DIR/.venv/bin/celery"

export PYTHONPATH="src:${PYTHONPATH:-}"

trap 'kill 0' EXIT

"$CELERY" --app config beat --loglevel info \
  --scheduler django_celery_beat.schedulers:DatabaseScheduler \
  2>&1 | sed 's/^/[beat]   /' &

"$CELERY" --app config worker --loglevel info \
  2>&1 | sed 's/^/[worker] /' &

"$PYTHON" src/manage.py runserver \
  2>&1 | sed 's/^/[web]    /' &

wait
