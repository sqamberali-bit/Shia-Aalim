"""Generic prose-PDF adapter (text-layer books with page-number headers).

For uploaded book PDFs laid out the common way: each page's text begins with
the printed page number, then a running header (the chapter title on one side
of the spread, the book title on the other), then the body. Citations are
*chapter + printed page* — precise and independently verifiable against the
named edition.

Honesty rules: text is taken verbatim from the PDF's text layer (no OCR, no
reflow beyond joining wrapped lines); table-of-contents chrome (dot leaders)
is dropped; a chunk is cited by the page it begins on and may run onto the
next page.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType

_PAGE_NO = re.compile(r"^[0-9]{1,4}$|^[ivxlcdm]{1,7}$", re.IGNORECASE)
_DOTS = re.compile(r"\.{6,}")
_WS = re.compile(r"[ \t]+")


def build_prose_pdf_documents(
    pdf_path: str | Path,
    *,
    source_id: str,
    evidence_type: EvidenceType,
    book_title_marker: str,
    translation_source: str,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    max_chars: int = 1500,
    min_chars: int = 60,
) -> list[Document]:
    """One cited Document per ~max_chars chunk of a text-layer book PDF.

    ``book_title_marker``: a substring of the running book-title header, used
    to tell "book title" headers apart from chapter headers.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("prose-PDF ingestion needs PyMuPDF — `pip install pymupdf`") from exc

    doc = fitz.open(str(pdf_path))
    chapter = ""
    page_label = ""
    # (chapter, page_label, text-line) stream
    stream: list[tuple[str, str, str]] = []
    try:
        for i in range(doc.page_count):
            lines = [_WS.sub(" ", ln).strip() for ln in doc[i].get_text().splitlines()]
            lines = [ln for ln in lines if ln and not _DOTS.search(ln)]
            if not lines:
                continue
            if _PAGE_NO.match(lines[0]):
                page_label = lines[0]
                lines = lines[1:]
            if lines and book_title_marker in lines[0]:
                lines = lines[1:]  # book-title header — chapter unchanged
            elif lines and len(lines[0]) < 70 and not lines[0][-1:] in ".:;,،":
                # chapter-side running header
                chapter = lines[0]
                lines = lines[1:]
            for ln in lines:
                stream.append((chapter, page_label, ln))
    finally:
        doc.close()

    docs: list[Document] = []
    buf: list[str] = []
    buf_key: Optional[tuple[str, str]] = None
    counter = 0

    def emit():
        nonlocal buf, buf_key, counter
        text = " ".join(buf).strip()
        if buf_key is not None and len(text) >= min_chars:
            ch, pg = buf_key
            citation = Citation(
                source_id=source_id,
                evidence_type=evidence_type,
                chapter=ch or None,
                page=pg or None,
                translation_source=translation_source,
            )
            docs.append(
                Document(
                    id=f"{source_id}-{counter}",
                    text=text,
                    evidence_type=evidence_type,
                    citation=citation,
                    confidence=confidence,
                    tags=[source_id, "prose"],
                    language="en",
                )
            )
            counter += 1
        buf = []
        buf_key = None

    for ch, pg, ln in stream:
        if buf and (buf_key is None or ch != buf_key[0]
                    or sum(len(b) for b in buf) + len(ln) > max_chars):
            emit()
        if not buf:
            buf_key = (ch, pg)
        buf.append(ln)
    emit()
    return docs
