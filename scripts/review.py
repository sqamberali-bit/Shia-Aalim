#!/usr/bin/env python3
"""Human-in-the-loop confidence review for registered sources.

Confidence must never be raised without a validation record (the charter). This
tool is that record: a reviewer scores a source on the source-validation
criteria; the framework computes the band; the registry is updated and an audit
line is appended.

    # 1. write a review queue (sources at unverified/low confidence):
    python scripts/review.py queue --out review.yaml

    # 2a. fill review.yaml (scores 0.0-1.0 per criterion), then apply:
    python scripts/review.py apply review.yaml --reviewer "A. Scholar"

    # 2b. or review interactively in the terminal:
    python scripts/review.py interactive --reviewer "A. Scholar"

    # audit history:
    python scripts/review.py log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.review import (  # noqa: E402
    ReviewDecision,
    apply_decisions,
    build_review_queue,
    parse_review,
    review_template,
)
from shia_aalim.source_validation import CRITERIA_WEIGHTS, SourceAssessment  # noqa: E402
from shia_aalim.sources import load_sources  # noqa: E402

REGISTRY = ROOT / "data" / "sources" / "registry.yaml"
AUDIT = ROOT / "research" / "reviews" / "audit.jsonl"


def _dump(data: dict, path: Path) -> None:
    try:
        import yaml  # type: ignore
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except ImportError:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return json.loads(text)


def cmd_queue(args) -> int:
    items = build_review_queue(load_sources(REGISTRY), only=args.only)
    if not items:
        print(f"No sources match --only {args.only!r}."); return 0
    out = Path(args.out)
    _dump(review_template(items, reviewer=args.reviewer or ""), out)
    print(f"Wrote {len(items)} source(s) to {out}. Fill in the scores, then: "
          f"python scripts/review.py apply {out}")
    return 0


def _apply(decisions, reviewer) -> int:
    if not decisions:
        print("No scored decisions to apply."); return 0
    changes = apply_decisions(REGISTRY, decisions, audit_path=AUDIT, reviewer=reviewer)
    for c in changes:
        arrow = f"{c.old_confidence} -> {c.new_confidence}" if c.applied else f"{c.old_confidence} (unchanged)"
        flag = "" if c.applied else "  [NOT FOUND in registry]"
        print(f"  {c.source_id:28s} {arrow:24s} score={c.score:.2f}{flag}")
    print(f"\nAudit appended to {AUDIT}")
    return 0


def cmd_apply(args) -> int:
    data = _load(Path(args.file))
    decisions, file_reviewer = parse_review(data)
    return _apply(decisions, args.reviewer or file_reviewer)


def cmd_interactive(args) -> int:
    items = build_review_queue(load_sources(REGISTRY), only=args.only)
    if not items:
        print(f"No sources match --only {args.only!r}."); return 0
    print(f"Reviewing {len(items)} source(s). Enter a score 0.0-1.0 per criterion, "
          "blank = N/A, 's' = skip source, 'q' = finish.\n")
    decisions: list[ReviewDecision] = []
    for it in items:
        print(f"--- {it.source_id} — {it.title} [{it.kind}] (now: {it.current_confidence}) ---")
        scores: dict = {}
        skip = False
        for crit in CRITERIA_WEIGHTS:
            raw = input(f"  {crit} (weight {CRITERIA_WEIGHTS[crit]}): ").strip().lower()
            if raw == "q":
                _apply(decisions, args.reviewer or ""); return 0
            if raw == "s":
                skip = True; break
            scores[crit] = None if raw == "" else float(raw)
        if skip:
            print("  (skipped)\n"); continue
        note = input("  notes: ").strip()
        decisions.append(ReviewDecision(it.source_id, SourceAssessment(**scores, notes=note),
                                        args.reviewer or "", note))
        print()
    return _apply(decisions, args.reviewer or "")


def cmd_log(args) -> int:
    if not AUDIT.exists():
        print("No audit history yet."); return 0
    for line in AUDIT.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        print(f"{r['timestamp']}  {r['source_id']:26s} {r['old_confidence']} -> "
              f"{r['new_confidence']}  score={r['score']}  by {r['reviewer'] or '?'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("queue", help="write a review template")
    q.add_argument("--only", default="pending", help="pending | all | <band> | id,id,...")
    q.add_argument("--out", default="review.yaml")
    q.add_argument("--reviewer", default="")
    q.set_defaults(func=cmd_queue)

    a = sub.add_parser("apply", help="apply a filled review file")
    a.add_argument("file")
    a.add_argument("--reviewer", default="")
    a.set_defaults(func=cmd_apply)

    it = sub.add_parser("interactive", help="review at the terminal")
    it.add_argument("--only", default="pending")
    it.add_argument("--reviewer", default="")
    it.set_defaults(func=cmd_interactive)

    lg = sub.add_parser("log", help="show audit history")
    lg.set_defaults(func=cmd_log)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
