#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -s "$PROJECT_ROOT/deployment/nginx/ssl/cert.key" ]; then
  bash "$PROJECT_ROOT/scripts/generate-ssl.sh"
fi

# Rebuild rag-api and rag-ui images from source on every deploy so code
# changes in agentic_rag_project/ are always picked up without manual steps.
echo "Building RAG service images..."
bash "$PROJECT_ROOT/scripts/compose.sh" build rag-api rag-ui

bash "$PROJECT_ROOT/scripts/compose.sh" up -d

# Nextcloud takes 2-5 min to finish first-run setup after the container starts.
# Poll `occ status` for up to 5 minutes before proceeding, or seeding fails silently.
echo "Waiting for Nextcloud to be ready (first deploy can take up to 5 minutes)..."
NC_WAIT_MAX=60   # 60 × 5s = 300s max
for i in $(seq 1 $NC_WAIT_MAX); do
  if docker exec -u www-data nextcloud_app php occ status 2>/dev/null | grep -q "installed: true"; then
    echo "Nextcloud is ready (${i}x5s elapsed)."
    break
  fi
  if [ "$i" = "$NC_WAIT_MAX" ]; then
    echo "WARNING: Nextcloud not confirmed ready after 300s — proceeding anyway"
    break
  fi
  printf "  ... %ds / 300s\r" "$((i * 5))"
  sleep 5
done

# Install/update NXT Workspace app
echo "Installing NXT AI Nextcloud app..."

docker exec -u www-data nextcloud_app php occ app:disable nxtworkspace 2>/dev/null || true

docker exec nextcloud_app rm -rf /var/www/html/custom_apps/nxtworkspace

docker cp "$PROJECT_ROOT/nxtworkspace" \
  nextcloud_app:/var/www/html/custom_apps/nxtworkspace

docker exec nextcloud_app chown -R www-data:www-data \
  /var/www/html/custom_apps/nxtworkspace

docker exec -u www-data nextcloud_app php -l \
  /var/www/html/custom_apps/nxtworkspace/lib/Controller/PageController.php

docker exec -u www-data nextcloud_app php -l \
  /var/www/html/custom_apps/nxtworkspace/lib/Controller/ApiController.php

docker exec -u www-data nextcloud_app php occ app:enable nxtworkspace

echo "NXT AI app installed and enabled."

# Tell Nextcloud it's behind HTTPS — without this, links break and logins 500.
# Safe to run on every deploy (idempotent).
docker exec -u www-data nextcloud_app php occ config:system:set trusted_proxies 0 --value="172.16.0.0/12" 2>/dev/null || true
docker exec -u www-data nextcloud_app php occ config:system:set overwriteprotocol --value=https 2>/dev/null || true
docker exec -u www-data nextcloud_app php occ config:system:set maintenance:mode --value=false 2>/dev/null || true

# Reload nginx so it picks up any Nextcloud container restarts (stale upstream → 502)
docker exec nextcloud_nginx nginx -s reload 2>/dev/null || true

bash "$PROJECT_ROOT/scripts/health-check.sh"

# First-deploy seed
# Seed Saudi enterprise data once, when the vector DB is empty (fresh VM).
DOC_COUNT=$(docker exec agentic_rag_postgres psql -U postgres -d vector_db -tAc "SELECT COUNT(*) FROM documents;" 2>/dev/null || echo "0")
if [ "${DOC_COUNT}" = "0" ]; then
  echo "Fresh deploy detected — seeding Saudi enterprise data..."
  bash "$PROJECT_ROOT/scripts/seed-saudi-company.sh" || echo "Seed warning (non-fatal)"
else
  echo "Documents already present (${DOC_COUNT} rows) — skipping first-deploy seed."
fi

# Post-deploy: generate any missing embeddings, then trigger an immediate
# Nextcloud sync instead of waiting for the next poller cycle.
RAG_PORT=$(docker exec agentic_rag_api printenv APP_PORT 2>/dev/null || echo "8058")
NC_ADMIN_USER=$(docker exec nextcloud_app printenv NEXTCLOUD_ADMIN_USER 2>/dev/null || echo "admin")
NC_ADMIN_PASS=$(docker exec nextcloud_app printenv NEXTCLOUD_ADMIN_PASSWORD 2>/dev/null)

echo "Waiting for RAG API..."
for i in $(seq 1 24); do
  HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${RAG_PORT}/health" 2>/dev/null || echo "000")
  [ "$HEALTH" = "200" ] && break
  [ "$i" = "24" ] && echo "RAG API not ready after 120s — skipping post-deploy tasks" && exit 0
  sleep 5
done

EMBED=$(curl -s -w "\n%{http_code}" -X POST -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
  "http://localhost:${RAG_PORT}/admin/embed-missing-chunks" 2>/dev/null)
EMBED_STATUS=$(echo "$EMBED" | tail -1)
echo "embed-missing-chunks: HTTP ${EMBED_STATUS} — $(echo "$EMBED" | head -1)"

SYNC=$(curl -s -w "\n%{http_code}" -X POST -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
  "http://localhost:${RAG_PORT}/admin/sync-nextcloud" 2>/dev/null)
SYNC_STATUS=$(echo "$SYNC" | tail -1)
echo "sync-nextcloud: HTTP ${SYNC_STATUS} — $(echo "$SYNC" | head -1)"

echo "Deploy complete."