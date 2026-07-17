# Citation standards

The rule: **no citation = do not state as fact.** These standards define what a
*complete* citation is for each evidence type. They are enforced by
`Citation.is_complete()` and the JSON Schema in
[`data/schema/citation.schema.json`](../data/schema/citation.schema.json).

## Required locators

### Qurʾān
- `source_id` (e.g. `quran`, or a translation source id)
- `surah` (1–114), `ayah`
- `translation_source` when quoting a translation
- Reference form: `Qur'an 5:55`

### Hadith
- `source_id` (a registered collection, e.g. `al-kafi`)
- **at least one** of: `hadith_number`, `page`, `volume` (ideally all)
- `grade` **and** `grade_source` when asserting authenticity — a grade with no
  attributable rijāl source is not a grade
- `arabic_text` strongly encouraged (enables passage-existence checks)
- Reference form: `al-Kāfī, v1, p.34, h.2 (grade: sahih, per <rijal source>)`

### Tafsīr
- `source_id` (e.g. `al-mizan`), `volume` and/or `page`
- Reference form: `al-Mīzān, v3, p.120`

### Scholarly works
- `source_id` (author's registered work), `volume`/`page`, publisher if known
- Reference form: `<Author>, <Book>, v2, p.55 (<publisher>)`

## Provenance discipline

- **Distinguish evidence types.** Never let a hadith masquerade as Qurʾān, or a
  scholar's view as a narration. `EvidenceType` is carried end to end.
- **Distinguish view status.** Mark `consensus` / `majority` / `minority` /
  `disputed` / `popular_unverified` where the claim's standing matters.
- **Attribute translations.** A translation is an interpretive act; always name
  its source and treat it as `medium` until verified against the canonical text.
- **Popular but unevidenced.** Widespread stories lacking a chain are labelled
  `popular_unverified` and never presented as established.

## Machine-checkable

Because citations are structured, the system verifies them automatically:
completeness (`is_complete`), source existence (against the registry) and, where
the corpus is loaded, passage existence (locator resolves to a real document).
This is what makes "every citation is verifiable" a testable property, not a
slogan.
