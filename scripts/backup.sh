#!/bin/bash
set -euo pipefail
umask 077
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose() { bash "$PROJECT_ROOT/scripts/compose.sh" "$@"; }
command -v python3 >/dev/null
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_ROOT/backups}"
mkdir -p "$BACKUP_ROOT"
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d_%H%M%S)_$$"
mkdir "$BACKUP_DIR"
# Check the effective persisted storage configuration, without printing secrets.
compose exec -T nextcloud sh /docker-entrypoint-hooks.d/before-starting/storage-guard.sh
maintenance_before=$(compose exec -T -u www-data nextcloud php occ status --output=json | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["maintenance"]).lower())')
rag_running=$(compose ps --status running --services | awk '/^(rag-api|rag-ui)$/')
cleanup() {
  rc=$?
  trap - EXIT
  if [ "$maintenance_before" = false ]; then
    compose exec -T -u www-data nextcloud php occ maintenance:mode --off || rc=1
  fi
  for service in $rag_running; do compose start "$service" || rc=1; done
  exit "$rc"
}
trap cleanup EXIT
compose exec -T -u www-data nextcloud php occ maintenance:mode --on
for service in $rag_running; do compose stop "$service"; done
compose run --rm --no-deps -T db-client pg_dump --no-owner --no-privileges --clean --if-exists > "$BACKUP_DIR/nextcloud.sql"
compose exec -T rag-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h localhost -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --clean --if-exists' > "$BACKUP_DIR/rag.sql"
compose exec -T nextcloud tar czf - --exclude=./data -C /var/www/html . > "$BACKUP_DIR/nextcloud_config.tar.gz"
compose exec -T nextcloud tar czf - -C /var/www/html/data . > "$BACKUP_DIR/nextcloud_data.tar.gz"
python3 - "$BACKUP_DIR" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()
files = ('nextcloud.sql', 'rag.sql', 'nextcloud_config.tar.gz', 'nextcloud_data.tar.gz')
(root / 'manifest.json').write_text(json.dumps({'version': 1, 'sha256': {n: digest(root / n) for n in files}}, indent=2))
PY
printf 'Backup complete: %s\n' "$BACKUP_DIR"
echo 'Copy this directory to a separate machine/disk. A copy on the same VM does not survive VM disk loss.'
