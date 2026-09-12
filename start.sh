#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
exec "$PYTHON" scripts/start_studio_guard.py "$@"
