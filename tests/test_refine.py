import pytest

from conftest import sample_corpus

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.refine import MockRefiner, make_refiner
from shia_aalim.research_loop import build_index


def test_mock_refiner_normalises_terms():
    r = MockRefiner().refine("what is tawheed and namaz")
    assert r.changed
    assert "tawhid" in r.corrected and "salat" in r.corrected


def test_mock_refiner_leaves_clean_query():
    r = MockRefiner().refine("what does the quran say about justice")
    # 'quran' is already canonical here; nothing to change beyond it
    assert not r.changed or r.corrected == "what does the quran say about justice"


def test_make_refiner_specs():
    assert make_refiner("none") is None
    assert isinstance(make_refiner("mock"), MockRefiner)
    with pytest.raises(ValueError):
        make_refiner("bogus")


def test_answer_records_refined_query_and_keeps_original():
    gen = AnswerGenerator(build_index(sample_corpus()), refiner=MockRefiner())
    ans = gen.answer("tawheed of the intellect", k=3)
    # original question preserved for display...
    assert ans.question == "tawheed of the intellect"
    # ...and the corrected form recorded + surfaced
    assert ans.refined_query == "tawhid of the intellect"
    assert any("Interpreted your question as" in c for c in ans.caveats)


def test_non_english_without_verifier_is_withheld():
    from shia_aalim.generation.synthesizer import MockSynthesizer

    gen = AnswerGenerator(build_index(sample_corpus()), synthesizer=MockSynthesizer())
    ans = gen.answer("guardian and prayer", k=3, answer_language="ur")
    assert ans.answer_language == "ur"
    assert ans.summary is None  # no cross-lingual verifier -> not emitted
    assert any("verifier" in c for c in ans.caveats)


def test_english_answer_still_synthesizes_with_old_signature_synthesizer():
    # a synthesizer with the pre-language two-arg signature must still work for English
    class OldSynth:
        def synthesize(self, q, ev):
            return ev[0].document.text.strip() + " [1]"

    gen = AnswerGenerator(build_index(sample_corpus()), synthesizer=OldSynth())
    ans = gen.answer("intellect worship paradise", k=2, answer_language="en")
    assert ans.summary is not None
