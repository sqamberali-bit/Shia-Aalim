import pytest
from conftest import DATA, sample_corpus

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.decompose import (
    RuleBasedDecomposer,
    make_decomposer,
)
from shia_aalim.research_loop import build_index
from shia_aalim.sources import load_registry_ids


D = RuleBasedDecomposer()


def test_splits_conjoined_interrogative_clauses():
    parts = D.decompose(
        "What does the Qur'an say about the Ahl al-Bayt and how do hadith describe their purification?"
    )
    assert len(parts) == 2
    assert parts[0].endswith("?") and parts[1].endswith("?")


def test_splits_enumeration_and_semicolons():
    assert len(D.decompose("Compare tawhid and shirk; then list the signs of faith")) == 2
    assert len(D.decompose("1. the nature of intellect 2. the reward of knowledge 3. the signs of faith")) == 3


def test_atomic_question_unchanged():
    q = "What does the Qur'an say about the purification of the Ahl al-Bayt?"
    assert D.decompose(q) == [q]


def test_does_not_split_noun_phrase_conjunction():
    # "and" joins noun phrases, not two questions -> must NOT split.
    assert len(D.decompose("the People of the House and their purification")) == 1


def test_make_decomposer_specs():
    assert make_decomposer("none") is None
    assert isinstance(make_decomposer("rule"), RuleBasedDecomposer)
    with pytest.raises(ValueError):
        make_decomposer("bogus")


def test_make_decomposer_claude_without_dep_or_key_raises():
    with pytest.raises(Exception) as ei:
        make_decomposer("claude:claude-sonnet-5")
    assert "anthropic" in str(ei.value).lower() or "api key" in str(ei.value).lower()


# ---- AnswerGenerator integration ----

def _gen(decomposer=None):
    r = build_index(sample_corpus())
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    return AnswerGenerator(r, known_source_ids=known, decomposer=decomposer)


def test_answer_records_sub_questions_when_decomposed():
    q = "What is said about guardianship wilayah and how is the intellect described?"
    ans = _gen(RuleBasedDecomposer()).answer(q, k=3)
    assert len(ans.sub_questions) == 2
    assert any("decomposed" in c.lower() for c in ans.caveats)


def test_answer_no_sub_questions_when_atomic():
    ans = _gen(RuleBasedDecomposer()).answer("purification of the People of the House", k=3)
    assert ans.sub_questions == []


def test_decomposition_merges_evidence_from_each_part():
    # A decomposer that returns two distinct topics; the merged evidence must
    # contain the best doc for EACH (which a single blended query can starve).
    class TwoParts:
        def decompose(self, q):
            return ["purification of the People of the House", "intellect worship paradise"]

    ans = _gen(TwoParts()).answer("purification and intellect", k=2)
    ids = {c.citations[0].reference_string() for c in ans.claims}
    assert any("33:33" in x for x in ids)                 # purification part
    assert any("al-kafi" in x for x in ids)               # intellect part
