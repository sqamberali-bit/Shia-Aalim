from shia_aalim.ingestion.normalize import (
    normalize_arabic,
    normalize_for_search,
    strip_tashkeel,
    tokens,
)


def test_strip_tashkeel_removes_diacritics():
    vocalised = "الرَّحْمَٰنِ الرَّحِيمِ"
    bare = strip_tashkeel(vocalised)
    assert "ً" not in bare  # no fatha-tanwin etc.
    assert "رحم" in normalize_for_search(vocalised)


def test_alef_folding_makes_variants_match():
    assert normalize_for_search("أحمد") == normalize_for_search("احمد")
    assert normalize_for_search("إسلام") == normalize_for_search("اسلام")


def test_alef_maksura_and_taa_marbuta_fold():
    assert normalize_for_search("علی") == normalize_for_search("علي")
    # taa marbuta -> haa
    assert normalize_for_search("مكة").endswith("ه")


def test_persian_kaf_yeh_fold():
    assert normalize_for_search("کتاب") == normalize_for_search("كتاب")


def test_tatweel_removed():
    assert "ـ" not in normalize_arabic("محـــمد")


def test_search_form_is_lowercased_and_collapsed():
    assert normalize_for_search("  Allah   AKBAR ") == "allah akbar"


def test_tokens_nonempty():
    assert tokens("إنَّ اللَّهَ") == ["ان", "الله"]
