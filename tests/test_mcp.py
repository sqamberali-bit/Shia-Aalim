import asyncio

import pytest

from conftest import ROOT

pytest.importorskip("mcp")  # optional extra; skip cleanly when absent

from shia_aalim import mcp_server, web  # noqa: E402


def _server():
    cfg = web.AppConfig(knowledge_dir=ROOT / "data" / "knowledge" / "sample")
    return mcp_server.create_mcp(cfg)


def _call(server, name, args) -> str:
    res = asyncio.run(server.call_tool(name, args))
    if isinstance(res, tuple):
        res = res[0]
    return "\n".join(getattr(c, "text", str(c)) for c in res)


def test_tools_are_registered():
    server = _server()
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"search_sources", "get_quran_verse", "verse_cross_references",
            "lookup_narrator", "list_books"} <= names


def test_search_returns_cited_passages():
    out = _call(_server(), "search_sources", {"query": "guardian wali prayer zakat", "k": 2})
    assert "Qur'an 5:55" in out
    assert "Arabic:" in out and "English:" in out and "Urdu:" in out


def test_get_quran_verse_trilingual():
    out = _call(_server(), "get_quran_verse", {"surah": 5, "ayah": 55})
    assert "[Qur'an 5:55]" in out
    assert "Arabic:" in out and "Urdu:" in out


def test_get_unknown_verse_is_graceful():
    out = _call(_server(), "get_quran_verse", {"surah": 114, "ayah": 1})
    assert "not in the loaded corpus" in out


def test_list_books_reports_the_corpus():
    out = _call(_server(), "list_books", {})
    assert "quran" in out and "al-kafi" in out


def test_search_respects_type_filter():
    out = _call(_server(), "search_sources",
                {"query": "intellect worship", "k": 5, "evidence_types": ["hadith"]})
    # only hadith passages -> no Qur'an reference lines
    assert "· quran ·" not in out
