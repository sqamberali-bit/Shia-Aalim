# Knowledge base (`data/knowledge/`)

This directory holds the ingested, citable knowledge as newline-delimited JSON
(`.jsonl`), one [`KnowledgeDocument`](../schema/document.schema.json) per line.

## Integrity policy (read before adding anything)

1. **Every document carries a citation to a registered source.** The
   `citation.source_id` must exist in [`../sources/registry.yaml`](../sources/registry.yaml).
   The grounding layer rejects citations to unregistered sources.
2. **No invented narrations or locators.** Never write a hadith with a
   volume/page/number you have not verified against the primary source. If you
   don't have the locator, don't create the document.
3. **Confidence is a ceiling, set by validation.** New content starts
   `unverified` and is only raised after passing the
   [source-validation framework](../../docs/source-validation-framework.md).
4. **Seed data is illustrative.** The files currently here are seeds for
   testing the pipeline:
   - `quran/seed.jsonl` — famous verses, translation only (M. H. Shakir via
     Tanzil), Arabic omitted, confidence capped at `medium` pending
     verification against Tanzil's canonical file.
   - `hadith/seed.jsonl` — **intentionally contains no narrations**, only a
     labelled schema placeholder, because no machine-verified Twelver hadith
     with exact locators has been ingested yet.

## Populating real content

See [`docs/ingestion-guide.md`](../../docs/ingestion-guide.md). Highest-value
clean-ingestion targets (from the
[landscape research](../../docs/landscape-existing-solutions.md)):

| Content | Recommended source | Format | Licence note |
|---|---|---|---|
| Qur'an + translations | Tanzil, QUL | XML / JSON | attribution + backlink |
| Twelver hadith (4 Books) | ThaqalaynAPI | JSON (REST/GraphQL) | GPL-3.0 |
| Al-Kafi, Bihar (translated) | Hubeali | EPUB / PDF | religious-use, attribution |
| Broad Twelver library | Shiavault (GitHub) | Markdown | open |
| Classical Arabic depth | OpenITI | mARkdown | CC BY-NC-SA |
