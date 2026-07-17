# Shia-Aalim (شیعہ عالِم)

**An evidence-first research & lecture assistant for Twelver (Ithnā ʿAsharī)
Shia Islam.**

Shia-Aalim is a retrieval-augmented knowledge system built around one
non-negotiable principle:

> **No citation = not a fact.**

It answers Islamic research questions, prepares lecture / majlis / khuṭba
material, and cross-references Qurʾān, Hadith, Tafsīr, history and scholarly
opinion — always with exact, verifiable references, explicit confidence levels,
and honest flagging of weak or disputed material. It is designed **not** to
hallucinate: in its default configuration it never writes a sentence that is not
a cited passage, and it refuses to answer beyond the evidence it holds.

This repository is the foundation of that system: the domain model, the
source-validation and grounding layers, a working (dependency-free) retrieval
pipeline, a lecture-generation framework, an evaluation harness, and the
continuous research/improvement loop — all governed by the
[Operating Charter (`AGENT.md`)](AGENT.md).

---

## Why it exists

The [landscape research](docs/landscape-existing-solutions.md) (verified
2026-07) found only a couple of closed, purpose-built Twelver systems, and **no
open system that advertises verifiable lecture/khuṭba preparation**. Shia-Aalim
targets exactly that gap, with scholarly integrity as the first requirement, not
an afterthought.

## Quick start (no dependencies required)

The core runs on the Python standard library alone.

```bash
# Answer a question from the seed knowledge base (evidence + citations only)
python scripts/demo.py "purification of the Ahl al-Bayt"

# Draft a structured lecture outline
python scripts/demo.py --lecture "The purification of the Ahl al-Bayt"

# Run one iteration of the evaluation / improvement loop
python scripts/run_research_loop.py --iterations 1

# Run the tests
pip install pytest         # only dependency needed for tests
python -m pytest -q
```

Optional providers (real embeddings, vector DBs, LLM synthesis, PDF/EPUB
ingestion) install via extras — see [`docs/architecture.md`](docs/architecture.md):

```bash
pip install -e ".[ingest,embeddings,llm]"
```

## How it works

```
 sources ──► ingestion ──► Documents (+citations) ──► index ──► retrieval
 (registry)   normalise      confidence-scored                    │
                                                                  ▼
                                          grounding / citation validation
                                                                  │
                                                                  ▼
                                     evidence-first Answer / Lecture outline
```

- **Domain model** (`models.py`) — `Source`, `Citation`, `Document`, `Claim`,
  `Answer`, with `ConfidenceLevel`, `EvidenceType`, `ViewStatus`, `HadithGrade`.
  Encodes the "no citation = not a fact" invariant.
- **Source validation** (`source_validation.py`) — transparent, weighted scoring
  of a source into a confidence band; every decision is explained.
- **Ingestion** (`ingestion/`) — Arabic normalisation (diacritic-insensitive
  matching, alef/yaa/taa/Persian folding) and pluggable loaders
  (text/HTML/PDF/EPUB/JSONL).
- **Retrieval** (`retrieval/`) — pluggable embeddings + vector store with a
  stdlib reference implementation; confidence-aware, type-filtered ranking and
  multi-source consensus.
- **Grounding** (`grounding/`) — citation completeness, source-existence and
  passage-existence checks, plus lexical answer-grounding — the hallucination
  firewall.
- **Generation** (`generation/`) — extractive-by-default answering and the full
  11-section lecture framework; an optional LLM `Synthesizer` composes prose but
  its output is re-verified before release.
- **Evaluation** (`evaluation/`) — citation accuracy, hallucination rate,
  retrieval precision/recall, source coverage, over a gold set.
- **Research loop** (`research_loop.py`) — bounded, logged iterations that
  re-index, evaluate, and emit improvement recommendations.

## Repository layout

```
AGENT.md                     Operating charter (the constitution)
docs/                        Architecture, validation, ingestion, citation, landscape, roadmap
src/shia_aalim/              The package (model, ingestion, retrieval, grounding, generation, eval, loop)
data/schema/                 JSON Schemas for documents, citations, sources
data/sources/registry.yaml   Registered, citable sources with confidence
data/knowledge/              Ingested knowledge (.jsonl) — seed data is clearly labelled
prompts/                     System prompts encoding the charter for any LLM synthesizer
templates/                   Lecture template
scripts/                     demo.py, run_research_loop.py
tests/                       Test suite (32 tests, stdlib-only)
```

## Scholarly integrity & scope

- **Sect scope.** This is a *Twelver Shia* system. Sources are labelled by sect;
  Sunni corpora (e.g. sunnah.com) are noted as such and not silently blended.
- **Seed data is illustrative.** The bundled Qurʾān seed carries verse
  translations (Shakir via Tanzil) with exact references and `medium` confidence
  pending verification; the hadith seed contains **no narrations**, only a
  labelled schema placeholder. Real content is added via validated ingestion.
- **Not a marjaʿ.** Shia-Aalim is a research aid, not a source of religious
  rulings. For fatwā and taqlīd, consult a qualified marjaʿ.
- **Licensing.** Respect each source's terms (attribution, non-commercial,
  caching limits) — see the landscape doc's licensing notes before ingesting.

## Status & roadmap

This is **iteration 1**: a complete, tested, runnable foundation. The immediate
next step is validated ingestion of real corpora (ThaqalaynAPI, Tanzil/QUL,
Shiavault, Hubeali) and wiring a semantic embedding model + LLM synthesizer
behind the existing interfaces. See [`docs/roadmap.md`](docs/roadmap.md).

## License

MIT (code). Ingested texts retain their own licenses — see the source registry.
