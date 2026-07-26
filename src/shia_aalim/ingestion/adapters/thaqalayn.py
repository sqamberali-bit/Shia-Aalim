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

from ...ingestion.normalize import normalize_for_search, strip_tashkeel
from ...models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Arabic grade term (diacritics stripped, Persian letters folded to Arabic) ->
# canonical grade. Checked in this order so more specific / weakness terms win
# over the generic صحيح substring.
_GRADE_TERMS: list[tuple[str, HadithGrade]] = [
    ("مرسل", HadithGrade.MURSAL),
    ("مجهول", HadithGrade.MAJHUL),
    ("موثق", HadithGrade.MUWATHTHAQ),
    ("قوي", HadithGrade.MUWATHTHAQ),  # qawī (strong) → nearest reliable tier
    ("معتبر", HadithGrade.MUWATHTHAQ),  # muʿtabar (reliable) — Muhsini's rulings
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
    # Fold diacritics + Persian letter forms (ضعیف→ضعيف, غیر→غير) so the Arabic
    # grade terms match regardless of the source's orthography.
    norm = normalize_for_search(grading)
    # "غير معتبر" (not reliable) must never be read as reliable — guard the
    # negation before the positive معتبر term below.
    if "معتبر" in norm and "غير" in norm:
        return HadithGrade.DAIF
    for term, grade in _GRADE_TERMS:
        if term in norm:
            return grade
    for word, grade in _GRADE_WORDS_EN:
        if word in norm:
            return grade
    return HadithGrade.UNGRADED


def parse_grading(gradings) -> tuple[HadithGrade, str, list[HadithGrade]]:
    """Parse a hadith's grading(s).

    ThaqalaynData stores gradings in two shapes: a **list** of attributed strings
    (e.g. al-Kāfī: ``"Majlisī: <grade> - Mirʾāt …"``) or a **{grader: grade}
    dict** (e.g. Muḥsinī's works: ``{"mohseni": "معتبر"}``). Both are accepted.

    Returns ``(primary_grade, grade_source, all_grades)`` where ``primary_grade``
    is the first grader's grade (typically Allāma al-Majlisī), ``grade_source``
    is the full cleaned text of *every* grading (so disagreement is preserved),
    and ``all_grades`` lists each grader's classification.
    """
    if not gradings:
        return HadithGrade.UNGRADED, "", []
    if isinstance(gradings, dict):
        items = [f"{grader}: {verdict}" for grader, verdict in gradings.items() if verdict]
    else:
        items = [g for g in gradings if g]
    if not items:
        return HadithGrade.UNGRADED, "", []
    grades = [_classify_one(g) for g in items]
    source = "; ".join(_clean(g) for g in items)
    primary = grades[0] if grades else HadithGrade.UNGRADED
    return primary, source, grades


def _confidence_from_grades(grades: list[HadithGrade]) -> ConfidenceLevel:
    """Most-conservative confidence across all graders (empty => ungraded tier)."""
    if not grades:
        return _GRADE_CONFIDENCE[HadithGrade.UNGRADED]
    levels = [_GRADE_CONFIDENCE[g] for g in grades]
    return min(levels, key=lambda c: c.rank)


def _decode_segments(path: str) -> list[str]:
    """'/books/al-kafi:1:3:3:2' -> ['1','3','3','2'] (drops the slug head)."""
    if ":" not in path:
        return []
    return path.split(":")[1:]


# Nahj al-Balagha's three top-level sections map to its classical citation types.
_NAHJ_SECTIONS = {"1": "Sermon", "2": "Letter", "3": "Saying"}


def _citation_locators(
    segments: list[str], book_title: str, style: str
) -> Optional[dict[str, str]]:
    """Map raw path segments to citation locators for a given book style.

    * ``hierarchical`` (al-Kafi/Faqih/Tahdhib/Istibsar): the first segment is the
      volume, the last is the hadith number, and any middle segments form the
      chapter path — this copes with both 4-segment (al-Kafi) and 3-segment
      (Faqih) layouts.
    * ``nahj``: sections are Sermon/Letter/Saying; we cite by that type + number
      and keep the sub-part as the hadith locator.
    """
    if not segments:
        return None
    if style == "nahj":
        section = segments[0]
        kind = _NAHJ_SECTIONS.get(section, "Part")
        number = segments[1] if len(segments) > 1 else section
        part = segments[-1] if len(segments) > 2 else "1"
        return {
            "chapter": f"{kind} {number}",
            "hadith_number": part,
            "id_suffix": "-".join(segments),
        }
    # hierarchical: last segment is the hadith; the rest is the chapter path.
    # Only call the first segment a "volume" when there is a genuine
    # volume+chapter hierarchy above the hadith (>=3 segments); with just
    # [chapter, hadith] there is no volume level, so keep the chapter locator.
    if len(segments) < 2:
        return None
    hadith_number = segments[-1]
    prefix = segments[:-1]
    if len(prefix) >= 2:
        volume = prefix[0]
        chapter_segs = prefix[1:]
    else:
        volume = ""
        chapter_segs = prefix
    chapter = book_title + (f", {':'.join(chapter_segs)}" if chapter_segs else "")
    return {
        "volume": volume,
        "chapter": chapter,
        "hadith_number": hadith_number,
        "id_suffix": "-".join(segments),
    }


def _pick_translation(translations: dict, keys: list[str]) -> tuple[str, str]:
    """Return (joined_text, key) for the first available candidate key."""
    for key in keys:
        parts = translations.get(key)
        if parts:
            return _WS.sub(" ", " ".join(parts)).strip(), key
    return "", ""


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
    translation_keys: Optional[list[str]] = None,
    translation_name: str = "Hubeali (via ThaqalaynData, CC0)",
    citation_style: str = "hierarchical",
    evidence_type: EvidenceType = EvidenceType.HADITH,
) -> list[Document]:
    """Build hadith :class:`Document`s from a ThaqalaynData book directory.

    Each returned document's ``text`` is the attributed English translation (for
    English retrieval); the Arabic matn+isnād is preserved in
    ``citation.arabic_text``, and ``grade``/``grade_source`` carry the real rijāl
    assessment. Confidence is derived conservatively from the grade(s).

    ``translation_keys`` is a candidate list (books use different translators);
    the first present key wins. ``citation_style`` selects the locator mapping
    (``hierarchical`` for the Four Books, ``nahj`` for Nahj al-Balāgha).
    ``evidence_type`` lets a rijāl work (e.g. Kitāb al-Ḍuʿafāʾ) be typed
    ``BIOGRAPHICAL`` rather than ``HADITH`` — the ThaqalaynData layout is the
    same; only the classification differs.
    """
    book_dir = Path(book_dir)
    keys = translation_keys or ["en.hubeali"]
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

        english, _ = _pick_translation(verse.get("translations", {}), keys)
        if not english and not arabic:
            continue

        loc = _citation_locators(_decode_segments(verse.get("path", "")), book_title, citation_style)
        if not loc:
            continue

        grade, grade_source, grades = parse_grading(verse.get("gradings"))
        confidence = _confidence_from_grades(grades)

        citation = Citation(
            source_id=source_id,
            evidence_type=evidence_type,
            volume=loc.get("volume") or None,
            chapter=loc.get("chapter"),
            hadith_number=loc.get("hadith_number"),
            arabic_text=arabic or None,
            translation=english or None,
            translation_source=translation_name if english else None,
            grade=grade,
            grade_source=grade_source or None,
        )
        docs.append(
            Document(
                id=f"{source_id}-{loc['id_suffix']}",
                text=english or arabic,
                evidence_type=evidence_type,
                citation=citation,
                confidence=confidence,
                tags=[evidence_type.value, source_id, f"grade-{grade.value}"],
                language="en" if english else "ar",
            )
        )
    docs.sort(key=lambda d: _sort_key(d.id))
    return docs


def _sort_key(doc_id: str) -> tuple:
    nums = re.findall(r"\d+", doc_id)
    return tuple(int(n) for n in nums)
