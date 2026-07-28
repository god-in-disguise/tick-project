#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl rsync
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
mkdir -p /opt/tick/backend /opt/tick/deploy/.runtime
chmod 755 /opt/tick /opt/tick/backend /opt/tick/deploy
chmod 700 /opt/tick/deploy/.runtime
