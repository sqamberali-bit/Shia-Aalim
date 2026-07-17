from shia_aalim.models import ConfidenceLevel
from shia_aalim.source_validation import (
    SourceAssessment,
    score_to_confidence,
    validate_source,
)


def test_high_scores_map_to_high_confidence():
    a = SourceAssessment(
        scholarly_acceptance=1.0,
        chain_availability=0.9,
        publisher_credibility=0.9,
        academic_references=0.9,
        community_acceptance=1.0,
        original_language=1.0,
        translation_quality=0.9,
    )
    report = validate_source(a)
    assert report.confidence is ConfidenceLevel.HIGH
    assert report.score >= 0.8


def test_empty_assessment_is_unverified():
    report = validate_source(SourceAssessment())
    assert report.confidence is ConfidenceLevel.UNVERIFIED
    assert report.score == 0.0


def test_na_criteria_are_renormalised_not_penalised():
    # A Qur'an text has no isnad; leaving chain_availability None must not drag
    # the score down relative to explicitly scoring the rest highly.
    a = SourceAssessment(
        scholarly_acceptance=1.0,
        publisher_credibility=1.0,
        academic_references=1.0,
        community_acceptance=1.0,
        original_language=1.0,
        translation_quality=1.0,
    )
    report = validate_source(a)
    assert "chain_availability" in report.skipped
    assert report.score >= 0.99  # renormalised over the active criteria


def test_thresholds():
    assert score_to_confidence(0.85) is ConfidenceLevel.HIGH
    assert score_to_confidence(0.65) is ConfidenceLevel.MEDIUM
    assert score_to_confidence(0.4) is ConfidenceLevel.LOW
    assert score_to_confidence(0.1) is ConfidenceLevel.UNVERIFIED
