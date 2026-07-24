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


def test_create_mcp_shares_a_prebuilt_stack():
    # Passing an existing Stack means the corpus/index is not rebuilt.
    stack = web.build_stack(web.AppConfig(knowledge_dir=ROOT / "data" / "knowledge" / "sample"))
    server = mcp_server.create_mcp(stack=stack)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert "search_sources" in names


def test_mounted_mcp_endpoint_handshakes_and_keeps_web_ui(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*")  # let the TestClient host through
    stack = web.build_stack(web.AppConfig(knowledge_dir=ROOT / "data" / "knowledge" / "sample"))
    mcp, mcp_app = mcp_server.build_http_app(stack=stack)

    from fastapi import FastAPI
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_server.session_lifespan(mcp):
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    app.mount("/", mcp_app)

    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}}}
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               # a real deploy allows its own host; TestClient uses "testserver"
               "Host": "localhost"}
    with TestClient(app) as client:
        assert client.get("/ping").status_code == 200  # host app routes survive
        r = client.post("/mcp", json=init, headers=headers)
        assert r.status_code == 200
        assert "shia-aalim" in r.text


def test_bearer_token_guards_the_endpoint(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from contextlib import asynccontextmanager

    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*")
    stack = web.build_stack(web.AppConfig(knowledge_dir=ROOT / "data" / "knowledge" / "sample"))
    mcp, mcp_app = mcp_server.build_http_app(stack=stack, bearer_token="secret")

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_server.session_lifespan(mcp):
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp_app)

    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}}}
    base = {"Content-Type": "application/json",
            "Accept": "application/json, text/event-stream", "Host": "localhost"}
    with TestClient(app) as client:
        assert client.post("/mcp", json=init, headers=base).status_code == 401
        ok = client.post("/mcp", json=init, headers={**base, "Authorization": "Bearer secret"})
        assert ok.status_code == 200
