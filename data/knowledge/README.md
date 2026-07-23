# Knowledge base (`data/knowledge/`)

This directory holds the ingested, citable knowledge as newline-delimited JSON
(`.jsonl`), one [`KnowledgeDocument`](../schema/document.schema.json) per line.

## What is ingested (Iteration 2 — real corpora)

**Totals: 121,871 cited documents across 27 works** — 6236 Qur'an verses,
94,527 hadith (incl. the complete 101-volume Biḥār al-Anwār), and 21,108 prose
passages (incl. the complete 40-volume Tafsīr al-Mīzān).

| File | Content | Count | Source | Confidence |
|---|---|---|---|---|
| `quran/quran.jsonl` | Complete Qur'an — English (Ali Quli Qarai) with canonical Uthmani Arabic in each citation | 6236 verses | [fawazahmed0/quran-api](https://github.com/fawazahmed0/quran-api) editions `ara-quranuthmanihaf` + `eng-aliquliqarai` | high |
| `hadith/al-kafi-*.jsonl` | **al-Kāfī, complete** — Uṣūl (vol. 1: Tawḥīd, Intellect, Ḥujjah, Knowledge = 1463), Furūʿ (vols 2–7 = 14,207), Rawḍa (vol. 8 = 597) | 16,267 hadith | [narmafraz/ThaqalaynData](https://github.com/narmafraz/ThaqalaynData) (CC0) | per-grade |
| `hadith/man-la-yahduruhu-al-faqih.jsonl` | Man Lā Yaḥḍuruhu al-Faqīh (complete) | 6382 hadith | ThaqalaynData (CC0) | per-grade |
| `hadith/tahdhib-al-ahkam.jsonl` | Tahdhīb al-Aḥkām (complete) | 13,201 hadith | ThaqalaynData (CC0) | per-grade |
| `hadith/al-istibsar.jsonl` | al-Istibṣār (complete) | 4220 hadith | ThaqalaynData (CC0) | per-grade |
| `hadith/nahj-al-balagha.jsonl` | Nahj al-Balāgha — Sermons, Letters, Sayings (complete) | 2260 units | ThaqalaynData (CC0) | high |
| `hadith/al-khisal.jsonl` | al-Khiṣāl (al-Saduq) | 1282 | ThaqalaynData (CC0) | per-grade |
| `hadith/al-amali-saduq.jsonl` · `al-amali-mufid.jsonl` | al-Amālī of al-Saduq (1082) + al-Mufid (387) | 1469 | ThaqalaynData (CC0) | per-grade |
| `hadith/uyun-akhbar-al-rida.jsonl` | ʿUyūn Akhbār al-Riḍā (al-Saduq) | 954 | ThaqalaynData (CC0) | per-grade |
| `hadith/al-tawhid-saduq.jsonl` | Kitāb al-Tawḥīd (al-Saduq — standalone, distinct from al-Kāfī's Book of Tawḥīd) | 575 | ThaqalaynData (CC0) | per-grade |
| `hadith/bihar-al-anwar-v*.jsonl` | **Biḥār al-Anwār — complete, all 101 volumes** (al-Majlisī). One doc/page, cited by volume + hubeali page | 43,292 | hubeali English PDFs ([source repo](https://github.com/sqamberali-bit/bihar-al-anwar-source)) | medium (ungraded — no rijāl grade in the PDFs; contains strong & weak reports) |
| `hadith/{thawab-al-amal, maani-al-akhbar, kitab-al-ghayba-numani/-tusi, kamil-al-ziyarat, kitab-al-zuhd, kitab-al-mumin, sifat-al-shia, risalat-al-huquq, fadail-al-shia}.jsonl` | Further al-Saduq / Ahwazi / Ghayba collections | 4583 | ThaqalaynData (CC0) | medium (ungraded) |

### Prose works (`prose/*.jsonl`) — coarser, chapter-level citations

Translations / secondary works from the [Shiavault](https://github.com/shiavault/shiavault-library)
al-islam.org Markdown mirror. Chunked as prose with **book + chapter + section**
locators (no ḥadīth number or rijāl grade), confidence capped at **medium**.

| File(s) | Content | Passages | Type |
|---|---|---|---|
| `prose/al-mizan-v{01..40}.jsonl` | **Tafsīr al-Mīzān — complete 40-volume English edition** (Tawheed Institute Australia; ʿAllāma Ṭabāṭabāʾī). OCR'd plain text, cited by volume + section | 18,125 | tafsīr |
| `prose/seerah-the-message.jsonl` | *The Message* — Sīra of the Prophet (Ja'far Subhani) | 1197 | historical |
| `prose/maqtal-al-husayn.jsonl` | *Maqtal al-Husayn* — the events of Karbala | 878 | historical |
| `prose/sahifa-sajjadiyya.jsonl` | al-Ṣaḥīfa al-Sajjādiyya (supplications; Arabic + English) | 582 | (words of the Imam) |
| `prose/kitab-al-irshad.jsonl` | *Kitāb al-Irshād* — biography of the Twelve Imams (al-Mufid) | 368 | historical |

Prose passages are a **different evidence tier** from the per-narration hadith
corpora: verify Maqtal/history reports against primary maqātil, and treat the
al-Mīzān text as an English rendering.

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
