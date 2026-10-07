#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose() { bash "$PROJECT_ROOT/scripts/compose.sh" "$@"; }
bash "$PROJECT_ROOT/scripts/health-check.sh"
name="storage-smoke-$(date +%s)-$$.txt"
upload() {
  compose exec -T nextcloud sh -c '
    set -eu
    url="http://localhost/remote.php/dav/files/$NEXTCLOUD_ADMIN_USER/$1"
    printf "%s" "$1" | curl -fsS -u "$NEXTCLOUD_ADMIN_USER:$NEXTCLOUD_ADMIN_PASSWORD" -T - "$url"
  ' sh "$name"
}
verify() {
  compose exec -T nextcloud sh -c '
    set -eu
    url="http://localhost/remote.php/dav/files/$NEXTCLOUD_ADMIN_USER/$1"
    actual=$(curl --retry 20 --retry-connrefused --retry-delay 2 -fsS -u "$NEXTCLOUD_ADMIN_USER:$NEXTCLOUD_ADMIN_PASSWORD" "$url")
    test "$actual" = "$1"
  ' sh "$name"
}
upload
verify
compose restart nextcloud
verify
compose exec -T nextcloud sh -c 'curl -fsS -u "$NEXTCLOUD_ADMIN_USER:$NEXTCLOUD_ADMIN_PASSWORD" -X DELETE "http://localhost/remote.php/dav/files/$NEXTCLOUD_ADMIN_USER/$1"' sh "$name"
echo 'PASS: WebDAV upload, download, restart persistence and test-file cleanup.'
