#!/usr/bin/env bash
set -euo pipefail

: "${TICK_HOST:?Set TICK_HOST to the DigitalOcean droplet IP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$(cd "$DEPLOY_DIR/../.." && pwd)"
RUNTIME_ENV="$DEPLOY_DIR/.runtime/backend.env"

if [[ ! -f "$RUNTIME_ENV" ]]; then
  echo "Missing $RUNTIME_ENV" >&2
  exit 1
fi

ssh "root@$TICK_HOST" "mkdir -p /opt/tick/backend/deploy/tick/.runtime"
rsync -az --delete \
  --exclude '.env' \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude 'deploy/digitalocean' \
  --exclude 'deploy/.local' \
  "$BACKEND_DIR/" "root@$TICK_HOST:/opt/tick/backend/"
scp "$RUNTIME_ENV" "root@$TICK_HOST:/opt/tick/backend/deploy/tick/.runtime/backend.env"
ssh "root@$TICK_HOST" \
  "cd /opt/tick/backend/deploy/tick && chmod 600 .runtime/backend.env && set -a && . .runtime/backend.env && set +a && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans"
