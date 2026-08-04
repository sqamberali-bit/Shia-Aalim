"""Wasāʾil al-Shīʿa ingestion — Arabic-edition volume PDFs (vols 17+).

wasail-al-shia.net's English translation currently covers vols 1-16 (see the
``wasail`` adapter). The later volumes circulate as **Arabic-only** text-layer
PDFs of the Āl al-Bayt edition, in which every narration opens with its
cumulative hadith number in parentheses — e.g. ``(23920)`` — continuing the
same numbering the English volumes use, and chapters are ``باب`` headings.
That still yields the precise citation *volume + bāb + cumulative hadith
number*.

Extraction quirks handled here (and their honesty implications):

* The text layer stores Arabic in **presentation forms** (ﺑﺎﺏ) — NFKC
  normalization restores standard letters so Arabic retrieval works.
* Digit runs inside RTL text are extracted **visually reversed** (``٠٢٩٣٢``
  for 23920) — digits are reversed back before use. This is verified per
  volume: if the recovered hadith numbers are not overwhelmingly increasing,
  the volume is rejected rather than mis-cited.
* A narration's first extracted line carries its marker at the line *end*
  (visual order), so word order at the very start of a narration can read
  slightly shuffled. Content is preserved verbatim otherwise; nothing is
  reflowed or paraphrased.
* No English translation exists in these PDFs, so ``text`` is the Arabic matn
  (``language="ar"``) and there is nothing in ``citation.translation``. These
  volumes carry no rijāl grade either — narrations stay ungraded, confidence
  capped at ``medium``.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterator, Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_AR_DIGIT_RUN = re.compile(r"[٠-٩]+")

# A narration marker: the cumulative hadith number in (mirrored) parentheses —
# or square brackets; the edition varies by volume (e.g. vols 19 and 26).
# Footnote references are 1-2 digits and cross-references to earlier hadith can
# reach 4; cumulative numbers in these volumes (17+) are all 5 digits
# (~22000+), so require exactly 5+ to never split on either.
_MARKER = re.compile(r"[()\[\]]\s*([٠-٩]{5,})\s*[()\[\]]")

# Footnote block separator: everything from this line to the end of the PAGE is
# the page's footnote apparatus, not narration matn.
_FOOTNOTE_RULE = re.compile(r"^_{6,}\s*$")

# A bāb (chapter) heading line. Matched AFTER NFKC normalization.
_BAB_LINE = re.compile(r"^\s*باب\s+\S", re.MULTILINE)

_PAGE_NUM_LINE = re.compile(r"^\s*[٠-٩0-9]{1,4}\s*$", re.MULTILINE)
_WS = re.compile(r"[ \t]+")


def _reverse_digits(run: str) -> str:
    """Visually-reversed Arabic-Indic digit run -> ASCII int string."""
    return "".join(str(_AR_DIGITS.index(c)) for c in reversed(run))


def _normalize(raw: str) -> str:
    """Presentation forms -> standard Arabic; strip page-number chrome."""
    text = unicodedata.normalize("NFKC", raw)
    text = _PAGE_NUM_LINE.sub("", text)
    return "\n".join(_WS.sub(" ", ln).rstrip() for ln in text.splitlines())


def _clean_chapter(line: str) -> str:
    """Render a bāb heading line as the chapter title (reverse its digit runs)."""
    line = _AR_DIGIT_RUN.sub(lambda m: _reverse_digits(m.group(0)), line)
    return line.strip(" -–:")[:200]


def iter_arabic_narrations(pdf_path: str | Path) -> Iterator[tuple[str, str, str]]:
    """Yield ``(bab_title, hadith_number, block_text)`` per narration.

    A line containing a 4+ digit parenthesized marker starts a new narration;
    the most recent ``باب`` line before it is its chapter.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "Wasāʾil ingestion needs PyMuPDF — `pip install pymupdf`"
        ) from exc

    doc = fitz.open(str(pdf_path))
    try:
        current_bab = ""
        number: Optional[str] = None
        block: list[str] = []
        for i in range(doc.page_count):
            for line in _normalize(doc[i].get_text()).splitlines():
                if not line.strip():
                    continue
                if _FOOTNOTE_RULE.match(line):
                    break  # rest of this page is footnotes
                if _BAB_LINE.match(line):
                    current_bab = _clean_chapter(line)
                    continue
                m = _MARKER.search(line)
                if m:
                    if number is not None and block:
                        yield current_bab, number, "\n".join(block)
                    number = _reverse_digits(m.group(1))
                    block = [line]
                elif number is not None:
                    block.append(line)
        if number is not None and block:
            yield current_bab, number, "\n".join(block)
    finally:
        doc.close()


def build_wasail_arabic_documents(
    pdf_path: str | Path,
    *,
    volume: str,
    source_id: str = "wasail-al-shia",
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    min_chars: int = 40,
    min_monotonic: float = 0.95,
) -> list[Document]:
    """Build one cited :class:`Document` per narration in an Arabic volume PDF.

    ``min_monotonic`` guards the digit-reversal assumption: if fewer than that
    fraction of consecutive hadith numbers are increasing, the volume's
    extraction is considered unreliable and an empty list is returned (nothing
    gets mis-cited).
    """
    rows = [
        (bab, number, text)
        for bab, number, text in iter_arabic_narrations(pdf_path)
        if len(text) >= min_chars
    ]
    if not rows:
        return []

    # One volume spans a contiguous run of ~1-2k cumulative numbers. A stray
    # digit run in end matter can fake a marker with a wild number — drop
    # narrations far from the volume's median rather than mis-cite them.
    import statistics

    med = statistics.median(int(n) for _, n, _ in rows)
    dropped = [r for r in rows if abs(int(r[1]) - med) > 5000]
    if dropped:
        print(f"  [drop] {Path(pdf_path).name}: {len(dropped)} narration "
              f"marker(s) far from the volume's range (median {int(med)}) — skipped")
        rows = [r for r in rows if abs(int(r[1]) - med) <= 5000]

    nums = [int(n) for _, n, _ in rows]
    if len(nums) > 1:
        increasing = sum(1 for a, b in zip(nums, nums[1:]) if b > a)
        if increasing / (len(nums) - 1) < min_monotonic:
            print(f"  [reject] {Path(pdf_path).name}: hadith numbers not "
                  f"monotonic ({increasing}/{len(nums) - 1}) — check extraction")
            return []

    docs: list[Document] = []
    seen: set[str] = set()
    for bab, number, text in rows:
        doc_id = f"{source_id}-v{volume}-h{number}"
        if doc_id in seen:
            continue
        seen.add(doc_id)
        citation = Citation(
            source_id=source_id,
            evidence_type=EvidenceType.HADITH,
            volume=volume,
            chapter=bab or None,
            hadith_number=number,
            arabic_text=text,
            translation=None,
            translation_source=None,
            grade=HadithGrade.UNGRADED,  # these PDFs record no rijal grade
            grade_source=None,
        )
        docs.append(
            Document(
                id=doc_id,
                text=text,
                evidence_type=EvidenceType.HADITH,
                citation=citation,
                confidence=confidence,
                tags=["hadith", source_id, f"grade-{HadithGrade.UNGRADED.value}"],
                language="ar",
            )
        )
    docs.sort(key=lambda d: int(d.citation.hadith_number or 0))
    return docs
