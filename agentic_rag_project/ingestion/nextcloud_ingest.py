
import argparse
import asyncio
import json
import logging
import os
import urllib.parse
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from dotenv import load_dotenv

from agent.db_utils import db_pool
from agent.models import IngestionConfig
from .ingest import DocumentIngestionPipeline

load_dotenv()

logger = logging.getLogger(__name__)
_scan_lock = asyncio.Lock()

NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL", "http://nextcloud").rstrip("/")
NEXTCLOUD_SERVICE_USER = os.getenv("NEXTCLOUD_SERVICE_USER", "admin")
NEXTCLOUD_SERVICE_PASSWORD = os.getenv("NEXTCLOUD_SERVICE_PASSWORD", "")
DEFAULT_GROUPS = os.getenv("NEXTCLOUD_INGEST_GROUPS", "Finance,Engineering")

POLL_INTERVAL_SECONDS = int(os.getenv("NEXTCLOUD_POLL_INTERVAL_SECONDS", "0") or "0")

DAV_NS = "{DAV:}"



async def list_group_folder_pdfs(client: httpx.AsyncClient, group: str) -> list[dict]:
    """
    PROPFIND-list PDF files directly under the service account's view of a Nextcloud
    group folder. Group folders (via the `groupfolders` app) show up in the service
    account's own WebDAV file list as long as it's a member of that group -- same
    path a normal user would use, e.g. /remote.php/dav/files/{user}/{group_folder}/.
    Non-recursive (top level only) for this MVP version.

    Returns a list of {"href": ..., "etag": ...} -- the etag changes whenever a
    file's content changes, which is how new-vs-unchanged-vs-updated is detected
    without re-downloading/re-embedding every file on every scan.
    """
    url = f"{NEXTCLOUD_URL}/remote.php/dav/files/{NEXTCLOUD_SERVICE_USER}/{group}/"
    body = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">
  <d:prop>
    <d:getetag/>
    <oc:fileid/>
  </d:prop>
</d:propfind>"""
    resp = await client.request(
        "PROPFIND", url, headers={"Depth": "1", "Content-Type": "application/xml"},
        content=body, auth=(NEXTCLOUD_SERVICE_USER, NEXTCLOUD_SERVICE_PASSWORD)
    )
    if resp.status_code not in (200, 207):
        logger.warning(
            f"Could not list Nextcloud folder '{group}' (HTTP {resp.status_code}) -- "
            f"does the group folder exist, and is '{NEXTCLOUD_SERVICE_USER}' a member of group '{group}'?"
        )
        return []

    root = ET.fromstring(resp.text)
    files = []
    for response_el in root.findall(f"{DAV_NS}response"):
        href = response_el.find(f"{DAV_NS}href").text
        if href.rstrip("/").endswith(f"/{group}"):
            continue  # skip the folder entry itself
        if not href.lower().endswith(".pdf"):
            continue
        etag_el = response_el.find(f".//{DAV_NS}getetag")
        etag = etag_el.text if etag_el is not None else None
        file_id_el = response_el.find(".//{http://owncloud.org/ns}fileid")
        file_id = file_id_el.text if file_id_el is not None else None
        files.append({"href": href, "etag": etag, "file_id": file_id})
    return files


async def _get_existing_document(nextcloud_path: str) -> dict | None:
    """Look up a previously-ingested document by its Nextcloud path, if any."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id::text, metadata FROM documents WHERE metadata->>'nextcloud_path' = $1",
            nextcloud_path,
        )
    if row is None:
        return None
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return {"id": row["id"], "metadata": metadata}


async def _delete_document(document_id: str) -> None:
    """Delete a document and its chunks (ON DELETE CASCADE) before re-ingesting
    an updated version of the same file."""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM documents WHERE id = $1::uuid", document_id)


async def download_file(client: httpx.AsyncClient, href: str, dest_path: Path) -> None:
    url = href if href.startswith("http") else f"{NEXTCLOUD_URL}{href}"
    resp = await client.get(url, auth=(NEXTCLOUD_SERVICE_USER, NEXTCLOUD_SERVICE_PASSWORD))
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(resp.content)


async def ingest_group_document(
    pipeline: DocumentIngestionPipeline, local_path: Path, group: str,
    nextcloud_href: str, etag: str | None, nextcloud_file_id: str | None
):
    """Extract, tag with allowed_group, chunk, embed, and save one file. Mirrors
    DocumentIngestionPipeline._ingest_single_document but injects the group tag
    between extraction and chunking."""
    if pipeline.use_docling:
        document_content, document_metadata = pipeline.extractor.extract_pdf_content(str(local_path))
    else:
        document_content, document_metadata = await pipeline.extractor.extract_pdf_content(str(local_path))
    document_metadata["allowed_group"] = group
    document_metadata["nextcloud_path"] = nextcloud_href
    document_metadata["nextcloud_etag"] = etag
    document_metadata["nextcloud_file_id"] = nextcloud_file_id
    document_source = f"nextcloud://{group}/{local_path.name}"
    document_title = document_metadata.get("title", local_path.stem)

    logger.info(f"Processing Nextcloud document: {document_title} (group={group})")

    main_chunks = pipeline.chunker.chunk_content(
        content=document_content,
        title=document_title,
        source=document_source,
        metadata=document_metadata
    )
    if not main_chunks:
        logger.warning(f"No chunks created for {document_title}")
        return None

    embedded_chunks = await pipeline.aembed_chunks(chunks=main_chunks)
    document_id = await pipeline._save_to_postgres(
        document_title, document_source, document_content, embedded_chunks, document_metadata
    )
    logger.info(f"Saved '{document_title}' -> document {document_id}, {len(main_chunks)} chunks, group={group}")
    return document_id


async def scan_and_ingest(pipeline: DocumentIngestionPipeline, groups: list[str], tmp_root: Path) -> dict:
    """
    One scan pass across the given Nextcloud group folders. Skips files whose
    Nextcloud etag hasn't changed since the last ingested version (no re-download,
    no re-embedding, no wasted OpenAI cost) -- new files get ingested, and a
    changed file (etag differs) replaces its old document + chunks rather than
    creating a duplicate. This is what makes repeated calls (the poller, or
    re-running the CLI) safe and cheap instead of re-ingesting everything each time.

    Guarded by _scan_lock so a manual sync landing mid-poll-cycle can't race the
    background poller and double-ingest the same new file.
    """
    async with _scan_lock:
        return await _scan_and_ingest_locked(pipeline, groups, tmp_root)


async def _scan_and_ingest_locked(pipeline: DocumentIngestionPipeline, groups: list[str], tmp_root: Path) -> dict:
    stats = {"new": 0, "updated": 0, "unchanged": 0, "failed": 0}
    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        for group in groups:
            logger.info(f"Scanning Nextcloud group folder: {group}")
            files = await list_group_folder_pdfs(client, group)
            logger.info(f"Found {len(files)} PDF(s) in '{group}'")
            for f in files:
                href, etag, file_id = f["href"], f["etag"], f["file_id"]
                try:
                    existing = await _get_existing_document(href)
                    if (
                        existing
                        and existing["metadata"].get("nextcloud_etag") == etag
                        and existing["metadata"].get("nextcloud_file_id")
                    ):
                        continue

                    filename = urllib.parse.unquote(href.rstrip("/").split("/")[-1])
                    local_path = tmp_root / group / filename
                    await download_file(client, href, local_path)

                    if existing:
                        logger.info(f"'{filename}' changed on Nextcloud -- re-ingesting")
                        await _delete_document(existing["id"])
                        result = await ingest_group_document(pipeline, local_path, group, href, etag, file_id)
                        if result:
                            stats["updated"] += 1
                    else:
                        result = await ingest_group_document(pipeline, local_path, group, href, etag, file_id)
                        if result:
                            stats["new"] += 1
                except Exception as e:
                    logger.error(f"Failed to ingest '{href}': {e}")
                    stats["failed"] += 1
    return stats


async def poll_forever(groups: list[str], interval_seconds: int, sql_schema_path: str = "sql/schema.sql"):
    """
    2026-09-23 update: background auto-ingestion. Runs scan_and_ingest() on a
    fixed interval for as long as the process lives -- this is the actual
    "upload a file to Nextcloud and it becomes searchable in RAG chat without
    a human running a command" behavior, closing the gap the original plan
    flagged as manual-only. Not truly instant (bounded by interval_seconds,
    not event-driven), but a real automatic trigger with no Nextcloud-side
    webhook/Flow app setup required. Intended to be launched as a background
    task from agent/api.py's startup, not run standalone (use `main()`/the CLI
    for a one-shot run instead).
    """
    if interval_seconds <= 0:
        logger.info("NEXTCLOUD_POLL_INTERVAL_SECONDS not set -- auto-ingestion poller disabled.")
        return
    if not NEXTCLOUD_SERVICE_PASSWORD:
        logger.warning("NEXTCLOUD_SERVICE_PASSWORD not set -- auto-ingestion poller disabled.")
        return

    tmp_root = Path("/tmp/nextcloud_ingest")
    pipeline = DocumentIngestionPipeline(
        config=IngestionConfig(),
        documents_folder=str(tmp_root),
        sql_schema_path=sql_schema_path,
    )
    await pipeline.initialize()
    logger.info(f"Nextcloud auto-ingestion poller started -- scanning every {interval_seconds}s: {groups}")

    try:
        while True:
            try:
                stats = await scan_and_ingest(pipeline, groups, tmp_root)
                if stats["new"] or stats["updated"] or stats["failed"]:
                    logger.info(f"Auto-ingestion scan complete: {stats}")
                else:
                    logger.debug(f"Auto-ingestion scan complete: {stats}")
            except Exception as e:
                # A single bad scan (e.g. Nextcloud briefly unreachable) shouldn't
                # kill the poller permanently -- log and try again next interval.
                logger.error(f"Auto-ingestion scan failed, will retry next interval: {e}")
            await asyncio.sleep(interval_seconds)
    finally:
        await pipeline.close()


async def main():
    parser = argparse.ArgumentParser(description="Ingest PDFs from Nextcloud group folders (permission-aware)")
    parser.add_argument("--groups", default=DEFAULT_GROUPS, help="Comma-separated Nextcloud group folder names")
    parser.add_argument("--sql-schema-path", "-sql", default="sql/schema.sql")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if not NEXTCLOUD_SERVICE_PASSWORD:
        logger.error("NEXTCLOUD_SERVICE_PASSWORD is not set in .env -- cannot authenticate to Nextcloud.")
        return

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    tmp_root = Path("/tmp/nextcloud_ingest")

    pipeline = DocumentIngestionPipeline(
        config=IngestionConfig(),
        documents_folder=str(tmp_root),
        sql_schema_path=args.sql_schema_path,
    )
    await pipeline.initialize()

    try:
        stats = await scan_and_ingest(pipeline, groups, tmp_root)
    finally:
        await pipeline.close()

    logger.info(
        f"Nextcloud ingestion complete: {stats['new']} new, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged, {stats['failed']} failed, across {len(groups)} group(s)"
    )


if __name__ == "__main__":
    asyncio.run(main())
