"""
Parser for PDF files using ``pypdf``.

Extracts text page-by-page and concatenates it into a single string.

OCR Strategy (scanned PDFs)
----------------------------
When pypdf finds less than 50 extractable characters (i.e. the PDF is image-only
/ scanned), we fall back to OCR. The critical memory constraint on Render Free
Tier (512 MB) is that pdf2image loads ALL pages as PIL Images into RAM at once.

At 200 DPI, a single A4 page = ~11 MB in RAM. A 10-page scanned PDF would
consume 110 MB of images alone, plus the 210 MB server baseline => OOM.

Fix: convert_from_bytes supports ``first_page`` / ``last_page`` parameters.
We iterate one page at a time, call GC after each page, and cap at
MAX_OCR_PAGES to prevent runaway allocation on any input.

At 150 DPI, one A4 page = ~6.2 MB. Peak during OCR = 210 MB + 6.2 MB = 216 MB.
This is provably safe regardless of how many pages the PDF has.
"""
from typing import Optional

from pypdf import PdfReader

from parsers.base import BaseParser, Document
from utils.logger import logger

# Maximum number of pages we attempt OCR on. Pages beyond this are silently
# skipped. 20 pages is more than enough for any typical document a user
# would include in a 5 MB workspace ZIP.
MAX_OCR_PAGES = 20

# Lower DPI = smaller PIL Image per page = less RAM.
# 150 DPI produces fully legible OCR text while using 44% less RAM than 200 DPI.
OCR_DPI = 150


class PdfParser(BaseParser):
    """Handles .pdf files."""

    def parse(self, file_content: bytes, filename: str, source_path: Optional[str] = None) -> Document:
        """
        Extract text from every page of a PDF, with safe per-page OCR fallback.

        Memory-safe contract
        --------------------
        - pypdf text extraction: O(page_text) memory, never holds all pages
        - OCR fallback: exactly ONE PIL Image in RAM at a time (per-page loop)
        - Peak memory on any 5 MB PDF: baseline + 6.2 MB = ~220 MB (safe on Render)
        """
        import io
        import gc

        reader = PdfReader(io.BytesIO(file_content))
        page_count = len(reader.pages)
        rel = source_path or filename
        pages_text: list[str] = []

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                pages_text.append(extracted)

        text = "\n\n".join(pages_text)

        # Gather metadata before deleting reader
        meta: dict = {"parser": "PdfParser", "page_count": page_count}
        if reader.metadata:
            if reader.metadata.title:
                meta["title"] = reader.metadata.title
            if reader.metadata.author:
                meta["author"] = reader.metadata.author

        # Free pypdf reader and page text list — no longer needed
        del reader, pages_text
        gc.collect()

        # If pypdf extracted almost nothing, it's likely a scanned PDF.
        # Fallback to OCR via pdf2image + pytesseract, ONE PAGE AT A TIME.
        if len(text.strip()) < 50:
            logger.info(
                f"PdfParser: '{rel}' has <50 extractable chars — falling back to "
                f"per-page OCR (max {MAX_OCR_PAGES} pages at {OCR_DPI} DPI)."
            )
            # Deliberately import inside the branch so the import cost (pdf2image,
            # Pillow, pytesseract) is NOT paid for normal text-extractable PDFs.
            from pdf2image import convert_from_bytes
            import pytesseract

            pages_to_ocr = min(page_count, MAX_OCR_PAGES)
            ocr_texts: list[str] = []

            for page_num in range(1, pages_to_ocr + 1):
                # Load exactly ONE page at a time.
                # convert_from_bytes with first_page=last_page always returns a
                # list of exactly one PIL Image. This is the critical fix that
                # limits RAM to ~6 MB per iteration instead of N*11 MB at once.
                images = convert_from_bytes(
                    file_content,
                    first_page=page_num,
                    last_page=page_num,
                    dpi=OCR_DPI,
                )
                page_text = pytesseract.image_to_string(images[0]).strip()

                # Release the PIL Image immediately — do not accumulate all pages
                del images
                gc.collect()

                if page_text:
                    ocr_texts.append(page_text)

                logger.debug(
                    f"PdfParser: OCR page {page_num}/{pages_to_ocr} of '{rel}' "
                    f"({len(page_text)} chars)"
                )

            text = "\n\n".join(ocr_texts)
            del ocr_texts
            gc.collect()

            if page_count > MAX_OCR_PAGES:
                logger.warning(
                    f"PdfParser: '{rel}' has {page_count} pages; "
                    f"OCR limited to first {MAX_OCR_PAGES} pages to stay within memory budget."
                )
            logger.info(
                f"PdfParser: OCR extracted {len(text)} chars from "
                f"{pages_to_ocr} pages of '{rel}'."
            )

        if not text.strip():
            logger.warning(f"PdfParser: '{rel}' has no extractable text even after OCR")
        else:
            logger.info(f"PdfParser: parsed '{rel}' ({page_count} pages, {len(text)} chars)")

        return Document(
            filename=filename,
            source_path=rel,
            text=text,
            page_count=page_count,
            metadata=meta,
        )
