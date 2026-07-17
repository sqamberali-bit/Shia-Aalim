# Knowledge base (`data/knowledge/`)

This directory holds the ingested, citable knowledge as newline-delimited JSON
(`.jsonl`), one [`KnowledgeDocument`](../schema/document.schema.json) per line.

## What is ingested (Iteration 2 — real corpora)

| File | Content | Count | Source | Confidence |
|---|---|---|---|---|
| `quran/quran.jsonl` | Complete Qur'an — English (Ali Quli Qarai) with canonical Uthmani Arabic in each citation | 6236 verses | [fawazahmed0/quran-api](https://github.com/fawazahmed0/quran-api) editions `ara-quranuthmanihaf` + `eng-aliquliqarai` | high |
| `hadith/al-kafi-tawhid.jsonl` | al-Kāfī, Book of Tawḥīd (Kitāb al-Tawḥīd) | 218 hadith | [narmafraz/ThaqalaynData](https://github.com/narmafraz/ThaqalaynData) (CC0) | per-grade |
| `hadith/al-kafi-intellect.jsonl` | al-Kāfī, Book of Intellect and Ignorance | 36 hadith | ThaqalaynData (CC0) | per-grade |

Every hadith carries its Arabic *matn*+*isnād*, the attributed **Hubeali**
English translation, and its **rijāl gradings** verbatim (e.g. Allāma
al-Majlisī's *Mir'āt al-'Uqūl*, Shaykh al-Behbudi's *Ṣaḥīḥ al-Kāfī*). Confidence
is derived **conservatively** from the grade(s): a narration graded weak by any
authority is capped at LOW and never presented as established. The upstream's
machine-generated (`ai`) analysis block is deliberately **not** ingested.

Rebuild with [`scripts/ingest.py`](../../scripts/ingest.py) — see
[`docs/ingestion-guide.md`](../../docs/ingestion-guide.md).

## Integrity policy (read before adding anything)

1. **Every document carries a citation to a registered source.** The
   `citation.source_id` must exist in [`../sources/registry.yaml`](../sources/registry.yaml).
   The grounding layer rejects citations to unregistered sources. Verified by
   `tests/test_corpus_integrity.py`.
2. **No invented narrations or locators.** A hadith is only created from real
   upstream data with real locators; missing verses/translations are skipped,
   not fabricated.
3. **Confidence is a ceiling, set by validation / grade.** See the
   [source-validation framework](../../docs/source-validation-framework.md).
4. **Gradings are attributable.** Any graded hadith names its grading authority
   in `grade_source`; ungraded narrations stay `ungraded`.

## Licensing

Qur'an editions and ThaqalaynData (CC0) permit reuse; retain attribution. The
canonical Uthmani Arabic is public. Respect each source's terms before
redistribution — see the source registry.
