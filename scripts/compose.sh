#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/deployment/.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy deployment/.env.example (VM) or .env.local.example (local) first." >&2
  exit 1
fi
exec docker compose --env-file "$ENV_FILE" -f "$PROJECT_ROOT/deployment/docker-compose.yml" "$@"
