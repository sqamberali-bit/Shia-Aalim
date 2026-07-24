import pytest
from conftest import DATA, sample_corpus

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.synthesizer import (
    MockSynthesizer,
    format_evidence_block,
    make_synthesizer,
)
from shia_aalim.grounding.synthesis import verify_synthesis
from shia_aalim.research_loop import build_index
from shia_aalim.sources import load_registry_ids


def _evidence(query="purification of the People of the House", k=3):
    return build_index(sample_corpus()).retrieve(query, k=k)


# ---- verify_synthesis ----

def test_verify_accepts_grounded_cited_prose():
    ev = _evidence()
    text = MockSynthesizer().synthesize("q", ev)
    assert verify_synthesis(text, ev).grounded


def test_verify_flags_invented_citation():
    ev = _evidence()
    rep = verify_synthesis("The household is purified [1] and a secret [9].", ev)
    assert not rep.grounded
    assert 9 in rep.invented_citations


def test_verify_flags_wrong_attribution():
    ev = _evidence()
    rep = verify_synthesis("The Tokyo stock market rose three percent today [1].", ev)
    assert not rep.grounded
    assert rep.ungrounded_sentences


def test_verify_flags_uncited_hallucinated_sentence():
    ev = _evidence()
    rep = verify_synthesis(
        "The household is purified [1]. Aliens landed in Paris yesterday.", ev
    )
    assert not rep.grounded
    assert rep.uncited_sentences


def test_verify_allows_multisentence_quote_with_trailing_marker():
    # A quote spanning two sentences with the marker only on the last is fine.
    ev = _evidence()
    passage = ev[0].document.text
    half = passage[: len(passage) // 2]
    rest = passage[len(passage) // 2:]
    rep = verify_synthesis(f"{half}. {rest} [1]", ev)
    assert not rep.uncited_sentences


# ---- factory ----

def test_make_synthesizer_specs():
    assert make_synthesizer("none") is None
    assert isinstance(make_synthesizer("mock"), MockSynthesizer)
    with pytest.raises(ValueError):
        make_synthesizer("bogus")


def test_make_synthesizer_claude_without_dep_or_key_raises():
    with pytest.raises(Exception) as ei:
        make_synthesizer("claude:claude-sonnet-5")
    msg = str(ei.value).lower()
    assert "anthropic" in msg or "api key" in msg


def test_format_evidence_block_is_numbered():
    ev = _evidence()
    block = format_evidence_block(ev)
    assert block.startswith("[1]")
    assert "[2]" in block


# ---- AnswerGenerator integration (the firewall in place) ----

def _gen(synth):
    r = build_index(sample_corpus())
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    return AnswerGenerator(r, synthesizer=synth, known_source_ids=known)


def test_answer_keeps_verified_synthesis():
    ans = _gen(MockSynthesizer()).answer("purification of the People of the House", k=3)
    assert ans.summary is not None


def test_answer_rejects_unverified_synthesis():
    class Hallucinator:
        def synthesize(self, q, ev):
            return "The household is purified [1]. Aliens landed in Paris yesterday."

    ans = _gen(Hallucinator()).answer("purification of the People of the House", k=3)
    assert ans.summary is None  # withheld
    assert any("REJECTED" in c for c in ans.caveats)


def test_paraphrased_synthesis_accepted_by_semantic_judge():
    # THE fix: genuine AI synthesis paraphrases the evidence, so the lexical
    # word-overlap judge wrongly rejects it. With a semantic (LLM) judge — modelled
    # here as a mock that entails — the paraphrase is accepted, not withheld.
    from shia_aalim.grounding.entailment import MockEntailmentJudge

    class Paraphraser:
        def synthesize(self, q, ev, *, language="English"):
            # faithful synthesis, but almost no shared content words with the verse
            return "Divine will removes impurity from the Prophet's household [1]."

    r = build_index(sample_corpus())
    # lexical judge alone would reject this (low overlap) -> withheld
    lexical_only = AnswerGenerator(r, synthesizer=Paraphraser())
    assert lexical_only.answer("purification of the People of the House", k=3).summary is None
    # with a semantic judge (mock: always entails), the synthesis is kept
    semantic = AnswerGenerator(
        r, synthesizer=Paraphraser(),
        cross_lingual_judge=MockEntailmentJudge(decide=lambda c, p: True),
    )
    assert semantic.answer("purification of the People of the House", k=3).summary is not None


def test_evidence_block_includes_arabic_and_english():
    from shia_aalim.generation.synthesizer import format_evidence_block
    from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType
    from shia_aalim.retrieval.retriever import RetrievalResult

    doc = Document(
        id="v", text="Your guardian is only Allah, His Apostle, and the faithful",
        evidence_type=EvidenceType.QURAN,
        citation=Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=5, ayah=55,
                          arabic_text="إِنَّمَا وَلِيُّكُمُ اللَّهُ", translation="Your guardian is only Allah…"),
        confidence=ConfidenceLevel.HIGH,
    )
    block = format_evidence_block([RetrievalResult(document=doc, similarity=0.9, score=0.9)])
    assert "ARABIC: إِنَّمَا وَلِيُّكُمُ اللَّهُ" in block
    assert "ENGLISH:" in block
    assert "Qur'an 5:55" in block


def test_answer_survives_synthesizer_exception():
    class Broken:
        def synthesize(self, q, ev):
            raise RuntimeError("api down")

    ans = _gen(Broken()).answer("purification of the People of the House", k=3)
    assert ans.summary is None
    assert ans.claims  # extractive evidence still returned


# ---- Lecture narrative synthesis ----

def _lecture(synth):
    from shia_aalim.generation.lecture import LectureGenerator
    return LectureGenerator(build_index(sample_corpus()), synthesizer=synth).generate(
        "purification of the People of the House"
    )


def test_lecture_without_synthesizer_keeps_lecturer_notes():
    lec = _lecture(None)
    es = next(s for s in lec.sections if s.title == "Executive Summary")
    assert not es.synthesized and es.note


def test_lecture_synthesizes_grounded_narrative_sections():
    lec = _lecture(MockSynthesizer())
    grounded = ["Executive Summary", "Introduction", "Practical Lessons",
                "Common Misconceptions", "Conclusion"]
    for title in grounded:
        s = next(x for x in lec.sections if x.title == title)
        assert s.synthesized and s.body and not s.note
    # Reflection Points is never auto-written (open questions, not grounded claims)
    refl = next(s for s in lec.sections if s.title == "Reflection Points")
    assert not refl.synthesized and refl.note
    assert "Synthesized" in lec.to_markdown()


def test_lecture_withholds_ungrounded_synthesis():
    class Hallucinator:
        def synthesize(self, q, ev):
            return "Aliens have colonised the surface of Mars this week."

    lec = _lecture(Hallucinator())
    es = next(s for s in lec.sections if s.title == "Executive Summary")
    assert not es.synthesized
    assert "withheld" in es.note.lower()
