#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose() { bash "$PROJECT_ROOT/scripts/compose.sh" "$@"; }
compose ps
compose exec -T nextcloud sh /docker-entrypoint-hooks.d/before-starting/storage-guard.sh
compose exec -T -u www-data nextcloud php occ status
compose exec -T -u www-data nextcloud test -w /var/www/html/data
compose run --rm --no-deps -T db-client psql -X --set ON_ERROR_STOP=on -c 'SELECT 1'
compose exec -T rag-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -h localhost -U "$POSTGRES_USER" -d "$POSTGRES_DB" --set ON_ERROR_STOP=on -c "SELECT count(*) FROM documents"'
compose exec -T nginx wget -q -O /dev/null --no-check-certificate https://localhost/status.php
compose exec -T rag-api sh -c 'curl -fsS "http://localhost:${APP_PORT:-8058}/health"'
compose exec -T rag-ui python -c 'import os,requests; r=requests.get(os.environ["API_URL"]+"/health",timeout=10); r.raise_for_status(); print("UI -> API: OK")'
compose exec -T rag-ui sh -c 'curl -fsS "http://localhost:${SERVER_PORT:-8501}/_stcore/health"'
echo 'All health checks passed. Upload/download and ingestion/chat still need functional tests.'
