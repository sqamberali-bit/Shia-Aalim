from conftest import DATA, sample_corpus

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.lecture import LectureGenerator
from shia_aalim.grounding.verify import check_answer_grounding, validate_citations
from shia_aalim.models import Citation, ConfidenceLevel, EvidenceType
from shia_aalim.research_loop import build_index
from shia_aalim.retrieval.embeddings import HashingEmbedder, cosine
from shia_aalim.sources import load_registry_ids


def test_embedder_similarity_is_symmetric_and_bounded():
    e = HashingEmbedder(dim=256)
    v1 = e.embed("purification of the household")
    v2 = e.embed("purification of the household")
    assert abs(cosine(v1, v2) - 1.0) < 1e-9
    v3 = e.embed("completely unrelated banking invoice")
    assert cosine(v1, v3) < cosine(v1, v2)


def test_retriever_finds_relevant_verse():
    retriever = build_index(sample_corpus())
    results = retriever.retrieve("purification of the People of the House", k=3)
    assert results
    assert "quran-33-33" in [r.document.id for r in results]


def test_retriever_type_filter():
    retriever = build_index(sample_corpus())
    results = retriever.retrieve("intellect worship paradise", k=5, evidence_types=[EvidenceType.HADITH])
    assert results
    assert all(r.document.evidence_type is EvidenceType.HADITH for r in results)


def test_retriever_source_filter():
    retriever = build_index(sample_corpus())
    results = retriever.retrieve("intellect", k=5, source_ids={"al-kafi"})
    assert results
    assert all(r.document.citation.source_id == "al-kafi" for r in results)
    # a source absent from the corpus yields nothing (never a wrong-source result)
    assert retriever.retrieve("intellect", k=5, source_ids={"no-such-book"}) == []


def test_answer_generator_is_extractive_and_grounded():
    retriever = build_index(sample_corpus())
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    gen = AnswerGenerator(retriever, known_source_ids=known)
    answer = gen.answer("love for the near relatives kinship", k=3)
    assert answer.claims
    assert all(c.citations for c in answer.claims)  # extractive => always cited
    md = gen.format_markdown(answer)
    assert "Qur'an 42:23" in md


def test_answer_refuses_when_below_similarity_floor():
    retriever = build_index(sample_corpus())
    gen = AnswerGenerator(retriever)
    # A query with no lexical/character overlap with any doc => nothing clears the floor.
    answer = gen.answer("zxqw vbnm plkj fghd", k=3, min_similarity=0.15)
    assert not answer.claims
    assert answer.caveats


def test_confidence_reranking_prefers_stronger_source():
    # Two near-identical passages; the higher-confidence one should rank first.
    from shia_aalim.models import Document

    def doc(i, conf):
        return Document(
            id=f"d{i}", text="the intellect aql is the proof hujjah of Allah",
            evidence_type=EvidenceType.HADITH,
            citation=Citation(source_id="al-kafi", evidence_type=EvidenceType.HADITH,
                              volume="1", hadith_number=str(i)),
            confidence=conf,
        )
    retriever = build_index([doc(1, ConfidenceLevel.UNVERIFIED), doc(2, ConfidenceLevel.HIGH)])
    top = retriever.retrieve("intellect aql proof hujjah of Allah", k=2)
    assert top[0].document.confidence is ConfidenceLevel.HIGH


def test_validate_citations_flags_unknown_source():
    bad = Citation(source_id="invented-book-xyz", evidence_type=EvidenceType.HADITH, hadith_number="1")
    checks = validate_citations([bad], known_source_ids={"al-kafi"})
    assert not checks[0].ok
    assert any("unknown" in p for p in checks[0].problems)


def test_grounding_rejects_unsupported_claim():
    from shia_aalim.models import Answer, Claim

    retriever = build_index(sample_corpus())
    evidence = retriever.retrieve("purification", k=3)
    fabricated = Answer(
        question="q",
        claims=[Claim(
            statement="The Eiffel Tower was completed in 1889 in Paris.",
            evidence_type=EvidenceType.HISTORICAL,
            confidence=ConfidenceLevel.HIGH,
        )],
    )
    report = check_answer_grounding(fabricated, evidence)
    assert not report.grounded


def test_lecture_has_all_sections():
    lecture = LectureGenerator(build_index(sample_corpus())).generate("purification of the household")
    titles = [s.title for s in lecture.sections]
    for expected in ["Executive Summary", "Qur'anic Foundations", "Hadith Foundations",
                     "Scholarly Analysis", "Conclusion", "Suggested Reading"]:
        assert expected in titles
    assert "Integrity notice" in lecture.to_markdown()
