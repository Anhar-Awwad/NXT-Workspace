
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import pypdfium2 as pdfium
from openai import AsyncOpenAI
import asyncio

logger = logging.getLogger(__name__)

CLEANUP_MODEL = os.getenv("EXTRACTION_MODEL", "gpt-4o-mini")
PAGES_PER_BATCH = int(os.getenv("EXTRACTION_PAGES_PER_BATCH", "8"))

PAGE_SEP = "\n\n=== PAGE BREAK ===\n\n"

CLEANUP_PROMPT = """Convert the following raw PDF page text into clean markdown.
Preserve all factual content exactly. Reconstruct any tables as markdown tables.
Fix broken line-wrapping and OCR-style artifacts. Do not summarize or omit content.
The input contains multiple pages separated by "=== PAGE BREAK ===" markers --
keep that exact separator between each page's cleaned output so page boundaries
are preserved. Return only the markdown, no commentary.

RAW TEXT:
{page_text}"""


def _extract_raw_text(pdf_path: Path) -> list[str]:
    """Fast native text extraction, one string per page. No ML models."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pages = []
        for page in pdf:
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return pages
    finally:
        pdf.close()


async def _cleanup_batch(client: AsyncOpenAI, pages: list[str]) -> list[str]:
    non_empty = [p for p in pages if p.strip()]
    if not non_empty:
        return ["" for _ in pages]

    batch_text = PAGE_SEP.join(non_empty)
    response = await client.chat.completions.create(
        model=CLEANUP_MODEL,
        messages=[{"role": "user", "content": CLEANUP_PROMPT.format(page_text=batch_text)}],
        temperature=0,
    )
    cleaned = (response.choices[0].message.content or "").split(PAGE_SEP.strip())
    if len(cleaned) != len(non_empty):
        # Model didn't preserve the separator exactly -- fall back to the raw batch
        # rather than silently losing/misaligning page content.
        logger.warning("Page-break markers lost in cleanup batch; using raw text for this batch")
        return pages

    result = []
    it = iter(cleaned)
    for p in pages:
        result.append(next(it).strip() if p.strip() else "")
    return result


class LightweightPDFExtractor:
    """Drop-in replacement for PDFExtractor: same extract_pdf_content(path) ->
    (content_text, metadata) interface, without Docling's local ML models."""

    def __init__(self, use_openai_cleanup: bool = True):
        self.use_openai_cleanup = use_openai_cleanup
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) if use_openai_cleanup else None

    async def extract_pdf_content(self, pdf_path: str) -> Tuple[str, Dict[str, Any]]:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        logger.info(f"Extracting content from: {pdf_path.name} (lightweight)")
        start_time = time.time()

        raw_pages = _extract_raw_text(pdf_path)

        if self.use_openai_cleanup:
            cleaned_pages = await self._cleanup_all_pages(raw_pages)
        else:
            cleaned_pages = raw_pages

        content_text = "\n\n".join(p for p in cleaned_pages if p.strip())
        end_time = time.time()

        metadata = {
            "source": str(pdf_path),
            "title": pdf_path.stem,
            "processing_time": round(end_time - start_time, 2),
            "pages": len(raw_pages),
            "extraction_method": "pypdfium2+openai" if self.use_openai_cleanup else "pypdfium2",
            "content_type": "pdf",
        }
        return content_text, metadata

    async def _cleanup_all_pages(self, raw_pages: list[str]) -> list[str]:
        batches = [
            raw_pages[i:i + PAGES_PER_BATCH]
            for i in range(0, len(raw_pages), PAGES_PER_BATCH)
        ]
        # Bounded concurrency to avoid rate-limit spikes on multi-batch docs.
        semaphore = asyncio.Semaphore(5)

        async def bounded(batch: list[str]) -> list[str]:
            async with semaphore:
                return await _cleanup_batch(self.client, batch)

        results = await asyncio.gather(*(bounded(b) for b in batches))
        return [page for batch_result in results for page in batch_result]


def create_pdf_extractor(use_openai_cleanup: bool = True) -> LightweightPDFExtractor:
    return LightweightPDFExtractor(use_openai_cleanup=use_openai_cleanup)
