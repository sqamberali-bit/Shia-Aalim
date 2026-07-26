"""Biḥār al-Anwār ingestion adapter (hubeali English text-layer PDFs).

The hubeali.com English Biḥār is distributed as one text-layer PDF per volume
(V1..V101). Every page carries an authoritative running header —
``Bihar Al-Anwaar  Volume N  www.hubeali.com  Page X of Y`` — from which we read
the exact volume and page.

**Per-hadith splitting.**  Each narration ends with a footnote reference number
(superscript), and the footnotes at the bottom of each page carry the official
Bihar citation in the form ``N Bihar Al-Anwaar – VN, {book}, Ch N H N``.  The
adapter parses these footnotes page by page, finds the inline superscripts in
the body text above the footnotes, and splits between them — producing one
:class:`Document` per narration, cited as *Biḥār al-Anwār, vNN, Ch X, H Y*
instead of a page-level approximation.

Design / honesty notes:

* Text is kept as-is: interleaved English (Hubeali translation) + Arabic matn +
  isnād. Arabic is separated by script detection and stored in
  ``citation.arabic_text``; English goes into ``text`` (for retrieval).
* Biḥār is a comprehensive compilation containing strong *and* weak reports and
  al-Majlisī's own commentary, and these PDFs carry **no per-hadith rijāl
  grade**. So confidence is capped at ``medium`` and grade stays ``ungraded`` —
  narrations must be graded against a rijāl source before being treated as
  authentic.
* Body text that cannot be attributed to a specific hadith (preambles, table of
  contents, commentary between footnote-delimited narrations) is emitted as a
  page-level fallback document so nothing is silently dropped.

Requires PyMuPDF (``pip install pymupdf``); imported lazily so the rest of the
package never depends on it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

# ---------------------------------------------------------------------------
# Running-header patterns (for stripping page chrome)
# ---------------------------------------------------------------------------
_HEADER = re.compile(
    r"Bihar\s+Al-?Anwaar\s+Volume\s+(\d+)\s+www\.hubeali\.com\s+Page\s+(\d+)\s+of\s+(\d+)",
    re.IGNORECASE,
)
_HEADER_LINE = re.compile(r"^\s*Bihar\s+Al-?Anwaar\b.*$", re.IGNORECASE | re.MULTILINE)
_HUBEALI = re.compile(r"^\s*www\.hubeali\.com\s*$", re.IGNORECASE | re.MULTILINE)
_PAGE_LINE = re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
_VOLUME_LINE = re.compile(r"^\s*Volume\s+\d+\s*$", re.IGNORECASE | re.MULTILINE)
_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")

_VOL_FROM_NAME = re.compile(r"[Vv](\d+)\.pdf$")

# ---------------------------------------------------------------------------
# Footnote patterns — the primary citation source
# ---------------------------------------------------------------------------
_FOOTNOTE = re.compile(
    r"^(\d+)\s+Bihar\s+Al.?An[wv].*?"
    r"(?:Ch|CH)\s*(\d+)\s*"
    r"H\s*(\d+)\s*([a-z]?)",
    re.IGNORECASE | re.MULTILINE,
)
_FOOTNOTE_LINE = re.compile(
    r"^\d+\s+Bihar\s+Al.?An[wv].*$",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Inline superscript reference — marks the end of a hadith in the body.
# ---------------------------------------------------------------------------
_INLINE_REF_PUNCT = re.compile(
    r"[‘’“”'\"`.]+\s*(\d{1,4})\s*$",
    re.MULTILINE,
)
_INLINE_REF_BARE = re.compile(r"^\s*(\d{1,4})\s*$", re.MULTILINE)

# ---------------------------------------------------------------------------
# Arabic script detection
# ---------------------------------------------------------------------------
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_LATIN = re.compile(r"[A-Za-z]")


def _clean_page(raw: str) -> str:
    """Strip running-header chrome; keep footnotes and body intact."""
    text = _HEADER_LINE.sub("", raw)
    text = _HUBEALI.sub("", text)
    text = _PAGE_LINE.sub("", text)
    text = _VOLUME_LINE.sub("", text)
    text = "\n".join(_WS.sub(" ", ln).rstrip() for ln in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def volume_from_filename(pdf_path: str | Path) -> Optional[str]:
    m = _VOL_FROM_NAME.search(Path(pdf_path).name)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Low-level page iterator (unchanged public API for backward compat)
# ---------------------------------------------------------------------------
def iter_bihar_pages(pdf_path: str | Path) -> Iterator[tuple[str, str, str]]:
    """Yield ``(volume, page, cleaned_text)`` for each non-trivial page."""
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


# ---------------------------------------------------------------------------
# Footnote parsing
# ---------------------------------------------------------------------------
def parse_footnotes(text: str) -> dict[int, tuple[str, str, str]]:
    """Extract footnote references from a page's text.

    Returns ``{ref_num: (chapter, hadith_num, suffix)}`` where *suffix* is
    an optional sub-letter (``"a"``, ``"b"``, …) or empty string.
    """
    result: dict[int, tuple[str, str, str]] = {}
    for m in _FOOTNOTE.finditer(text):
        ref = int(m.group(1))
        chapter = m.group(2)
        hadith = m.group(3)
        suffix = m.group(4).strip()
        result[ref] = (chapter, hadith, suffix)
    return result


def _footnote_section_start(text: str) -> int:
    """Return the character offset where the footnote section begins.

    Footnotes appear at the bottom of each page.  Returns ``len(text)`` when
    no footnote line is found.
    """
    m = _FOOTNOTE_LINE.search(text)
    return m.start() if m else len(text)


def _strip_footnotes(text: str) -> str:
    """Remove footnote lines from the page body."""
    return _FOOTNOTE_LINE.sub("", text)


# ---------------------------------------------------------------------------
# Arabic / English separation
# ---------------------------------------------------------------------------
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
# Per-page inline superscript finder
# ---------------------------------------------------------------------------
def _find_page_inline_refs(
    body_section: str, known_refs: set[int],
) -> list[tuple[int, int]]:
    """Find inline superscript references in the body section of one page.

    Searches *only* the body text (before the footnote section) to avoid
    false positives from numbers elsewhere in the volume.  Returns
    ``[(ref_num, end_position), ...]`` sorted by position.
    """
    candidates: dict[int, int] = {}
    for pat in (_INLINE_REF_PUNCT, _INLINE_REF_BARE):
        for m in pat.finditer(body_section):
            num = int(m.group(1))
            if num in known_refs and num not in candidates:
                candidates[num] = m.end()

    result = sorted(candidates.items(), key=lambda x: x[1])
    # Enforce strictly increasing ref numbers (drop noise)
    filtered: list[tuple[int, int]] = []
    prev = 0
    for ref, pos in result:
        if ref > prev:
            filtered.append((ref, pos))
            prev = ref
    return filtered


# ---------------------------------------------------------------------------
# Per-hadith iterator
# ---------------------------------------------------------------------------
def iter_bihar_narrations(
    pdf_path: str | Path,
) -> Iterator[tuple[str, str, str, str, str]]:
    """Yield ``(volume, page, chapter, hadith_id, body_text)`` per narration.

    *hadith_id* is the canonical Bihar hadith number within the chapter, e.g.
    ``"7"`` or ``"4b"`` (with sub-letter if present).  *page* is the PDF page
    where the narration *ends* (where its footnote appears).

    Pages whose text cannot be split into narrations are yielded as a single
    entry with ``chapter=""`` and ``hadith_id=""`` so that no content is lost.
    """
    # --- First pass: read all pages -----------------------------------------
    page_records: list[tuple[str, str, str]] = []
    for vol, page, cleaned in iter_bihar_pages(pdf_path):
        page_records.append((vol, page, cleaned))

    yield from _split_pages_into_narrations(page_records)


def _split_pages_into_narrations(
    page_records: list[tuple[str, str, str]],
) -> Iterator[tuple[str, str, str, str, str]]:
    """Core splitter shared by the PDF path and the JSONL reprocessor."""
    pending_body = ""
    pending_fn: dict[int, tuple[str, str, str]] = {}
    last_vol = ""
    last_page = ""

    for vol, page, cleaned in page_records:
        fns = parse_footnotes(cleaned)
        fn_start = _footnote_section_start(cleaned)
        body_section = cleaned[:fn_start]
        body_section = _BLANKS.sub("\n\n", body_section).strip()

        if fns:
            combined_body = (pending_body + "\n\n" + body_section).strip()
            all_fn = {**pending_fn, **fns}
            inline = _find_page_inline_refs(combined_body, set(all_fn.keys()))

            if inline:
                prev_end = 0
                for ref, end_pos in inline:
                    segment = combined_body[prev_end:end_pos].strip()
                    prev_end = end_pos
                    if not segment:
                        continue
                    ch, h, suf = all_fn[ref]
                    hid = f"{h}{suf}" if suf else h
                    yield vol, page, ch, hid, segment
                pending_body = combined_body[prev_end:].strip()
            else:
                # Footnotes on this page but no inline refs found — emit
                # the combined body keyed to the first footnote.
                first_ref = min(all_fn)
                ch, h, suf = all_fn[first_ref]
                hid = f"{h}{suf}" if suf else h
                if combined_body:
                    yield vol, page, ch, hid, combined_body
                pending_body = ""

            pending_fn = {}
        else:
            # No footnotes on this page — buffer the body for the next page
            pending_body = (pending_body + "\n\n" + body_section).strip()

        last_vol = vol
        last_page = page

    # Flush any remaining buffered text as a page-level doc
    if pending_body and len(pending_body) >= 80:
        yield last_vol, last_page, "", "", pending_body


# ---------------------------------------------------------------------------
# Public document builder
# ---------------------------------------------------------------------------
def _hadith_sort_key(h: str) -> tuple[int, str]:
    """Parse ``"15a"`` into ``(15, "a")`` for sorting."""
    m = re.match(r"(\d+)(.*)", h)
    if m:
        return (int(m.group(1)), m.group(2))
    return (0, h)


def build_bihar_documents(
    pdf_path: str | Path,
    *,
    source_id: str = "bihar-al-anwar",
    volume: Optional[str] = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    translation_source: str = "Hubeali (English), www.hubeali.com",
    min_chars: int = 120,
) -> list[Document]:
    """Build one cited :class:`Document` per narration in a Biḥār volume PDF.

    Falls back to page-level documents for content that cannot be split into
    individual narrations (table-of-contents pages, commentary without
    footnotes).
    """
    docs: list[Document] = []
    seen: set[str] = set()

    for detected_vol, page, chapter, hadith_id, body in iter_bihar_narrations(pdf_path):
        _emit_doc(
            docs, seen, detected_vol, page, chapter, hadith_id, body,
            volume_override=volume, source_id=source_id,
            confidence=confidence, translation_source=translation_source,
            min_chars=min_chars,
        )

    docs.sort(key=lambda d: (
        d.citation.volume or "",
        _hadith_sort_key(d.citation.hadith_number or "0"),
    ))
    return docs


def _emit_doc(
    docs: list[Document],
    seen: set[str],
    detected_vol: str,
    page: str,
    chapter: str,
    hadith_id: str,
    body: str,
    *,
    volume_override: Optional[str],
    source_id: str,
    confidence: ConfidenceLevel,
    translation_source: str,
    min_chars: int,
) -> None:
    arabic, english = split_arabic_english(body)
    if len(arabic) + len(english) < min_chars:
        return

    vol = str(volume_override) if volume_override is not None else detected_vol

    if chapter and hadith_id:
        doc_id = f"{source_id}-v{vol}-ch{chapter}-h{hadith_id}"
        chap_str = f"Ch {chapter}"
    else:
        doc_id = f"{source_id}-v{vol}-p{page}"
        chap_str = None

    if doc_id in seen:
        return
    seen.add(doc_id)

    citation = Citation(
        source_id=source_id,
        evidence_type=EvidenceType.HADITH,
        volume=vol,
        chapter=chap_str,
        page=page,
        hadith_number=hadith_id or None,
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
            tags=["hadith", source_id, "bihar", f"grade-{HadithGrade.UNGRADED.value}"],
            language="en" if english else "ar",
        )
    )
