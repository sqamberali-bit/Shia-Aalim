"""The continuous research & self-improvement loop.

The charter describes an infinite ``LOOP FOREVER``. In practice an autonomous
agent runs in *bounded, logged iterations* — each iteration is a resumable unit
of work that leaves an auditable trail, so progress survives restarts and every
change is reviewable. This module implements one such iteration and a small
driver to run N of them.

An iteration does NOT invent content. It:

1. Loads the knowledge corpus and source registry from disk.
2. (Re)builds the retrieval index.
3. Runs the evaluation suite over the gold set.
4. Compares metrics against the previous iteration.
5. Emits *recommendations* (never silent changes) for a human/agent to action.
6. Appends a structured log entry.

Source *discovery* (finding new repositories/datasets) is intentionally a
human-in-the-loop step here: candidate sources are recorded in the registry with
``confidence: unverified`` and only promoted after passing
:mod:`shia_aalim.source_validation`. The loop reports coverage gaps; it does not
auto-ingest unvetted material.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .evaluation.metrics import EvaluationSummary, GoldQuery, evaluate
from .ingestion.loaders import iter_knowledge_dir
from .models import ConfidenceLevel, Document
from .retrieval.embeddings import TfidfHashingEmbedder, fit_if_needed
from .retrieval.retriever import Retriever
from .retrieval.vectorstore import InMemoryVectorStore


@dataclass
class LoopConfig:
    knowledge_dir: Path
    registry_source_ids: set[str]
    gold: list[GoldQuery]
    embedding_dim: int = 512
    k: int = 6
    log_path: Optional[Path] = None


@dataclass
class IterationReport:
    iteration: int
    n_documents: int
    metrics: EvaluationSummary
    recommendations: list[str] = field(default_factory=list)
    deltas: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "iteration": self.iteration,
            "n_documents": self.n_documents,
            "metrics": self.metrics.as_dict(),
            "deltas": {k: round(v, 4) for k, v in self.deltas.items()},
            "recommendations": self.recommendations,
        }


def build_index(
    docs: list[Document],
    *,
    embedder: Optional[object] = None,
    dim: int = 2048,
) -> Retriever:
    """Embed and index documents into a fresh in-memory retriever.

    Defaults to the dependency-free IDF-weighted embedder, fit on this corpus
    (a solid, runnable retrieval upgrade over blind hashing). Pass ``embedder``
    (e.g. a :class:`SentenceTransformerEmbedder`, or ``make_embedder("st:...")``)
    to use a semantic model instead.
    """
    if embedder is None:
        embedder = TfidfHashingEmbedder(dim=dim)
    fit_if_needed(embedder, [d.text for d in docs])
    store = InMemoryVectorStore(embedder)
    store.add(docs)
    return Retriever(store)


def _recommendations(
    summary: EvaluationSummary,
    docs: list[Document],
    registry_ids: set[str],
) -> list[str]:
    """Turn metrics into concrete, low-risk improvement suggestions."""
    recs: list[str] = []

    if summary.source_coverage < 1.0:
        present = {d.citation.source_id for d in docs}
        missing = sorted(registry_ids - present)
        if missing:
            recs.append(
                f"Coverage gap: {len(missing)} registered source(s) have no ingested "
                f"documents — {', '.join(missing[:8])}"
                + ("…" if len(missing) > 8 else "")
                + ". Prioritise ingestion (see docs/landscape-existing-solutions.md)."
            )

    if summary.recall_at_k < 0.7 and summary.n_queries:
        recs.append(
            f"Recall@{summary.n_queries} is {summary.recall_at_k:.2f} (<0.70). "
            "Consider a stronger embedding model (BGE-M3/E5) or chunk-size tuning."
        )
    if summary.citation_accuracy < 0.95 and summary.n_queries:
        recs.append(
            f"Citation accuracy {summary.citation_accuracy:.2f} (<0.95). Audit "
            "incomplete/unresolved citations before exposing answers as fact."
        )
    if summary.hallucination_rate > 0.0:
        recs.append(
            f"Hallucination rate {summary.hallucination_rate:.2f} (>0). Tighten "
            "grounding threshold or add an LLM entailment check."
        )

    unverified = sum(1 for d in docs if d.confidence is ConfidenceLevel.UNVERIFIED)
    if unverified:
        recs.append(
            f"{unverified} ingested document(s) are UNVERIFIED. Run source "
            "validation and re-grade before citing them as established."
        )
    if not recs:
        recs.append("All tracked metrics within target. Expand gold set to keep raising the bar.")
    return recs


def run_iteration(
    config: LoopConfig,
    iteration: int,
    *,
    previous: Optional[EvaluationSummary] = None,
) -> IterationReport:
    """Execute a single loop iteration and (optionally) append a log entry."""
    docs = list(iter_knowledge_dir(config.knowledge_dir))
    retriever = build_index(docs, dim=config.embedding_dim)
    summary = evaluate(
        config.gold, retriever, docs, config.registry_source_ids, k=config.k
    )

    deltas: dict[str, float] = {}
    if previous is not None:
        deltas = {
            "citation_accuracy": summary.citation_accuracy - previous.citation_accuracy,
            "hallucination_rate": summary.hallucination_rate - previous.hallucination_rate,
            "precision_at_k": summary.precision_at_k - previous.precision_at_k,
            "recall_at_k": summary.recall_at_k - previous.recall_at_k,
            "source_coverage": summary.source_coverage - previous.source_coverage,
        }

    report = IterationReport(
        iteration=iteration,
        n_documents=len(docs),
        metrics=summary,
        recommendations=_recommendations(summary, docs, config.registry_source_ids),
        deltas=deltas,
    )

    if config.log_path is not None:
        config.log_path.parent.mkdir(parents=True, exist_ok=True)
        with config.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.as_dict(), ensure_ascii=False) + "\n")

    return report


def run_loop(config: LoopConfig, *, iterations: int = 1) -> list[IterationReport]:
    """Run a bounded number of iterations, carrying metrics forward for deltas."""
    reports: list[IterationReport] = []
    previous: Optional[EvaluationSummary] = None
    for i in range(1, iterations + 1):
        report = run_iteration(config, i, previous=previous)
        reports.append(report)
        previous = report.metrics
    return reports
