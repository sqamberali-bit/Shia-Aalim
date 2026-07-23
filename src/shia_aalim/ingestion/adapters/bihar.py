"""Biḥār al-Anwār ingestion adapter (hubeali English text-layer PDFs).

The hubeali.com English Biḥār is distributed as one text-layer PDF per volume
(V1..V101). Every page carries an authoritative running header —
``Bihar Al-Anwaar  Volume N  www.hubeali.com  Page X of Y`` — from which we read
the exact volume and page, giving each passage a verifiable
``Biḥār al-Anwār, vNN, hubeali p.X`` citation.

Design / honesty notes:

* One :class:`Document` per PDF page (the page number in the header is the
  citable locator). The header/footer chrome is stripped from the body.
* Text is kept as-is: interleaved English (Hubeali translation) + Arabic matn +
  isnād. Both are indexed; neither is fabricated or "cleaned up" into a claim.
* Biḥār is a comprehensive compilation containing strong *and* weak reports and
  al-Majlisī's own commentary, and these PDFs carry **no per-hadith rijāl
  grade**. So confidence is capped at ``medium`` and grade stays ``ungraded`` —
  narrations must be graded against a rijāl source before being treated as
  authentic.

Requires PyMuPDF (``pip install pymupdf``); imported lazily so the rest of the
package never depends on it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType

# Running header, tolerant of whitespace/newlines and the "Anwaar/Anwar" spelling.
_HEADER = re.compile(
    r"Bihar\s+Al-?Anwaar\s+Volume\s+(\d+)\s+www\.hubeali\.com\s+Page\s+(\d+)\s+of\s+(\d+)",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(r"^\s*Bihar\s+Al-?Anwaar\b.*$", re.IGNORECASE | re.MULTILINE)
_HUBEALI = re.compile(r"^\s*www\.hubeali\.com\s*$", re.IGNORECASE | re.MULTILINE)
_PAGE_LINE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
# The running header often extracts as separate lines; drop a lone "Volume N" too.
_VOLUME_LINE = re.compile(r"^\s*Volume\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")

_VOL_FROM_NAME = re.compile(r"[Vv](\d+)\.pdf$")


def _clean_page(raw: str) -> str:
    text = _HEADER_LINE.sub("", raw)
    text = _HUBEALI.sub("", text)
    text = _PAGE_LINE.sub("", text)
    text = _VOLUME_LINE.sub("", text)
    text = "\n".join(_WS.sub(" ", ln).rstrip() for ln in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def volume_from_filename(pdf_path: str | Path) -> Optional[str]:
    m = _VOL_FROM_NAME.search(Path(pdf_path).name)
    return m.group(1) if m else None


def iter_bihar_pages(pdf_path: str | Path) -> Iterator[tuple[str, str, str]]:
    """Yield ``(volume, page, cleaned_text)`` for each non-trivial page.

    Volume/page come from the in-page header when present, else fall back to the
    filename volume and the sequential page index.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Biḥār ingestion needs PyMuPDF — `pip install pymupdf`"
        ) from exc

    fallback_vol = volume_from_filename(pdf_path) or "?"
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(doc.page_count):
            raw = doc[i].get_text()
            m = _HEADER.search(raw.replace("\n", " "))
            vol = m.group(1) if m else fallback_vol
            page = m.group(2) if m else str(i + 1)
            yield vol, page, _clean_page(raw)
    finally:
        doc.close()


def build_bihar_documents(
    pdf_path: str | Path,
    *,
    source_id: str = "bihar-al-anwar",
    volume: Optional[str] = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    min_chars: int = 200,
) -> list[Document]:
    """Build one cited :class:`Document` per page of a Biḥār volume PDF.

    ``volume`` overrides the detected volume (use the filename's V-number to be
    safe). Pages below ``min_chars`` (covers/blank/title pages) are skipped —
    never padded.
    """
    docs: list[Document] = []
    for detected_vol, page, text in iter_bihar_pages(pdf_path):
        if len(text) < min_chars:
            continue
        vol = str(volume) if volume is not None else detected_vol
        citation = Citation(
            source_id=source_id,
            evidence_type=EvidenceType.HADITH,
            volume=vol,
            page=page,
            translation_source="Hubeali (English), www.hubeali.com",
            grade_source=None,  # no per-hadith grade in these PDFs
        )
        docs.append(
            Document(
                id=f"{source_id}-v{vol}-p{page}",
                text=text,
                evidence_type=EvidenceType.HADITH,
                citation=citation,
                confidence=confidence,
                tags=["hadith", source_id, "bihar", "prose"],
                language="en",
            )
        )
    return docs
