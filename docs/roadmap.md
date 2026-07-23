# Roadmap

The charter describes a system that improves continuously. This roadmap tracks
what exists and what each future iteration should add. It is itself an artefact
the research loop updates.

## Iteration 1 — Foundation (this repository) ✅

- [x] Domain model enforcing "no citation = not a fact" + confidence + view status
- [x] Source-validation framework (weighted, auditable, N/A-aware)
- [x] Arabic normalisation (diacritic-insensitive, alef/yaa/taa/Persian folding)
- [x] Pluggable ingestion loaders (text/HTML/PDF/EPUB/JSONL) + chunking + dedupe
- [x] Pluggable embeddings + vector store (stdlib reference impls)
- [x] Confidence-aware, type-filtered retrieval + multi-source consensus
- [x] Grounding firewall: similarity floor, source/citation/passage checks, overlap
- [x] Extractive answer generation + 11-section lecture framework
- [x] Evaluation harness: citation accuracy, hallucination rate, precision/recall, coverage
- [x] Bounded, logged research/improvement loop with recommendations
- [x] Source registry (25+ works) + labelled seed knowledge
- [x] Verified landscape research of existing systems & open data sources
- [x] Passing test suite, runnable demos, full docs

## Iteration 2 — Real corpora & semantic retrieval (in progress)

- [x] Ingest the complete Qurʾān (canonical Uthmani Arabic + Ali Quli Qarai
      translation), verified — 6236 verses, HIGH confidence
- [x] Ingest the **complete Four Books + Nahj al-Balāgha** with exact locators
      **and rijāl gradings**, from CC0 ThaqalaynData: al-Kāfī in full (all 8
      volumes — Uṣūl, Furūʿ, Rawḍa = 16,267), Man Lā Yaḥḍuruhu al-Faqīh (6382),
      Tahdhīb al-Aḥkām (13,201), al-Istibṣār (4220), Nahj al-Balāgha (2260) =
      **42,330 hadith**. Grade + attributable grade_source carried through;
      confidence derived conservatively from the grade(s)
- [x] Reusable, tested ingestion adapters (`ingestion/adapters/`, variable-depth
      paths + Nahj Sermon/Letter/Saying scheme + al-Kāfī volume auto-enumeration
      with real Book titles) + `scripts/ingest.py`
- [x] Further al-Saduq/al-Mufid hadith collections (al-Khiṣāl, both Amālī, ʿUyūn
      Akhbār al-Riḍā, al-Tawḥīd = 4280) from CC0 ThaqalaynData
- [x] Prose tier via a new Shiavault Markdown adapter — Sīra (*The Message*),
      Maqtal al-Husayn, Kitāb al-Irshād, al-Ṣaḥīfa al-Sajjādiyya, chapter-level
      citations, medium confidence.
- [x] Tafsīr al-Mīzān — **complete 40-volume English edition** (Tawheed Institute
      Australia) via a new plain-text/OCR adapter (`adapters/plaintext.py`),
      18,125 sections cited by volume + section (supersedes the earlier partial
      Shiavault vols 1,2,4,7,8). **Corpus now 117,288 docs across 17 works.**
- [x] Real-corpus integrity tests (every citation complete + registered; grades honest)
- [x] External-data infrastructure — the built corpus now lives outside git
      (`data/manifest.yaml` + `scripts/fetch_data.py` for status/bundle/fetch;
      small committed sample; integrity tests skip on bare checkouts). See
      [`docs/data-management.md`](data-management.md). Chosen over Git LFS
      because the corpus is derived and outgrows the LFS free tier.
- [x] **Biḥār al-Anwār — complete (all 101 volumes)** ingested from the uploaded
      hubeali English text-layer PDFs via a new PyMuPDF adapter (`adapters/bihar.py`),
      one document per page cited by volume + hubeali page (~43k pages, medium
      confidence, ungraded). Corpus lives in external data.
- [ ] Upload-needed (not on GitHub): Wasāʾil al-Shīʿa, Mustadrak al-Wasāʾil,
      Mafātīḥ al-Jinān; enrich Faqīh/Tahdhīb/Istibṣār with Kitāb titles
- [x] Semantic-embedder integration + retrieval upgrades:
      - `SentenceTransformerEmbedder` (BGE-M3/E5/Jina) behind `EmbeddingProvider`,
        selectable via `make_embedder("st:<model>")` — runs wherever the model is
        reachable (the HuggingFace Hub is blocked in the hosted sandbox)
      - `TfidfHashingEmbedder` — dependency-free IDF-weighted default that **~2×'s
        recall** over the hashing baseline (0.33 → 0.67 recall@10 on the Qur'an
        gold set) and runs everywhere
      - `PersistentVectorStore` — embed the 101k-doc corpus once, cache on disk
      - `scripts/benchmark_retrieval.py` — measure embedders on the gold set
- [x] Benchmark harnesses that record results — `scripts/benchmark_retrieval.py`
      and `scripts/eval_end_to_end.py` (both `--out`). Measured TF-IDF ~2x's
      hashing recall (0.33 -> 0.67 recall@10); citation-accuracy 1.0 /
      hallucination 0.0 hold across embedders. See [`docs/benchmarks.md`](benchmarks.md).
- [ ] Run BGE-M3 + Claude end-to-end in an HF/key-enabled env and fill in the
      pending rows (this sandbox blocks HuggingFace + has no key — numbers NOT fabricated)
- [ ] Stand up Qdrant behind `VectorStore`; persistence + filtering at scale
- [ ] Add a reranker stage (bge-reranker) and re-measure precision/recall
- [ ] Grow the evaluation gold set to 100+ labelled queries

## Iteration 3 — Grounded synthesis & lectures

- [x] LLM `Synthesizer` (Claude) using the charter prompts — `ClaudeSynthesizer`
      (+ offline `MockSynthesizer`), selectable via `make_synthesizer("claude:<model>")`.
      Cites evidence with `[n]` markers; **output re-verified before release**
      (`verify_synthesis`): invented citations, wrong attribution, and
      uncited/hallucinated sentences are rejected and the prose withheld in
      favour of the extractive cited evidence. `demo.py --synthesize`.
- [x] Grounded lecture synthesis — the narrative sections (Executive Summary,
      Introduction, Practical Lessons, Common Misconceptions, Conclusion) are
      auto-written from a pooled evidence set and verified; ungrounded prose is
      withheld back to the lecturer prompt. Reflection Points stays a human task.
- [x] LLM entailment judge (`grounding/entailment.py`) complementing the lexical
      grounding gate — pluggable `EntailmentJudge` (`lexical` default,
      `claude:<model>`, `mock`), batched, defaults to UNSUPPORTED-when-unsure,
      wired through `verify_synthesis` / `AnswerGenerator` / `LectureGenerator`
      / `demo.py --judge`. Rescues true paraphrases and rejects lexical-match
      contradictions the overlap gate gets wrong.
- [x] Query decomposition for multi-part questions (`generation/decompose.py`) —
      pluggable `QueryDecomposer` (`rule` default, `claude:<model>`). Splits
      compound questions (multiple `?`, enumerations, interrogative conjunctions;
      conservative — won't split a noun phrase), retrieves each part, and merges
      the evidence so no clause starves. Recorded on `Answer.sub_questions`;
      `demo.py --decompose`.
- [x] Human-in-the-loop confidence review (`review.py` + `src/shia_aalim/review.py`)
      — queue sources needing review, score them on the source-validation
      criteria (file-based or interactive terminal UI), compute the band, and
      update the registry **with an audit trail**. Never raises confidence
      without a validation record. See [`docs/review-workflow.md`](review-workflow.md).
- [x] Local web front-end (`src/shia_aalim/web.py`, `python -m shia_aalim.web`)
      — a FastAPI app + one self-contained HTML page (search box, lecture-builder
      tab, cited/confidence-badged results) wrapping the **same**
      `AnswerGenerator`/`LectureGenerator`. Presentation only — the grounding
      guarantees are unchanged. `[web]` extra; degrades to a clear install hint
      without it. Copy-/download-Markdown export on every result, and a
      **retrieval-index toggle** (`--embedder tfidf,st:BAAI/bge-m3`) that builds
      each index lazily and marks an unreachable semantic model *unavailable*
      rather than crashing. A **filter panel** narrows retrieval by evidence
      type, source book (with per-book counts + confidence, from `/api/sources`),
      and minimum confidence; excluded-everything results name the active
      filters. A **citation drawer** (click any passage) shows the full Arabic +
      grade/locator record; a **Compare sources** view answers one question per
      book side by side (`/api/compare`); and a browser-local **History** tab
      revisits past answers/lectures/comparisons. See [`docs/web-app.md`](web-app.md).

## Iteration 4 — Depth & rigour

- [ ] Rijāl integration: narrator lookup, chain evaluation surfacing grade sources
- [x] Cross-referencing: link a Qurʾān verse to its tafsīr and related narrations
      (`generation/crossref.py`, `POST /api/crossref`, and a "related tafsir &
      narrations" action in the citation drawer). Content-based (tafsir/hadith
      are cited by book, not surah:ayah), labelling each link *explicit* (cites
      the reference or quotes the verse) vs *thematic*. Nothing invented — every
      link is a real cited passage that keeps its own confidence.
- [ ] Tafsīr coverage (al-Mīzān, Majmaʿ al-Bayān, Nemuneh)
- [ ] Persian/Urdu query + answer support
- [ ] Comparative (Twelver vs other) mode with explicit sect labelling

## Continuous (every iteration)

- Refresh [`landscape-existing-solutions.md`](landscape-existing-solutions.md)
- Re-run evaluation; keep hallucination rate at 0 and drive precision/recall up
- Expand source coverage only through **validated** ingestion
- Log every change; never auto-raise confidence without a validation record

## Known limitations (tracked honestly)

- Baseline embedder is lexical/character-based, not semantic (Iteration 2 fixes).
- Grounding is lexical overlap until the LLM entailment judge lands (Iteration 3).
- Seed knowledge is illustrative; real ingestion is Iteration 2.
- Precision@k on the tiny starter gold set is low by construction (k > relevant
  count); it becomes meaningful once the gold set grows.
