"""Adapter tests for Wasāʾil al-Shīʿa (PDF, per-hadith) and Mafātīḥ al-Jinān (JSON).

Both adapters are exercised on synthetic inputs shaped exactly like the real
sources, so the tests run without the (large, external) corpus files.
"""

import json

from shia_aalim.ingestion.adapters.mafatih import build_mafatih_documents
from shia_aalim.ingestion.adapters.wasail import (
    split_arabic_english,
    volume_from_filename,
)
from shia_aalim.models import ConfidenceLevel, EvidenceType, HadithGrade

# --- Wasail ----------------------------------------------------------------


def test_wasail_volume_from_filename():
    assert volume_from_filename("ws1_eng.pdf") == "1"
    assert volume_from_filename("/a/b/ws12_eng.pdf") == "12"
    assert volume_from_filename("random.pdf") is None


def test_split_arabic_english_separates_by_script():
    block = (
        "قال أبو عبد الله عليه السلام: من صدق لسانه زكى عمله\n"
        "Abu Abdullah (peace be upon him) said: Whoever is truthful in speech,\n"
        "his deeds become pure.\n"
    )
    arabic, english = split_arabic_english(block)
    assert "أبو عبد الله" in arabic
    assert "Abu Abdullah" in english
    # the Arabic must not leak into the English side (and vice versa)
    assert "Abu Abdullah" not in arabic
    assert "أبو عبد الله" not in english


def test_split_arabic_english_handles_missing_sides():
    assert split_arabic_english("Only English here.") == ("", "Only English here.")
    ar, en = split_arabic_english("بسم الله الرحمن الرحيم")
    assert ar and not en


# --- Mafatih ---------------------------------------------------------------


def _mafatih_fixture(tmp_path):
    data = [
        {
            "title": "\nباب اول: ادعیه\n",
            "sections": [
                {
                    "title": "\nفصل اول\n",
                    "articles": [
                        {
                            "title": "\nتعقیبات مشترک\n",
                            "href": "/x",
                            "items": [
                                {"type": "AboutText", "content": "پس از نماز بگو:"},
                                {"type": "Text", "content": "لَا إلهَ إلَّا اللّهُ إلَهاً واحِداً وَ نَحْنُ لَهُ مُسْلِمُونَ"},
                                {"type": "Translate", "content": "هیچ معبودی جز خدا نیست"},
                                {"type": "Text", "content": "\n"},  # spacer -> skipped
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    p = tmp_path / "chapters.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_mafatih_builds_one_doc_per_arabic_passage(tmp_path):
    docs = build_mafatih_documents(_mafatih_fixture(tmp_path))
    assert len(docs) == 1  # the whitespace-only Text item is skipped, never padded
    d = docs[0]
    assert d.evidence_type is EvidenceType.SCHOLARLY_OPINION
    assert d.confidence is ConfidenceLevel.MEDIUM
    assert d.language == "ar"
    assert "لَا إلهَ إلَّا اللّهُ" in d.text
    assert d.citation.arabic_text == d.text


def test_mafatih_citation_is_complete_and_carries_the_path(tmp_path):
    d = build_mafatih_documents(_mafatih_fixture(tmp_path))[0]
    c = d.citation
    assert c.is_complete()
    assert c.source_id == "mafatih-al-jinan"
    # bab / fasl / article path, flattened (no stray newlines)
    assert "باب اول: ادعیه" in c.chapter and "تعقیبات مشترک" in c.chapter
    assert "\n" not in c.chapter
    assert c.page  # within-book locator


def test_mafatih_attaches_persian_translation_named_as_persian(tmp_path):
    d = build_mafatih_documents(_mafatih_fixture(tmp_path))[0]
    assert d.citation.translation == "هیچ معبودی جز خدا نیست"
    src = d.citation.translation_source or ""
    # the translation must be labelled Persian — never presented as English
    assert "Persian" in src
    assert "English" not in src


def test_mafatih_missing_or_bad_file_yields_nothing(tmp_path):
    assert build_mafatih_documents(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert build_mafatih_documents(bad) == []


def test_mafatih_never_implies_a_grade(tmp_path):
    # A devotional compilation carries no rijal grading; it must not imply one.
    d = build_mafatih_documents(_mafatih_fixture(tmp_path))[0]
    assert d.citation.grade is HadithGrade.UNGRADED
    assert d.citation.grade_source is None
