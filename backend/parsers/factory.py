"""
Parser factory — routes file extensions to the correct parser.

Usage::

    from parsers.factory import get_parser

    parser = get_parser(".pdf")
    doc = parser.parse(filepath, source_path="lectures/notes.pdf")
"""
from parsers.base import BaseParser
from parsers.text_parser import TextParser
from parsers.pdf_parser import PdfParser
from parsers.docx_parser import DocxParser
from parsers.pptx_parser import PptxParser
from parsers.image_parser import ImageParser, GroqCaptionProvider
from utils.config import settings

# Setup Caption Provider if GROQ_API_KEY is available
caption_provider = None
if settings.GROQ_API_KEY:
    caption_provider = GroqCaptionProvider(api_key=settings.GROQ_API_KEY)

# Singleton instances — parsers are stateless, so a single instance is fine.
_text_parser = TextParser()
_pdf_parser = PdfParser()
_docx_parser = DocxParser()
_pptx_parser = PptxParser()
_image_parser = ImageParser(caption_provider=caption_provider)

# Extension → parser mapping
_PARSER_REGISTRY: dict[str, BaseParser] = {
    # Text
    ".txt": _text_parser,
    ".md": _text_parser,
    ".markdown": _text_parser,
    # PDF
    ".pdf": _pdf_parser,
    # Microsoft Office
    ".docx": _docx_parser,
    ".pptx": _pptx_parser,
    # Images
    ".jpg": _image_parser,
    ".jpeg": _image_parser,
    ".png": _image_parser,
    ".gif": _image_parser,
    ".webp": _image_parser,
}


def get_parser(extension: str) -> BaseParser:
    """
    Return the appropriate parser for the given file extension.

    Args:
        extension: Lowercase file extension including the dot (e.g. ".pdf").

    Returns:
        A BaseParser instance.

    Raises:
        ValueError: If no parser is registered for this extension.
    """
    ext = extension.lower()
    parser = _PARSER_REGISTRY.get(ext)
    if parser is None:
        raise ValueError(f"No parser registered for extension: {ext}")
    return parser
