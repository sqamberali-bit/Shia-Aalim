"""Unit tests for the Biḥār adapter's text handling (no PDF/PyMuPDF needed)."""

from shia_aalim.ingestion.adapters import bihar


def test_volume_from_filename():
    assert bihar.volume_from_filename("pdfs/BiharAlAnwaar_V1.pdf") == "1"
    assert bihar.volume_from_filename("/x/BiharAlAnwaar_V101.pdf") == "101"
    assert bihar.volume_from_filename("nope.pdf") is None


def test_header_regex_reads_volume_and_page():
    line = "Bihar Al-Anwaar    Volume 45  www.hubeali.com  Page 267 of 532"
    m = bihar._HEADER.search(line)
    assert m and m.group(1) == "45" and m.group(2) == "267" and m.group(3) == "532"


def test_clean_page_strips_running_header_chrome():
    raw = (
        "Bihar Al-Anwaar\n"
        "Volume 45\n"
        "www.hubeali.com\n"
        "Page 267 of 532\n"
        "\n"
        "The actual narration text about Imam al-Husayn-asws is kept intact.\n"
    )
    out = bihar._clean_page(raw)
    assert "www.hubeali.com" not in out
    assert "Page 267 of 532" not in out
    assert "Bihar Al-Anwaar" not in out
    assert "Volume 45" not in out
    assert "narration text about Imam al-Husayn" in out
