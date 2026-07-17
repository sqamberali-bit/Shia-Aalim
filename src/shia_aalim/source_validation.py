"""Source-validation framework.

Implements the charter rule *"Never trust a source automatically."* Each source
is scored across weighted criteria and mapped to a :class:`ConfidenceLevel`.

The scoring is deliberately transparent and deterministic: given the same
inputs it always yields the same confidence, and every decision is explained in
the returned :class:`ValidationReport` so a human reviewer can audit it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import ConfidenceLevel


# Weighted criteria (weights sum to 1.0). Each criterion is scored in [0, 1].
CRITERIA_WEIGHTS: dict[str, float] = {
    "scholarly_acceptance": 0.22,   # accepted within the Shia scholarly tradition
    "chain_availability": 0.15,     # isnad / sanad availability where relevant
    "publisher_credibility": 0.13,  # reputable publisher / institution
    "academic_references": 0.12,    # cited by academic / peer works
    "community_acceptance": 0.10,   # accepted by the wider community
    "original_language": 0.13,      # original (Arabic/Persian) text available
    "translation_quality": 0.15,    # faithful, attributable translation
}


@dataclass
class SourceAssessment:
    """Raw human/heuristic scores for one source. Each field is in [0.0, 1.0].

    Use ``None`` for *not applicable* (e.g. ``chain_availability`` for a Qur'an
    text) — N/A criteria are dropped and the remaining weights renormalised so
    they are neither rewarded nor penalised.
    """

    scholarly_acceptance: Optional[float] = None
    chain_availability: Optional[float] = None
    publisher_credibility: Optional[float] = None
    academic_references: Optional[float] = None
    community_acceptance: Optional[float] = None
    original_language: Optional[float] = None
    translation_quality: Optional[float] = None
    notes: str = ""

    def scores(self) -> dict[str, Optional[float]]:
        return {k: getattr(self, k) for k in CRITERIA_WEIGHTS}


@dataclass
class ValidationReport:
    """Outcome of scoring a source: a number, a level, and an explanation."""

    score: float
    confidence: ConfidenceLevel
    contributions: dict[str, float] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "score": round(self.score, 4),
            "confidence": self.confidence.value,
            "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
            "skipped_na_criteria": self.skipped,
            "rationale": self.rationale,
        }


def score_to_confidence(score: float) -> ConfidenceLevel:
    """Map a [0,1] composite score to a confidence band.

    Thresholds are intentionally conservative: the burden of proof is on the
    source, so the default (0) is ``UNVERIFIED``.
    """
    if score >= 0.80:
        return ConfidenceLevel.HIGH
    if score >= 0.60:
        return ConfidenceLevel.MEDIUM
    if score >= 0.35:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNVERIFIED


def validate_source(assessment: SourceAssessment) -> ValidationReport:
    """Score an assessment and return a full, auditable report."""
    contributions: dict[str, float] = {}
    skipped: list[str] = []

    active = {
        name: (getattr(assessment, name), weight)
        for name, weight in CRITERIA_WEIGHTS.items()
        if getattr(assessment, name) is not None
    }
    for name in CRITERIA_WEIGHTS:
        if name not in active:
            skipped.append(name)

    if not active:
        return ValidationReport(
            score=0.0,
            confidence=ConfidenceLevel.UNVERIFIED,
            rationale="No criteria supplied; cannot verify — defaulting to UNVERIFIED.",
        )

    total_weight = sum(w for _, w in active.values())
    score = 0.0
    for name, (value, weight) in active.items():
        clamped = max(0.0, min(1.0, float(value)))
        norm_weight = weight / total_weight
        contribution = clamped * norm_weight
        contributions[name] = contribution
        score += contribution

    confidence = score_to_confidence(score)
    rationale = (
        f"Composite score {score:.2f} over {len(active)} active criteria "
        f"({', '.join(sorted(active))}) → {confidence.value.upper()}."
    )
    if skipped:
        rationale += f" N/A (renormalised out): {', '.join(skipped)}."
    if assessment.notes:
        rationale += f" Notes: {assessment.notes}"

    return ValidationReport(
        score=score,
        confidence=confidence,
        contributions=contributions,
        skipped=skipped,
        rationale=rationale,
    )
