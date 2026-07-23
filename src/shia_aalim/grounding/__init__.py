"""Grounding & hallucination prevention: verify that answers are supported by
retrieved evidence and carry valid, verifiable citations before they are shown."""

from .synthesis import SynthesisReport, verify_synthesis
from .verify import (
    CitationCheck,
    GroundingReport,
    check_answer_grounding,
    citation_exists_in_corpus,
    validate_citations,
)

__all__ = [
    "CitationCheck",
    "GroundingReport",
    "check_answer_grounding",
    "citation_exists_in_corpus",
    "validate_citations",
    "SynthesisReport",
    "verify_synthesis",
]
