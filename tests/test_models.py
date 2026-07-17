from shia_aalim.models import (
    Answer,
    Citation,
    Claim,
    ConfidenceLevel,
    Document,
    EvidenceType,
    HadithGrade,
)


def test_confidence_ordering_and_fact_gate():
    assert ConfidenceLevel.HIGH.rank > ConfidenceLevel.LOW.rank
    assert ConfidenceLevel.HIGH.can_state_as_fact()
    assert ConfidenceLevel.MEDIUM.can_state_as_fact()
    assert not ConfidenceLevel.LOW.can_state_as_fact()
    assert not ConfidenceLevel.UNVERIFIED.can_state_as_fact()


def test_quran_citation_completeness():
    ok = Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=5, ayah=55)
    bad = Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=5)
    assert ok.is_complete()
    assert not bad.is_complete()
    assert ok.reference_string() == "Qur'an 5:55"


def test_hadith_citation_needs_a_locator():
    no_locator = Citation(source_id="al-kafi", evidence_type=EvidenceType.HADITH)
    with_number = Citation(
        source_id="al-kafi", evidence_type=EvidenceType.HADITH, volume="1", hadith_number="3"
    )
    assert not no_locator.is_complete()
    assert with_number.is_complete()
    assert "al-kafi" in with_number.reference_string()


def test_claim_cannot_be_fact_without_complete_citation():
    claim = Claim(
        statement="x",
        evidence_type=EvidenceType.HADITH,
        citations=[Citation(source_id="al-kafi", evidence_type=EvidenceType.HADITH)],
        confidence=ConfidenceLevel.HIGH,
    )
    assert not claim.can_state_as_fact()
    assert claim.validate()  # has problems


def test_claim_with_no_citation_is_flagged():
    claim = Claim(statement="x", evidence_type=EvidenceType.QURAN, confidence=ConfidenceLevel.HIGH)
    problems = claim.validate()
    assert any("no citation" in p for p in problems)


def test_document_roundtrip_and_hash_id():
    doc = Document(
        id="",
        text="Only Allah is your Vali...",
        evidence_type=EvidenceType.QURAN,
        citation=Citation(source_id="tanzil-shakir", evidence_type=EvidenceType.QURAN, surah=5, ayah=55),
        confidence=ConfidenceLevel.MEDIUM,
    )
    assert doc.id.startswith("doc_")  # content hash assigned
    restored = Document.from_dict(doc.to_dict())
    assert restored.text == doc.text
    assert restored.citation.surah == 5
    assert restored.confidence is ConfidenceLevel.MEDIUM


def test_answer_serialisation_marks_fact_status():
    claim = Claim(
        statement="verse",
        evidence_type=EvidenceType.QURAN,
        citations=[Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=1, ayah=1)],
        confidence=ConfidenceLevel.MEDIUM,
    )
    ans = Answer(question="q", claims=[claim])
    d = ans.to_dict()
    assert d["claims"][0]["asserted_as_fact"] is True
    assert "generated_on" in d


def test_grade_enum_defaults_ungraded():
    c = Citation(source_id="al-kafi", evidence_type=EvidenceType.HADITH, hadith_number="1")
    assert c.grade is HadithGrade.UNGRADED
