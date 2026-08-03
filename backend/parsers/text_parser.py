"""
Parser for plain-text files: .txt, .md, .markdown

These files are read directly with UTF-8 encoding.  No third-party
library is required.
"""
from pathlib import Path
from typing import Optional

from parsers.base import BaseParser, Document
from utils.logger import logger


class TextParser(BaseParser):
    """Handles .txt, .md, and .markdown files."""

    # Encodings to attempt, in order of preference
    _ENCODINGS = ("utf-8", "utf-8-sig", "latin-1")

    def parse(self, filepath: Path, source_path: Optional[str] = None) -> Document:
        """
        Read the file as plain text.

        Tries UTF-8 first, falls back to latin-1 so that we never crash
        on encoding issues (latin-1 can decode any byte sequence).
        """
        text = self._read_with_fallback(filepath)
        rel = source_path or filepath.name

        logger.info(f"TextParser: parsed '{rel}' ({len(text)} chars)")

        return Document(
            filename=filepath.name,
            source_path=rel,
            text=text,
            page_count=1,
            metadata={"parser": "TextParser"},
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_with_fallback(self, filepath: Path) -> str:
        """Try each encoding in turn; raise on total failure."""
        for enc in self._ENCODINGS:
            try:
                return filepath.read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue

        raise ValueError(
            f"Could not decode {filepath.name} with any supported encoding"
        )
