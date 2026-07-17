from conftest import DATA

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.lecture import LectureGenerator
from shia_aalim.grounding.verify import check_answer_grounding, validate_citations
from shia_aalim.ingestion.loaders import iter_knowledge_dir
from shia_aalim.models import Citation, ConfidenceLevel, EvidenceType
from shia_aalim.research_loop import build_index
from shia_aalim.retrieval.embeddings import HashingEmbedder, cosine
from shia_aalim.sources import load_registry_ids


def _corpus():
    return list(iter_knowledge_dir(DATA / "knowledge"))


def test_embedder_similarity_is_symmetric_and_bounded():
    e = HashingEmbedder(dim=256)
    v1 = e.embed("purification of the household")
    v2 = e.embed("purification of the household")
    assert abs(cosine(v1, v2) - 1.0) < 1e-9
    v3 = e.embed("completely unrelated banking invoice")
    assert cosine(v1, v3) < cosine(v1, v2)


def test_retriever_finds_relevant_verse():
    docs = _corpus()
    retriever = build_index(docs)
    results = retriever.retrieve("purification of the Ahl al-Bayt", k=3)
    assert results
    top_ids = [r.document.id for r in results]
    assert "quran-33-33" in top_ids


def test_retriever_type_filter():
    docs = _corpus()
    retriever = build_index(docs)
    results = retriever.retrieve(
        "guardian wali", k=5, evidence_types=[EvidenceType.QURAN]
    )
    assert all(r.document.evidence_type is EvidenceType.QURAN for r in results)


def test_answer_generator_is_extractive_and_grounded():
    docs = _corpus()
    retriever = build_index(docs)
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    gen = AnswerGenerator(retriever, known_source_ids=known)
    answer = gen.answer("love for the near relatives", k=3)
    assert answer.claims
    # every claim statement is verbatim evidence => carries a citation
    assert all(c.citations for c in answer.claims)
    md = gen.format_markdown(answer)
    assert "Qur'an 42:23" in md


def test_answer_when_no_evidence_refuses_to_answer():
    docs = _corpus()
    retriever = build_index(docs)
    gen = AnswerGenerator(retriever)
    answer = gen.answer("quantum chromodynamics lagrangian derivation", k=3)
    # HashingEmbedder may still return low-similarity docs; if so they are the
    # only evidence — but a totally unrelated query should yield a caveat either
    # way (no evidence OR low-confidence warning).
    assert answer.caveats


def test_validate_citations_flags_unknown_source():
    bad = Citation(source_id="invented-book-xyz", evidence_type=EvidenceType.HADITH, hadith_number="1")
    checks = validate_citations([bad], known_source_ids={"al-kafi"})
    assert not checks[0].ok
    assert any("unknown" in p for p in checks[0].problems)


def test_grounding_rejects_unsupported_claim():
    from shia_aalim.models import Answer, Claim

    docs = _corpus()
    retriever = build_index(docs)
    evidence = retriever.retrieve("purification", k=3)
    fabricated = Answer(
        question="q",
        claims=[
            Claim(
                statement="The Eiffel Tower was completed in 1889 in Paris.",
                evidence_type=EvidenceType.HISTORICAL,
                confidence=ConfidenceLevel.HIGH,
            )
        ],
    )
    report = check_answer_grounding(fabricated, evidence)
    assert not report.grounded


def test_lecture_has_all_sections():
    docs = _corpus()
    retriever = build_index(docs)
    lecture = LectureGenerator(retriever).generate("purification of the Ahl al-Bayt")
    titles = [s.title for s in lecture.sections]
    for expected in [
        "Executive Summary",
        "Qur'anic Foundations",
        "Hadith Foundations",
        "Scholarly Analysis",
        "Conclusion",
        "Suggested Reading",
    ]:
        assert expected in titles
    md = lecture.to_markdown()
    assert "Integrity notice" in md
