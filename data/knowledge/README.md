# Knowledge base (`data/knowledge/`)

This directory holds the ingested, citable knowledge as newline-delimited JSON
(`.jsonl`), one [`KnowledgeDocument`](../schema/document.schema.json) per line.

## What is ingested (Iteration 2 — real corpora)

**Totals: 6236 Qur'an verses + 42,330 hadith — the complete Four Books and Nahj al-Balāgha.**

| File | Content | Count | Source | Confidence |
|---|---|---|---|---|
| `quran/quran.jsonl` | Complete Qur'an — English (Ali Quli Qarai) with canonical Uthmani Arabic in each citation | 6236 verses | [fawazahmed0/quran-api](https://github.com/fawazahmed0/quran-api) editions `ara-quranuthmanihaf` + `eng-aliquliqarai` | high |
| `hadith/al-kafi-*.jsonl` | **al-Kāfī, complete** — Uṣūl (vol. 1: Tawḥīd, Intellect, Ḥujjah, Knowledge = 1463), Furūʿ (vols 2–7 = 14,207), Rawḍa (vol. 8 = 597) | 16,267 hadith | [narmafraz/ThaqalaynData](https://github.com/narmafraz/ThaqalaynData) (CC0) | per-grade |
| `hadith/man-la-yahduruhu-al-faqih.jsonl` | Man Lā Yaḥḍuruhu al-Faqīh (complete) | 6382 hadith | ThaqalaynData (CC0) | per-grade |
| `hadith/tahdhib-al-ahkam.jsonl` | Tahdhīb al-Aḥkām (complete) | 13,201 hadith | ThaqalaynData (CC0) | per-grade |
| `hadith/al-istibsar.jsonl` | al-Istibṣār (complete) | 4220 hadith | ThaqalaynData (CC0) | per-grade |
| `hadith/nahj-al-balagha.jsonl` | Nahj al-Balāgha — Sermons, Letters, Sayings (complete) | 2260 units | ThaqalaynData (CC0) | high |

All **Four Books are ingested in full** — al-Kāfī (all 8 volumes: Uṣūl, Furūʿ,
Rawḍa), Man Lā Yaḥḍuruhu al-Faqīh, Tahdhīb al-Aḥkām, al-Istibṣār — plus the
complete Nahj al-Balāgha (cited by Sermon/Letter/Saying number). al-Kāfī's
Furūʿ/Rawḍa volumes are auto-enumerated per volume (each Book keeps its real
title) by `scripts/ingest.py`.

The fiqh collections and Nahj are largely **ungraded** in this dataset (marked
`ungraded`, confidence `medium` — a real, cited narration whose chain
authenticity is simply not recorded here, never asserted as authentic); al-Kāfī
carries real gradings (ṣaḥīḥ/ḥasan/muwaththaq/ḍaʿīf/majhūl/mursal).

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
