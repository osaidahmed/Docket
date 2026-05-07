#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"

if [ -n "${REMOTE_RUN:-}" ] && [ -x "$ROOT_DIR/scripts/remote.sh" ]; then
  exec "$ROOT_DIR/scripts/remote.sh" "./scripts/$(basename "$0")" "$@"
fi

# auto-activate virtualenv if present and not already active
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "$ROOT_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.venv/bin/activate"
fi

# ── source → test mapping ─────────────────────────────────────────
map_file_to_tests() {
  local file="$1"

  # skip non-src files
  [[ "$file" != src/* ]] && return

  # already a test file — include directly
  if [[ "$file" == */tests/* ]]; then
    [ -f "$ROOT_DIR/$file" ] && echo "$ROOT_DIR/$file"
    return
  fi

  # template files → map to app view tests
  if [[ "$file" == src/templates/* ]]; then
    local tpl_dir
    tpl_dir=$(echo "$file" | cut -d/ -f3)
    case "$tpl_dir" in
      app)    [ -d "$SRC_DIR/app/tests/views" ] && echo "$SRC_DIR/app/tests/views" ;;
      events) [ -d "$SRC_DIR/events/tests" ] && echo "$SRC_DIR/events/tests" ;;
      lists)  [ -d "$SRC_DIR/lists/tests" ] && echo "$SRC_DIR/lists/tests" ;;
      users)  [ -d "$SRC_DIR/users/tests" ] && echo "$SRC_DIR/users/tests" ;;
    esac
    return
  fi

  # static files — skip
  [[ "$file" == src/static/* ]] && return

  # extract app name and relative path
  local app rel_path basename test_dir
  app=$(echo "$file" | cut -d/ -f2)
  rel_path=$(echo "$file" | sed "s|src/$app/||")
  basename=$(basename "$rel_path" .py)
  test_dir="$SRC_DIR/$app/tests"

  [ -d "$test_dir" ] || return

  case "$rel_path" in
    views/*.py)
      local found=false
      for f in "$test_dir"/views/test_*"${basename}"*.py; do
        [ -f "$f" ] && echo "$f" && found=true
      done
      if [ "$found" = false ] && [ -d "$test_dir/views" ]; then
        echo "$test_dir/views"
      fi
      ;;

    providers/*.py)
      for f in "$test_dir"/providers/test_"${basename}"*.py; do
        [ -f "$f" ] && echo "$f"
      done
      ;;

    services/*.py)
      for f in "$test_dir"/test_*"${basename}"*.py; do
        [ -f "$f" ] && echo "$f"
      done
      ;;

    imports/*.py)
      [ -f "$test_dir/imports/test_${basename}.py" ] && echo "$test_dir/imports/test_${basename}.py"
      ;;

    webhooks/*.py)
      if [ "$basename" = "base" ]; then
        for f in "$test_dir"/test_webhooks_*.py; do
          [ -f "$f" ] && echo "$f"
        done
      else
        [ -f "$test_dir/test_webhooks_${basename}.py" ] && echo "$test_dir/test_webhooks_${basename}.py"
      fi
      ;;

    templatetags/*.py)
      [ -f "$test_dir/test_templatetags.py" ] && echo "$test_dir/test_templatetags.py"
      ;;

    management/commands/*.py)
      [ -f "$test_dir/test_management.py" ] && echo "$test_dir/test_management.py"
      ;;

    models.py)
      [ -d "$test_dir/models" ] && echo "$test_dir/models"
      [ -f "$test_dir/test_models.py" ] && echo "$test_dir/test_models.py"
      [ -f "$test_dir/test_forms.py" ] && echo "$test_dir/test_forms.py"
      ;;

    *.py)
      if [ -f "$test_dir/test_${basename}.py" ]; then
        echo "$test_dir/test_${basename}.py"
      else
        echo "$test_dir"
      fi
      ;;
  esac
}

get_changed_files() {
  local ref="$1"
  {
    # committed changes vs compare branch
    git diff --name-only "origin/$ref...HEAD" 2>/dev/null || true
    # staged changes
    git diff --cached --name-only 2>/dev/null || true
    # unstaged changes
    git diff --name-only 2>/dev/null || true
  } | sort -u
}

# ── usage ──────────────────────────────────────────────────────────
usage() {
  cat <<EOF
usage: $0 [options] [-- pytest-args]

modes (pick one, default: --diff):
  --diff           diff coverage against compare branch (default)
  --full           full coverage report, no diff filtering
  --targeted       auto-detect changed files, run only their tests

options:
  --fail-under N   fail if diff coverage < N% (default: 80)
  --no-open        skip auto-opening HTML report
  --no-html        skip HTML report generation
  --serial         disable parallel execution
  --no-reuse       recreate test database
  --compare REF    git ref to compare against (default: dev)
  -h, --help       show this help

examples:
  $0                          diff coverage vs dev
  $0 --targeted               run only tests for changed files
  $0 --full --fail-under 70   full report, fail below 70%
  $0 --diff -- -x --pdb       diff mode with extra pytest flags
EOF
  exit 0
}

# ── parse arguments ────────────────────────────────────────────────
mode="diff"
fail_under=80
open_report=true
html=true
reuse_db=true
parallel=true
compare_ref="dev"
pytest_extra=""
parsing_flags=true

for arg in "$@"; do
  if [ "$parsing_flags" = false ]; then
    pytest_extra="$pytest_extra $arg"
  elif [ "$arg" = "--" ]; then
    parsing_flags=false
  elif [ "$arg" = "--diff" ]; then
    mode="diff"
  elif [ "$arg" = "--full" ]; then
    mode="full"
  elif [ "$arg" = "--targeted" ]; then
    mode="targeted"
  elif [ "$arg" = "--no-open" ]; then
    open_report=false
  elif [ "$arg" = "--no-html" ]; then
    html=false
  elif [ "$arg" = "--serial" ]; then
    parallel=false
  elif [ "$arg" = "--no-reuse" ]; then
    reuse_db=false
  elif [ "$arg" = "-h" ] || [ "$arg" = "--help" ]; then
    usage
  elif [[ "$prev_arg" == "--fail-under" ]]; then
    fail_under="$arg"
    prev_arg=""
    continue
  elif [[ "$prev_arg" == "--compare" ]]; then
    compare_ref="$arg"
    prev_arg=""
    continue
  elif [ "$arg" = "--fail-under" ] || [ "$arg" = "--compare" ]; then
    prev_arg="$arg"
    continue
  else
    echo "error: unknown option '$arg'" >&2
    echo "run '$0 --help' for usage" >&2
    exit 1
  fi
  prev_arg=""
done

# ── determine test paths ──────────────────────────────────────────
cd "$ROOT_DIR"
test_paths="$SRC_DIR"

if [ "$mode" = "targeted" ]; then
  echo "detecting changed files vs origin/$compare_ref..."
  changed_files=$(get_changed_files "$compare_ref")

  if [ -z "$changed_files" ]; then
    echo "no changes detected, nothing to analyze"
    exit 0
  fi

  mapped_tests=""
  while IFS= read -r file; do
    mapped_tests="$mapped_tests $(map_file_to_tests "$file")"
  done <<< "$changed_files"

  # deduplicate
  mapped_tests=$(echo "$mapped_tests" | tr ' ' '\n' | sort -u | tr '\n' ' ')
  mapped_tests=$(echo "$mapped_tests" | xargs)

  if [ -z "$mapped_tests" ]; then
    echo "no test mappings found for changed files, falling back to all tests"
  else
    test_paths="$mapped_tests"
    echo "running tests: $test_paths"
  fi
fi

# ── build pytest flags ─────────────────────────────────────────────
pytest_flags="-v --tb=short --durations=10"

if [ "$reuse_db" = true ]; then
  pytest_flags="$pytest_flags --reuse-db"
fi

if [ "$parallel" = true ]; then
  pytest_flags="$pytest_flags -n auto"
fi

# ── build coverage flags ──────────────────────────────────────────
cov_flags="--cov=src --cov-report=term"

if [ "$html" = true ]; then
  cov_flags="$cov_flags --cov-report=html"
fi

# always generate xml for diff-cover
cov_flags="$cov_flags --cov-report=xml"

# ── run tests with coverage ───────────────────────────────────────
echo ""
echo "running tests with coverage..."
# shellcheck disable=SC2086
python -m pytest $cov_flags $pytest_flags $test_paths $pytest_extra

# ── diff coverage ─────────────────────────────────────────────────
if [ "$mode" != "full" ]; then
  echo ""
  echo "diff coverage vs origin/$compare_ref:"
  diff-cover coverage.xml \
    --compare-branch="origin/$compare_ref" \
    --fail-under "$fail_under" || {
    echo ""
    echo "diff coverage below ${fail_under}% threshold"
    exit 2
  }
fi

# ── open html report ──────────────────────────────────────────────
if [ "$open_report" = true ] && [ "$html" = true ]; then
  echo ""
  case "$(uname -s)" in
    Darwin) open htmlcov/index.html ;;
    *)      xdg-open htmlcov/index.html 2>/dev/null || true ;;
  esac
fi

echo ""
echo "html report: htmlcov/index.html"
