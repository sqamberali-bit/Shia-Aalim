"""ʿIlal al-Sharāʾiʿ ingestion adapter (hubeali English text-layer PDFs).

Shaykh al-Ṣadūq's *ʿIlal al-Sharāʾiʿ* is distributed by hubeali.com as
text-layer PDFs in two volumes, each split into multiple parts
(``ILLAL AL SHARAIE - V 1 P 1.pdf`` … ``V 2 P 9.pdf``).  Every page carries
a running header of the form::

    Illal Al-Sharaie  Volume N  www.hubeali.com  Page X of Y

The book has 647 chapters, each titled ``CHAPTER N – Reasons for …``.
Narrations within each chapter are split when numbered ``Hadith N`` markers
appear in the text; otherwise the chapter body is emitted as a single passage
(chunked if long).  Arabic *matn* is separated by script detection and stored
in ``citation.arabic_text``.

Design / honesty notes:

* These PDFs carry **no per-hadith rijāl grade**, so ``grade`` stays
  ``ungraded`` and confidence is capped at ``medium``.
* Text is kept as-is — English translation plus interleaved Arabic.
* Content that doesn't fall inside a detected chapter is emitted as a
  page-level fallback so nothing is silently dropped.

Requires PyMuPDF (``pip install pymupdf``); imported lazily.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from ...ingestion.loaders import chunk_text
from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

# ---------------------------------------------------------------------------
# Running-header patterns
# ---------------------------------------------------------------------------
_HEADER = re.compile(
    r"Ill?al\s+Al[- ]Shara[ie']+\s+Volume\s+(\d+)\s+www\.hubeali\.com\s+Page\s+(\d+)\s+of\s+(\d+)",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(r"^\s*Ill?al\s+Al[- ]Shara[ie']+\b.*$", re.IGNORECASE | re.MULTILINE)
_HUBEALI = re.compile(r"^\s*www\.hubeali\.com\s*$", re.IGNORECASE | re.MULTILINE)
_PAGE_LINE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
_VOLUME_LINE = re.compile(r"^\s*Volume\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
_PART_LINE = re.compile(r"^\s*Part\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
_REASONS_TITLE = re.compile(
    r"^\s*(?:REASONS\s+FOR\s+THE\s+LAWS|علل\s+الشرائع)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")

_VOL_PART_FROM_NAME = re.compile(r"V\s*(\d+)\s*P\s*(\d+)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Chapter boundary — ``CHAPTER 42 – Reasons for …``
# ---------------------------------------------------------------------------
_CHAPTER = re.compile(
    r"^\s*CHAPTER\s+(\d+)\s*[-–—:]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Hadith marker inside a chapter — ``Hadith 3`` on its own line
# ---------------------------------------------------------------------------
_HADITH_SPLIT = re.compile(r"^\s*Hadith\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)

# ---------------------------------------------------------------------------
# Arabic script detection
# ---------------------------------------------------------------------------
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")


def _clean_page(raw: str) -> str:
    """Strip running-header chrome from one page."""
    text = _HEADER_LINE.sub("", raw)
    text = _HUBEALI.sub("", text)
    text = _PAGE_LINE.sub("", text)
    text = _VOLUME_LINE.sub("", text)
    text = _PART_LINE.sub("", text)
    text = _REASONS_TITLE.sub("", text)
    text = "\n".join(_WS.sub(" ", ln).rstrip() for ln in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def volume_part_from_filename(pdf_path: str | Path) -> tuple[Optional[str], Optional[str]]:
    """``ILLAL AL SHARAIE - V 1 P 3.pdf`` -> ``("1", "3")``."""
    m = _VOL_PART_FROM_NAME.search(Path(pdf_path).name)
    if m:
        return m.group(1), m.group(2)
    return None, None


def _is_arabic_line(line: str) -> bool:
    ar = len(_ARABIC.findall(line))
    la = len(_LATIN.findall(line))
    return ar > 0 and ar >= la


def split_arabic_english(block: str) -> tuple[str, str]:
    """Separate an interleaved block into ``(arabic, english)``."""
    arabic: list[str] = []
    english: list[str] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        (arabic if _is_arabic_line(line) else english).append(line.strip())
    return (" ".join(arabic).strip(), " ".join(english).strip())


# ---------------------------------------------------------------------------
# Page iterator
# ---------------------------------------------------------------------------
def iter_ilal_pages(pdf_path: str | Path) -> Iterator[tuple[str, str, str]]:
    """Yield ``(volume, page, cleaned_text)`` for each non-trivial page."""
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "ʿIlal ingestion needs PyMuPDF — `pip install pymupdf`"
        ) from exc

    fallback_vol, _ = volume_part_from_filename(pdf_path)
    fallback_vol = fallback_vol or "?"
    doc = fitz.open(str(pdf_path))
    try:
        for i in range(doc.page_count):
            raw = doc[i].get_text()
            m = _HEADER.search(raw.replace("\n", " "))
            vol = m.group(1) if m else fallback_vol
            page = m.group(2) if m else str(i + 1)
            cleaned = _clean_page(raw)
            if len(cleaned) > 30:
                yield vol, page, cleaned
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Chapter + hadith splitter
# ---------------------------------------------------------------------------
def _split_into_chapters(
    page_records: list[tuple[str, str, str]],
) -> Iterator[tuple[str, str, str, str, str]]:
    """Yield ``(volume, page, chapter_num, chapter_title, body)`` per chapter.

    Text before the first chapter heading is yielded with
    ``chapter_num=""`` and ``chapter_title=""`` as a preamble.
    """
    full_text = "\n\n".join(cleaned for _, _, cleaned in page_records)
    if not full_text.strip():
        return

    last_vol = page_records[-1][0] if page_records else "?"
    last_page = page_records[-1][1] if page_records else "?"

    splits = _CHAPTER.split(full_text)
    # splits = [preamble, ch_num, ch_title, body, ch_num, ch_title, body, ...]
    if splits[0].strip():
        yield last_vol, last_page, "", "", splits[0].strip()

    for i in range(1, len(splits) - 2, 3):
        ch_num = splits[i].strip()
        ch_title = splits[i + 1].strip()
        body = splits[i + 2].strip() if i + 2 < len(splits) else ""
        if body:
            yield last_vol, last_page, ch_num, ch_title, body


def _split_chapter_into_hadiths(
    body: str,
) -> list[tuple[str, str]]:
    """Split a chapter body into ``[(hadith_number, text), ...]``.

    Returns an empty list if no hadith markers are found (chapter stays whole).
    """
    parts = _HADITH_SPLIT.split(body)
    if len(parts) < 3:
        return []
    result: list[tuple[str, str]] = []
    for j in range(1, len(parts) - 1, 2):
        number = parts[j].strip()
        text = parts[j + 1].strip()
        if number and text:
            result.append((number, text))
    return result


# ---------------------------------------------------------------------------
# Public document builder
# ---------------------------------------------------------------------------
def build_ilal_documents(
    pdf_path: str | Path,
    *,
    source_id: str = "ilal-al-sharayi",
    volume: Optional[str] = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    translation_source: str = "Hubeali (English), www.hubeali.com",
    min_chars: int = 80,
    max_chunk: int = 1500,
) -> list[Document]:
    """Build cited :class:`Document`s from one ʿIlal al-Sharāʾiʿ PDF part.

    Splits by chapter, then by hadith markers within each chapter. Long
    chapters without hadith markers are chunked. Arabic/English are separated.
    """
    page_records: list[tuple[str, str, str]] = list(iter_ilal_pages(pdf_path))
    if not page_records:
        return []

    detected_vol = page_records[0][0]
    vol = str(volume) if volume is not None else detected_vol

    docs: list[Document] = []
    seen: set[str] = set()

    for _, page, ch_num, ch_title, body in _split_into_chapters(page_records):
        hadiths = _split_chapter_into_hadiths(body)

        if hadiths:
            for h_num, h_text in hadiths:
                _emit_hadith(
                    docs, seen, vol, page, ch_num, ch_title, h_num, h_text,
                    source_id=source_id, confidence=confidence,
                    translation_source=translation_source, min_chars=min_chars,
                )
        elif ch_num:
            _emit_chapter(
                docs, seen, vol, page, ch_num, ch_title, body,
                source_id=source_id, confidence=confidence,
                translation_source=translation_source,
                min_chars=min_chars, max_chunk=max_chunk,
            )
        else:
            _emit_preamble(
                docs, seen, vol, page, body,
                source_id=source_id, confidence=confidence,
                translation_source=translation_source,
                min_chars=min_chars, max_chunk=max_chunk,
            )

    docs.sort(key=lambda d: (
        d.citation.volume or "",
        _ch_sort_key(d.citation.chapter or ""),
        int(d.citation.hadith_number or 0),
    ))
    return docs


def _ch_sort_key(ch: str) -> int:
    m = re.search(r"\d+", ch)
    return int(m.group()) if m else 0


def _emit_hadith(
    docs: list[Document],
    seen: set[str],
    vol: str, page: str, ch_num: str, ch_title: str,
    h_num: str, text: str,
    *, source_id: str, confidence: ConfidenceLevel,
    translation_source: str, min_chars: int,
) -> None:
    arabic, english = split_arabic_english(text)
    if len(arabic) + len(english) < min_chars:
        return
    doc_id = f"{source_id}-v{vol}-ch{ch_num}-h{h_num}"
    if doc_id in seen:
        return
    seen.add(doc_id)
    citation = Citation(
        source_id=source_id,
        evidence_type=EvidenceType.HADITH,
        volume=vol,
        chapter=f"Ch {ch_num}" + (f" — {ch_title}" if ch_title else ""),
        page=page,
        hadith_number=h_num,
        arabic_text=arabic or None,
        translation=english or None,
        translation_source=translation_source if english else None,
        grade=HadithGrade.UNGRADED,
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


def _emit_chapter(
    docs: list[Document],
    seen: set[str],
    vol: str, page: str, ch_num: str, ch_title: str, body: str,
    *, source_id: str, confidence: ConfidenceLevel,
    translation_source: str, min_chars: int, max_chunk: int,
) -> None:
    """Emit a chapter as one or more chunked documents."""
    arabic, english = split_arabic_english(body)
    combined = english or arabic
    if len(combined) < min_chars:
        return

    chunks = chunk_text(combined, max_chars=max_chunk, overlap=150) if len(combined) > max_chunk else [combined]
    for i, chunk in enumerate(chunks):
        doc_id = f"{source_id}-v{vol}-ch{ch_num}" + (f"-{i}" if len(chunks) > 1 else "")
        if doc_id in seen:
            continue
        seen.add(doc_id)
        ar_chunk = arabic if i == 0 else None
        citation = Citation(
            source_id=source_id,
            evidence_type=EvidenceType.HADITH,
            volume=vol,
            chapter=f"Ch {ch_num}" + (f" — {ch_title}" if ch_title else ""),
            page=page,
            arabic_text=ar_chunk,
            translation=chunk if english else None,
            translation_source=translation_source if english else None,
            grade=HadithGrade.UNGRADED,
            grade_source=None,
        )
        docs.append(
            Document(
                id=doc_id,
                text=chunk,
                evidence_type=EvidenceType.HADITH,
                citation=citation,
                confidence=confidence,
                tags=["hadith", source_id, f"grade-{HadithGrade.UNGRADED.value}"],
                language="en" if english else "ar",
            )
        )


def _emit_preamble(
    docs: list[Document],
    seen: set[str],
    vol: str, page: str, body: str,
    *, source_id: str, confidence: ConfidenceLevel,
    translation_source: str, min_chars: int, max_chunk: int,
) -> None:
    """Emit unchaptered preamble text as page-level fallback docs."""
    arabic, english = split_arabic_english(body)
    combined = english or arabic
    if len(combined) < min_chars:
        return
    chunks = chunk_text(combined, max_chars=max_chunk, overlap=150) if len(combined) > max_chunk else [combined]
    for i, chunk in enumerate(chunks):
        doc_id = f"{source_id}-v{vol}-p{page}-{i}"
        if doc_id in seen:
            continue
        seen.add(doc_id)
        citation = Citation(
            source_id=source_id,
            evidence_type=EvidenceType.HADITH,
            volume=vol,
            page=page,
            arabic_text=arabic if i == 0 else None,
            translation=chunk if english else None,
            translation_source=translation_source if english else None,
            grade=HadithGrade.UNGRADED,
            grade_source=None,
        )
        docs.append(
            Document(
                id=doc_id,
                text=chunk,
                evidence_type=EvidenceType.HADITH,
                citation=citation,
                confidence=confidence,
                tags=["hadith", source_id, f"grade-{HadithGrade.UNGRADED.value}"],
                language="en" if english else "ar",
            )
        )
