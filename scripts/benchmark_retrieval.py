#!/usr/bin/env python3
"""Benchmark retrieval embedders on a labelled gold set.

Compares embedders (dependency-free baselines and, where available, a semantic
model) on recall@k / MRR so retrieval upgrades are measured, not assumed — the
charter's evaluation discipline.

    # default: compare hashing vs tfidf over the Qur'an
    python scripts/benchmark_retrieval.py

    # add the semantic model (needs `pip install shia-aalim[embeddings]` + weights)
    python scripts/benchmark_retrieval.py --embedders hashing,tfidf,st:BAAI/bge-m3

    # benchmark over a different corpus file
    python scripts/benchmark_retrieval.py --corpus data/knowledge/hadith/al-kafi-tawhid.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.evaluation.metrics import retrieval_precision_recall  # noqa: E402
from shia_aalim.ingestion.loaders import load_documents_jsonl  # noqa: E402
from shia_aalim.retrieval.embeddings import fit_if_needed, make_embedder  # noqa: E402
from shia_aalim.retrieval.retriever import Retriever  # noqa: E402
from shia_aalim.retrieval.vectorstore import InMemoryVectorStore  # noqa: E402

# A small Qur'an gold set (query -> the verse id that should be retrieved).
DEFAULT_GOLD = [
    ("purification of the People of the House", "quran-33-33"),
    ("love for the near relatives kinship", "quran-42-23"),
    ("this day I have perfected your religion", "quran-5-3"),
    ("there is no god but He the Living the self-subsisting", "quran-2-255"),
    ("your guardian is only Allah and His messenger", "quran-5-55"),
    ("the mutual cursing prayer sons and women", "quran-3-61"),
]


def evaluate_embedder(spec: str, docs, gold, k: int) -> dict:
    emb = make_embedder(spec)
    fit_if_needed(emb, [d.text for d in docs])
    store = InMemoryVectorStore(emb)
    store.add(docs)
    retriever = Retriever(store)

    recalls, precisions, rr = [], [], []
    for query, gid in gold:
        ids = [r.document.id for r in retriever.retrieve(query, k=k)]
        p, r = retrieval_precision_recall(ids, {gid}, k)
        precisions.append(p)
        recalls.append(r)
        rr.append(1.0 / (ids.index(gid) + 1) if gid in ids else 0.0)
    n = len(gold)
    return {
        "embedder": spec,
        "dim": getattr(emb, "dim", "?"),
        f"recall@{k}": round(sum(recalls) / n, 3),
        "mrr": round(sum(rr) / n, 3),
        "hits": f"{sum(1 for x in recalls if x > 0)}/{n}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedders", default="hashing,tfidf",
                        help="comma-separated specs (e.g. hashing,tfidf,st:BAAI/bge-m3)")
    parser.add_argument("--corpus", default=str(ROOT / "data/knowledge/quran/quran.jsonl"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out", metavar="PATH",
                        help="append the results as a JSON line (e.g. research/benchmarks/retrieval.jsonl)")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        sys.exit(f"corpus not found: {corpus}\n"
                 "Build it (scripts/ingest.py) or point --corpus at an existing shard "
                 "(the committed sample is data/knowledge/sample/sample.jsonl).")
    docs = load_documents_jsonl(corpus)
    print(f"Corpus: {corpus.name} ({len(docs)} docs) | gold: {len(DEFAULT_GOLD)} queries | k={args.k}\n")

    rows = []
    for spec in [s.strip() for s in args.embedders.split(",") if s.strip()]:
        try:
            rows.append(evaluate_embedder(spec, docs, DEFAULT_GOLD, args.k))
        except Exception as exc:  # noqa: BLE001 - report and continue (e.g. missing model)
            print(f"  [skip] {spec}: {exc}")

    if rows:
        cols = list(rows[0].keys())
        widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
        print("  ".join(c.ljust(widths[c]) for c in cols))
        print("  ".join("-" * widths[c] for c in cols))
        for r in rows:
            print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))

    if args.out and rows:
        import datetime as _dt
        record = {
            "run_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "corpus": corpus.name,
            "n_docs": len(docs),
            "k": args.k,
            "n_gold": len(DEFAULT_GOLD),
            "results": rows,
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\nrecorded -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
