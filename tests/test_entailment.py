import pytest
from conftest import DATA, sample_corpus

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.synthesizer import MockSynthesizer
from shia_aalim.grounding.entailment import (
    ClaudeEntailmentJudge,
    LexicalEntailmentJudge,
    MockEntailmentJudge,
    judge_one,
    make_judge,
)
from shia_aalim.grounding.synthesis import verify_synthesis
from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType
from shia_aalim.research_loop import build_index
from shia_aalim.retrieval.retriever import RetrievalResult
from shia_aalim.sources import load_registry_ids


def _ev(text, i=1):
    d = Document(id=f"d{i}", text=text, evidence_type=EvidenceType.QURAN,
                 citation=Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=33, ayah=33),
                 confidence=ConfidenceLevel.HIGH)
    return RetrievalResult(document=d, similarity=0.9, score=0.9)


PURITY = "Allah only desires to repel all impurity from you, O People of the House, and purify you"


# ---- judges ----

def test_lexical_judge_supports_by_overlap():
    j = LexicalEntailmentJudge(min_overlap=0.2)
    assert judge_one(j, "repel impurity from the People of the House", [PURITY]).supported
    assert not judge_one(j, "the price of tea in China rose sharply", [PURITY]).supported


def test_mock_judge_custom_decision():
    j = MockEntailmentJudge(decide=lambda c, p: "yes" in c.lower())
    assert judge_one(j, "yes indeed", ["anything"]).supported
    assert not judge_one(j, "no way", ["anything"]).supported


def test_make_judge_specs():
    assert make_judge("none") is None
    assert isinstance(make_judge("lexical"), LexicalEntailmentJudge)
    assert isinstance(make_judge("mock"), MockEntailmentJudge)
    with pytest.raises(ValueError):
        make_judge("bogus")


def test_make_judge_claude_without_dep_or_key_raises():
    with pytest.raises(Exception) as ei:
        make_judge("claude:claude-sonnet-5")
    assert "anthropic" in str(ei.value).lower() or "api key" in str(ei.value).lower()


def test_claude_parse_verdicts():
    text = "1: SUPPORTED clearly stated\n2: UNSUPPORTED adds new info\n"
    v = ClaudeEntailmentJudge._parse(text, 3)
    assert v[0].supported and not v[1].supported
    assert not v[2].supported  # missing -> default UNSUPPORTED (burden of proof)


# ---- the judge complements the lexical gate in verify_synthesis ----

def test_semantic_judge_rescues_true_paraphrase():
    evd = [_ev(PURITY)]
    para = "The Prophet's kin are divinely kept immaculate [1]."
    assert not verify_synthesis(para, evd, judge=LexicalEntailmentJudge()).grounded
    smart = MockEntailmentJudge(decide=lambda c, p: "impurity" in " ".join(p).lower())
    assert verify_synthesis(para, evd, judge=smart).grounded


def test_semantic_judge_rejects_lexical_match_contradiction():
    evd = [_ev(PURITY)]
    tricky = "Allah desires impurity to remain upon the People of the House [1]."
    assert verify_synthesis(tricky, evd, judge=LexicalEntailmentJudge()).grounded  # lexical false positive
    strict = MockEntailmentJudge(decide=lambda c, p: "remain" not in c.lower())
    assert not verify_synthesis(tricky, evd, judge=strict).grounded


def test_default_judge_preserves_lexical_behaviour():
    evd = [_ev(PURITY)]
    # no judge -> defaults to lexical -> same as passing LexicalEntailmentJudge
    good = "Allah desires to purify the People of the House [1]."
    assert verify_synthesis(good, evd).grounded


# ---- wired through AnswerGenerator ----

def test_answer_generator_uses_judge():
    r = build_index(sample_corpus())
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    reject_all = MockEntailmentJudge(decide=lambda c, p: False)
    gen = AnswerGenerator(r, synthesizer=MockSynthesizer(), known_source_ids=known, judge=reject_all)
    ans = gen.answer("purification of the People of the House", k=3)
    assert ans.summary is None  # judge rejected everything -> synthesis withheld
