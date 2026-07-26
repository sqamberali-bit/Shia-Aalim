from conftest import FIXTURES

from shia_aalim.ingestion.adapters.shiavault import _clean_markdown, build_prose_documents
from shia_aalim.models import ConfidenceLevel, EvidenceType


def test_clean_markdown_strips_syntax_html_footnotes_escapes():
    raw = "A *bold* word[^1] with <blockquote>html</blockquote> and al-\\Allamah.\n\n[^1]: def"
    out = _clean_markdown(raw)
    assert "*" not in out
    assert "<" not in out and ">" not in out
    assert "[^1]" not in out
    assert "def" not in out          # footnote definition removed
    assert "al-Allamah" in out       # backslash escape removed


def test_build_prose_documents_basic():
    docs = build_prose_documents(
        FIXTURES / "shiavault" / "sample-book",
        source_id="the-message-subhani",
        evidence_type=EvidenceType.HISTORICAL,
        confidence=ConfidenceLevel.MEDIUM,
    )
    assert docs
    titles = {d.citation.chapter for d in docs}
    assert "Introduction" in titles and "On Patience" in titles
    for d in docs:
        assert d.evidence_type is EvidenceType.HISTORICAL
        assert d.confidence is ConfidenceLevel.MEDIUM
        assert d.citation.is_complete()          # chapter + section locator present
        assert d.citation.page                    # within-book section locator
        assert d.citation.source_id == "the-message-subhani"
        assert "Test Author" in (d.citation.translation_source or "")


def test_prose_volume_is_carried_and_in_id():
    docs = build_prose_documents(
        FIXTURES / "shiavault" / "sample-book",
        source_id="al-mizan",
        evidence_type=EvidenceType.TAFSIR,
        volume="3",
    )
    assert docs
    assert all(d.citation.volume == "3" for d in docs)
    assert all(d.id.startswith("al-mizan-v3-") for d in docs)


def test_prose_skips_short_chapters(tmp_path):
    book = tmp_path / "b"
    book.mkdir()
    (book / "1-tiny.md").write_text("Tiny\n====\n\nshort", encoding="utf-8")
    docs = build_prose_documents(book, source_id="x", evidence_type=EvidenceType.HISTORICAL)
    assert docs == []  # too-short chapter is skipped, never padded/fabricated


def test_prose_source_drops_placeholder_metadata(tmp_path):
    # Upstream metadata sometimes carries "N/A" placeholders; they must not leak
    # into the citation's source string.
    book = tmp_path / "b"
    book.mkdir()
    (book / "metadata.yml").write_text(
        "translator: N/A\npublisher: Ansariyan\nsource_url: http://example.org/x\n",
        encoding="utf-8",
    )
    (book / "1-intro.md").write_text(
        "Intro\n====\n\n" + ("This is a sufficiently long chapter body. " * 4),
        encoding="utf-8",
    )
    docs = build_prose_documents(book, source_id="x", evidence_type=EvidenceType.HADITH)
    assert docs
    src = docs[0].citation.translation_source or ""
    assert "N/A" not in src and "Ansariyan" in src
