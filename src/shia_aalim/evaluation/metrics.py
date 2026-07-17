"""Evaluation metrics for the continuous-improvement loop.

The charter requires the loop to measure, every iteration:

* **Citation accuracy** — fraction of an answer's citations that are complete
  and point at a passage actually present in the corpus (no invented refs).
* **Hallucination rate** — fraction of claims that fail the grounding check.
* **Retrieval precision / recall** — against a labelled gold set.
* **Source coverage** — fraction of registered sources represented in the index.

These are deliberately simple, transparent and dependency-free so results are
reproducible and trend lines are trustworthy over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..generation.answer import AnswerGenerator
from ..grounding.verify import check_answer_grounding, validate_citations
from ..models import Answer, Document
from ..retrieval.retriever import Retriever


@dataclass
class GoldQuery:
    """A labelled evaluation example.

    ``relevant_doc_ids`` are the document ids that *should* be retrieved for
    ``question``. ``expected_source_ids`` (optional) are sources whose presence
    in the answer indicates good coverage.
    """

    question: str
    relevant_doc_ids: set[str]
    expected_source_ids: set[str] = field(default_factory=set)


@dataclass
class EvaluationSummary:
    n_queries: int
    citation_accuracy: float
    hallucination_rate: float
    precision_at_k: float
    recall_at_k: float
    source_coverage: float
    per_query: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "n_queries": self.n_queries,
            "citation_accuracy": round(self.citation_accuracy, 4),
            "hallucination_rate": round(self.hallucination_rate, 4),
            "precision_at_k": round(self.precision_at_k, 4),
            "recall_at_k": round(self.recall_at_k, 4),
            "source_coverage": round(self.source_coverage, 4),
            "per_query": self.per_query,
        }


def citation_accuracy(
    answer: Answer, corpus: list[Document], known_source_ids: set[str]
) -> float:
    """Fraction of citations that are complete AND resolve in the corpus."""
    citations = answer.all_citations()
    if not citations:
        return 0.0
    checks = validate_citations(
        citations, known_source_ids=known_source_ids, corpus=corpus
    )
    good = sum(1 for c in checks if c.ok)
    return good / len(checks)


def hallucination_rate(answer: Answer, evidence, min_overlap: float = 0.25) -> float:
    """Fraction of claims that fail the lexical grounding threshold."""
    if not answer.claims:
        return 0.0
    report = check_answer_grounding(answer, evidence, min_overlap=min_overlap)
    ungrounded = sum(1 for s in report.claim_scores if s < min_overlap)
    return ungrounded / len(answer.claims)


def retrieval_precision_recall(
    retrieved_ids: list[str], relevant_ids: set[str], k: int
) -> tuple[float, float]:
    """Precision@k and recall@k for one query."""
    top = retrieved_ids[:k]
    if not top:
        return (0.0, 0.0 if relevant_ids else 1.0)
    hits = sum(1 for d in top if d in relevant_ids)
    precision = hits / len(top)
    recall = hits / len(relevant_ids) if relevant_ids else 1.0
    return (precision, recall)


def source_coverage(corpus: list[Document], registered_source_ids: set[str]) -> float:
    """Fraction of registered sources that appear at least once in the corpus."""
    if not registered_source_ids:
        return 0.0
    present = {d.citation.source_id for d in corpus}
    covered = registered_source_ids & present
    return len(covered) / len(registered_source_ids)


def evaluate(
    gold: list[GoldQuery],
    retriever: Retriever,
    corpus: list[Document],
    registered_source_ids: set[str],
    *,
    k: int = 6,
    generator: Optional[AnswerGenerator] = None,
) -> EvaluationSummary:
    """Run the full metric suite over a gold set and return a summary.

    Uses ``generator`` if supplied (to score citation/hallucination on real
    answers); otherwise builds a default extractive generator from ``retriever``.
    """
    gen = generator or AnswerGenerator(retriever, known_source_ids=registered_source_ids)

    precisions: list[float] = []
    recalls: list[float] = []
    cit_accs: list[float] = []
    halluc: list[float] = []
    per_query: list[dict] = []

    for gq in gold:
        results = retriever.retrieve(gq.question, k=k)
        retrieved_ids = [r.document.id for r in results]
        p, r = retrieval_precision_recall(retrieved_ids, gq.relevant_doc_ids, k)
        precisions.append(p)
        recalls.append(r)

        answer = gen.answer(gq.question, k=k)
        ca = citation_accuracy(answer, corpus, registered_source_ids)
        hr = hallucination_rate(answer, results)
        cit_accs.append(ca)
        halluc.append(hr)

        per_query.append(
            {
                "question": gq.question,
                "precision_at_k": round(p, 4),
                "recall_at_k": round(r, 4),
                "citation_accuracy": round(ca, 4),
                "hallucination_rate": round(hr, 4),
                "n_claims": len(answer.claims),
            }
        )

    n = len(gold)
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
    return EvaluationSummary(
        n_queries=n,
        citation_accuracy=mean(cit_accs),
        hallucination_rate=mean(halluc),
        precision_at_k=mean(precisions),
        recall_at_k=mean(recalls),
        source_coverage=source_coverage(corpus, registered_source_ids),
        per_query=per_query,
    )
