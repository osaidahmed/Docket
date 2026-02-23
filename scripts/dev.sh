#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# auto-activate venv
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

export PYTHONPATH="src:${PYTHONPATH:-}"

trap 'kill 0' EXIT

celery --app config beat --loglevel info \
  --scheduler django_celery_beat.schedulers:DatabaseScheduler \
  2>&1 | sed 's/^/[beat]   /' &

celery --app config worker --loglevel info \
  2>&1 | sed 's/^/[worker] /' &

python src/manage.py runserver \
  2>&1 | sed 's/^/[web]    /' &

wait
