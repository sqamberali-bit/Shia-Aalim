# Ingestion guide

How to grow the knowledge base **without** violating the charter. The golden
rule: a document is only born once it has a verifiable citation to a registered
source. If you don't have the locator, you don't have the document.

## The pipeline

```
raw source ─► load ─► normalise ─► chunk ─► attach citation ─► validate ─► index
 (PDF/JSON/…)  loaders  normalize   loaders   (per passage)   source_val  vectorstore
```

1. **Register the source first** in
   [`data/sources/registry.yaml`](../data/sources/registry.yaml) with an initial
   `confidence` from the [validation framework](source-validation-framework.md).
2. **Load** the raw text (`ingestion/loaders.py`): `load_documents_jsonl` for
   curated JSONL, or `load_any` for text/HTML/PDF/EPUB (optional extras).
3. **Normalise** Arabic with `ingestion/normalize.py` before indexing so
   vocalised and unvocalised forms match.
4. **Chunk** long texts with `chunk_text` (paragraph-aware, overlapping).
5. **Attach a citation** to every chunk — exact sūra:āya, or volume/page/ḥadīth
   number. This is the step that must never be faked.
6. **De-duplicate** with `dedupe_documents`.
7. **Index** via `build_index` (or a production `VectorStore`).

## Recommended sources (from the landscape research)

See [`landscape-existing-solutions.md`](landscape-existing-solutions.md) for the
full, verified table and licensing caveats. Highest-value clean-ingestion
targets for a Twelver system:

| Content | Source | Format | Licence note |
|---|---|---|---|
| Qurʾān + translations | **Tanzil**, **QUL** (Tarteel) | XML / JSON | attribution + backlink; QUL code MIT |
| Twelver hadith (Four Books) | **ThaqalaynAPI** | JSON (REST/GraphQL) | GPL-3.0 |
| Al-Kāfī, Biḥār (translated) | **Hubeali** | EPUB / PDF | religious-use, attribution |
| Broad Twelver library | **Shiavault** (GitHub) | Markdown | open, clone the repo |
| Classical Arabic depth | **OpenITI** | mARkdown | CC BY-NC-SA (non-commercial) |

**Respect licences.** The Quran Foundation API forbids caching >1 week and
scraping; Tanzil and the Quranic Arabic Corpus require attribution + backlink;
OpenITI is non-commercial. Record the licence on the source and honour it.

## Example: ingesting a JSONL hadith export

```python
from shia_aalim.ingestion.loaders import load_documents_jsonl, dedupe_documents
from shia_aalim.research_loop import build_index

docs = dedupe_documents(load_documents_jsonl("data/knowledge/hadith/kafi_book1.jsonl"))
retriever = build_index(docs)
```

Each line must conform to [`document.schema.json`](../data/schema/document.schema.json),
with a complete `citation` (source in the registry, locator present) and a
`grade` + `grade_source` if you assert authenticity.

## Sect-awareness

Label every source by sect. Sunni collections (e.g. sunnah.com data) may be
ingested for comparative study but must be tagged and **never blended silently**
into Twelver answers. The registry `kind` + `notes` and document `tags` carry
this.

## Scanned manuscripts (OCR)

`loaders.py::ocr_placeholder` is an explicit hook — wire in an Arabic-capable
OCR backend (Tesseract with `ara` traineddata, or a cloud OCR API). It raises a
clear error until configured rather than silently returning empty text.
