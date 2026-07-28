#!/usr/bin/env bash
set -euo pipefail

: "${TICK_HOST:?Set TICK_HOST to the DigitalOcean droplet IP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TICK_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
BACKEND_DIR="$TICK_DIR/backend"
RUNTIME_ENV="$DEPLOY_DIR/.runtime/backend.env"
SSH_KEY="${TICK_SSH_KEY:-$DEPLOY_DIR/.runtime/tick_ed25519}"
SSH=(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)
RSYNC_KEY="$SSH_KEY"
RSYNC_KEY_DIR=""
if [[ "$RSYNC_KEY" == *" "* ]]; then
  RSYNC_KEY_DIR="$(mktemp -d)"
  ln -s "$SSH_KEY" "$RSYNC_KEY_DIR/tick_ed25519"
  RSYNC_KEY="$RSYNC_KEY_DIR/tick_ed25519"
fi
trap '[[ -z "$RSYNC_KEY_DIR" ]] || rm -rf "$RSYNC_KEY_DIR"' EXIT
RSYNC_SSH="ssh -i $RSYNC_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

if [[ ! -f "$RUNTIME_ENV" ]]; then
  echo "Missing $RUNTIME_ENV" >&2
  exit 1
fi

if [[ ! -f "$SSH_KEY" ]]; then
  echo "Missing SSH key $SSH_KEY" >&2
  exit 1
fi

"${SSH[@]}" "root@$TICK_HOST" "mkdir -p /opt/tick/backend /opt/tick/deploy/.runtime"
rsync -az --delete \
  -e "$RSYNC_SSH" \
  --exclude '.env' \
  --exclude '.venv' \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  "$BACKEND_DIR/" "root@$TICK_HOST:/opt/tick/backend/"
rsync -az --delete \
  -e "$RSYNC_SSH" \
  --exclude '.env' \
  --exclude '.runtime' \
  --exclude '.terraform' \
  --exclude '*.tfstate*' \
  "$DEPLOY_DIR/" "root@$TICK_HOST:/opt/tick/deploy/"
scp -i "$SSH_KEY" -o IdentitiesOnly=yes "$RUNTIME_ENV" \
  "root@$TICK_HOST:/opt/tick/deploy/.runtime/backend.env"
"${SSH[@]}" "root@$TICK_HOST" \
  "cd /opt/tick/deploy && chmod 600 .runtime/backend.env && docker compose --env-file .runtime/backend.env -f docker-compose.prod.yml up -d --build --remove-orphans"
