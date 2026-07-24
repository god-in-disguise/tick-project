#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin npm run start -- --host lan --port 8085 --clear
