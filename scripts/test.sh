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
    e2e)          echo "$ROOT_DIR/e2e" ;;
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
e2e              e2e/ (playwright browser tests)
EOF
}

usage() {
  cat <<EOF
usage: $0 [options] [category ...] [-- pytest-args]

options:
  --list       show available categories and exit
  --quick      skip integrations and events tests for faster iteration
  --cov        enable coverage collection
  --no-reuse   recreate the test database from scratch
  --serial     disable parallel execution (run on single core)
  -h           show this help

examples:
  $0                          run all tests
  $0 --quick providers        run provider tests only
  $0 --cov app                run app tests with coverage
  $0 models -- -x --pdb       run model tests, stop on first failure
  $0 --no-reuse               force fresh database

categories:
$(list_categories | sed 's/^/  /')
EOF
  exit 0
}

# ── parse arguments ───────────────────────────────────────────────
categories=""
pytest_extra=""
use_coverage=false
reuse_db=true
parallel=true
quick_mode=false
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
  elif [ "$arg" = "--no-reuse" ]; then
    reuse_db=false
  elif [ "$arg" = "--serial" ]; then
    parallel=false
  elif [ "$arg" = "--quick" ]; then
    quick_mode=true
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

# ── e2e: force serial mode (browsers + live_server) ──────────────
case "$test_paths" in
  *"/e2e"*) parallel=false ;;
esac

# ── build flags ───────────────────────────────────────────────────
# interactive terminals get verbose output with durations;
# non-interactive callers (Claude Code, CI) get quiet, minimal output
if [ -t 1 ]; then
  pytest_flags="-v --tb=short --durations=10"
else
  pytest_flags="-q --tb=short --no-header -p no:warnings"
fi

if [ "$reuse_db" = true ]; then
  pytest_flags="$pytest_flags --reuse-db"
fi

if [ "$parallel" = true ]; then
  pytest_flags="$pytest_flags -n auto"
fi

# --quick: exclude heavier peripheral test suites
if [ "$quick_mode" = true ]; then
  pytest_flags="$pytest_flags --ignore=$SRC_DIR/integrations/tests"
  pytest_flags="$pytest_flags --ignore=$SRC_DIR/events/tests"
fi

# ── run ───────────────────────────────────────────────────────────
# shellcheck disable=SC1091
. "$SCRIPT_DIR/_lock.sh"
acquire_test_lock "$0 $*"

cd "$ROOT_DIR"

pytest_cmd="$ROOT_DIR/.venv/bin/python -m pytest"

if [ "$use_coverage" = true ]; then
  echo "running tests with coverage..."
  # shellcheck disable=SC2086
  $pytest_cmd --cov=src --cov-report=term --cov-report=html $pytest_flags $test_paths $pytest_extra
  echo ""
  echo "html report: htmlcov/index.html"
else
  # shellcheck disable=SC2086
  $pytest_cmd $pytest_flags $test_paths $pytest_extra
fi
