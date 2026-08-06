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


# --- stateless restart-proof tokens (MCP_OAUTH_SECRET) ----------------------

def _oauth_params():
    from mcp.server.auth.provider import AuthorizationParams

    return AuthorizationParams(
        state="s1", scopes=["claudeai"], code_challenge="c" * 43,
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        redirect_uri_provided_explicitly=True, resource="https://x/mcp",
    )


def test_tokens_survive_provider_restart(monkeypatch):
    from shia_aalim.mcp_oauth import ShiaAalimOAuthProvider

    monkeypatch.setenv("MCP_OAUTH_SECRET", "test-secret-123")
    p1 = ShiaAalimOAuthProvider()
    client = asyncio.run(p1.get_client("shia-aalim-mcp"))
    # full handshake on instance 1
    url = asyncio.run(p1.authorize(client, _oauth_params()))
    code = url.split("code=")[1].split("&")[0]
    import urllib.parse
    code = urllib.parse.unquote(code)
    ac = asyncio.run(p1.load_authorization_code(client, code))
    assert ac is not None and ac.code_challenge == "c" * 43
    tok = asyncio.run(p1.exchange_authorization_code(client, ac))

    # "restart": a brand-new provider instance must accept everything
    p2 = ShiaAalimOAuthProvider()
    at = asyncio.run(p2.load_access_token(tok.access_token))
    assert at is not None and at.client_id == "shia-aalim-mcp" and "claudeai" in at.scopes
    rt = asyncio.run(p2.load_refresh_token(client, tok.refresh_token))
    assert rt is not None
    tok2 = asyncio.run(p2.exchange_refresh_token(client, rt, rt.scopes))
    assert asyncio.run(p2.load_access_token(tok2.access_token)) is not None

    # unknown (pre-restart DCR) client ids still resolve
    dyn = asyncio.run(p2.get_client("dyn-forgotten-after-restart"))
    assert dyn is not None


def test_tampered_and_cross_client_tokens_rejected(monkeypatch):
    from shia_aalim.mcp_oauth import ShiaAalimOAuthProvider

    monkeypatch.setenv("MCP_OAUTH_SECRET", "test-secret-123")
    p = ShiaAalimOAuthProvider()
    tok = p._issue("shia-aalim-mcp", ["claudeai"], None)
    tampered = tok.access_token[:-4] + ("aaaa" if not tok.access_token.endswith("aaaa") else "bbbb")
    assert asyncio.run(p.load_access_token(tampered)) is None
    # refresh token bound to its client id
    other = asyncio.run(p.get_client("someone-else"))
    assert asyncio.run(p.load_refresh_token(other, tok.refresh_token)) is None
    # a different secret invalidates everything (rotation = global revoke)
    monkeypatch.setenv("MCP_OAUTH_SECRET", "rotated")
    assert asyncio.run(p.load_access_token(tok.access_token)) is None


def test_without_secret_falls_back_to_memory(monkeypatch):
    from shia_aalim.mcp_oauth import ShiaAalimOAuthProvider

    monkeypatch.delenv("MCP_OAUTH_SECRET", raising=False)
    p1 = ShiaAalimOAuthProvider()
    tok = p1._issue("shia-aalim-mcp", [], None)
    assert asyncio.run(p1.load_access_token(tok.access_token)) is not None
    p2 = ShiaAalimOAuthProvider()  # restart loses memory — documented behavior
    assert asyncio.run(p2.load_access_token(tok.access_token)) is None
