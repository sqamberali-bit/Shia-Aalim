from conftest import FIXTURES

from shia_aalim.ingestion.adapters.quran import build_quran_documents, load_edition
from shia_aalim.ingestion.adapters.thaqalayn import build_hadith_documents, parse_grading
from shia_aalim.models import ConfidenceLevel, EvidenceType, HadithGrade


# ---- Qur'an adapter ----

def test_load_edition_maps_by_ref():
    ed = load_edition(FIXTURES / "quran-ar.min.json")
    assert ed[(1, 1)].startswith("ب")  # bismillah, Arabic
    assert (112, 1) in ed


def test_build_quran_documents():
    docs = build_quran_documents(
        FIXTURES / "quran-ar.min.json",
        FIXTURES / "quran-en.min.json",
        translation_name="Ali Quli Qarai",
    )
    assert len(docs) == 3
    d = next(x for x in docs if x.id == "quran-112-1")
    assert d.evidence_type is EvidenceType.QURAN
    assert d.citation.is_complete()
    assert d.citation.arabic_text  # canonical Arabic preserved
    assert d.text == "Say, He is Allah, the One"
    assert d.citation.translation_source == "Ali Quli Qarai"
    assert d.confidence is ConfidenceLevel.HIGH


def test_quran_adapter_skips_missing_translation(tmp_path):
    import json
    ar = {"quran": [{"chapter": 2, "verse": 1, "text": "الم"}]}
    en = {"quran": []}  # no translation for 2:1
    (tmp_path / "ar.json").write_text(json.dumps(ar), encoding="utf-8")
    (tmp_path / "en.json").write_text(json.dumps(en), encoding="utf-8")
    docs = build_quran_documents(tmp_path / "ar.json", tmp_path / "en.json", translation_name="x")
    assert docs == []  # never invents a translation


# ---- ThaqalaynData hadith adapter ----

def test_parse_grading_extracts_grade_and_source():
    gradings = [
        "Allamah Baqir al-Majlisi: <span class=\"g-weak\">ضَعِيفٌ</span> - Mir'at al 'Uqul (0/11)"
    ]
    grade, source, all_grades = parse_grading(gradings)
    assert grade is HadithGrade.DAIF
    assert "Majlisi" in source and "Mir'at" in source
    assert all_grades == [HadithGrade.DAIF]


def test_parse_grading_multiple_graders_preserved():
    gradings = [
        "Allamah Baqir al-Majlisi: <span>صحيح</span> - Mir'at al 'Uqul",
        "Shaykh Baqir al-Behbudi: <span>ضعيف</span> - Sahih al-Kafi",
    ]
    grade, source, all_grades = parse_grading(gradings)
    assert all_grades == [HadithGrade.SAHIH, HadithGrade.DAIF]
    assert "Behbudi" in source  # disagreement preserved


def test_parse_grading_empty_is_ungraded():
    assert parse_grading(None)[0] is HadithGrade.UNGRADED
    assert parse_grading([])[0] is HadithGrade.UNGRADED


def test_build_hadith_documents_from_fixtures():
    docs = build_hadith_documents(
        FIXTURES / "thaqalayn" / "1", source_id="al-kafi", book_title="Book of Tawheed"
    )
    assert docs
    for d in docs:
        assert d.evidence_type is EvidenceType.HADITH
        assert d.citation.source_id == "al-kafi"
        assert d.citation.is_complete()  # has a locator
        assert d.citation.arabic_text  # Arabic matn carried through
    # the graded fixture yields a real grade + attributable source
    graded = [d for d in docs if d.citation.grade is not HadithGrade.UNGRADED]
    assert graded
    assert graded[0].citation.grade_source


def test_hadith_confidence_is_conservative_across_graders():
    # Fixture 1 (Tawhid 3:3) is graded authentic-ish; fixture 2 (Intellect 1:1) ungraded.
    docs = build_hadith_documents(
        FIXTURES / "thaqalayn" / "1", source_id="al-kafi", book_title="Book of Tawheed"
    )
    for d in docs:
        # a daif/majhul/mursal grade must never yield HIGH confidence
        if d.citation.grade in (HadithGrade.DAIF, HadithGrade.MAJHUL, HadithGrade.MURSAL):
            assert d.confidence.rank <= ConfidenceLevel.LOW.rank
