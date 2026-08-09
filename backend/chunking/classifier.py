"""
chunking/classifier.py — Generalized Chunk Type Classifier

Detects the structural role of a text chunk using lightweight regex heuristics.
This runs at index time (during chunking) and writes a `chunk_type` label to
Postgres so the retrieval layer can make smarter decisions.

Supported Types
---------------
- "text"       : Default. General prose, paragraphs, sentences.
- "answer_key" : Numbered/lettered answer lists (e.g. "1. A  2. C  3. B").
                 Works for any domain: exams, quizzes, exercises, workbooks.
- "table"      : Tabular data detected by pipe separators or aligned columns.
- "toc"        : Table of contents entries with page numbers.
- "reference"  : Bibliography, citation lists, footnotes.
- "code"       : Source code blocks detected by common syntax patterns.

Design Philosophy
-----------------
- Heuristics only — no ML models. Fast, deterministic, zero latency overhead.
- Generalized — no domain-specific assumptions. Works for books, notes,
  question papers, research papers, code repos, etc.
- Conservative — when in doubt, returns "text". A false negative (missing a
  real answer_key) is far better than a false positive (wrongly tagging prose).
"""
import re

# ── Pattern definitions ────────────────────────────────────────────────────

# Answer key: dense list of numbered items paired with single-letter answers.
# Matches: "1. A", "2) B", "Q3: C", "12.A", "42 - D", etc.
# Requires at least 4 such items to avoid tagging prose with "e.g. A, B, C".
_ANSWER_KEY_ITEM = re.compile(
    r'^\s*(?:Q\.?|question\s*)?\d{1,3}[\.\)\-:\s]+[A-Ea-e]\b',
    re.IGNORECASE | re.MULTILINE,
)
_ANSWER_KEY_MIN_ITEMS = 4

# Table: has markdown pipe separators or header-separator rows (---) or
# multiple whitespace-aligned columns with consistent spacing.
_TABLE_PIPE = re.compile(r'\|.+\|')
_TABLE_SEPARATOR = re.compile(r'^\s*[-:| ]+$', re.MULTILINE)

# Table of contents: lines with text followed by a page number (digits),
# optionally separated by dots/spaces. Requires at least 4 entries.
_TOC_ITEM = re.compile(
    r'^.{3,60}[.\s]{2,}\d{1,4}\s*$',
    re.MULTILINE,
)
_TOC_MIN_ITEMS = 4

# Reference / Bibliography: lines that look like citations.
# Matches: "[1] Author...", "1. Author, Title...", "Author, A. (Year)."
_REFERENCE_ITEM = re.compile(
    r'(?:^\[\d+\]\s|\b\(\d{4}\)\.?\s|^\d+\.\s[A-Z][a-z]+,)',
    re.MULTILINE,
)
_REFERENCE_MIN_ITEMS = 3

# Code: indented code blocks, common keywords, or backtick fences.
_CODE_PATTERN = re.compile(
    r'(?:'
    r'```[\w\s]*\n'                     # fenced code block
    r'|(?:def |class |import |from \w+ import )'  # Python
    r'|(?:function\s+\w+\s*\(|const |let |var )'  # JS/TS
    r'|(?:#include\s*<|int main\s*\()'  # C/C++
    r'|(?:public\s+(?:class|static|void)\s)'  # Java
    r')',
    re.MULTILINE,
)
_CODE_MIN_MATCHES = 2


def classify_chunk(text: str) -> str:
    """
    Classify the structural type of a document chunk.

    Args:
        text: The raw text content of the chunk.

    Returns:
        One of: "answer_key", "table", "toc", "reference", "code", "text".
    """
    if not text or len(text.strip()) < 10:
        return "text"

    # ── Code detection (highest specificity) ──────────────────────────────
    if len(_CODE_PATTERN.findall(text)) >= _CODE_MIN_MATCHES:
        return "code"

    # ── Answer key detection ───────────────────────────────────────────────
    answer_matches = _ANSWER_KEY_ITEM.findall(text)
    if len(answer_matches) >= _ANSWER_KEY_MIN_ITEMS:
        return "answer_key"

    # ── Table detection ────────────────────────────────────────────────────
    pipe_rows = _TABLE_PIPE.findall(text)
    sep_rows = _TABLE_SEPARATOR.findall(text)
    if len(pipe_rows) >= 2 or (len(pipe_rows) >= 1 and len(sep_rows) >= 1):
        return "table"

    # ── Table of contents detection ────────────────────────────────────────
    toc_matches = _TOC_ITEM.findall(text)
    if len(toc_matches) >= _TOC_MIN_ITEMS:
        return "toc"

    # ── Reference / bibliography detection ───────────────────────────────
    ref_matches = _REFERENCE_ITEM.findall(text)
    if len(ref_matches) >= _REFERENCE_MIN_ITEMS:
        return "reference"

    return "text"
