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
import base64
import json

from PIL import Image
import pytesseract
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from groq import Groq
from groq import InternalServerError, RateLimitError

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
    def caption(self, file_content: bytes, filename: str) -> str:
        """Return a natural-language caption for the image."""
        ...


# ------------------------------------------------------------------
# Concrete Implementation: Groq Vision Caption Provider
# ------------------------------------------------------------------

class GroqCaptionProvider(CaptionProvider):
    """
    Uses Groq's Llama 3.2 Vision model to generate captions for images.
    Implements exponential backoff to handle rate limits gracefully.
    """
    def __init__(self, api_key: str, model_name: str = "llama-3.2-11b-vision-preview"):
        self.client = Groq(api_key=api_key)
        self.model_name = model_name

    def _encode_image(self, file_content: bytes) -> str:
        return base64.b64encode(file_content).decode('utf-8')

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((RateLimitError, InternalServerError)),
        reraise=True
    )
    def caption(self, file_content: bytes, filename: str) -> str:
        logger.info(f"GroqCaptionProvider: Generating caption for {filename}")
        base64_image = self._encode_image(file_content)
        
        # Determine mime type based on extension
        ext = Path(filename).suffix.lower()
        mime_type = f"image/{ext[1:]}" if ext in ['.png', '.jpeg', '.webp', '.gif'] else "image/jpeg"

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe this image in detail. Focus on any charts, text, diagrams, or key structural elements. Be highly descriptive as this will be used for semantic search."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model=self.model_name,
            max_tokens=1024,
            temperature=0.2,
        )

        caption = chat_completion.choices[0].message.content
        return caption or ""


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

    def parse(self, file_content: bytes, filename: str, source_path: Optional[str] = None) -> Document:
        """
        Run OCR on the image and optionally generate a caption.
        """
        import io
        image = Image.open(io.BytesIO(file_content))
        ocr_text = pytesseract.image_to_string(image).strip()

        rel = source_path or filename
        meta: dict = {
            "parser": "ImageParser",
            "width": image.width,
            "height": image.height,
            "format": image.format,
        }

        # Future: call caption provider if available
        if self._caption_provider is not None:
            try:
                caption = self._caption_provider.caption(file_content, filename)
                meta["caption"] = caption
            except Exception as exc:
                logger.warning(f"ImageParser: captioning failed for '{rel}': {exc}")

        if not ocr_text:
            logger.warning(f"ImageParser: '{rel}' has no extractable text via OCR")

        logger.info(f"ImageParser: parsed '{rel}' ({image.width}x{image.height}, {len(ocr_text)} chars OCR)")

        return Document(
            filename=filename,
            source_path=rel,
            text=ocr_text,
            page_count=1,
            metadata=meta,
        )
