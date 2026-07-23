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


def test_answer_survives_synthesizer_exception():
    class Broken:
        def synthesize(self, q, ev):
            raise RuntimeError("api down")

    ans = _gen(Broken()).answer("purification of the People of the House", k=3)
    assert ans.summary is None
    assert ans.claims  # extractive evidence still returned
