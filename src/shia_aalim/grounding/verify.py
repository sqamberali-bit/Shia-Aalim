"""Answer grounding and citation verification.

This module is the last line of defence before an answer reaches a user. It
implements four of the charter's hallucination-prevention controls:

1. **Citation completeness** — every citation has the locators it needs.
2. **Source existence** — every cited source id is a real, registered source
   (no invented books), and, where possible, the cited passage actually exists
   in the ingested corpus (no invented volume/page/hadith number).
3. **Answer grounding** — each claim's text overlaps materially with at least
   one retrieved passage, so the model is not asserting things the evidence
   does not contain.
4. **Fact/hedge consistency** — nothing is asserted as established fact unless
   its confidence and citations permit it.

The lexical-overlap grounding check is a deliberately conservative baseline: it
can flag ungrounded claims but should be *complemented* (not replaced) by an
LLM-based entailment check in production. It never silently passes a claim it
cannot corroborate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from ..ingestion.normalize import tokens
from ..models import Answer, Citation, ConfidenceLevel, Document
from ..retrieval.retriever import RetrievalResult


@dataclass
class CitationCheck:
    citation: Citation
    complete: bool
    source_known: bool
    passage_found: Optional[bool]  # None => corpus not provided, cannot check
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.complete and self.source_known and self.passage_found is not False


@dataclass
class GroundingReport:
    grounded: bool
    claim_scores: list[float]
    citation_checks: list[CitationCheck]
    problems: list[str] = field(default_factory=list)

    @property
    def weakest_claim_score(self) -> float:
        return min(self.claim_scores) if self.claim_scores else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "grounded": self.grounded,
            "weakest_claim_score": round(self.weakest_claim_score, 3),
            "claim_scores": [round(s, 3) for s in self.claim_scores],
            "citation_problems": [p for c in self.citation_checks for p in c.problems],
            "problems": self.problems,
        }


def citation_exists_in_corpus(
    citation: Citation, corpus: Iterable[Document]
) -> Optional[bool]:
    """Best-effort check that a cited passage is actually present in the corpus.

    Returns ``True`` if a document with the same source and locators exists,
    ``False`` if the source is present but no matching locator is, and ``None``
    if the source itself is absent from the corpus (can't judge the locator).
    """
    same_source = [d for d in corpus if d.citation.source_id == citation.source_id]
    if not same_source:
        return None
    for d in same_source:
        c = d.citation
        if citation.evidence_type.value == "quran":
            if c.surah == citation.surah and c.ayah == citation.ayah:
                return True
        else:
            locator_match = (
                (citation.hadith_number is None or c.hadith_number == citation.hadith_number)
                and (citation.page is None or c.page == citation.page)
                and (citation.volume is None or c.volume == citation.volume)
            )
            # Require at least one locator to have been supplied and matched.
            if locator_match and any(
                [citation.hadith_number, citation.page, citation.volume]
            ):
                return True
    return False


def validate_citations(
    citations: list[Citation],
    *,
    known_source_ids: Optional[set[str]] = None,
    corpus: Optional[list[Document]] = None,
) -> list[CitationCheck]:
    """Check each citation for completeness, source existence and passage existence."""
    checks: list[CitationCheck] = []
    for cit in citations:
        problems: list[str] = []

        complete = cit.is_complete()
        if not complete:
            problems.append(f"incomplete locators for {cit.reference_string()}")

        source_known = True
        if known_source_ids is not None:
            source_known = cit.source_id in known_source_ids
            if not source_known:
                problems.append(
                    f"unknown/unregistered source '{cit.source_id}' "
                    "(possible invented source — refusing to treat as fact)"
                )

        passage_found: Optional[bool] = None
        if corpus is not None:
            passage_found = citation_exists_in_corpus(cit, corpus)
            if passage_found is False:
                problems.append(
                    f"cited passage not found in corpus: {cit.reference_string()}"
                )

        checks.append(
            CitationCheck(
                citation=cit,
                complete=complete,
                source_known=source_known,
                passage_found=passage_found,
                problems=problems,
            )
        )
    return checks


def _overlap(claim_text: str, passage_text: str) -> float:
    """Jaccard-style token overlap of the claim against a passage (0..1)."""
    a = set(tokens(claim_text))
    b = set(tokens(passage_text))
    if not a:
        return 0.0
    return len(a & b) / len(a)


def check_answer_grounding(
    answer: Answer,
    evidence: list[RetrievalResult],
    *,
    known_source_ids: Optional[set[str]] = None,
    corpus: Optional[list[Document]] = None,
    min_overlap: float = 0.25,
) -> GroundingReport:
    """Verify an :class:`Answer` against the evidence it was generated from.

    An answer is considered grounded only if **every** claim clears the overlap
    threshold against some retrieved passage AND all citations pass validation
    AND no claim over-asserts its confidence.
    """
    problems: list[str] = []
    passages = [r.document.text for r in evidence]

    claim_scores: list[float] = []
    for i, claim in enumerate(answer.claims):
        best = max((_overlap(claim.statement, p) for p in passages), default=0.0)
        claim_scores.append(best)
        if best < min_overlap:
            problems.append(
                f"claim[{i}] weakly grounded (overlap {best:.2f} < {min_overlap}): "
                f"{claim.statement[:80]!r}"
            )
        if claim.confidence.can_state_as_fact() and not claim.complete_citations():
            problems.append(
                f"claim[{i}] asserts fact-level confidence without a complete citation"
            )

    checks = validate_citations(
        answer.all_citations(), known_source_ids=known_source_ids, corpus=corpus
    )
    citation_problems = [p for c in checks for p in c.problems]

    grounded = (
        not problems
        and not citation_problems
        and all(s >= min_overlap for s in claim_scores)
        and len(answer.claims) > 0
    )
    return GroundingReport(
        grounded=grounded,
        claim_scores=claim_scores,
        citation_checks=checks,
        problems=problems + citation_problems,
    )
