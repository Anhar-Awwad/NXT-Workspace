#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose() { bash "$PROJECT_ROOT/scripts/compose.sh" "$@"; }
if [ "$#" -ne 2 ] || [ "$2" != --yes ]; then
  echo "Usage: bash scripts/restore.sh BACKUP_DIRECTORY --yes" >&2
  echo "Replaces Nextcloud files and both databases in the selected Compose stack." >&2
  exit 1
fi
BACKUP_DIR="$(cd "$1" && pwd)"
# Validate completeness and checksums before stopping anything or deleting files.
python3 - "$BACKUP_DIR" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
m = json.loads((root / 'manifest.json').read_text())
expected = {'nextcloud.sql', 'rag.sql', 'nextcloud_config.tar.gz', 'nextcloud_data.tar.gz'}
if m.get('version') != 1 or set(m.get('sha256', {})) != expected:
    raise SystemExit('Unsupported or incomplete backup manifest')
for name, digest in m['sha256'].items():
    h = hashlib.sha256()
    with (root / name).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    if h.hexdigest() != digest: raise SystemExit('Checksum mismatch: ' + name)
print('Backup checksums verified')
PY
compose exec -T nextcloud sh /docker-entrypoint-hooks.d/before-starting/storage-guard.sh
compose exec -T -u www-data nextcloud php occ maintenance:mode --on
compose stop nginx nextcloud rag-api rag-ui
trap 'echo "Restore failed. Services remain stopped; fix the error and rerun restore before starting them." >&2' ERR
# Stream through the selected service volumes; never guess Compose-prefixed volume names.
compose run --rm --no-deps -T --entrypoint bash nextcloud -c 'find /var/www/html -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf -- {} +; tar xzf - -C /var/www/html' < "$BACKUP_DIR/nextcloud_config.tar.gz"
compose run --rm --no-deps -T --entrypoint bash nextcloud -c 'find /var/www/html/data -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; tar xzf - -C /var/www/html/data' < "$BACKUP_DIR/nextcloud_data.tar.gz"
compose run --rm --no-deps -T db-client psql -X --set ON_ERROR_STOP=on --single-transaction < "$BACKUP_DIR/nextcloud.sql"
compose exec -T rag-db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -h localhost -U "$POSTGRES_USER" -d "$POSTGRES_DB" --set ON_ERROR_STOP=on --single-transaction' < "$BACKUP_DIR/rag.sql"
compose start nextcloud
compose exec -T -u www-data nextcloud php occ maintenance:data-fingerprint
compose exec -T -u www-data nextcloud php occ maintenance:mode --off
compose start nginx rag-api rag-ui
echo 'Restore complete. Run scripts/health-check.sh and verify a restored file and RAG document.'
