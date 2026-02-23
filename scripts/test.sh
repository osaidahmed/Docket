#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

# auto-activate virtualenv if present and not already active
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.venv/bin/activate"
fi

# ── category → test path ──────────────────────────────────────────
# add new categories here: one case branch = one category
resolve_category() {
  case "$1" in
    # by app
    app)          echo "$SRC_DIR/app/tests" ;;
    users)        echo "$SRC_DIR/users/tests" ;;
    integrations) echo "$SRC_DIR/integrations/tests" ;;
    lists)        echo "$SRC_DIR/lists/tests" ;;
    events)       echo "$SRC_DIR/events/tests" ;;
    config)       echo "$SRC_DIR/config/tests" ;;
    # by sub-category
    models)       echo "$SRC_DIR/app/tests/models" ;;
    views)        echo "$SRC_DIR/app/tests/views" ;;
    providers)    echo "$SRC_DIR/app/tests/providers" ;;
    imports)      echo "$SRC_DIR/integrations/tests/imports" ;;
    webhooks)     echo "$SRC_DIR/integrations/tests/test_webhooks_emby.py $SRC_DIR/integrations/tests/test_webhooks_jellyfin.py $SRC_DIR/integrations/tests/test_webhooks_plex.py" ;;
    *)            return 1 ;;
  esac
}

list_categories() {
  cat <<EOF
app              app/tests
users            users/tests
integrations     integrations/tests
lists            lists/tests
events           events/tests
config           config/tests
models           app/tests/models
views            app/tests/views
providers        app/tests/providers
imports          integrations/tests/imports
webhooks         integrations/tests/test_webhooks_*.py
EOF
}

usage() {
  cat <<EOF
usage: $0 [options] [category ...] [-- pytest-args]

options:
  --list   show available categories and exit
  --cov    enable coverage collection
  -h       show this help

examples:
  $0                          run all tests
  $0 providers views          run providers and views tests
  $0 --cov app                run app tests with coverage
  $0 models -- -x --pdb       run model tests, stop on first failure

categories:
$(list_categories | sed 's/^/  /')
EOF
  exit 0
}

# ── parse arguments ───────────────────────────────────────────────
categories=""
pytest_extra=""
use_coverage=false
parsing_categories=true

for arg in "$@"; do
  if [ "$parsing_categories" = false ]; then
    pytest_extra="$pytest_extra $arg"
  elif [ "$arg" = "--" ]; then
    parsing_categories=false
  elif [ "$arg" = "--list" ] || [ "$arg" = "-h" ] || [ "$arg" = "--help" ]; then
    if [ "$arg" = "--list" ]; then
      echo "available categories:"
      list_categories | sed 's/^/  /'
      exit 0
    fi
    usage
  elif [ "$arg" = "--cov" ]; then
    use_coverage=true
  else
    resolved=$(resolve_category "$arg" 2>/dev/null) || {
      echo "error: unknown category '$arg'" >&2
      echo "run '$0 --list' to see available categories" >&2
      exit 1
    }
    categories="$categories $resolved"
  fi
done

# ── resolve paths ─────────────────────────────────────────────────
if [ -z "$categories" ]; then
  test_paths="$SRC_DIR"
else
  test_paths="$categories"
fi

# ── run ───────────────────────────────────────────────────────────
cd "$ROOT_DIR"

if [ "$use_coverage" = true ]; then
  echo "running tests with coverage..."
  # shellcheck disable=SC2086
  coverage run -m pytest -v --tb=short --durations=10 $test_paths $pytest_extra
  echo ""
  coverage report
  coverage html --quiet
  echo ""
  echo "html report: htmlcov/index.html"
else
  # shellcheck disable=SC2086
  python -m pytest -v --tb=short --durations=10 $test_paths $pytest_extra
fi
