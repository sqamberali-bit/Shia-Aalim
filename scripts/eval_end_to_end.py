#!/usr/bin/env python3
"""End-to-end pipeline evaluation — measure a full configuration on a gold set.

Runs the whole answer path (embedder → retrieval → optional LLM synthesis →
grounding + entailment verification) for one or more configurations and reports
comparable metrics, so the *semantic lift* of upgrading the embedder (tfidf →
BGE-M3) and/or the synthesizer/judge (mock → Claude) is measured, not asserted.

    # runs anywhere (dependency-free):
    python scripts/eval_end_to_end.py --embedder tfidf --synthesize mock --judge lexical

    # the real semantic config (needs [embeddings]+[llm], HuggingFace + a key):
    python scripts/eval_end_to_end.py --embedder st:BAAI/bge-m3 \
        --synthesize claude:claude-sonnet-5 --judge claude:claude-sonnet-5 --out research/benchmarks/e2e.jsonl

Metrics (per config, over the gold set):
  recall@k          — did retrieval surface the labelled relevant verse?
  citation_accuracy — fraction of answer citations that are complete + resolve
  hallucination     — fraction of claims failing the grounding check
  synth_kept_rate   — fraction of answers whose LLM summary passed verification
                      (0 with --synthesize none)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.evaluation.metrics import (  # noqa: E402
    citation_accuracy,
    hallucination_rate,
    retrieval_precision_recall,
)
from shia_aalim.generation.answer import AnswerGenerator  # noqa: E402
from shia_aalim.generation.decompose import make_decomposer  # noqa: E402
from shia_aalim.generation.synthesizer import make_synthesizer  # noqa: E402
from shia_aalim.grounding.entailment import make_judge  # noqa: E402
from shia_aalim.ingestion.loaders import load_documents_jsonl  # noqa: E402
from shia_aalim.retrieval.embeddings import fit_if_needed, make_embedder  # noqa: E402
from shia_aalim.retrieval.retriever import Retriever  # noqa: E402
from shia_aalim.retrieval.vectorstore import InMemoryVectorStore  # noqa: E402
from shia_aalim.sources import load_registry_ids  # noqa: E402

GOLD = [
    ("purification of the People of the House", "quran-33-33"),
    ("love for the near relatives kinship", "quran-42-23"),
    ("this day I have perfected your religion", "quran-5-3"),
    ("there is no god but He the Living the self-subsisting", "quran-2-255"),
    ("your guardian is only Allah and His messenger", "quran-5-55"),
    ("the mutual cursing prayer sons and women", "quran-3-61"),
]


def run_config(embedder_spec, synth_spec, judge_spec, decompose_spec, docs, known, k):
    emb = make_embedder(embedder_spec)
    fit_if_needed(emb, [d.text for d in docs])
    store = InMemoryVectorStore(emb)
    store.add(docs)
    gen = AnswerGenerator(
        Retriever(store),
        synthesizer=make_synthesizer(synth_spec),
        judge=make_judge(judge_spec),
        decomposer=make_decomposer(decompose_spec),
        known_source_ids=known,
    )
    recalls, cit_accs, hallucs, kept = [], [], [], []
    for query, gid in GOLD:
        ids = [r.document.id for r in gen.retriever.retrieve(query, k=k)]
        recalls.append(retrieval_precision_recall(ids, {gid}, k)[1])
        ans = gen.answer(query, k=k)
        cit_accs.append(citation_accuracy(ans, docs, known))
        hallucs.append(hallucination_rate(ans, gen.retriever.retrieve(query, k=k)))
        kept.append(1.0 if ans.summary else 0.0)
    n = len(GOLD)
    mean = lambda xs: round(sum(xs) / n, 3)  # noqa: E731
    return {
        "embedder": embedder_spec, "synthesize": synth_spec, "judge": judge_spec,
        f"recall@{k}": mean(recalls), "citation_accuracy": mean(cit_accs),
        "hallucination": mean(hallucs), "synth_kept_rate": mean(kept),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--embedder", default="tfidf", help="embedder spec, or comma-separated list to compare")
    p.add_argument("--synthesize", default="none")
    p.add_argument("--judge", default="lexical")
    p.add_argument("--decompose", default="none")
    p.add_argument("--corpus", default=str(ROOT / "data/knowledge/quran/quran.jsonl"))
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--out", metavar="PATH")
    args = p.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        sys.exit(f"corpus not found: {corpus} (build with scripts/ingest.py, or use the sample)")
    docs = load_documents_jsonl(corpus)
    known = load_registry_ids(ROOT / "data" / "sources" / "registry.yaml")
    print(f"Corpus: {corpus.name} ({len(docs)} docs) | gold: {len(GOLD)} | k={args.k}\n")

    rows = []
    for spec in [s.strip() for s in args.embedder.split(",") if s.strip()]:
        try:
            rows.append(run_config(spec, args.synthesize, args.judge, args.decompose, docs, known, args.k))
        except Exception as exc:  # noqa: BLE001 - e.g. missing model/key: report, continue
            print(f"  [skip] {spec}: {exc}")

    if rows:
        cols = list(rows[0].keys())
        w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
        print("  ".join(c.ljust(w[c]) for c in cols))
        print("  ".join("-" * w[c] for c in cols))
        for r in rows:
            print("  ".join(str(r[c]).ljust(w[c]) for c in cols))
    if args.out and rows:
        import datetime as _dt
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with Path(args.out).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"run_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                 "corpus": corpus.name, "n_docs": len(docs), "k": args.k, "results": rows},
                ensure_ascii=False) + "\n")
        print(f"\nrecorded -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
