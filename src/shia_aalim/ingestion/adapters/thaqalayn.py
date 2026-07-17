"""Twelver hadith ingestion adapter for the CC0 ``narmafraz/ThaqalaynData`` set.

That dataset (the data behind thaqalayn.net) stores each hadith as a
``verse_detail`` JSON file holding the Arabic *matn* + *isnād*, one or more
attributed translations (e.g. ``en.hubeali``), and — crucially — **rijāl
gradings** as attributed strings (grader + grade + source work), which lets us
populate ``grade`` and ``grade_source`` honestly instead of leaving them blank
or (forbidden) inventing them.

Design choices that keep this charter-compliant:

* The dataset also contains an ``ai`` analysis block (machine-generated narrator
  identification, machine translations). We deliberately **ignore** it — only
  the human, attributable ``text`` / ``translations`` / ``gradings`` are used.
* When graders disagree, the document's confidence is the **most conservative**
  across all gradings, and the full grading text of every grader is preserved in
  ``grade_source`` so nothing is lost.
* Ungraded hadith stay ``UNGRADED`` and are never presented as authentic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Optional

from ...ingestion.normalize import strip_tashkeel
from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Arabic grade term (diacritics stripped) -> canonical grade. Checked in this
# order so more specific / weakness terms win over the generic صحيح substring.
_GRADE_TERMS: list[tuple[str, HadithGrade]] = [
    ("مرسل", HadithGrade.MURSAL),
    ("مجهول", HadithGrade.MAJHUL),
    ("موثق", HadithGrade.MUWATHTHAQ),
    ("قوي", HadithGrade.MUWATHTHAQ),  # qawī (strong) → nearest reliable tier
    ("ضعيف", HadithGrade.DAIF),
    ("حسن", HadithGrade.HASAN),
    ("صحيح", HadithGrade.SAHIH),  # also matches كالصحيح ("like-authentic")
]

# English fallbacks (some gradings use CSS classes / English words).
_GRADE_WORDS_EN: list[tuple[str, HadithGrade]] = [
    ("mursal", HadithGrade.MURSAL),
    ("unknown", HadithGrade.MAJHUL),
    ("majhul", HadithGrade.MAJHUL),
    ("reliable", HadithGrade.MUWATHTHAQ),
    ("muwaththaq", HadithGrade.MUWATHTHAQ),
    ("weak", HadithGrade.DAIF),
    ("daif", HadithGrade.DAIF),
    ("good", HadithGrade.HASAN),
    ("hasan", HadithGrade.HASAN),
    ("authentic", HadithGrade.SAHIH),
    ("sahih", HadithGrade.SAHIH),
]

_GRADE_CONFIDENCE = {
    HadithGrade.SAHIH: ConfidenceLevel.HIGH,
    HadithGrade.HASAN: ConfidenceLevel.MEDIUM,
    HadithGrade.MUWATHTHAQ: ConfidenceLevel.MEDIUM,
    HadithGrade.DAIF: ConfidenceLevel.LOW,
    HadithGrade.MAJHUL: ConfidenceLevel.LOW,
    HadithGrade.MURSAL: ConfidenceLevel.LOW,
    HadithGrade.UNGRADED: ConfidenceLevel.MEDIUM,  # source authoritative; grade simply unrecorded
}


def _clean(text: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", text)).strip()


def _classify_one(grading: str) -> HadithGrade:
    stripped = strip_tashkeel(grading)
    for term, grade in _GRADE_TERMS:
        if term in stripped:
            return grade
    low = grading.lower()
    for word, grade in _GRADE_WORDS_EN:
        if word in low:
            return grade
    return HadithGrade.UNGRADED


def parse_grading(gradings: Optional[list[str]]) -> tuple[HadithGrade, str, list[HadithGrade]]:
    """Parse a hadith's grading strings.

    Returns ``(primary_grade, grade_source, all_grades)`` where ``primary_grade``
    is the first grader's grade (typically Allāma al-Majlisī), ``grade_source``
    is the full cleaned text of *every* grading (so disagreement is preserved),
    and ``all_grades`` lists each grader's classification.
    """
    if not gradings:
        return HadithGrade.UNGRADED, "", []
    grades = [_classify_one(g) for g in gradings]
    source = "; ".join(_clean(g) for g in gradings)
    primary = grades[0] if grades else HadithGrade.UNGRADED
    return primary, source, grades


def _confidence_from_grades(grades: list[HadithGrade]) -> ConfidenceLevel:
    """Most-conservative confidence across all graders (empty => ungraded tier)."""
    if not grades:
        return _GRADE_CONFIDENCE[HadithGrade.UNGRADED]
    levels = [_GRADE_CONFIDENCE[g] for g in grades]
    return min(levels, key=lambda c: c.rank)


def _decode_path(path: str) -> Optional[tuple[str, str, str, str]]:
    """'/books/al-kafi:1:3:3:2' -> (volume, book_idx, chapter_idx, hadith_idx)."""
    if ":" not in path:
        return None
    segs = path.split(":")[1:]  # drop the '/books/<slug>' head
    if len(segs) < 4:
        return None
    return segs[0], segs[1], segs[2], segs[3]


def _iter_verse_files(book_dir: Path) -> Iterable[Path]:
    for p in sorted(book_dir.rglob("*.json")):
        name = p.name
        # skip per-language (X.en.json) and narrator (X.narrators.json) files
        if re.search(r"\.[a-z]{2}\.json$", name) or name.endswith(".narrators.json"):
            continue
        if not re.match(r"^\d+\.json$", name):
            continue
        yield p


def build_hadith_documents(
    book_dir: str | Path,
    *,
    source_id: str,
    book_title: str,
    translation_key: str = "en.hubeali",
    translation_name: str = "Hubeali (via ThaqalaynData, CC0)",
) -> list[Document]:
    """Build hadith :class:`Document`s from a ThaqalaynData book directory.

    Each returned document's ``text`` is the attributed English translation (for
    English retrieval); the Arabic matn+isnād is preserved in
    ``citation.arabic_text``, and ``grade``/``grade_source`` carry the real rijāl
    assessment. Confidence is derived conservatively from the grade(s).
    """
    book_dir = Path(book_dir)
    docs: list[Document] = []
    for path in _iter_verse_files(book_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if payload.get("kind") != "verse_detail":
            continue
        verse = payload.get("data", {}).get("verse", {})

        text_field = verse.get("text")
        if isinstance(text_field, dict):
            ar_parts = text_field.get("ar", [])
        else:
            ar_parts = text_field or []
        arabic = _WS.sub(" ", " ".join(ar_parts)).strip()

        translations = verse.get("translations", {})
        en_parts = translations.get(translation_key, [])
        english = _WS.sub(" ", " ".join(en_parts)).strip()
        if not english and not arabic:
            continue

        decoded = _decode_path(verse.get("path", ""))
        if not decoded:
            continue
        volume, book_idx, chapter_idx, hadith_idx = decoded

        grade, grade_source, grades = parse_grading(verse.get("gradings"))
        confidence = _confidence_from_grades(grades)

        citation = Citation(
            source_id=source_id,
            evidence_type=EvidenceType.HADITH,
            volume=volume,
            chapter=f"{book_title}, bab {chapter_idx}",
            hadith_number=hadith_idx,
            arabic_text=arabic or None,
            translation=english or None,
            translation_source=translation_name if english else None,
            grade=grade,
            grade_source=grade_source or None,
        )
        docs.append(
            Document(
                id=f"{source_id}-{volume}-{book_idx}-{chapter_idx}-{hadith_idx}",
                text=english or arabic,
                evidence_type=EvidenceType.HADITH,
                citation=citation,
                confidence=confidence,
                tags=["hadith", source_id, f"grade-{grade.value}"],
                language="en" if english else "ar",
            )
        )
    docs.sort(key=lambda d: _sort_key(d.id))
    return docs


def _sort_key(doc_id: str) -> tuple:
    nums = re.findall(r"\d+", doc_id)
    return tuple(int(n) for n in nums)
