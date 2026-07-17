"""Core domain model for the Shia-Aalim knowledge system.

Design principles (derived directly from the project charter in AGENT.md):

* **No citation = not a fact.** A :class:`Claim` cannot be marked as
  established unless it carries at least one :class:`Citation`.
* **Confidence is explicit.** Every source and every claim carries a
  :class:`ConfidenceLevel`. Low / unverified content is never silently
  promoted to fact.
* **Provenance is typed.** Quran, Tafsir, Hadith, Historical report and
  Scholarly opinion are distinct :class:`EvidenceType` values so an answer can
  always tell the reader *what kind* of evidence a statement rests on.

The module depends only on the Python standard library so it can be imported
and tested anywhere with no installation step.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ConfidenceLevel(str, Enum):
    """How much epistemic weight the system may place on a source/claim.

    Ordered from strongest to weakest. ``UNVERIFIED`` content must never be
    presented to a user as established fact.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"

    @property
    def rank(self) -> int:
        return {"high": 3, "medium": 2, "low": 1, "unverified": 0}[self.value]

    def can_state_as_fact(self) -> bool:
        """Only HIGH/MEDIUM confidence may be asserted without a hedge."""
        return self.rank >= ConfidenceLevel.MEDIUM.rank


class EvidenceType(str, Enum):
    """The category of evidence a citation/claim rests on."""

    QURAN = "quran"
    TAFSIR = "tafsir"
    HADITH = "hadith"
    HISTORICAL = "historical"
    SCHOLARLY_OPINION = "scholarly_opinion"
    BIOGRAPHICAL = "biographical"  # rijal / ilm al-rijal
    LINGUISTIC = "linguistic"


class ViewStatus(str, Enum):
    """Where a claim sits within the spectrum of Shia scholarly opinion."""

    CONSENSUS = "consensus"  # ijma / near-universal
    MAJORITY = "majority"
    MINORITY = "minority"
    DISPUTED = "disputed"
    POPULAR_UNVERIFIED = "popular_unverified"  # widespread but weakly evidenced


class HadithGrade(str, Enum):
    """Classical Shia hadith authenticity grades (ilm al-dirayah).

    Kept descriptive only. The system never *derives* a grade on its own; a
    grade must come from an attributable rijal source, otherwise it stays
    ``UNGRADED``.
    """

    SAHIH = "sahih"  # authentic
    HASAN = "hasan"  # good
    MUWATHTHAQ = "muwaththaq"  # reliable
    DAIF = "daif"  # weak
    MAJHUL = "majhul"  # unknown narrator
    MURSAL = "mursal"  # broken chain
    UNGRADED = "ungraded"


# ---------------------------------------------------------------------------
# Sources & citations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """A bibliographic source in the knowledge base (a book, corpus or dataset).

    ``confidence`` is assigned by the source-validation framework
    (:mod:`shia_aalim.source_validation`), never guessed ad hoc.
    """

    id: str
    title: str
    kind: EvidenceType
    author: Optional[str] = None
    translator: Optional[str] = None
    publisher: Optional[str] = None
    language: str = "ar"
    url: Optional[str] = None
    license: Optional[str] = None
    confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["confidence"] = self.confidence.value
        return d


@dataclass(frozen=True)
class Citation:
    """A precise, verifiable pointer into a :class:`Source`.

    The required locator fields depend on ``evidence_type``; use
    :meth:`is_complete` to check whether enough locators are present for the
    citation to be independently verifiable, per the charter's citation rules.
    """

    source_id: str
    evidence_type: EvidenceType

    # Quran locators
    surah: Optional[int] = None
    ayah: Optional[int] = None

    # Book locators (tafsir / hadith / scholarly / historical)
    volume: Optional[str] = None
    page: Optional[str] = None
    hadith_number: Optional[str] = None
    chapter: Optional[str] = None

    # Verbatim text (strongly encouraged — enables grounding checks)
    arabic_text: Optional[str] = None
    translation: Optional[str] = None
    translation_source: Optional[str] = None

    # Authenticity metadata (hadith)
    grade: HadithGrade = HadithGrade.UNGRADED
    grade_source: Optional[str] = None  # who assigned the grade

    def is_complete(self) -> bool:
        """True when the citation carries enough locators to be verifiable."""
        if self.evidence_type is EvidenceType.QURAN:
            return self.surah is not None and self.ayah is not None
        if self.evidence_type is EvidenceType.HADITH:
            # A hadith needs the book plus at least one precise locator.
            return bool(self.source_id) and bool(
                self.hadith_number or self.page or self.volume
            )
        # Tafsir / scholarly / historical: book + a page or volume locator.
        return bool(self.source_id) and bool(self.page or self.volume or self.chapter)

    def reference_string(self) -> str:
        """Human-readable short reference, e.g. ``Al-Kafi, v1, p.34, h.2``."""
        if self.evidence_type is EvidenceType.QURAN:
            return f"Qur'an {self.surah}:{self.ayah}"
        parts: list[str] = [self.source_id]
        if self.volume:
            parts.append(f"v{self.volume}")
        if self.page:
            parts.append(f"p.{self.page}")
        if self.hadith_number:
            parts.append(f"h.{self.hadith_number}")
        if self.chapter:
            parts.append(f"ch.{self.chapter}")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        d["evidence_type"] = self.evidence_type.value
        d["grade"] = self.grade.value
        return d


# ---------------------------------------------------------------------------
# Knowledge documents (retrieval units)
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """A retrievable unit of text plus its provenance.

    A document is what the retriever indexes and returns. Its ``citation``
    makes every retrieved chunk traceable back to an exact reference.
    """

    id: str
    text: str
    evidence_type: EvidenceType
    citation: Citation
    confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    view_status: Optional[ViewStatus] = None
    tags: list[str] = field(default_factory=list)
    language: str = "ar"

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.content_hash()

    def content_hash(self) -> str:
        h = hashlib.sha256(self.text.strip().encode("utf-8")).hexdigest()
        return f"doc_{h[:16]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "evidence_type": self.evidence_type.value,
            "citation": self.citation.to_dict(),
            "confidence": self.confidence.value,
            "view_status": self.view_status.value if self.view_status else None,
            "tags": self.tags,
            "language": self.language,
        }

    def to_json_line(self) -> str:
        """Serialise to a single-line JSON string for ``.jsonl`` knowledge files."""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Document":
        cit = d["citation"]
        citation = Citation(
            source_id=cit["source_id"],
            evidence_type=EvidenceType(cit["evidence_type"]),
            surah=cit.get("surah"),
            ayah=cit.get("ayah"),
            volume=cit.get("volume"),
            page=cit.get("page"),
            hadith_number=cit.get("hadith_number"),
            chapter=cit.get("chapter"),
            arabic_text=cit.get("arabic_text"),
            translation=cit.get("translation"),
            translation_source=cit.get("translation_source"),
            grade=HadithGrade(cit.get("grade", "ungraded")),
            grade_source=cit.get("grade_source"),
        )
        return cls(
            id=d.get("id", ""),
            text=d["text"],
            evidence_type=EvidenceType(d["evidence_type"]),
            citation=citation,
            confidence=ConfidenceLevel(d.get("confidence", "unverified")),
            view_status=ViewStatus(d["view_status"]) if d.get("view_status") else None,
            tags=list(d.get("tags", [])),
            language=d.get("language", "ar"),
        )


# ---------------------------------------------------------------------------
# Claims & answers
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """A single assertion inside a generated answer, with its backing evidence.

    Invariant enforced by :meth:`validate`: a claim may only be marked
    established (``can_state_as_fact``) if it carries at least one *complete*
    citation whose confidence permits assertion.
    """

    statement: str
    evidence_type: EvidenceType
    citations: list[Citation] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    view_status: Optional[ViewStatus] = None

    def complete_citations(self) -> list[Citation]:
        return [c for c in self.citations if c.is_complete()]

    def can_state_as_fact(self) -> bool:
        return bool(self.complete_citations()) and self.confidence.can_state_as_fact()

    def validate(self) -> list[str]:
        """Return a list of integrity problems (empty list == valid)."""
        problems: list[str] = []
        if not self.citations:
            problems.append("claim has no citations (charter: no citation = not a fact)")
        for c in self.citations:
            if not c.is_complete():
                problems.append(f"incomplete citation: {c.reference_string()}")
        if self.confidence.can_state_as_fact() and not self.complete_citations():
            problems.append(
                "claim asserts fact-level confidence but has no complete citation"
            )
        return problems


@dataclass
class Answer:
    """A fully-formed, evidence-first answer to a research question."""

    question: str
    claims: list[Claim] = field(default_factory=list)
    summary: Optional[str] = None
    caveats: list[str] = field(default_factory=list)
    generated_on: Optional[str] = None

    def all_citations(self) -> list[Citation]:
        return [c for claim in self.claims for c in claim.citations]

    def validate(self) -> list[str]:
        problems: list[str] = []
        for i, claim in enumerate(self.claims):
            for p in claim.validate():
                problems.append(f"claim[{i}]: {p}")
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "summary": self.summary,
            "generated_on": self.generated_on or date.today().isoformat(),
            "claims": [
                {
                    "statement": c.statement,
                    "evidence_type": c.evidence_type.value,
                    "confidence": c.confidence.value,
                    "view_status": c.view_status.value if c.view_status else None,
                    "citations": [cit.to_dict() for cit in c.citations],
                    "asserted_as_fact": c.can_state_as_fact(),
                }
                for c in self.claims
            ],
            "caveats": self.caveats,
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, **kwargs)
