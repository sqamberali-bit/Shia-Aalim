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
- [x] **Complete ThaqalaynData coverage** — added the last two collections:
      **Muʿjam al-Aḥādīth al-Muʿtabara** (Muḥsinī, 555 narrations, 428 graded
      *muʿtabar*/reliable) as hadith, and **Kitāb al-Ḍuʿafāʾ** (Ibn al-Ghaḍāʾirī,
      226 entries) typed **BIOGRAPHICAL** — a rijāl work (narrator criticism), not
      isnād-bearing hadith. Also fixed dict-form `{grader: grade}` grading parsing
      (Muḥsinī's Faqīh/ʿUyūn/Muʿjam were silently ungraded) and added the
      *muʿtabar* grade with a `غير معتبر` ("not reliable") negation guard. Corpus
      now **~122.7k docs**. (Kamāl al-Dīn remains out — it is an empty stub in the
      source dataset.)
- [x] Prose tier via a new Shiavault Markdown adapter — Sīra (*The Message*),
      Maqtal al-Husayn, Kitāb al-Irshād, al-Ṣaḥīfa al-Sajjādiyya, chapter-level
      citations, medium confidence.
- [x] Classical primary works from the Shiavault mirror (chapter-level citations,
      medium confidence): **Tawḥīd al-Mufaḍḍal** (153), **Tuḥaf al-ʿUqūl**
      (al-Ḥarrānī, 937), **Mishkāt al-Anwār** (al-Ṭabarsī, 2 vols, 959),
      **A Shiʿite Creed** (al-Ṣadūq's Iʿtiqādāt, 210) and **Jāmiʿ al-Saʿādāt**
      (al-Narāqī, akhlāq, 108) = +2367 passages. Creed/ethics typed
      `scholarly_opinion`; the rest `hadith`. Adapter now drops placeholder
      ("N/A") metadata from citation provenance.
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
- [x] **Biḥār al-Anwār — per-hadith (all 101 volumes)** ingested from the uploaded
      hubeali English text-layer PDFs via `adapters/bihar.py`, one document per
      narration cited as *Biḥār al-Anwār, vN, Ch X, H Y* using footnote-based
      splitting (medium confidence, ungraded). Corpus lives in external data.
- [x] **Mafātīḥ al-Jinān — complete** from the Apache-2.0 `aminpaydar/Mafatih`
      JSON tree via a new adapter (`adapters/mafatih.py`): 1991 Arabic
      supplication passages cited by bāb / faṣl / article, with the **Persian**
      (Ansariyan) rendering attached where present. No English edition — the
      adapter labels the translation Persian and never machine-translates.
- [x] **Wasāʾil al-Shīʿa — per-hadith ingestion** from English text-layer volume
      PDFs via a new adapter (`adapters/wasail.py`): splits on the `Hadith N`
      markers and reads volume + section from each page's running header, so every
      narration is cited as *v1, Section 8, h.114* with the Arabic matn preserved
      (1296 narrations from vol 1). **Partial — vol 1 of ~30**; more volumes drop
      in automatically as `ws<N>_eng.pdf` files are added. Ungraded (the PDFs
      record no rijāl grade), confidence capped at medium.
- [ ] Wasāʾil al-Shīʿa remaining volumes (2–30) as `ws<N>_eng.pdf`; Mustadrak
      al-Wasāʾil (Arabic full text is available from OpenITI — needs a mARkdown
      adapter — or upload an English edition); enrich Faqīh/Tahdhīb/Istibṣār with
      Kitāb titles
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

- [x] Rijāl integration (`rijal.py`, `/api/rijal/*`, a **Narrators** tab):
      heuristically reads each narration's chain (isnad) *as it appears in the
      text*, indexes narrators, and surfaces the **attributed** gradings
      (`grade_source` parsed into attributor → grade → work). Narrator lookup +
      corpus grade distribution; the drawer shows the chain and gradings for any
      hadith. Strictly *surfacing*, never *deriving* — the system still never
      grades a narrator or narration itself. (Full rijāl-database evaluation —
      Najāshī/Ṭūsī reliability judgements — remains future work.)
- [x] Cross-referencing: link a Qurʾān verse to its tafsīr and related narrations
      (`generation/crossref.py`, `POST /api/crossref`, and a "related tafsir &
      narrations" action in the citation drawer). Content-based (tafsir/hadith
      are cited by book, not surah:ayah), labelling each link *explicit* (cites
      the reference or quotes the verse) vs *thematic*. Nothing invented — every
      link is a real cited passage that keeps its own confidence.
- [ ] Tafsīr coverage (al-Mīzān, Majmaʿ al-Bayān, Nemuneh)
- [~] Persian/Urdu query + answer support — **language layer done**
      (`language.py`): detects the query language (English/Arabic/Persian/Urdu by
      script heuristic), records it on `Answer.query_language`, and — honestly —
      warns when a Persian/Urdu query hits a *lexical* index that cannot bridge
      scripts, pointing to the multilingual semantic embedder (`st:BAAI/bge-m3`,
      already integrated) that makes cross-lingual retrieval work. Arabic is not
      flagged (the corpus carries Arabic originals). Full cross-lingual *answer
      generation* still depends on running that semantic model on a reachable
      host. Query-language shown in the UI + answer Markdown.
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
