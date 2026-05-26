#!/usr/bin/env bash
set -euo pipefail

echo "[netfleet-api] running alembic migrations..."
alembic upgrade head

echo "[netfleet-api] starting: $*"
exec "$@"
