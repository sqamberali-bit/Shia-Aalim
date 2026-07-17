# Source-validation framework

> *"Never trust a source automatically."* — the charter

Every source is scored before it may be cited with any confidence above
`unverified`. Scoring is transparent, deterministic and auditable: the same
inputs always yield the same band, and every decision is explained. Implemented
in [`source_validation.py`](../src/shia_aalim/source_validation.py).

## Criteria and weights

| Criterion | Weight | What it asks |
|---|---|---|
| Scholarly acceptance | 0.22 | Is the work accepted within the Twelver scholarly tradition? |
| Chain availability | 0.15 | Is the isnād / sanad available where relevant? |
| Publisher credibility | 0.13 | Reputable publisher / institution? |
| Academic references | 0.12 | Cited by academic / peer scholarship? |
| Community acceptance | 0.10 | Accepted by the wider community? |
| Original language | 0.13 | Is the original (Arabic/Persian) text available? |
| Translation quality | 0.15 | Faithful, attributable translation? |

Each criterion is scored in `[0, 1]`. **Not-applicable** criteria are set to
`None` and *renormalised out* — e.g. the Qurʾān has no isnād, so
`chain_availability=None` neither rewards nor penalises it.

## Bands

| Composite score | Confidence | Meaning |
|---|---|---|
| ≥ 0.80 | `high` | May be asserted as fact (with citation). |
| ≥ 0.60 | `medium` | May be asserted, but note it is not the strongest tier. |
| ≥ 0.35 | `low` | Must be hedged; never stated as established fact. |
| < 0.35 | `unverified` | Default. Not citable as fact. |

The default is deliberately `unverified`: the burden of proof is on the source.

## Two levels of confidence

Confidence exists at **two** levels and they are not the same:

1. **Source-level** (in `registry.yaml`) — the standing of the *work*. This is a
   **ceiling**.
2. **Passage-level** (per `Document`/`Citation`) — the standing of the specific
   narration, which may be lower (e.g. a ḍaʿīf hadith inside a highly-regarded
   collection). A passage's confidence must never exceed its source's ceiling.

Hadith grades (`sahih`, `hasan`, `muwaththaq`, `daif`, `majhul`, `mursal`) are a
**separate, descriptive** field. The system never *derives* a grade; a grade
must carry a `grade_source` (the rijāl authority who assigned it). An ungraded
narration stays `ungraded` and is not presented as authentic.

## Worked example

```python
from shia_aalim.source_validation import SourceAssessment, validate_source

report = validate_source(SourceAssessment(
    scholarly_acceptance=0.95, chain_availability=0.85, publisher_credibility=0.9,
    academic_references=0.8, community_acceptance=0.95,
    original_language=1.0, translation_quality=0.85,
    notes="Al-Kafi — foremost of the Four Books; grade individual narrations.",
))
print(report.as_dict())   # -> confidence: "high", with per-criterion contributions
```

Store the resulting `confidence` on the source in `registry.yaml` and keep the
`report` (rationale + contributions) in review notes so the decision is auditable.
