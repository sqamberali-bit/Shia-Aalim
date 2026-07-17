"""Evaluation: the metrics the charter's continuous loop must measure —
citation accuracy, hallucination rate, retrieval precision/recall, source
coverage — plus a small gold-set harness to compute them reproducibly."""

from .metrics import (
    EvaluationSummary,
    GoldQuery,
    citation_accuracy,
    evaluate,
    hallucination_rate,
    retrieval_precision_recall,
    source_coverage,
)

__all__ = [
    "GoldQuery",
    "EvaluationSummary",
    "citation_accuracy",
    "hallucination_rate",
    "retrieval_precision_recall",
    "source_coverage",
    "evaluate",
]
