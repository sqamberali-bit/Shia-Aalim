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
| Embeddings | `retrieval/embeddings.py` | `HashingEmbedder` (feature hashing) | BGE-M3, E5, Jina, Nomic, OpenAI |
| Vector store | `retrieval/vectorstore.py` | `InMemoryVectorStore` (brute force) | Qdrant, Weaviate, Milvus, Chroma |
| Retrieval | `retrieval/retriever.py` | confidence-aware re-rank + consensus | +reranker (bge-reranker) |
| Grounding | `grounding/verify.py` | lexical overlap + citation checks | + LLM entailment |
| Generation | `generation/` | extractive answer + lecture framework | LLM `Synthesizer` (Claude, …) |
| Evaluation | `evaluation/metrics.py` | gold-set metrics | +human eval, +RAGAS-style |
| Orchestration | `research_loop.py` | bounded logged iterations | scheduler / CI cron |

## Pluggable interfaces

**Embeddings** — implement `EmbeddingProvider` (`dim`, `embed`, `embed_batch`).
Example with `sentence-transformers`:

```python
class BGEEmbedder:
    def __init__(self, model="BAAI/bge-m3"):
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer(model); self.dim = self.m.get_sentence_embedding_dimension()
    def embed(self, text): return self.m.encode(text, normalize_embeddings=True).tolist()
    def embed_batch(self, texts): return self.m.encode(list(texts), normalize_embeddings=True).tolist()
```

Pass it to `InMemoryVectorStore(BGEEmbedder())` or a real store implementing the
`VectorStore` protocol (`add`, `search`, `__len__`).

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
