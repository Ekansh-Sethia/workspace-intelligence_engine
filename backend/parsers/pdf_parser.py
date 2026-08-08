"""
Parser for PDF files using ``pypdf``.

Extracts text page-by-page and concatenates it into a single string.
"""
from pathlib import Path
from typing import Optional
import tempfile
import concurrent.futures

from pypdf import PdfReader
from pdf2image import convert_from_path
import pytesseract

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

        # If pypdf extracted almost nothing, it's likely a scanned PDF.
        # Fallback to OCR via pdf2image + pytesseract.
        if len(text.strip()) < 50:
            logger.info(f"PdfParser: '{rel}' has <50 extractable chars. Falling back to OCR.")
            pages_text = []
            
            # Use a temporary directory for images to avoid memory spikes
            with tempfile.TemporaryDirectory() as temp_dir:
                # convert_from_path returns a list of PIL Images
                images = convert_from_path(filepath, output_folder=temp_dir, dpi=200)
                page_count = len(images)
                
                # Parallelize OCR using ThreadPoolExecutor
                def ocr_page(args):
                    i, img = args
                    logger.debug(f"PdfParser: OCRing page {i+1}/{page_count} of '{rel}'")
                    return pytesseract.image_to_string(img).strip()

                # Using max_workers=4 (or up to cpu_count) to massively speed up OCR
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    results = list(executor.map(ocr_page, enumerate(images)))
                
                for ocr_text in results:
                    if ocr_text:
                        pages_text.append(ocr_text)
            
            text = "\n\n".join(pages_text)
            logger.info(f"PdfParser: OCR extracted {len(text)} chars from {page_count} pages.")
        
        # Gather whatever metadata pypdf exposes
        meta: dict = {"parser": "PdfParser", "page_count": page_count}
        if reader.metadata:
            if reader.metadata.title:
                meta["title"] = reader.metadata.title
            if reader.metadata.author:
                meta["author"] = reader.metadata.author

        if not text.strip():
            logger.warning(f"PdfParser: '{rel}' has no extractable text even after OCR")
        else:
            logger.info(f"PdfParser: parsed '{rel}' ({page_count} pages, {len(text)} chars)")

        return Document(
            filename=filepath.name,
            source_path=rel,
            text=text,
            page_count=page_count,
            metadata=meta,
        )
