#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# ── docker / redis ────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "error: docker not found (install Docker Desktop or OrbStack)" >&2
  exit 1
fi

if ! docker info &>/dev/null; then
  echo "error: docker daemon not running — start Docker Desktop or OrbStack" >&2
  exit 1
fi

echo "==> starting redis..."
if docker ps --format '{{.Names}}' | grep -q '^yamtrack-redis$'; then
  echo "    redis already running"
else
  docker run -d --name yamtrack-redis -p 6379:6379 redis:8-alpine >/dev/null 2>&1 || \
    docker start yamtrack-redis >/dev/null 2>&1
  echo "    redis started on localhost:6379"
fi

# ── python environment ────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3 python; do
  if command -v "$cmd" &>/dev/null && "$cmd" -c "import sys; assert sys.version_info >= (3,12)" 2>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "error: python 3.12+ not found" >&2
  exit 1
fi

echo "==> creating virtualenv ($PYTHON)..."
"$PYTHON" -m venv .venv

# shellcheck disable=SC1091
. .venv/bin/activate

echo "==> installing dependencies..."
pip install -U -r requirements-dev.txt --quiet

echo "==> installing pre-commit hooks..."
pre-commit install

echo "==> running migrations..."
python src/manage.py migrate --noinput

echo "==> installing playwright browsers..."
playwright install chromium

echo "==> done. activate with: source .venv/bin/activate"
