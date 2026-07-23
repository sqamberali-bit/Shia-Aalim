import json

from conftest import DATA

from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade
from shia_aalim.rijal import (
    NarratorIndex,
    extract_chain,
    is_narrator_name,
    normalize_name,
    parse_grade_source,
)

SAMPLE = DATA / "knowledge" / "sample" / "sample.jsonl"


# --- chain extraction on REAL corpus text ----------------------------------

REAL_ISNAD = (
    "Abu Ja’far Muhammad Bin Yaqoub informed us saying, ‘Ali Bin Ibrahim Bin Hashim "
    "narrated to me, from his father, from Al Hassan Bin Ibrahim, from Yunus Bin Abdul "
    "Rahman, from Ali Bin Mansour who said, ‘Hisham Bin Al Hakam said to me, ‘There was "
    "an atheist in Egypt.’"
)


def test_extract_chain_reads_real_isnad():
    r = extract_chain(REAL_ISNAD)
    assert r.has_chain
    # the ordered narrators as they appear (relational 'his father' kept in the chain)
    assert r.narrators[0] == "Abu Ja’far Muhammad Bin Yaqoub"
    assert "Ali Bin Ibrahim Bin Hashim" in r.narrators
    assert "his father" in r.narrators
    assert "Yunus Bin Abdul Rahman" in r.narrators
    assert r.narrators[-1] == "Ali Bin Mansour"     # chain ends at 'who said'
    # the matn (content) is separated out, chain names not in it
    assert r.matn.startswith("Hisham Bin Al Hakam said to me")


def test_extract_chain_handles_or_from_and_markup():
    txt = ("Ali Bin Ibrahim, from Muhammad Bin Is’haq Al Khaffaf, or from his father, "
           "from Muhammad Bin Is’haq<sup>asws</sup> who said, ‘Abdullah Al-Daysani asked.’")
    r = extract_chain(txt)
    assert r.narrators == [
        "Ali Bin Ibrahim", "Muhammad Bin Is’haq Al Khaffaf", "his father", "Muhammad Bin Is’haq",
    ]


def test_no_chain_when_no_matn_marker():
    r = extract_chain("A general statement with no isnad structure at all.")
    assert not r.has_chain and r.narrators == []


def test_is_narrator_name_filters_relational_tokens():
    assert is_narrator_name("Yunus Bin Abdul Rahman")
    assert not is_narrator_name("his father")
    assert not is_narrator_name("A number of our companions")


def test_normalize_name_folds_ibn_and_al():
    assert normalize_name("Ali Ibn Ibrahim") == normalize_name("Ali Bin Ibrahim")
    assert normalize_name("Al-Hassan Bin Ibrahim") == normalize_name("Al Hassan Bin Ibrahim")


# --- grade attribution parsing ---------------------------------------------

def test_parse_grade_source_splits_attributors():
    gs = ("Allamah Baqir al-Majlisi: مجهول - Mir‘at al ‘Uqul (1/235); "
          "Shaykh Baqir al-Behbudi: ضعيف - Sahih al-Kafi")
    attrs = parse_grade_source(gs)
    assert [a.attributor for a in attrs] == ["Allamah Baqir al-Majlisi", "Shaykh Baqir al-Behbudi"]
    assert attrs[0].grade == "مجهول" and attrs[0].work.startswith("Mir")
    assert attrs[1].grade == "ضعيف"


def test_parse_grade_source_empty():
    assert parse_grade_source(None) == []
    assert parse_grade_source("") == []


# --- narrator index over the committed sample corpus -----------------------

def _sample_docs():
    docs = []
    for line in SAMPLE.read_text(encoding="utf-8").splitlines():
        docs.append(Document.from_dict(json.loads(line)))
    return docs


def test_index_builds_over_sample_and_finds_a_real_narrator():
    idx = NarratorIndex(_sample_docs())
    assert idx.narrator_count > 0
    summary = idx.grade_summary()
    assert summary["hadith"] >= 1
    # sample al-Kafi narrations are graded by Majlisi / Behbudi
    attributors = {a["attributor"] for a in summary["attributors"]}
    assert any("Majlisi" in a for a in attributors)

    prof = idx.lookup("Yunus Bin Abdul Rahman")
    assert prof.narration_count >= 1
    assert prof.matched_names
    # every mention resolves back to a real hadith document
    for men in prof.mentions:
        assert idx.document(men.doc_id) is not None


def test_lookup_unknown_narrator_is_empty_not_error():
    idx = NarratorIndex(_sample_docs())
    prof = idx.lookup("Zzz Nonexistent Narrator")
    assert prof.narration_count == 0 and prof.mentions == []


def test_index_ignores_non_hadith():
    quran = Document(
        id="q1", text="Some verse text who said nothing", evidence_type=EvidenceType.QURAN,
        citation=Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=1, ayah=1),
        confidence=ConfidenceLevel.HIGH,
    )
    idx = NarratorIndex([quran])
    assert idx.grade_summary()["hadith"] == 0
