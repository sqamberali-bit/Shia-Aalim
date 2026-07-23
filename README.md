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

## The corpus is external

The built knowledge base (~350 MB, 122k docs) is **derived data and lives outside
git** — see [`docs/data-management.md`](docs/data-management.md). A fresh checkout
ships a small **sample** so everything runs; get the full corpus by rebuilding
from sources (`scripts/ingest.py`) or fetching a bundle:

```bash
python scripts/fetch_data.py --status                  # what's present vs the manifest
python scripts/fetch_data.py --from-bundle <url|path>  # fetch + verify + extract a snapshot
```

## Quick start (no dependencies required)

The core runs on the Python standard library alone. These work on the committed
sample out of the box:

```bash
# Answer a question from the knowledge base (evidence + citations only)
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
- **Retrieval** (`retrieval/`) — pluggable embeddings (dependency-free `hashing`
  and IDF-weighted `tfidf`; semantic `st:BAAI/bge-m3` where a model is reachable)
  + in-memory or on-disk-cached vector store; confidence-aware, type-filtered
  ranking and multi-source consensus. Compare embedders with
  `scripts/benchmark_retrieval.py`.
- **Grounding** (`grounding/`) — citation completeness, source-existence and
  passage-existence checks, plus lexical answer-grounding — the hallucination
  firewall.
- **Generation** (`generation/`) — extractive-by-default answering and the full
  11-section lecture framework; an optional LLM synthesizer (Claude via
  `make_synthesizer`) composes cited prose that is **re-verified** before
  release — invented citations / wrong attribution / hallucinated sentences are
  rejected and the prose withheld (`grounding/synthesis.py`).
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
data/manifest.yaml           Corpus manifest — what's in the (external) corpus + how to rebuild/fetch
src/shia_aalim/ingestion/adapters/  Verified-source adapters (Qur'an, ThaqalaynData hadith, Shiavault prose)
data/knowledge/              Built corpus (external/git-ignored) + a small committed sample/
prompts/                     System prompts encoding the charter for any LLM synthesizer
templates/                   Lecture template
scripts/                     demo.py, run_research_loop.py, ingest.py, fetch_data.py
tests/                       Test suite (78 tests, stdlib-only) + fixtures
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

**Iteration 2 (in progress): real corpora ingested.** The knowledge base now
holds the complete Qur'an (canonical Uthmani Arabic + Ali Quli Qarai
translation, 6236 verses) and **42,330 Twelver hadith** — the **complete Four
Books** and Nahj al-Balāgha: al-Kāfī in full (all 8 volumes, 16,267), Man Lā
Yaḥḍuruhu al-Faqīh (6382), Tahdhīb al-Aḥkām (13,201), al-Istibṣār (4220), and
Nahj al-Balāgha (2260). That is **48,566 cited documents.** Each hadith carries
its Arabic *matn*, an attributed translation, and — where the source records
them — **rijāl gradings** (Majlisī, Behbudi) carried through verbatim, so weak
narrations are flagged, never asserted. All from verified, permissively-licensed
GitHub datasets ([fawazahmed0/quran-api](https://github.com/fawazahmed0/quran-api),
CC0 [ThaqalaynData](https://github.com/narmafraz/ThaqalaynData)) via tested
adapters (`src/shia_aalim/ingestion/adapters/`, `scripts/ingest.py`).

On top of that, further al-Saduq/al-Mufid hadith collections (al-Khiṣāl, both
Amālī, ʿUyūn Akhbār al-Riḍā, al-Tawḥīd) and a **prose tier** — Sīra, Maqtal
al-Husayn, Kitāb al-Irshād, and al-Ṣaḥīfa al-Sajjādiyya (from the
[Shiavault](https://github.com/shiavault/shiavault-library) al-islam.org mirror,
chapter-level citations at *medium* confidence). The **complete 101-volume Biḥār
al-Anwār** (~43k page-documents) is ingested from hubeali English text-layer PDFs
(PyMuPDF adapter), and the **complete 40-volume Tafsīr al-Mīzān** (18,125
sections, Tawheed Institute English edition) from uploaded OCR'd text (plain-text
adapter). These prose tiers are clearly a lower evidence tier than the graded
hadith corpora. **The corpus is now 121,871 cited documents across 27 works** —
all external to git (see [`docs/data-management.md`](docs/data-management.md)).

Integrity holds on the real corpus (citation accuracy 1.0, hallucination 0.0,
verified by `tests/test_corpus_integrity.py`). The measured recall@5 ≈ 0.40 with
the lexical baseline is the honest signal driving the next step: a semantic
embedder (BGE-M3) behind the existing `EmbeddingProvider` interface, then an LLM
synthesizer. See [`docs/roadmap.md`](docs/roadmap.md).

## License

MIT (code). Ingested texts retain their own licenses — see the source registry.
