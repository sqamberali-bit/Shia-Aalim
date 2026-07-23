"""Human-in-the-loop confidence review.

The charter forbids raising a source's confidence without a validation record.
This module is the workflow for doing it properly: a human scores a source on
the :mod:`shia_aalim.source_validation` criteria, the framework computes the
resulting confidence band, and the change is written to the registry **with an
audit record** (who, when, the scores, old → new).

Nothing here decides confidence on its own — it turns a reviewer's judgement into
an auditable, reproducible registry update. Pure standard library except the
optional YAML review-file I/O.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import ConfidenceLevel, Source
from .source_validation import CRITERIA_WEIGHTS, SourceAssessment, validate_source

# Sources in these bands are surfaced for review by default (candidates for
# promotion once a human has assessed them).
PENDING_BANDS = {ConfidenceLevel.UNVERIFIED, ConfidenceLevel.LOW}


@dataclass
class ReviewItem:
    source_id: str
    title: str
    kind: str
    current_confidence: str
    notes: str = ""


@dataclass
class ReviewDecision:
    source_id: str
    assessment: SourceAssessment
    reviewer: str = ""
    notes: str = ""


@dataclass
class AppliedChange:
    source_id: str
    old_confidence: str
    new_confidence: str
    score: float
    rationale: str
    applied: bool


def build_review_queue(sources: Iterable[Source], *, only: str = "pending") -> list[ReviewItem]:
    """Select sources needing review.

    ``only``: ``pending`` (unverified+low, the default), ``all``, a single band
    name (e.g. ``medium``), or a comma-separated list of explicit source ids.
    """
    only = (only or "pending").strip()
    ids: Optional[set[str]] = None
    bands: Optional[set[ConfidenceLevel]] = None
    if only == "pending":
        bands = set(PENDING_BANDS)
    elif only == "all":
        bands = None
    elif only in {c.value for c in ConfidenceLevel}:
        bands = {ConfidenceLevel(only)}
    else:
        ids = {s.strip() for s in only.split(",") if s.strip()}

    out: list[ReviewItem] = []
    for s in sources:
        if ids is not None and s.id not in ids:
            continue
        if bands is not None and s.confidence not in bands:
            continue
        out.append(ReviewItem(s.id, s.title, s.kind.value, s.confidence.value, s.notes or ""))
    return out


def review_template(items: Iterable[ReviewItem], *, reviewer: str = "") -> dict:
    """Build a fill-in review document (YAML/JSON-serialisable)."""
    return {
        "reviewer": reviewer,
        "_help": "Score each criterion 0.0-1.0, or null for not-applicable. "
                 "Then apply with: python scripts/review.py apply <this-file>",
        "items": [
            {
                "source_id": it.source_id,
                "title": it.title,
                "current_confidence": it.current_confidence,
                "assessment": {c: None for c in CRITERIA_WEIGHTS},
                "notes": "",
            }
            for it in items
        ],
    }


def parse_review(data: dict) -> tuple[list[ReviewDecision], str]:
    """Turn a filled review document into decisions. Skips items with no scores."""
    reviewer = str(data.get("reviewer") or "")
    decisions: list[ReviewDecision] = []
    for item in data.get("items", []):
        scores = item.get("assessment") or {}
        if not any(v is not None for v in scores.values()):
            continue  # untouched item — nothing to apply
        assessment = SourceAssessment(
            **{c: _as_float(scores.get(c)) for c in CRITERIA_WEIGHTS},
            notes=str(item.get("notes") or ""),
        )
        decisions.append(ReviewDecision(item["source_id"], assessment, reviewer, str(item.get("notes") or "")))
    return decisions, reviewer


def _as_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    return float(v)


_ID_LINE = re.compile(r"^\s*-\s*id:\s*(\S+)\s*$")
_CONF_LINE = re.compile(r"^(\s*confidence:\s*)(\S+)(.*)$")


def set_source_confidence(registry_text: str, source_id: str, new_confidence: str) -> tuple[str, bool]:
    """Replace one source's ``confidence:`` in the registry text, in place.

    A targeted line edit (not a YAML round-trip) so comments, order and
    formatting are preserved. Returns ``(new_text, changed)``.
    """
    lines = registry_text.split("\n")
    in_entry = False
    for i, line in enumerate(lines):
        m = _ID_LINE.match(line)
        if m:
            in_entry = m.group(1) == source_id
            continue
        if in_entry:
            c = _CONF_LINE.match(line)
            if c:
                lines[i] = f"{c.group(1)}{new_confidence}{c.group(3)}"
                return "\n".join(lines), True
    return registry_text, False


def apply_decisions(
    registry_path: str | Path,
    decisions: list[ReviewDecision],
    *,
    audit_path: Optional[str | Path] = None,
    reviewer: str = "",
    now: Optional[str] = None,
) -> list[AppliedChange]:
    """Validate each decision, update the registry, and append audit records."""
    from .sources import load_sources  # local import avoids a cycle

    registry_path = Path(registry_path)
    text = registry_path.read_text(encoding="utf-8")
    current = {s.id: s.confidence.value for s in load_sources(registry_path)}
    stamp = now or datetime.now(timezone.utc).isoformat()

    changes: list[AppliedChange] = []
    audit_records: list[dict] = []
    for d in decisions:
        report = validate_source(d.assessment)
        old = current.get(d.source_id, "unknown")
        new = report.confidence.value
        text, changed = set_source_confidence(text, d.source_id, new)
        changes.append(AppliedChange(d.source_id, old, new, report.score, report.rationale, changed))
        audit_records.append({
            "timestamp": stamp,
            "reviewer": reviewer or d.reviewer,
            "source_id": d.source_id,
            "old_confidence": old,
            "new_confidence": new if changed else old,
            "applied": changed,
            "score": round(report.score, 4),
            "contributions": {k: round(v, 4) for k, v in report.contributions.items()},
            "rationale": report.rationale,
            "notes": d.notes,
        })

    registry_path.write_text(text, encoding="utf-8")
    if audit_path is not None:
        audit_path = Path(audit_path)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as fh:
            for rec in audit_records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return changes
