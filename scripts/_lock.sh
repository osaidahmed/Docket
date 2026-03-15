#!/usr/bin/env bash
# shared test/coverage lock — prevents concurrent runs that cause SQLite contention

LOCK_DIR="/tmp/docket-test.lock"
LOCK_PID_FILE="$LOCK_DIR/pid"
LOCK_CMD_FILE="$LOCK_DIR/cmd"

acquire_test_lock() {
  local caller="${1:-unknown}"

  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo $$ > "$LOCK_PID_FILE"
    echo "$caller" > "$LOCK_CMD_FILE"
    trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM HUP
    return 0
  fi

  # lock exists — check if the holder is still alive
  if [ -f "$LOCK_PID_FILE" ]; then
    local held_pid held_cmd
    held_pid=$(cat "$LOCK_PID_FILE" 2>/dev/null)
    held_cmd=$(cat "$LOCK_CMD_FILE" 2>/dev/null || echo "unknown")

    if [ -n "$held_pid" ] && kill -0 "$held_pid" 2>/dev/null; then
      echo ""
      echo "================================================================"
      echo "BLOCKED: another test process is running (PID $held_pid)"
      echo "  holder: $held_cmd"
      echo "  caller: $caller (PID $$)"
      echo "================================================================"
      echo ""
      echo "HUMAN: wait for the other run to finish, or kill it:"
      echo "  kill $held_pid"
      echo ""
      echo "AGENT: do NOT retry. Do NOT run tests concurrently."
      echo "  Make your code changes and exit — tests will be run separately."
      echo ""
      exit 1
    fi
  fi

  # stale lock (holder died without cleanup) — reclaim
  rm -rf "$LOCK_DIR"
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    echo $$ > "$LOCK_PID_FILE"
    echo "$caller" > "$LOCK_CMD_FILE"
    trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM HUP
    return 0
  fi

  echo "error: could not acquire test lock" >&2
  exit 1
}
