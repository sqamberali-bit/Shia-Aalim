import json

from conftest import DATA

from shia_aalim.models import ConfidenceLevel
from shia_aalim.review import (
    ReviewDecision,
    apply_decisions,
    build_review_queue,
    parse_review,
    review_template,
    set_source_confidence,
)
from shia_aalim.source_validation import SourceAssessment
from shia_aalim.sources import load_sources

REGISTRY = DATA / "sources" / "registry.yaml"


def test_build_queue_pending_selects_unverified_and_low():
    items = build_review_queue(load_sources(REGISTRY), only="pending")
    bands = {it.current_confidence for it in items}
    assert bands <= {"unverified", "low"}
    # kamal-al-din was marked unverified/not-ingested -> should appear
    assert any(it.source_id == "kamal-al-din" for it in items)


def test_build_queue_by_ids_and_band():
    by_id = build_review_queue(load_sources(REGISTRY), only="al-kafi")
    assert [it.source_id for it in by_id] == ["al-kafi"]
    highs = build_review_queue(load_sources(REGISTRY), only="high")
    assert highs and all(it.current_confidence == "high" for it in highs)


def test_review_template_has_all_criteria():
    items = build_review_queue(load_sources(REGISTRY), only="al-kafi")
    tmpl = review_template(items)
    a = tmpl["items"][0]["assessment"]
    assert set(a) == {"scholarly_acceptance", "chain_availability", "publisher_credibility",
                      "academic_references", "community_acceptance", "original_language",
                      "translation_quality"}


def test_parse_review_skips_untouched_and_parses_scored():
    data = {"reviewer": "R", "items": [
        {"source_id": "a", "assessment": {"scholarly_acceptance": None}, "notes": ""},  # untouched
        {"source_id": "b", "assessment": {"scholarly_acceptance": 0.9, "community_acceptance": 0.8}, "notes": "ok"},
    ]}
    decisions, reviewer = parse_review(data)
    assert reviewer == "R"
    assert [d.source_id for d in decisions] == ["b"]
    assert decisions[0].assessment.scholarly_acceptance == 0.9


def test_set_source_confidence_edits_only_target(tmp_path):
    text = REGISTRY.read_text(encoding="utf-8")
    new, changed = set_source_confidence(text, "kamal-al-din", "high")
    assert changed
    # the targeted entry changed...
    import re
    block = re.search(r"- id: kamal-al-din.*?(?=\n  - id:|\Z)", new, re.DOTALL).group(0)
    assert "confidence: high" in block
    # ...and al-kafi (a different high source) is untouched / still parseable
    assert "- id: al-kafi\n" in new


def test_apply_decisions_promotes_and_audits(tmp_path):
    # Work on a COPY so the real registry is untouched.
    reg = tmp_path / "registry.yaml"
    reg.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
    audit = tmp_path / "audit.jsonl"

    strong = SourceAssessment(
        scholarly_acceptance=1.0, chain_availability=0.9, publisher_credibility=0.9,
        academic_references=0.9, community_acceptance=1.0, original_language=1.0,
        translation_quality=0.9, notes="verified edition",
    )
    changes = apply_decisions(
        reg, [ReviewDecision("kamal-al-din", strong, "A. Scholar")],
        audit_path=audit, reviewer="A. Scholar", now="2026-08-01T00:00:00Z",
    )
    assert changes[0].applied
    assert changes[0].old_confidence == "unverified"
    assert changes[0].new_confidence == "high"

    # registry file actually updated to high
    updated = {s.id: s.confidence for s in load_sources(reg)}
    assert updated["kamal-al-din"] is ConfidenceLevel.HIGH

    # audit trail written with the scores
    rec = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert rec["source_id"] == "kamal-al-din" and rec["new_confidence"] == "high"
    assert rec["reviewer"] == "A. Scholar" and rec["contributions"]


def test_apply_unknown_source_is_flagged_not_applied(tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text(REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
    changes = apply_decisions(
        reg, [ReviewDecision("does-not-exist", SourceAssessment(scholarly_acceptance=1.0))],
        now="2026-08-01T00:00:00Z",
    )
    assert not changes[0].applied
