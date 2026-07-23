from shia_aalim.generation.crossref import CrossReferencer, build_verse_index
from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType
from shia_aalim.research_loop import build_index


def _doc(id, text, etype, **cit):
    return Document(
        id=id, text=text, evidence_type=etype,
        citation=Citation(source_id=cit.pop("source_id"), evidence_type=etype, **cit),
        confidence=ConfidenceLevel.HIGH, language="en",
    )


def _corpus():
    return [
        _doc("v-5-55", "Your guardian is only Allah His Apostle and the faithful who "
                       "maintain the prayer and give the zakat while bowing down",
             EvidenceType.QURAN, source_id="quran", surah=5, ayah=55),
        _doc("v-112-1", "Say He is Allah the One", EvidenceType.QURAN,
             source_id="quran", surah=112, ayah=1),
        # tafsir that quotes the verse heavily -> explicit
        _doc("t-guardian", "The guardian is only Allah and His Apostle and the faithful "
                           "who maintain the prayer and give the zakat while bowing; this "
                           "establishes the wilayah of Ali", EvidenceType.TAFSIR,
             source_id="al-mizan", volume="6", chapter="commentary"),
        # tafsir on an unrelated topic -> should be floored out
        _doc("t-fasting", "The rulings of fasting in the month of Ramadan and its exemptions",
             EvidenceType.TAFSIR, source_id="al-mizan", volume="2", chapter="fasting"),
        # hadith that cites the reference token 5:55 -> explicit
        _doc("h-ref", "The Imam said regarding the verse of wilayah 5:55 that the faithful "
                      "who gives zakat while bowing is Ali", EvidenceType.HADITH,
             source_id="al-kafi", volume="1", hadith_number="1"),
    ]


def _xref():
    docs = _corpus()
    return CrossReferencer(build_index(docs), build_verse_index(docs))


def test_verse_index_and_lookup():
    idx = build_verse_index(_corpus())
    assert (5, 55) in idx and (112, 1) in idx
    assert _xref().verse(5, 55).id == "v-5-55"


def test_unknown_verse_returns_none():
    assert _xref().related(2, 255) is None


def test_related_links_tafsir_and_hadith_to_verse():
    res = _xref().related(5, 55, k=5)
    assert res is not None
    tafsir_ids = {r.document.id for r in res.tafsir}
    hadith_ids = {r.document.id for r in res.hadith}
    assert "t-guardian" in tafsir_ids           # the on-topic tafsir is linked
    assert "t-fasting" not in tafsir_ids         # the unrelated tafsir is floored out
    assert "h-ref" in hadith_ids                 # the citing narration is linked


def test_link_type_explicit_vs_thematic():
    res = _xref().related(5, 55, k=5)
    by_id = {r.document.id: r for r in res.tafsir + res.hadith}
    assert by_id["t-guardian"].link_type == "explicit"   # quotes the verse text
    assert by_id["h-ref"].link_type == "explicit"        # cites 5:55


def test_verse_not_linked_to_itself():
    res = _xref().related(5, 55, k=5)
    assert all(r.document.id != "v-5-55" for r in res.verses)
