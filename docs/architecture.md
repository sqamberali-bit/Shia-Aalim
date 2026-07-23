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

**LLM synthesizer** — composes fluent, *cited* prose from the retrieved
evidence. Select via `make_synthesizer(spec)`:

| spec | class | needs | notes |
|---|---|---|---|
| `none` | — | — | default: extractive only (never writes original prose) |
| `mock` | `MockSynthesizer` | — | deterministic offline; runs/tests the pipeline with no API key |
| `claude:<model>` | `ClaudeSynthesizer` | `[llm]` + `ANTHROPIC_API_KEY` | Anthropic API; uses [`prompts/answer_system.md`](../prompts/answer_system.md) |

The synthesizer is handed the evidence as a numbered `[n]` list and must cite it
with `[n]` markers. **Its output is re-verified before release** by
`grounding/synthesis.py::verify_synthesis`, which rejects prose that (1) cites a
marker outside the evidence (**invented citation**), (2) puts a citation on a
sentence its cited passage doesn't support (**wrong attribution**), or (3) makes
a substantive claim grounded in **no** cited evidence (**hallucination**). On
failure, `AnswerGenerator` **withholds** the prose and falls back to the
extractive, always-cited evidence — the LLM can make an answer readable, never
less grounded.

The entailment decision (2 and 3 above) is a pluggable **`EntailmentJudge`**
(`grounding/entailment.py`), selected with `make_judge(spec)`:

| spec | class | needs |
|---|---|---|
| `lexical` | `LexicalEntailmentJudge` | none — content-overlap proxy (default) |
| `claude:<model>` | `ClaudeEntailmentJudge` | `[llm]` + `ANTHROPIC_API_KEY` |
| `mock` | `MockEntailmentJudge` | none (tests/offline) |

The lexical judge is fast but blunt; a `claude:` judge *complements* it with true
semantic entailment — rescuing paraphrases the lexical gate wrongly rejects and
rejecting same-words/wrong-meaning it wrongly passes (both demonstrated in
`tests/test_entailment.py`). Judges batch all a text's claims into one call and
default to **UNSUPPORTED when unsure**. Pass one via
`AnswerGenerator(..., judge=make_judge("claude:claude-sonnet-5"))` (and likewise
`LectureGenerator`), or `demo.py --judge`.

```python
from shia_aalim.generation import make_synthesizer, AnswerGenerator
gen = AnswerGenerator(retriever, synthesizer=make_synthesizer("claude:claude-sonnet-5"),
                      known_source_ids=known)
answer = gen.answer("What does the Qur'an say about the Ahl al-Bayt?")  # summary verified or withheld
```

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

0. (Optional) **Decompose** a multi-part question into sub-questions
   (`generation/decompose.py`: `rule` heuristics or `claude:<model>`), retrieve
   each part separately, and merge the evidence (dedupe by id, best score) so no
   clause starves. The sub-questions are recorded on `Answer.sub_questions`.
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
