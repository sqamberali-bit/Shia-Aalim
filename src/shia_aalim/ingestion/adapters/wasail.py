"""Wasāʾil al-Shīʿa ingestion adapter (English text-layer PDF, per-hadith).

al-Ḥurr al-ʿĀmilī's *Wasāʾil al-Shīʿa* is distributed by wasail-al-shia.net as
text-layer PDFs of an English translation in which **every narration is numbered**
(``Hadith 114``) and each page carries a running header naming the volume and
section (``Wasa'il al-Shia Vol. 1, Section 8``). That gives a genuinely precise,
verifiable citation — *volume + section + hadith number* — rather than a
page-level approximation.

Design / honesty notes:

* One :class:`Document` per numbered narration. The Arabic *matn*/*isnād* and the
  English translation are interleaved in the PDF; the adapter separates them by
  script, so ``text`` is the English (for retrieval) and
  ``citation.arabic_text`` preserves the original.
* Volume and section come from the page's own running header — never inferred.
  A narration is skipped if no hadith number can be read; nothing is invented.
* These PDFs carry **no per-hadith rijāl grade**, so ``grade`` stays
  ``ungraded`` and confidence is capped at ``medium``. Wasāʾil is a
  jurisprudential compilation containing strong *and* weak reports: narrations
  must be graded against a rijāl source before being treated as authentic.
* Running chrome (site URL, page numbers, the header line, and the truncated
  chapter title in the footer) is stripped from the body.

Requires PyMuPDF (``pip install pymupdf``); imported lazily so the rest of the
package never depends on it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

# Running header: "Wasa'il al-Shia Vol. 1, Section 8" (apostrophe varies).
_HEADER = re.compile(
    r"Wasa['’`]?il\s+al-Shia\s+Vol\.?\s*(\d+)\s*,\s*Section\s*(\d+)",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(r"^\s*Wasa['’`]?il\s+al-Shia\s+Vol\..*$", re.IGNORECASE | re.MULTILINE)
_SITE_LINE = re.compile(r"^\s*https?://\S*wasail?-al-shia\.\S*\s*$", re.IGNORECASE | re.MULTILINE)
_PAGE_NUM_LINE = re.compile(r"^\s*\d{1,4}\s*$", re.MULTILINE)
# Footer carries the chapter title truncated with an ellipsis — drop that line.
_TRUNC_TITLE = re.compile(r"^.{10,}\.\.\.\s*$", re.MULTILINE)

_HADITH_SPLIT = re.compile(r"^\s*Hadith\s+(\d+)\s*$", re.MULTILINE)

_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")

_VOL_FROM_NAME = re.compile(r"ws(\d+)", re.IGNORECASE)


def volume_from_filename(pdf_path: str | Path) -> Optional[str]:
    """``ws1_eng.pdf`` -> ``"1"`` (fallback when a page header is unreadable)."""
    m = _VOL_FROM_NAME.search(Path(pdf_path).name)
    return m.group(1) if m else None


def _strip_chrome(raw: str) -> str:
    text = _HEADER_LINE.sub("", raw)
    text = _SITE_LINE.sub("", text)
    text = _TRUNC_TITLE.sub("", text)
    text = _PAGE_NUM_LINE.sub("", text)
    text = "\n".join(_WS.sub(" ", ln).rstrip() for ln in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def _is_arabic_line(line: str) -> bool:
    """A line belongs to the Arabic matn when Arabic script dominates it."""
    ar = len(_ARABIC.findall(line))
    la = len(_LATIN.findall(line))
    return ar > 0 and ar >= la


def split_arabic_english(block: str) -> tuple[str, str]:
    """Separate an interleaved narration block into (arabic, english)."""
    arabic: list[str] = []
    english: list[str] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        (arabic if _is_arabic_line(line) else english).append(line.strip())
    return (" ".join(arabic).strip(), " ".join(english).strip())


def iter_wasail_narrations(pdf_path: str | Path) -> Iterator[tuple[str, str, str, str]]:
    """Yield ``(volume, section, hadith_number, block_text)`` for each narration.

    Pages are read in order and their cleaned bodies concatenated per
    (volume, section) run, so a narration split across a page break stays whole.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Wasāʾil ingestion needs PyMuPDF — `pip install pymupdf`"
        ) from exc

    fallback_vol = volume_from_filename(pdf_path) or "?"
    doc = fitz.open(str(pdf_path))
    try:
        current: Optional[tuple[str, str]] = None
        buffer: list[str] = []
        for i in range(doc.page_count):
            raw = doc[i].get_text()
            m = _HEADER.search(raw.replace("\n", " "))
            if m:
                key = (m.group(1), m.group(2))
            else:
                key = current or (fallback_vol, "")
            if current is not None and key != current:
                yield from _emit(current, "\n".join(buffer))
                buffer = []
            current = key
            buffer.append(_strip_chrome(raw))
        if current is not None:
            yield from _emit(current, "\n".join(buffer))
    finally:
        doc.close()


def _emit(key: tuple[str, str], text: str) -> Iterator[tuple[str, str, str, str]]:
    """Split one (volume, section) run into its numbered narrations."""
    volume, section = key
    parts = _HADITH_SPLIT.split(text)
    # parts = [preamble, num, body, num, body, ...] — the preamble has no number.
    for j in range(1, len(parts) - 1, 2):
        number = parts[j].strip()
        body = parts[j + 1].strip()
        if number and body:
            yield volume, section, number, body


def build_wasail_documents(
    pdf_path: str | Path,
    *,
    source_id: str = "wasail-al-shia",
    volume: Optional[str] = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    translation_source: str = "English translation, wasail-al-shia.net",
    min_chars: int = 40,
) -> list[Document]:
    """Build one cited :class:`Document` per numbered narration in a volume PDF.

    ``volume`` overrides the volume read from the page headers. Narrations whose
    combined text falls below ``min_chars`` (stray artefacts) are skipped.
    """
    docs: list[Document] = []
    seen: set[str] = set()
    for detected_vol, section, number, block in iter_wasail_narrations(pdf_path):
        arabic, english = split_arabic_english(block)
        if len(arabic) + len(english) < min_chars:
            continue
        vol = str(volume) if volume is not None else detected_vol
        doc_id = f"{source_id}-v{vol}-h{number}"
        if doc_id in seen:  # a repeated header can restate a number; keep the first
            continue
        seen.add(doc_id)
        citation = Citation(
            source_id=source_id,
            evidence_type=EvidenceType.HADITH,
            volume=vol,
            chapter=f"Section {section}" if section else None,
            hadith_number=number,
            arabic_text=arabic or None,
            translation=english or None,
            translation_source=translation_source if english else None,
            grade=HadithGrade.UNGRADED,  # these PDFs record no rijal grade
            grade_source=None,
        )
        docs.append(
            Document(
                id=doc_id,
                text=english or arabic,
                evidence_type=EvidenceType.HADITH,
                citation=citation,
                confidence=confidence,
                tags=["hadith", source_id, f"grade-{HadithGrade.UNGRADED.value}"],
                language="en" if english else "ar",
            )
        )
    docs.sort(key=lambda d: (d.citation.volume or "", int(d.citation.hadith_number or 0)))
    return docs
