"""Unit tests for the plain-text (OCR'd volume) adapter — no external files."""

from shia_aalim.ingestion.adapters import plaintext
from shia_aalim.models import ConfidenceLevel, EvidenceType


def test_clean_text_strips_toc_headers_and_garbled_lines():
    raw = (
        "Chapter One: real body text that should absolutely be kept in the output.\n"
        "Introduction .................................................... 12\n"   # dotted TOC leader
        "Al-Mizan Volume 1\n"                                                       # running header
        "42\n"                                                                      # lone page number
        "www.tawheed.com.au\n"                                                      # footer url
        "الالتلاتلاتلاخ ختلاخ تلاخ ةى ةى ٌى ٌى ٌى ٌى ٌى\n"                          # garbled OCR (low ascii)
        "Another clean sentence of commentary about tawhid and divine justice.\n"
    )
    out = plaintext.clean_text(raw)
    assert "real body text that should absolutely be kept" in out
    assert "Another clean sentence of commentary" in out
    assert "www.tawheed.com.au" not in out
    assert "Al-Mizan Volume 1" not in out
    assert "................" not in out


def test_volume_from_filename():
    assert plaintext.volume_from_filename("/x/1.txt") == "1"
    assert plaintext.volume_from_filename("40.txt") == "40"


def test_build_textbook_documents(tmp_path):
    body = ("Commentary paragraph number %d discussing the verse in depth with "
            "enough words to survive chunking and the minimum length filter. " )
    f = tmp_path / "3.txt"
    f.write_text("".join(body % i for i in range(60)), encoding="utf-8")
    docs = plaintext.build_textbook_documents(
        f, source_id="al-mizan", evidence_type=EvidenceType.TAFSIR,
        translation_source="Test edition",
    )
    assert docs
    for d in docs:
        assert d.evidence_type is EvidenceType.TAFSIR
        assert d.confidence is ConfidenceLevel.MEDIUM
        assert d.citation.volume == "3"          # from filename
        assert d.citation.is_complete()          # volume + section locator
        assert d.id.startswith("al-mizan-v3-")
