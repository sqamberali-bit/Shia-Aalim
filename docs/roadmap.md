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
- [x] 32 passing tests, runnable demos, full docs

## Iteration 2 — Real corpora & semantic retrieval

- [ ] Ingest Qurʾān (Tanzil/QUL) with Arabic + multiple translations, verified
- [ ] Ingest Twelver hadith via ThaqalaynAPI (Four Books) with exact locators
- [ ] Swap in a semantic embedder (BGE-M3) behind `EmbeddingProvider`; benchmark
      vs the hashing baseline on a domain gold set
- [ ] Stand up Qdrant behind `VectorStore`; persistence + filtering
- [ ] Add a reranker stage (bge-reranker) and re-measure precision/recall
- [ ] Grow the evaluation gold set to 100+ labelled queries

## Iteration 3 — Grounded synthesis & lectures

- [ ] Implement an LLM `Synthesizer` (Claude) using the charter prompts
- [ ] Add LLM-based entailment to complement lexical grounding
- [ ] Query decomposition for multi-part questions
- [ ] Full lecture generation with sourced tafsīr/hadith/history sections
- [ ] Human-in-the-loop review UI for confidence promotion

## Iteration 4 — Depth & rigour

- [ ] Rijāl integration: narrator lookup, chain evaluation surfacing grade sources
- [ ] Cross-referencing: link a verse to its tafsīr and related narrations
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
