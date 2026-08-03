"""
Parser for PDF files using ``pypdf``.

Extracts text page-by-page and concatenates it into a single string.
"""
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from parsers.base import BaseParser, Document
from utils.logger import logger


class PdfParser(BaseParser):
    """Handles .pdf files."""

    def parse(self, filepath: Path, source_path: Optional[str] = None) -> Document:
        """
        Extract text from every page of a PDF.

        Raises ValueError if the PDF is unreadable or contains zero
        extractable text (e.g. scanned images with no OCR layer).
        """
        reader = PdfReader(filepath)
        pages_text: list[str] = []

        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                pages_text.append(extracted)

        text = "\n\n".join(pages_text)
        page_count = len(reader.pages)
        rel = source_path or filepath.name

        # Gather whatever metadata pypdf exposes
        meta: dict = {"parser": "PdfParser", "page_count": page_count}
        if reader.metadata:
            if reader.metadata.title:
                meta["title"] = reader.metadata.title
            if reader.metadata.author:
                meta["author"] = reader.metadata.author

        if not text.strip():
            logger.warning(f"PdfParser: '{rel}' has no extractable text (scanned?)")

        logger.info(f"PdfParser: parsed '{rel}' ({page_count} pages, {len(text)} chars)")

        return Document(
            filename=filepath.name,
            source_path=rel,
            text=text,
            page_count=page_count,
            metadata=meta,
        )
