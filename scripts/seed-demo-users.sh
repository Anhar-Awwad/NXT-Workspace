#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_PASSWORD="${DEMO_PASSWORD:-NextcloudDemo2026!}"

echo "================================================================"
echo " Seeding Demo Users and Departments"
echo " Nextcloud & Agentic RAG Unified Stack"
echo " Default Demo Password: ${DEMO_PASSWORD}"
echo "================================================================"

# Seed Nextcloud Groups & Users 
echo -e "\n[1/4] Seeding Nextcloud Groups and Users..."

docker exec -u www-data nextcloud_app php occ group:add Engineering 2>/dev/null || true
docker exec -u www-data nextcloud_app php occ group:add Finance 2>/dev/null || true
docker exec -u www-data nextcloud_app php occ group:add Marketing 2>/dev/null || true

docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:add \
  --password-from-env --display-name="Alice Engineer" --group="Engineering" alice 2>/dev/null \
  || docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:resetpassword --password-from-env alice 2>/dev/null || true

docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:add \
  --password-from-env --display-name="Bob Finance" --group="Finance" bob 2>/dev/null \
  || docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:resetpassword --password-from-env bob 2>/dev/null || true

docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:add \
  --password-from-env --display-name="Charlie Marketing" --group="Marketing" charlie 2>/dev/null \
  || docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:resetpassword --password-from-env charlie 2>/dev/null || true

echo "✓ Nextcloud demo users seeded successfully!"

# Create Nextcloud Group Folders (WebDAV)
# The RAG poller scans /remote.php/dav/files/{admin}/{group}/ for PDFs.
echo -e "\n[2/4] Creating Nextcloud group folders for ingestion..."
NC_ADMIN_USER=$(docker exec nextcloud_app printenv NEXTCLOUD_ADMIN_USER 2>/dev/null || echo "admin")
NC_ADMIN_PASS=$(docker exec nextcloud_app printenv NEXTCLOUD_ADMIN_PASSWORD 2>/dev/null)
for group in Engineering Finance Marketing; do
  HTTP_CODE=$(docker exec nextcloud_app curl -s -o /dev/null -w "%{http_code}" \
    -X MKCOL -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
    "http://localhost/remote.php/dav/files/${NC_ADMIN_USER}/${group}/" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "201" ]; then
    echo "  ✓ Created folder: ${group}"
  elif [ "$HTTP_CODE" = "405" ]; then
    echo "  - Folder already exists: ${group}"
  else
    echo "  ! Could not create folder '${group}' (HTTP ${HTTP_CODE}) -- create it manually in Nextcloud"
  fi
done
echo "✓ Nextcloud group folders ready (upload PDFs here for RAG auto-ingestion)"

# Upload Seed PDF Documents to Nextcloud 
echo -e "\n[3/4] Uploading seed PDF documents to Nextcloud..."
DOCS_DIR="${REPO_DIR}/scripts/seed-documents"

# Each entry: "filename.pdf:TargetDepartment"
PDF_MAPPINGS=(
  "finance_test.pdf:Finance"
)

if [ -d "$DOCS_DIR" ]; then
  for mapping in "${PDF_MAPPINGS[@]}"; do
    pdf="${mapping%%:*}"
    dept="${mapping##*:}"
    src="${DOCS_DIR}/${pdf}"
    if [ -f "$src" ]; then
      docker cp "$src" nextcloud_app:"/tmp/${pdf}"
      HTTP_CODE=$(docker exec nextcloud_app curl -s -o /dev/null -w "%{http_code}" \
        -X PUT \
        -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
        --data-binary "@/tmp/${pdf}" \
        "http://localhost/remote.php/dav/files/${NC_ADMIN_USER}/${dept}/${pdf}" 2>/dev/null || echo "000")
      docker exec nextcloud_app rm -f "/tmp/${pdf}" 2>/dev/null || true
      if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "204" ]; then
        echo "  ✓ Uploaded ${pdf} → ${dept}/"
      else
        echo "  ! Upload failed: ${pdf} (HTTP ${HTTP_CODE})"
      fi
    else
      echo "  - Skipping ${pdf} (not found in seed-documents/)"
    fi
  done
else
  echo "  - ${DOCS_DIR} not found — skipping PDF upload"
fi
echo "✓ Nextcloud PDF upload complete!"

# Seed Demo Documents into Vector Knowledge Base 
echo -e "\n[4/4] Seeding Demo Documents into RAG Vector DB..."

docker exec -i agentic_rag_postgres psql -U postgres -d vector_db <<EOSQL
DELETE FROM chunks WHERE document_id IN (
  SELECT id FROM documents WHERE metadata->>'source_type' = 'demo_seed'
);
DELETE FROM documents WHERE metadata->>'source_type' = 'demo_seed';

WITH ins_docs AS (
  INSERT INTO documents (title, source, content, metadata, created_at)
  VALUES
    (
      'Engineering Best Practices Guide',
      'internal://engineering/best-practices.pdf',
      'Engineering Department Standards: All code must be reviewed before merging. CI/CD pipelines run automated tests on every pull request. Docker containers are used for all services. Infrastructure is managed via Terraform. Security patches must be applied within 48 hours of disclosure.',
      '{"department":"Engineering","source_type":"demo_seed","owner":"alice"}',
      now()
    ),
    (
      'Finance & Budget Policy 2026',
      'internal://finance/budget-policy-2026.pdf',
      'Finance Department Policy: All purchases above $5,000 require manager approval. Monthly financial reports are due on the 5th of each month. Expense reimbursements are processed within 10 business days. Annual budget planning begins in October each year.',
      '{"department":"Finance","source_type":"demo_seed","owner":"bob"}',
      now()
    ),
    (
      'Marketing Campaign Guidelines',
      'internal://marketing/campaign-guidelines.pdf',
      'Marketing Department Guidelines: All external communications must be reviewed by legal before publication. Brand assets are stored in the shared drive under /Marketing/Assets. Campaign performance is tracked via monthly KPI dashboards. Social media posts require 24-hour advance approval.',
      '{"department":"Marketing","source_type":"demo_seed","owner":"charlie"}',
      now()
    )
  RETURNING id, title, content, metadata
)
INSERT INTO chunks (document_id, chunk_index, content, metadata)
SELECT
  d.id,
  0,
  d.content,
  jsonb_build_object('department', d.metadata->>'department', 'title', d.title, 'source_type', 'demo_seed')
FROM ins_docs d;
EOSQL

echo "✓ RAG demo documents seeded successfully!"

# RAG: embed seed chunks + ingest uploaded PDFs 
echo -e "\nConnecting to RAG API..."
RAG_PORT=$(docker exec agentic_rag_api printenv APP_PORT 2>/dev/null || echo "8058")

for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${RAG_PORT}/health" 2>/dev/null || echo "000")
  [ "$HEALTH" = "200" ] && break
  echo "  Waiting for RAG API (attempt ${i}/12)..."
  sleep 5
done

EMBED_CODE=$(curl -s -o /tmp/rag_embed_result.json -w "%{http_code}" \
  -X POST \
  -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
  "http://localhost:${RAG_PORT}/admin/embed-missing-chunks" 2>/dev/null || echo "000")
if [ "$EMBED_CODE" = "200" ]; then
  echo "  ✓ SQL seed embeddings generated: $(cat /tmp/rag_embed_result.json 2>/dev/null)"
else
  echo "  ! embed-missing-chunks returned HTTP ${EMBED_CODE}"
fi
rm -f /tmp/rag_embed_result.json

SYNC_CODE=$(curl -s -o /tmp/rag_sync_result.json -w "%{http_code}" \
  -X POST \
  -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
  "http://localhost:${RAG_PORT}/admin/sync-nextcloud" 2>/dev/null || echo "000")
if [ "$SYNC_CODE" = "200" ]; then
  echo "  ✓ Nextcloud PDF ingestion triggered: $(cat /tmp/rag_sync_result.json 2>/dev/null)"
else
  echo "  ! sync-nextcloud returned HTTP ${SYNC_CODE} — PDFs will be auto-ingested within ${NEXTCLOUD_POLL_INTERVAL_SECONDS:-300}s"
fi
rm -f /tmp/rag_sync_result.json

echo -e "\n================================================================"
echo " Seeding Summary:"
echo " 1. Nextcloud App (https://localhost):"
echo "    - admin   / (see NEXTCLOUD_ADMIN_PASSWORD in .env)"
echo "    - alice   / ${DEMO_PASSWORD} (Group: Engineering)"
echo "    - bob     / ${DEMO_PASSWORD} (Group: Finance)"
echo "    - charlie / ${DEMO_PASSWORD} (Group: Marketing)"
echo ""
echo " 2. Documents uploaded to Nextcloud:"
echo "    Finance/ → sr_2020.pdf, sr_2021.pdf, sr_2022.pdf, sr2023.pdf, sr2024.pdf, sr_2024_cb_v.pdf"
echo ""
echo " 3. RAG UI (http://localhost:8501):"
echo "    Log in with any Nextcloud username/password above"
echo "================================================================"