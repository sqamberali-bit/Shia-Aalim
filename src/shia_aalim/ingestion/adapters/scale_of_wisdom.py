"""Mīzān al-Ḥikma / "The Scale of Wisdom" bilingual-PDF adapter.

Rayshahri's one-volume selection (ICAS Press bilingual edition) numbers every
narration and, crucially, prints the ORIGINAL source of each report inline —
e.g. ``[Mustadrak al-Wasa'il, v. 12, p. 154, no. 13761]`` — so every ingested
document carries a pointer back to the primary Arabic collection (many of
which are in this corpus).

Honesty rules:

* One :class:`Document` per numbered English narration, verbatim, with its
  inline source reference preserved.
* The PDF's Arabic text layer is corrupted (visually reordered glyphs), so
  Arabic lines are DROPPED rather than ingested as garbage; the registry
  entry says so. Lines are classed as Arabic by script-character ratio.
* Theme headings (short Title-Case lines) become the chapter; the page cited
  is the PDF page of this bilingual edition (stated in the registry).
"""

from __future__ import annotations

import re
from pathlib import Path

from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

_NARRATION = re.compile(r"^\s*(\d{1,4})\s*[–\-−]\s+(.*)$")
_WS = re.compile(r"[ \t]+")


def _arabic_ratio(line: str) -> float:
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return 0.0
    ar = sum(1 for c in letters if "؀" <= c <= "ۿ" or "ﭐ" <= c <= "﻿")
    return ar / len(letters)


def _is_heading(line: str) -> bool:
    t = line.strip()
    if not (3 < len(t) < 65) or any(ch.isdigit() for ch in t):
        return False
    if _arabic_ratio(t) > 0.05 or t.endswith((".", "'", "’", "]", ",")):
        return False
    words = t.split()
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= max(1, len(words) - 2)


def build_scale_of_wisdom_documents(
    pdf_path: str | Path,
    *,
    source_id: str = "mizan-al-hikmah",
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    min_chars: int = 30,
) -> list[Document]:
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Scale of Wisdom ingestion needs PyMuPDF") from exc

    doc = fitz.open(str(pdf_path))
    docs: list[Document] = []
    chapter = ""
    num: str | None = None
    buf: list[str] = []
    page_of: int = 0
    seen = 0

    def emit():
        nonlocal num, buf, seen
        if num is not None and buf:
            text = _WS.sub(" ", " ".join(buf)).strip()
            if len(text) >= min_chars:
                citation = Citation(
                    source_id=source_id,
                    evidence_type=EvidenceType.HADITH,
                    chapter=chapter or None,
                    page=str(page_of),
                    hadith_number=None,  # numbering restarts per theme; kept in text
                    translation=text,
                    translation_source="N. Virjee et al. (ICAS Press bilingual edition)",
                    grade=HadithGrade.UNGRADED,
                    grade_source=None,
                )
                docs.append(
                    Document(
                        id=f"{source_id}-{seen}",
                        text=f"{num}. {text}",
                        evidence_type=EvidenceType.HADITH,
                        citation=citation,
                        confidence=confidence,
                        tags=["hadith", source_id],
                        language="en",
                    )
                )
                seen += 1
        num, buf = None, []

    try:
        for i in range(doc.page_count):
            for raw in doc[i].get_text().splitlines():
                line = raw.strip()
                if not line or _arabic_ratio(line) > 0.3:
                    continue
                m = _NARRATION.match(line)
                if m:
                    emit()
                    num, buf, page_of = m.group(1), [m.group(2)], i + 1
                    continue
                if _is_heading(line):
                    emit()
                    chapter = _WS.sub(" ", line).strip()
                    continue
                if num is not None:
                    buf.append(line)
        emit()
    finally:
        doc.close()
    return docs
