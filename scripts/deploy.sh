#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Configure via environment variables:
#   DEPLOY_SERVER  - SSH host (e.g. "myserver" or "user@1.2.3.4")
#   DEPLOY_DIR     - Remote directory for the project
SERVER="${DEPLOY_SERVER:?Set DEPLOY_SERVER (e.g. export DEPLOY_SERVER=myserver)}"
REMOTE_DIR="${DEPLOY_DIR:?Set DEPLOY_DIR (e.g. export DEPLOY_DIR=~/services/docket)}"

echo "Syncing source to $SERVER:$REMOTE_DIR..."
rsync -az \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='htmlcov' \
  --exclude='*.pyc' \
  --exclude='.codegraph' \
  --delete \
  "$ROOT_DIR/" "$SERVER:$REMOTE_DIR/src/"

echo "Building and restarting..."
ssh "$SERVER" "cd $REMOTE_DIR && docker compose build --quiet && docker compose up -d"

echo "Deployed."
ssh "$SERVER" "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep docket"
