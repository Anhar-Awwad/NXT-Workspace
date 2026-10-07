#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_PASSWORD="${DEMO_PASSWORD:-Tahweel@KSA2026!}"

echo "================================================================"
echo " Seeding Real Saudi Enterprise Data (Tahweel Tech Solutions)"
echo " Nextcloud & Agentic RAG Unified Stack"
echo " Default Enterprise Password: ${DEMO_PASSWORD}"
echo "================================================================"

# Nextcloud Groups & Users (Saudi Enterprise)
echo -e "\n[1/4] Creating Saudi Enterprise Groups & Users in Nextcloud..."

DEPARTMENTS=(
  "Executive"
  "Human-Resources"
  "Finance"
  "IT-Cybersecurity"
  "Legal-Compliance"
  "Operations"
  "Sales-BD"
)

for dept in "${DEPARTMENTS[@]}"; do
  docker exec -u www-data nextcloud_app php occ group:add "$dept" 2>/dev/null || true
done

USERS_DATA=(
  "tariq.ghamdi|طارق الغامدي - Tariq Al-Ghamdi|Executive"
  "sara.otaibi|سارة العتيبي - Sara Al-Otaibi|Human-Resources"
  "fahad.zahrani|فهد الزهراني - Fahad Al-Zahrani|Finance"
  "noura.shehri|نورة الشهري - Noura Al-Shehri|IT-Cybersecurity"
  "abdulaziz.dosari|عبدالعزيز الدوسري - Abdulaziz Al-Dosari|Legal-Compliance"
  "reem.harbi|ريم الحربي - Reem Al-Harbi|Operations"
  "mohammed.qahtani|محمد القحطاني - Mohammed Al-Qahtani|Sales-BD"
)

for item in "${USERS_DATA[@]}"; do
  IFS="|" read -r username display_name group <<< "$item"
  echo "Processing Nextcloud user: $username ($group)..."
  docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:add \
    --password-from-env --display-name="${display_name}" --group="${group}" "${username}" 2>/dev/null \
    || docker exec -u www-data -e OC_PASS="${DEMO_PASSWORD}" nextcloud_app php occ user:resetpassword --password-from-env "${username}" 2>/dev/null || true
done

# Ensure internal container hostname is in trusted_domains
docker exec -u www-data nextcloud_app php occ config:system:set trusted_domains 4 --value=nextcloud 2>/dev/null || true
docker exec nextcloud_app apache2ctl graceful 2>/dev/null || true

echo "✓ Nextcloud Saudi enterprise users and groups created successfully!"

# Create Nextcloud Department Folders (WebDAV)
# The RAG poller scans /remote.php/dav/files/{admin}/{group}/ for PDFs.
# Folders must exist before the poller starts or it logs 404 on every cycle.
echo -e "\n[2/4] Creating Nextcloud department folders for ingestion..."
NC_ADMIN_USER=$(docker exec nextcloud_app printenv NEXTCLOUD_ADMIN_USER 2>/dev/null || echo "admin")
NC_ADMIN_PASS=$(docker exec nextcloud_app printenv NEXTCLOUD_ADMIN_PASSWORD 2>/dev/null)
for group in Executive Human-Resources Finance IT-Cybersecurity Legal-Compliance Operations Sales-BD; do
  HTTP_CODE=$(docker exec nextcloud_app curl -s -o /dev/null -w "%{http_code}" \
    -X MKCOL -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
    "http://localhost/remote.php/dav/files/${NC_ADMIN_USER}/${group}/" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "201" ]; then
    echo "  ✓ Created folder: ${group}"
  elif [ "$HTTP_CODE" = "405" ]; then
    echo "  - Folder already exists: ${group}"
  else
    echo "  ! Could not create folder '${group}' (HTTP ${HTTP_CODE})"
  fi
done
echo "✓ Nextcloud department folders ready!"

# Upload Seed PDF Documents to Nextcloud
echo -e "\n[3/4] Uploading seed PDF documents to Nextcloud..."
DOCS_DIR="${REPO_DIR}/scripts/seed-documents"

# Each entry: "filename.pdf:TargetDepartment"
PDF_MAPPINGS=(
  "executive_test.pdf:Executive"
  "finance_test.pdf:Finance"
  "hr_test.pdf:Human-Resources"
  "it_test.pdf:IT-Cybersecurity"
  "legal_test.pdf:Legal-Compliance"
  "operations_test.pdf:Operations"
  "sales_test.pdf:Sales-BD"
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

# Seed Corporate Documents into Vector Knowledge Base 
echo -e "\n[4/4] Ingesting Saudi Enterprise Corporate Knowledge into Vector DB..."

docker exec -i agentic_rag_postgres psql -U postgres -d vector_db <<EOSQL
DELETE FROM chunks WHERE document_id IN (
  SELECT id FROM documents WHERE metadata->>'source_type' = 'enterprise_seed'
);
DELETE FROM documents WHERE metadata->>'source_type' = 'enterprise_seed';

WITH ins_docs AS (
  INSERT INTO documents (title, source, content, metadata, created_at)
  VALUES
    (
      'NCA Cybersecurity Compliance Manual (ECC-1:2018)',
      'https://tahweel.sa/docs/it/NCA_ECC_Framework.pdf',
      'Tahweel Information Technology & Cybersecurity Policy: Aligned with the National Cybersecurity Authority (NCA) Essential Cybersecurity Controls (ECC-1:2018). All systems require multi-factor authentication (MFA), end-to-end data encryption at rest (AES-256) and in transit (TLS 1.3), automated vulnerability scanning, and incident response within 60 minutes for high-severity threats.',
      '{"department":"IT-Cybersecurity","source_type":"enterprise_seed","owner":"noura.shehri"}',
      now()
    ),
    (
      'Tahweel ZATCA E-Invoicing Phase 2 Implementation Guide',
      'https://tahweel.sa/docs/finance/ZATCA_Fatoora_Phase2.pdf',
      'Tahweel Financial & Accounting Standards: Compliant with the Zakat, Tax and Customs Authority (ZATCA) regulations for Phase 2 Integration of E-Invoicing (Fatoora). All invoices must be cryptographically signed using cryptographic stamps and QR codes generated compliant with ZATCA standard format XML specifications. Monthly VAT returns are filed before the end of each Gregorian calendar month.',
      '{"department":"Finance","source_type":"enterprise_seed","owner":"fahad.zahrani"}',
      now()
    ),
    (
      'Tahweel Employee Handbook & Saudization (Nitaqat Platinum) Guidelines',
      'https://tahweel.sa/docs/hr/Employee_Handbook_2026.pdf',
      'Tahweel Human Resources Policy: Tahweel is classified in the Platinum tier of the Ministry of Human Resources Saudization program (Nitaqat). Working hours are 40 hours per week Sunday through Thursday. Annual leave is 30 calendar days per annum. Training budgets are allocated semi-annually under the Vision 2030 Human Capability Development Program.',
      '{"department":"Human-Resources","source_type":"enterprise_seed","owner":"sara.otaibi"}',
      now()
    ),
    (
      'Tahweel Standard Commercial Agreement & KSA Legal Bylaws',
      'https://tahweel.sa/docs/legal/Commercial_Agreement_Template.pdf',
      'Tahweel Legal Governance & Standard Contracts: All commercial engagements are governed under the laws of the Kingdom of Saudi Arabia with arbitration jurisdiction in Riyadh. Non-Disclosure Agreements (NDAs) are mandatory for all vendor contracts. Data privacy is strictly enforced following the KSA Personal Data Protection Law (PDPL).',
      '{"department":"Legal-Compliance","source_type":"enterprise_seed","owner":"abdulaziz.dosari"}',
      now()
    ),
    (
      'Tahweel Strategic Growth Vision 2030 Roadmap',
      'https://tahweel.sa/docs/exec/Vision_2030_Strategy.pdf',
      'Tahweel Executive Strategy & Vision 2030: Expanding enterprise AI solutions and sovereign cloud file-sharing across Saudi government entities and private enterprises. Key performance indicators target 45% annual growth, enterprise retention rate of 98%, and complete digital transformation across all branches in Riyadh, Jeddah, and Dammam.',
      '{"department":"Executive","source_type":"enterprise_seed","owner":"tariq.ghamdi"}',
      now()
    )
  RETURNING id, title, content, metadata
)
INSERT INTO chunks (document_id, chunk_index, content, metadata)
SELECT
  d.id,
  0,
  d.content,
  jsonb_build_object('department', d.metadata->>'department', 'title', d.title, 'source_type', 'enterprise_seed')
FROM ins_docs d;
EOSQL

echo "✓ Vector knowledge base seeded!"

# RAG: embed seed chunks + ingest uploaded PDFs 
echo -e "\nConnecting to RAG API..."
RAG_PORT=$(docker exec agentic_rag_api printenv APP_PORT 2>/dev/null || echo "8058")

# Wait up to 60s for the RAG API to be ready
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${RAG_PORT}/health" 2>/dev/null || echo "000")
  [ "$HEALTH" = "200" ] && break
  echo "  Waiting for RAG API (attempt ${i}/12)..."
  sleep 5
done

# Step 5a: generate embeddings for the SQL-seeded chunks (no embedding = invisible to vector search)
EMBED_CODE=$(curl -s -o /tmp/rag_embed_result.json -w "%{http_code}" \
  -X POST \
  -u "${NC_ADMIN_USER}:${NC_ADMIN_PASS}" \
  "http://localhost:${RAG_PORT}/admin/embed-missing-chunks" 2>/dev/null || echo "000")
if [ "$EMBED_CODE" = "200" ]; then
  echo "  ✓ SQL seed embeddings generated: $(cat /tmp/rag_embed_result.json 2>/dev/null)"
else
  echo "  ! embed-missing-chunks returned HTTP ${EMBED_CODE} — vector search may not find seeded knowledge"
fi
rm -f /tmp/rag_embed_result.json

# Step 5b: trigger Nextcloud PDF ingestion (chunking + embedding of uploaded files)
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

echo -e "\n✓ Successfully seeded complete Saudi enterprise environment!"
echo "================================================================"
echo " Saudi Enterprise Credentials:"
echo " Company: Tahweel Tech Solutions (شركة تحويل التقنية)"
echo " Default Password: ${DEMO_PASSWORD}"
echo ""
echo " 1. Executive / CEO:"
echo "    Nextcloud: tariq.ghamdi / ${DEMO_PASSWORD} [Group: Executive]"
echo " 2. Human Resources:"
echo "    Nextcloud: sara.otaibi / ${DEMO_PASSWORD} [Group: Human-Resources]"
echo " 3. Finance & Accounting:"
echo "    Nextcloud: fahad.zahrani / ${DEMO_PASSWORD} [Group: Finance]"
echo " 4. Cybersecurity & IT:"
echo "    Nextcloud: noura.shehri / ${DEMO_PASSWORD} [Group: IT-Cybersecurity]"
echo " 5. Legal & Compliance:"
echo "    Nextcloud: abdulaziz.dosari / ${DEMO_PASSWORD} [Group: Legal-Compliance]"
echo " 6. Operations:"
echo "    Nextcloud: reem.harbi / ${DEMO_PASSWORD} [Group: Operations]"
echo " 7. Sales & Business Dev:"
echo "    Nextcloud: mohammed.qahtani / ${DEMO_PASSWORD} [Group: Sales-BD]"
echo ""
echo " Documents uploaded to Nextcloud:"
echo "    Finance/   → sr_2020.pdf, sr_2021.pdf, sr_2022.pdf"
echo "    Executive/ → sr2023.pdf, sr2024.pdf, sr_2024_cb_v.pdf"
echo ""
echo " RAG UI (port 8501): Log in with any Nextcloud username/password"
echo "================================================================"