"""
Base abstractions for the document parsing layer.

Document: A unified internal representation of a parsed file.
BaseParser: Abstract interface that all concrete parsers must implement.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Document:
    """
    Unified internal representation of a parsed document.

    This is an in-memory object passed downstream to the chunking and
    embedding layers.  It is NOT persisted to the database.

    Attributes:
        filename:    Original file name (e.g. "notes.pdf").
        source_path: Relative path within the workspace (e.g. "lectures/notes.pdf").
        text:        Extracted raw text content.
        page_count:  Number of pages (meaningful for PDF/PPTX; 1 for plain text).
        metadata:    Arbitrary key-value metadata from the parser (e.g. author, title).
    """
    filename: str
    source_path: str
    text: str
    page_count: int = 1
    metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """
    Abstract base class for all file parsers.

    Every concrete parser (TextParser, PdfParser, …) must implement the
    ``parse`` method.  The parser factory in ``factory.py`` maps file
    extensions to their corresponding parser class.
    """

    @abstractmethod
    def parse(self, file_content: bytes, filename: str, source_path: Optional[str] = None) -> Document:
        """
        Parse a single file and return a Document.

        Args:
            file_content: The raw bytes of the file.
            filename:     Original file name.
            source_path:  Relative path within the workspace (used for metadata).

        Returns:
            A Document instance containing the extracted text.

        Raises:
            ValueError: If the file cannot be parsed (corrupt, empty, etc.).
        """
        ...
