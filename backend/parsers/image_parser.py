"""
Parser for image files (.jpg, .jpeg, .png, .gif, .webp) using ``pytesseract``.

Performs OCR to extract visible text from images.

Design Note — Future CaptionProvider Extension
-----------------------------------------------
This parser is intentionally designed so that a *CaptionProvider* can be
plugged in later without modifying the parser itself.  The extension point
works as follows:

1.  Define an abstract ``CaptionProvider`` protocol with a
    ``caption(image_path: Path) -> str`` method.
2.  Concrete implementations (e.g. ``GeminiCaptionProvider``,
    ``OpenAICaptionProvider``, ``Florence2CaptionProvider``) call the
    respective Vision API / local model.
3.  Pass the provider into ``ImageParser.__init__`` (dependency injection).
4.  The parser appends the caption to ``Document.metadata["caption"]``.

No code changes are required in the parser's ``parse()`` method beyond
calling ``self._caption_provider.caption(filepath)`` if one is set.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from PIL import Image
import pytesseract

from parsers.base import BaseParser, Document
from utils.logger import logger


# ------------------------------------------------------------------
# Future extension point (not activated in V1)
# ------------------------------------------------------------------

class CaptionProvider(ABC):
    """
    Abstract interface for image captioning.

    Concrete implementations will wrap an external Vision API or a
    local model (Florence-2, BLIP-2, etc.).
    """

    @abstractmethod
    def caption(self, image_path: Path) -> str:
        """Return a natural-language caption for the image."""
        ...


# ------------------------------------------------------------------
# Image parser
# ------------------------------------------------------------------

class ImageParser(BaseParser):
    """
    Handles image files by running OCR via pytesseract.

    Args:
        caption_provider: Optional CaptionProvider for image captioning.
                          Pass ``None`` (default) to skip captioning in V1.
    """

    def __init__(self, caption_provider: Optional[CaptionProvider] = None):
        self._caption_provider = caption_provider

    def parse(self, filepath: Path, source_path: Optional[str] = None) -> Document:
        """
        Run OCR on the image and optionally generate a caption.
        """
        image = Image.open(filepath)
        ocr_text = pytesseract.image_to_string(image).strip()

        rel = source_path or filepath.name
        meta: dict = {
            "parser": "ImageParser",
            "width": image.width,
            "height": image.height,
            "format": image.format,
        }

        # Future: call caption provider if available
        if self._caption_provider is not None:
            try:
                caption = self._caption_provider.caption(filepath)
                meta["caption"] = caption
            except Exception as exc:
                logger.warning(f"ImageParser: captioning failed for '{rel}': {exc}")

        if not ocr_text:
            logger.warning(f"ImageParser: '{rel}' has no extractable text via OCR")

        logger.info(f"ImageParser: parsed '{rel}' ({image.width}x{image.height}, {len(ocr_text)} chars OCR)")

        return Document(
            filename=filepath.name,
            source_path=rel,
            text=ocr_text,
            page_count=1,
            metadata=meta,
        )
