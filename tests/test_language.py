from conftest import sample_corpus

from shia_aalim.language import Language, detect_language, display_name, is_cross_lingual
from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.research_loop import build_index


def test_detect_english():
    assert detect_language("What does the Qur'an say about justice?") is Language.ENGLISH


def test_detect_arabic():
    # plain Arabic (Arabic yaa/kaf), no Persianate letters
    assert detect_language("ما هو التوحيد في الإسلام") is Language.ARABIC


def test_detect_persian():
    # Persian yeh (ی) / gaf (گ) mark it as Persian, not Arabic
    assert detect_language("توحید در نگاه اسلام چیست") is Language.PERSIAN


def test_detect_urdu():
    # Urdu-specific letters (ہ, ے) mark it as Urdu
    assert detect_language("اسلام میں توحید کیا ہے") is Language.URDU


def test_detect_empty_and_symbols():
    assert detect_language("") is Language.UNKNOWN
    assert detect_language("123 ... !!!") is Language.UNKNOWN


def test_is_cross_lingual_only_for_fa_ur():
    assert is_cross_lingual(Language.PERSIAN)
    assert is_cross_lingual(Language.URDU)
    assert not is_cross_lingual(Language.ARABIC)   # Arabic originals are in the corpus
    assert not is_cross_lingual(Language.ENGLISH)


def test_display_name():
    assert display_name("fa") == "Persian"
    assert display_name("bogus") == "Unknown"


def test_answer_records_query_language():
    gen = AnswerGenerator(build_index(sample_corpus()))
    ans = gen.answer("purify the People of the House", k=3)
    assert ans.query_language == "en"


def test_lexical_index_warns_on_persian_query():
    gen = AnswerGenerator(build_index(sample_corpus()), multilingual=False)
    ans = gen.answer("توحید چیست", k=3)
    assert ans.query_language == "fa"
    assert any("multilingual semantic embedder" in c for c in ans.caveats)


def test_multilingual_index_does_not_warn():
    gen = AnswerGenerator(build_index(sample_corpus()), multilingual=True)
    ans = gen.answer("اسلام میں توحید کیا ہے", k=3)
    assert ans.query_language == "ur"
    # no "needs the ... embedder" warning when multilingual retrieval is active
    assert not any("needs the multilingual" in c for c in ans.caveats)
