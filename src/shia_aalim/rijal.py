"""Rijāl / narrator tooling — *surfacing*, never *deriving*.

The charter is strict: the system never assigns or derives a hadith grade or a
narrator's reliability on its own. Only an attributable rijāl source may do that.
This module therefore does two honest things and nothing more:

1. **Read the chain (isnad) as it literally appears in the narration text** — a
   transparent heuristic that splits the "A, from B, from C … who said" preamble
   into an ordered list of narrators. It is a surface reading of the text, not a
   verified isnad or a rijāl evaluation, and it is labelled as such.

2. **Surface the grade attributions already carried in the data** — parse the
   ``grade_source`` field into ``(attributor → grade → work)`` records, so a
   reader can see *who* graded a narration and to *what*, and browse narrations
   by grade. The grades come entirely from the corpus; nothing is computed here.

Built from what the corpus already contains; pure standard library.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .models import Document, EvidenceType

# --- chain (isnad) reading --------------------------------------------------

# Honorific markers (asws/azwj/saww/as) are rendered inside <sup> tags — drop the
# whole block (tag *and* its content), then any other stray tags.
_SUP = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_MARKUP = re.compile(r"<[^>]+>")
_PARENS = re.compile(r"\([^)]*\)")
# Where the matn (the reported content) begins — the chain ends here.
_MATN = re.compile(r"\bwho\s+(?:has\s+)?said\b", re.IGNORECASE)
# Transmission connectives that separate one narrator from the next.
_CONNECTOR = re.compile(
    r"\s*,?\s*(?:"
    r"narrated\s+to\s+(?:me|us)|"
    r"informed\s+(?:us|me)(?:\s+saying)?|"
    r"reported\s+to\s+(?:us|me)|"
    r"it\s+has\s+been\s+narrated|"
    r"or\s+from|"
    r"from"
    r")\s*,?\s*",
    re.IGNORECASE,
)
# Tokens that are chain links but not proper names (skipped from the index).
_RELATIONAL = re.compile(
    r"^(his\s+(father|grandfather|uncle|brother|companions?)|"
    r"a\s+(number|group|man)\b|some\s+of|certain|our\s+companions|a\s+servant)",
    re.IGNORECASE,
)


@dataclass
class ChainReading:
    narrators: list[str]          # ordered surface names as they appear
    has_chain: bool               # a matn boundary + at least one connector was found
    matn: str = ""                # the reported content after the chain


def strip_markup(text: str) -> str:
    return _MARKUP.sub("", _SUP.sub("", text or ""))


def extract_chain(text: str) -> ChainReading:
    """Heuristically read the isnad from a narration's text (surface reading only)."""
    clean = strip_markup(text)
    m = _MATN.search(clean)
    if not m:
        return ChainReading(narrators=[], has_chain=False, matn="")
    isnad = clean[: m.start()]
    matn = clean[m.end():].lstrip(" ,'‘’\":")
    # Drop trailing descriptor like ", a servant of Al-Reza".
    isnad = re.sub(r",\s*a\s+servant\s+of.*$", "", isnad, flags=re.IGNORECASE)
    isnad = _PARENS.sub(" ", isnad)

    parts = _CONNECTOR.split(isnad)
    narrators: list[str] = []
    for p in parts:
        name = p.strip().strip("’‘'\".,;:")
        name = re.sub(r"\s+", " ", name)
        if name:
            narrators.append(name)
    return ChainReading(narrators=narrators, has_chain=bool(narrators), matn=matn.strip())


def is_narrator_name(token: str) -> bool:
    """True if a chain token looks like an actual name (not 'his father' etc.)."""
    t = (token or "").strip()
    if len(t) < 3 or _RELATIONAL.match(t):
        return False
    return any(ch.isalpha() for ch in t)


def normalize_name(name: str) -> str:
    """Fold a narrator name to a lookup key (ibn/bin, Al-/Al, punctuation, case)."""
    s = strip_markup(name).lower()
    s = re.sub(r"[’‘`]", "'", s)
    s = re.sub(r"\b(?:ibn|b\.)\b", "bin", s)
    s = re.sub(r"\bal[-\s]+", "al ", s)
    s = re.sub(r"[^a-z' ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- grade attributions -----------------------------------------------------


@dataclass
class GradeAttribution:
    attributor: str   # who assigned the grade (e.g. "Allamah Baqir al-Majlisi")
    grade: str        # the grade term as recorded (may be Arabic, e.g. مجهول)
    work: str = ""    # the rijāl/hadith work it is stated in


def parse_grade_source(grade_source: Optional[str]) -> list[GradeAttribution]:
    """Split a ``grade_source`` string into per-attributor records.

    Expected shape (as ingested): ``"Attributor: <grade> - <work>; Attributor: …"``.
    Anything that doesn't fit is returned as a single free-text attribution so
    nothing is silently dropped.
    """
    if not grade_source:
        return []
    out: list[GradeAttribution] = []
    for piece in grade_source.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        if ":" in piece:
            who, rest = piece.split(":", 1)
            grade, work = rest, ""
            if " - " in rest:
                grade, work = rest.split(" - ", 1)
            out.append(GradeAttribution(who.strip(), grade.strip(), work.strip()))
        else:
            out.append(GradeAttribution(attributor="", grade=piece, work=""))
    return out


# --- narrator index ---------------------------------------------------------


@dataclass
class Mention:
    doc_id: str
    source_id: str
    grade: str
    grade_source: Optional[str]
    position: int          # index of the narrator within the chain
    chain_length: int


@dataclass
class NarratorProfile:
    query: str
    matched_names: list[str]                 # surface forms that matched
    narration_count: int
    grade_distribution: dict[str, int]
    mentions: list[Mention] = field(default_factory=list)


class NarratorIndex:
    """Index narrators as they appear in narration chains (surface reading)."""

    def __init__(self, docs: Iterable[Document]) -> None:
        self._by_key: dict[str, dict] = {}
        self._docs_by_id: dict[str, Document] = {}
        self._grade_counts: Counter = Counter()
        self._attributor_grades: dict[str, Counter] = {}
        self._n_hadith = 0
        self._n_with_chain = 0

        for d in docs:
            if d.evidence_type is not EvidenceType.HADITH:
                continue
            self._n_hadith += 1
            self._docs_by_id[d.id] = d
            grade = d.citation.grade.value
            self._grade_counts[grade] += 1
            for attr in parse_grade_source(d.citation.grade_source):
                if attr.attributor:
                    self._attributor_grades.setdefault(attr.attributor, Counter())[attr.grade] += 1

            reading = extract_chain(d.text)
            if reading.has_chain:
                self._n_with_chain += 1
            names = reading.narrators
            for pos, nm in enumerate(names):
                if not is_narrator_name(nm):
                    continue
                key = normalize_name(nm)
                if not key:
                    continue
                slot = self._by_key.setdefault(key, {"display": Counter(), "mentions": []})
                slot["display"][nm.strip()] += 1
                slot["mentions"].append(Mention(
                    doc_id=d.id, source_id=d.citation.source_id, grade=grade,
                    grade_source=d.citation.grade_source, position=pos, chain_length=len(names),
                ))

    # -- introspection --

    @property
    def narrator_count(self) -> int:
        return len(self._by_key)

    def document(self, doc_id: str) -> Optional[Document]:
        return self._docs_by_id.get(doc_id)

    def display_name(self, key: str) -> str:
        slot = self._by_key.get(key)
        return slot["display"].most_common(1)[0][0] if slot else key

    def top_narrators(self, n: int = 20) -> list[dict]:
        rows = [
            {"name": self.display_name(k), "key": k, "count": len(v["mentions"])}
            for k, v in self._by_key.items()
        ]
        rows.sort(key=lambda r: (-r["count"], r["name"]))
        return rows[:n]

    def grade_summary(self) -> dict:
        attributors = [
            {"attributor": a, "grades": dict(c), "total": sum(c.values())}
            for a, c in self._attributor_grades.items()
        ]
        attributors.sort(key=lambda r: -r["total"])
        return {
            "hadith": self._n_hadith,
            "with_readable_chain": self._n_with_chain,
            "grades": dict(self._grade_counts.most_common()),
            "attributors": attributors,
        }

    def lookup(self, query: str) -> NarratorProfile:
        """Find narrators whose name contains all tokens of ``query`` (folded)."""
        qkey = normalize_name(query)
        qtokens = [t for t in qkey.split() if t]
        matched_keys: list[str] = []
        for key in self._by_key:
            words = key.split()
            if qtokens and all(t in words for t in qtokens):
                matched_keys.append(key)
        if not matched_keys and qkey:  # fall back to substring match
            matched_keys = [k for k in self._by_key if qkey in k]

        mentions: list[Mention] = []
        names: Counter = Counter()
        grade_dist: Counter = Counter()
        seen_docs: set[str] = set()
        for key in matched_keys:
            slot = self._by_key[key]
            names.update(slot["display"])
            for men in slot["mentions"]:
                mentions.append(men)
                if men.doc_id not in seen_docs:
                    seen_docs.add(men.doc_id)
                    grade_dist[men.grade] += 1
        return NarratorProfile(
            query=query,
            matched_names=[n for n, _ in names.most_common()],
            narration_count=len(seen_docs),
            grade_distribution=dict(grade_dist.most_common()),
            mentions=mentions,
        )
