"""Unit tests for the ʿIlal al-Sharāʾiʿ adapter (no PDF/PyMuPDF needed)."""

from shia_aalim.ingestion.adapters import ilal
from shia_aalim.models import HadithGrade


def test_volume_part_from_filename():
    assert ilal.volume_part_from_filename("ILLAL AL SHARAIE - V 1 P 3.pdf") == ("1", "3")
    assert ilal.volume_part_from_filename("ILLAL AL SHARAIE - V 2 P 9.pdf") == ("2", "9")
    assert ilal.volume_part_from_filename("random.pdf") == (None, None)


def test_header_regex():
    line = "Illal Al-Sharaie  Volume 1  www.hubeali.com  Page 42 of 186"
    m = ilal._HEADER.search(line)
    assert m and m.group(1) == "1" and m.group(2) == "42" and m.group(3) == "186"


def test_header_regex_variant_spelling():
    line = "Illal Al Sharaie Volume 2 www.hubeali.com Page 5 of 125"
    m = ilal._HEADER.search(line)
    assert m and m.group(1) == "2" and m.group(2) == "5"


def test_clean_page_strips_chrome():
    raw = (
        "Illal Al-Sharaie\n"
        "Volume 1\n"
        "www.hubeali.com\n"
        "Page 42 of 186\n"
        "REASONS FOR THE LAWS\n"
        "\n"
        "The narration text about reasons for prayer.\n"
    )
    out = ilal._clean_page(raw)
    assert "www.hubeali.com" not in out
    assert "Page 42 of 186" not in out
    assert "Illal Al-Sharaie" not in out
    assert "Volume 1" not in out
    assert "REASONS FOR THE LAWS" not in out
    assert "narration text about reasons for prayer" in out


def test_chapter_regex():
    text = "CHAPTER 42 – Reasons for the legislation of Salaat"
    m = ilal._CHAPTER.search(text)
    assert m and m.group(1) == "42"
    assert "Reasons for the legislation of Salaat" in m.group(2)


def test_chapter_regex_colon_separator():
    text = "CHAPTER 15: Reasons for Fasting"
    m = ilal._CHAPTER.search(text)
    assert m and m.group(1) == "15"


def test_split_arabic_english():
    block = (
        "قال الإمام الصادق عليه السلام\n"
        "Imam al-Sadiq (as) said: The reason for prayer\n"
    )
    ar, en = ilal.split_arabic_english(block)
    assert "الإمام الصادق" in ar
    assert "Imam al-Sadiq" in en
    assert "Imam al-Sadiq" not in ar


def test_split_into_chapters():
    pages = [
        ("1", "1", "Preamble text here."),
        ("1", "2", (
            "CHAPTER 1 – Reasons for Prayer\n"
            "The reason for prayer is that it is an acknowledgement of the Lord.\n"
            "\n"
            "CHAPTER 2 – Reasons for Fasting\n"
            "The reason for fasting is to know the pain of hunger.\n"
        )),
    ]
    results = list(ilal._split_into_chapters(pages))
    assert len(results) == 3
    assert results[0][2] == ""  # preamble has no chapter
    assert results[1][2] == "1"
    assert results[1][3] == "Reasons for Prayer"
    assert results[2][2] == "2"
    assert "pain of hunger" in results[2][4]


def test_split_chapter_into_hadiths():
    body = (
        "Introduction to the chapter.\n"
        "Hadith 1\n"
        "He said: The reason for ablution is cleanliness.\n"
        "Hadith 2\n"
        "He said: The reason for ghusl is purification.\n"
    )
    hadiths = ilal._split_chapter_into_hadiths(body)
    assert len(hadiths) == 2
    assert hadiths[0][0] == "1"
    assert "ablution" in hadiths[0][1]
    assert hadiths[1][0] == "2"
    assert "ghusl" in hadiths[1][1]


def test_split_chapter_no_hadith_markers():
    body = "Just some text without any hadith markers present."
    hadiths = ilal._split_chapter_into_hadiths(body)
    assert hadiths == []


def test_never_implies_a_grade():
    assert HadithGrade.UNGRADED.value == "ungraded"
