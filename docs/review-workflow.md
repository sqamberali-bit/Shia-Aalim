# Confidence review workflow (human-in-the-loop)

The charter is strict: **confidence is never raised without a validation record.**
A source starts at its ingested/default band; promoting it (e.g. `unverified` →
`high`) requires a human to assess it against the
[source-validation criteria](source-validation-framework.md), and that decision
must be auditable.

`scripts/review.py` (backed by `src/shia_aalim/review.py`) is that workflow. It
never decides confidence itself — it turns a reviewer's scores into a
reproducible registry update plus an audit line.

## The loop

```
 registry ──► queue (sources needing review) ──► human scores the 7 criteria
                                                          │
                    source_validation.validate_source ◄───┘
                                                          │
                        band (high/medium/low/unverified) │
                                                          ▼
                       registry confidence updated  +  audit record appended
```

## Commands

**1. Build a review queue** — by default, sources at `unverified`/`low`
(candidates for promotion):

```bash
python scripts/review.py queue --out review.yaml
# --only pending (default) | all | high | medium | low | unverified | id,id,...
```

**2a. Fill `review.yaml`** — a score `0.0`–`1.0` per criterion (or `null` for
not-applicable, which is renormalised out), then apply:

```bash
python scripts/review.py apply review.yaml --reviewer "A. Scholar"
#   kamal-al-din    unverified -> high    score=0.94
#   Audit appended to research/reviews/audit.jsonl
```

**2b. Or review interactively** at the terminal (prompts for each criterion;
`s` skips a source, `q` finishes and applies what's done):

```bash
python scripts/review.py interactive --reviewer "A. Scholar"
```

**3. Audit history**:

```bash
python scripts/review.py log
# 2026-08-01T00:00:00Z  kamal-al-din  unverified -> high  score=0.94  by A. Scholar
```

## What gets recorded

The registry's `confidence:` for the source is updated **in place** (a targeted
line edit — comments, order and formatting are preserved; not a lossy YAML
round-trip). Every decision appends a line to `research/reviews/audit.jsonl`:

```json
{"timestamp": "...", "reviewer": "A. Scholar", "source_id": "kamal-al-din",
 "old_confidence": "unverified", "new_confidence": "high", "applied": true,
 "score": 0.94, "contributions": {"scholarly_acceptance": 0.22, ...},
 "rationale": "Composite score 0.94 ... -> HIGH.", "notes": "verified edition"}
```

The registry change is versioned by git (the durable record); the audit JSONL is
the per-decision detail (with the exact scores) and is git-ignored as a runtime
artefact — commit it too if you want the scores in history.

## Notes

* The band is computed by `source_validation.validate_source`, the same
  transparent, weighted, N/A-aware scoring the rest of the system uses — so a
  reviewer's judgement is converted to confidence the *same* way everywhere.
* This governs the **source-level** confidence (a ceiling). Passage-level
  confidence (per hadith grade, etc.) is set at ingestion and is a separate
  concern.
* An unknown source id is reported and **not** applied — the tool won't invent
  a registry entry.
