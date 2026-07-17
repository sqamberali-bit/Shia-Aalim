"""Integrity checks over the REAL ingested knowledge base.

These guard the charter's guarantees against the actual committed corpus (not a
fixture): every citation is complete and resolves to a registered source, no
fabricated placeholders remain, and hadith gradings are carried through honestly.
"""

from collections import Counter

import pytest
from conftest import DATA, full_corpus_available

from shia_aalim.ingestion.loaders import iter_knowledge_dir
from shia_aalim.models import ConfidenceLevel, EvidenceType
from shia_aalim.sources import load_registry_ids

# The full corpus is external (out-of-git). Skip these integrity checks unless it
# has been built/fetched locally — the committed sample is exercised separately.
pytestmark = pytest.mark.skipif(
    not full_corpus_available(),
    reason="full corpus not present; build with scripts/ingest.py or "
    "fetch with scripts/fetch_data.py --from-bundle",
)


def _corpus():
    # Exclude the committed sample/ (a subset) so it isn't double-counted.
    docs = []
    for sub in ("quran", "hadith", "prose"):
        d = DATA / "knowledge" / sub
        if d.exists():
            docs += list(iter_knowledge_dir(d))
    return docs


def test_corpus_is_substantial():
    docs = _corpus()
    quran = [d for d in docs if d.evidence_type is EvidenceType.QURAN]
    hadith = [d for d in docs if d.evidence_type is EvidenceType.HADITH]
    assert len(quran) == 6236  # complete Qur'an
    assert len(hadith) >= 40000  # complete Four Books + Nahj
    # every one of the Four Books + Nahj is represented
    by_source = {}
    for d in hadith:
        by_source[d.citation.source_id] = by_source.get(d.citation.source_id, 0) + 1
    for expected in ["al-kafi", "man-la-yahduruhu-al-faqih", "tahdhib-al-ahkam",
                     "al-istibsar", "nahj-al-balagha"]:
        assert expected in by_source
    # al-Kafi is ingested in full (all 8 volumes ~16k narrations)
    assert by_source["al-kafi"] >= 16000


def test_every_citation_is_complete_and_registered():
    docs = _corpus()
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    for d in docs:
        assert d.citation.is_complete(), f"incomplete citation: {d.id}"
        assert d.citation.source_id in known, f"unregistered source in {d.id}: {d.citation.source_id}"


def test_quran_docs_have_canonical_arabic():
    quran = [d for d in _corpus() if d.evidence_type is EvidenceType.QURAN]
    for d in quran[:50]:
        assert d.citation.arabic_text, f"missing Arabic for {d.id}"
        assert d.citation.surah and d.citation.ayah
        assert d.confidence is ConfidenceLevel.HIGH


def test_hadith_gradings_are_honest():
    hadith = [d for d in _corpus() if d.evidence_type is EvidenceType.HADITH]
    grades = Counter(d.citation.grade.value for d in hadith)
    # real rijal data => a mix of authentic and weak, not a uniform label
    assert grades["sahih"] > 0
    assert grades["daif"] > 0 or grades["majhul"] > 0
    # any weak narration must be flagged low confidence, never asserted as fact
    for d in hadith:
        if d.citation.grade.value in ("daif", "majhul", "mursal"):
            assert d.confidence.rank <= ConfidenceLevel.LOW.rank
        # graded hadith must name their grading authority
        if d.citation.grade.value != "ungraded":
            assert d.citation.grade_source


def test_no_placeholder_or_do_not_cite_content_remains():
    for d in _corpus():
        assert "placeholder" not in d.tags
        assert "do-not-cite" not in d.tags
        assert "SCHEMA PLACEHOLDER" not in d.text


def test_prose_works_are_medium_confidence_and_complete():
    prose = [d for d in _corpus() if "prose" in d.tags]
    assert len(prose) >= 3000  # al-Mizan (partial) + Sahifa + Seerah/Maqtal/Irshad
    types = {d.evidence_type.value for d in prose}
    assert "tafsir" in types and "historical" in types
    for d in prose:
        # prose is a translation/secondary tier — never asserted above medium
        assert d.confidence.rank <= ConfidenceLevel.MEDIUM.rank
        assert d.citation.is_complete()  # chapter + section locator
