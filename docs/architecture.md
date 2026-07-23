# Architecture

Shia-Aalim is a RAG (retrieval-augmented generation) system whose every layer is
subordinate to the [Operating Charter](../AGENT.md). This document describes the
layers, the pluggable interfaces, and how to swap the stdlib reference
implementations for production components.

## Design goals

1. **Integrity over fluency.** The default path is *extractive* — answers are
   cited passages. Fluent prose is opt-in (an LLM `Synthesizer`) and is
   re-verified before release.
2. **Zero-install core.** The model, validation, grounding, evaluation and a
   working retrieval pipeline run on the Python standard library, so the
   integrity guarantees are always testable.
3. **Pluggable everything.** Embeddings, vector store, LLM and document loaders
   sit behind small protocols; production backends drop in without touching the
   guarantees.

## Layered view

| Layer | Module | Reference impl (stdlib) | Production options |
|---|---|---|---|
| Domain model | `models.py` | dataclasses + enums | — |
| Source validation | `source_validation.py` | weighted scoring | human review workflow |
| Ingestion | `ingestion/` | Arabic normaliser, JSONL/text loaders | pypdf, ebooklib, bs4, OCR |
| Source adapters | `ingestion/adapters/` | Qur'an (fawazahmed0), hadith (CC0 ThaqalaynData) w/ gradings | add adapters per upstream |
| Embeddings | `retrieval/embeddings.py` | `HashingEmbedder`, `TfidfHashingEmbedder` (IDF-weighted, fit on corpus — the default) | `SentenceTransformerEmbedder` (BGE-M3/E5/Jina) via `st:<model>` |
| Vector store | `retrieval/vectorstore.py`, `retrieval/index.py` | `InMemoryVectorStore`, `PersistentVectorStore` (embed once, cache on disk) | Qdrant, Weaviate, Milvus, Chroma |
| Retrieval | `retrieval/retriever.py` | confidence-aware re-rank + consensus | +reranker (bge-reranker) |
| Grounding | `grounding/verify.py` | lexical overlap + citation checks | + LLM entailment |
| Generation | `generation/` | extractive answer + lecture framework | LLM `Synthesizer` (Claude, …) |
| Evaluation | `evaluation/metrics.py` | gold-set metrics | +human eval, +RAGAS-style |
| Orchestration | `research_loop.py` | bounded logged iterations | scheduler / CI cron |

## Pluggable interfaces

**Embeddings** — three implementations of `EmbeddingProvider` ship in-box; pick
via `make_embedder(spec)`:

| spec | class | deps | when |
|---|---|---|---|
| `hashing` | `HashingEmbedder` | none | baseline / lower bound |
| `tfidf` | `TfidfHashingEmbedder` | none | **default** — IDF-weighted, fit on the corpus; runs anywhere |
| `st:BAAI/bge-m3` | `SentenceTransformerEmbedder` | `[embeddings]` + model | semantic; best quality where the model is reachable |

```python
from shia_aalim.retrieval import make_embedder, build_persistent_index
emb = make_embedder("st:BAAI/bge-m3")          # or "tfidf" (default), "hashing"
store = build_persistent_index(docs, emb, "data/index/vectors.pkl")  # embed once, reuse
retriever = Retriever(store)
```

`TfidfHashingEmbedder` roughly **doubles recall** over `hashing` on the Qur'an
gold set (measure with `scripts/benchmark_retrieval.py`); `st:` closes the
remaining *semantic* gaps (synonyms across translations). Because BGE-M3 weights
download from the HuggingFace Hub, run the `st:` path where the Hub — or a
pre-downloaded model — is reachable. `PersistentVectorStore` caches vectors on
disk keyed by an embedder signature, so a 101k-doc corpus embeds once.

**LLM synthesizer** — implement `Synthesizer.synthesize(question, evidence) ->
str`, using [`prompts/answer_system.md`](../prompts/answer_system.md) as the
system prompt and passing only the retrieved evidence. The result is still run
through `check_answer_grounding`, so a synthesizer that drifts off-evidence is
caught, not trusted.

**LLM synthesizer** — implement `Synthesizer.synthesize(question, evidence) ->
str`, using [`prompts/answer_system.md`](../prompts/answer_system.md) as the
system prompt and passing only the retrieved evidence. The result is still run
through `check_answer_grounding`, so a synthesizer that drifts off-evidence is
caught, not trusted.

## Component selection (benchmark before committing)

The charter asks for continuous comparison. Recommended starting points, to be
validated with `evaluation/` on a domain gold set:

- **LLM:** Claude (strong instruction-following & citation discipline) for
  synthesis; keep a local option (Qwen/Llama) for cost/offline. Evaluate Arabic
  understanding and citation reliability, not just fluency.
- **Embeddings:** BGE-M3 (multilingual, strong on Arabic) as the default to
  beat; benchmark E5-multilingual and Jina-v3.
- **Vector DB:** Qdrant (self-hostable, good filtering) for production;
  `InMemoryVectorStore` for dev/CI.
- **RAG orchestration:** the loop here is deliberately explicit; LangGraph or
  LlamaIndex can host it if you need their tooling, but the integrity checks must
  remain in the critical path.

## Data flow (one query)

1. Normalise + embed the query.
2. Vector search (over-sampled) → filter by evidence type + min confidence →
   re-rank with confidence bonus → apply similarity floor.
3. If nothing clears the floor → **refuse** (no answer beyond evidence).
4. Build claims from passages (extractive) and/or synthesise prose (LLM).
5. Ground-check every claim + validate every citation.
6. Attach caveats for any low-confidence evidence, gaps, or disputes.

## Configuration

`config/settings.example.yaml` documents the knobs (embedding model, store
backend, similarity floor, k, grounding threshold, LLM provider). Copy to
`config/settings.yaml` (git-ignored) and fill in provider keys via environment
variables — never commit secrets.
