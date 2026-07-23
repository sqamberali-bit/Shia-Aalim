# Benchmarks — measuring the semantic lift

The charter says improvements must be *measured, not asserted*. This page records
what has actually been run, and gives the exact commands to fill in the rest in
an environment that can reach the models.

Two harnesses:

* `scripts/benchmark_retrieval.py` — retrieval only: recall@k / MRR per embedder.
* `scripts/eval_end_to_end.py` — the full answer path (retrieval → synthesis →
  grounding + entailment verification), per configuration.

Both take `--out <path>` to append a JSON record of the run.

## Gold set

A small labelled Qur'an set (query → the verse id that should be retrieved),
defined in the scripts. It targets cross-translation vocabulary gaps on purpose
(e.g. "self-subsisting" vs the Qarai "All-sustainer") — exactly where lexical
retrieval breaks and semantics should win.

## Results — retrieval (measured 2026-07, `quran.jsonl`, 6236 docs, k=10)

| embedder | recall@10 | MRR | hits |
|---|---|---|---|
| `hashing` (blind feature hashing) | 0.333 | 0.125 | 2/6 |
| `tfidf` (IDF-weighted, **current default**) | **0.667** | **0.458** | 4/6 |
| `st:BAAI/bge-m3` (semantic) | _pending — see below_ | | |

**The TF-IDF default roughly doubles recall over the hashing baseline** — a real,
reproducible, dependency-free win. The remaining 2/6 misses are pure
cross-translation synonymy, which is what BGE-M3 is expected to close.

## Results — end-to-end (measured 2026-07, same corpus, mock synth + lexical judge)

| embedder | recall@10 | citation_accuracy | hallucination | synth_kept_rate\* |
|---|---|---|---|---|
| `hashing` | 0.333 | 1.000 | 0.000 | — |
| `tfidf` | 0.667 | 1.000 | 0.000 | — |

Citation accuracy is 1.0 and hallucination 0.0 in both — the grounding firewall
holds regardless of embedder. \*`synth_kept_rate` is only meaningful with a real
synthesizer (the offline mock just quotes evidence), so it is left out here.

## BGE-M3 + Claude — PENDING (not run in this environment)

**These rows are intentionally blank. They have NOT been run and no numbers are
invented.** The hosted sandbox this project was built in **blocks the
HuggingFace Hub** (so BGE-M3 weights can't download) and has **no
`ANTHROPIC_API_KEY`** (so Claude can't be called). Verified: `huggingface.co` →
HTTP 403; key unset.

To produce the semantic-lift numbers, run — in any environment with HuggingFace
access + a key:

```bash
pip install -e ".[embeddings,llm]"          # sentence-transformers + torch + anthropic
export ANTHROPIC_API_KEY=sk-...
# (re)build the corpus first if needed: scripts/ingest.py  (see docs/data-management.md)

# retrieval lift (tfidf vs BGE-M3):
python scripts/benchmark_retrieval.py \
    --embedders tfidf,st:BAAI/bge-m3 \
    --out research/benchmarks/retrieval.jsonl

# full pipeline lift (add Claude synthesis + Claude entailment judge):
python scripts/eval_end_to_end.py \
    --embedder tfidf,st:BAAI/bge-m3 \
    --synthesize claude:claude-sonnet-5 \
    --judge claude:claude-sonnet-5 \
    --out research/benchmarks/e2e.jsonl
```

Then paste the printed table into the rows above (and commit the `--out` JSONL if
you want the raw record). The first BGE-M3 run downloads the model (~2 GB) once;
wrap it in `PersistentVectorStore` so the corpus embeds only once.

## Notes

* Recall on the tiny 6-query gold set is coarse; grow the gold set (more queries,
  hadith/tafsīr targets) before drawing strong conclusions — the harness takes
  any corpus shard via `--corpus`.
* `synth_kept_rate` with a real Claude synthesizer measures how often its prose
  passes verification — a direct read on synthesis grounding quality.
