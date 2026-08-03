"""MCP server — expose the Shia-Aalim corpus to Claude as tools.

Model Context Protocol (MCP) lets Claude Desktop / claude.ai call external tools.
This server wraps the *retrieval* side of Shia-Aalim (no LLM of its own — Claude
is the LLM) so Claude can pull cited passages from the whole corpus and ground
its own answers on them. It reuses the same corpus, index, cross-referencer and
rijāl index as the web app (via :func:`shia_aalim.web.build_stack`).

Tools exposed:
  * ``search_sources``       — semantic/lexical search over the corpus (the core RAG tool)
  * ``get_quran_verse``      — a verse in Arabic + English + Urdu with its reference
  * ``verse_cross_references``— tafsir + narrations related to a verse
  * ``lookup_narrator``      — narrations whose chain mentions a narrator, with gradings
  * ``list_books``           — which source books are in the corpus

Transports: ``stdio`` (local, for Claude Desktop) and ``sse`` /
``streamable-http`` (remote, so it can run on a host and Claude connects by URL).

``mcp`` is an optional extra: ``pip install -e ".[mcp]"``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from . import web
from .models import EvidenceType
from .retrieval.retriever import RetrievalResult

_MCP_HINT = (
    "The MCP server needs the `mcp` package (optional extra):\n\n"
    "    pip install -e \".[mcp]\"\n"
)


# --- rendering: cited passages Claude can read and quote --------------------

def _render(results: list[RetrievalResult], *, max_chars: int = 1200) -> str:
    if not results:
        return "No relevant passages found in the corpus for that query."
    blocks: list[str] = []
    for r in results:
        d = r.document
        c = d.citation
        head = f"[{c.reference_string()} · {d.evidence_type.value} · confidence={d.confidence.value}"
        if c.grade and c.grade.value != "ungraded":
            head += f" · grade={c.grade.value}"
            if c.grade_source:
                head += f" ({c.grade_source})"
        head += "]"
        parts = [head]
        if d.evidence_type is EvidenceType.QURAN:
            if c.arabic_text:
                parts.append(f"Arabic: {c.arabic_text.strip()}")
            parts.append(f"English: {d.text.strip()}")
            if c.translation_ur:
                parts.append(f"Urdu: {c.translation_ur.strip()}")
        else:
            text = d.text.strip()
            if len(text) > max_chars:
                text = text[:max_chars] + " …"
            parts.append(text)
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _transport_security():
    """DNS-rebinding / Host-header policy for the HTTP transports.

    A hosted MCP endpoint sits behind an unpredictable public domain (e.g. an HF
    Space URL), which the default localhost-only allowlist would reject with 421.
    Configure it via env:

      * ``MCP_ALLOWED_HOSTS``   — comma-separated Host values to allow
        (e.g. ``my-space.hf.space``). ``*`` disables Host/Origin checks entirely
        (rely on ``MCP_BEARER_TOKEN`` + HTTPS instead).
      * ``MCP_ALLOWED_ORIGINS`` — comma-separated allowed Origins (optional).

    With nothing set, the library default (localhost only) stands — correct for
    local stdio/desktop use.
    """
    try:
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError:  # pragma: no cover - optional extra
        return None
    hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    origins = [o.strip() for o in os.environ.get("MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if not hosts and not origins:
        return None
    if "*" in hosts or "*" in origins:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(allowed_hosts=hosts or ["*"], allowed_origins=origins or ["*"])


def _types(evidence_types: Optional[list[str]]) -> Optional[list[EvidenceType]]:
    if not evidence_types:
        return None
    out: list[EvidenceType] = []
    for t in evidence_types:
        try:
            out.append(EvidenceType(t))
        except ValueError:
            continue
    return out or None


_INSTRUCTIONS = (
    "Twelver (Ithnā ʿAsharī) Shia source corpus: the Qur'an (Arabic + English + "
    "Urdu), the Four Books, Nahj al-Balāgha, Biḥār al-Anwār, Tafsīr al-Mīzān and "
    "more — every passage cited. Use `search_sources` to fetch evidence before "
    "answering any Islamic question, and cite the reference shown in [brackets] "
    "for every claim. Never state a fact these tools did not return; if nothing "
    "relevant comes back, say so. Show Qur'anic verses in Arabic + English + Urdu."
)


def _maybe_oauth():
    """Build OAuth provider + AuthSettings when MCP_OAUTH=1 (or MCP_OAUTH_CLIENT_ID is set)."""
    enabled = os.environ.get("MCP_OAUTH", "").strip().lower() in ("1", "true", "yes", "on")
    has_client = bool(os.environ.get("MCP_OAUTH_CLIENT_ID"))
    if not enabled and not has_client:
        return None, None

    try:
        from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
    except ImportError:  # pragma: no cover
        return None, None

    from .mcp_oauth import ShiaAalimOAuthProvider

    issuer = os.environ.get("MCP_OAUTH_ISSUER_URL", "").strip()
    if not issuer:
        issuer = os.environ.get("SPACE_HOST", "").strip()
        if issuer and not issuer.startswith("http"):
            issuer = f"https://{issuer}"
    if not issuer:
        print("[shia-aalim] MCP OAuth: set MCP_OAUTH_ISSUER_URL or SPACE_HOST", file=sys.stderr)
        return None, None

    provider = ShiaAalimOAuthProvider()
    resource_url = issuer.rstrip("/") + "/mcp"
    settings = AuthSettings(
        issuer_url=issuer,
        resource_server_url=resource_url,
        client_registration_options=ClientRegistrationOptions(enabled=True),
    )
    return provider, settings


def create_mcp(config: Optional[web.AppConfig] = None, *, stack: Optional[web.Stack] = None):
    """Build the FastMCP server with the corpus loaded and tools registered.

    ``stack`` lets a caller pass an already-built :class:`shia_aalim.web.Stack`
    (e.g. the web app's) so the corpus + index load once and are shared by both
    the web UI and the MCP endpoint. Otherwise it is built from ``config``.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional extra
        raise ImportError(_MCP_HINT) from exc

    config = config or (stack.config if stack else web.AppConfig())
    stack = stack or web.build_stack(config)
    retriever = stack.engine().answers.retriever

    oauth_provider, auth_settings = _maybe_oauth()

    _common = dict(
        instructions=_INSTRUCTIONS,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        transport_security=_transport_security(),
    )

    try:
        mcp = FastMCP(
            "shia-aalim",
            **_common,
            auth_server_provider=oauth_provider,
            auth=auth_settings,
        )
    except Exception as exc:
        print(f"[shia-aalim] MCP OAuth init failed, starting without OAuth: {exc}",
              file=sys.stderr)
        mcp = FastMCP("shia-aalim", **_common)

    @mcp.tool()
    def search_sources(
        query: str,
        k: int = 8,
        evidence_types: Optional[list[str]] = None,
        sources: Optional[list[str]] = None,
    ) -> str:
        """Search the Twelver Shia corpus and return the most relevant CITED passages.

        Call this before answering any Islamic question, then ground your answer
        strictly on what it returns, citing each reference.

        Args:
            query: what to search for (a topic, question, or phrase).
            k: how many passages to return (1–25).
            evidence_types: optional filter, any of quran/tafsir/hadith/historical/
                scholarly_opinion/biographical/linguistic.
            sources: optional list of book ids to restrict to (see list_books).
        """
        k = max(1, min(25, k))
        results = retriever.retrieve(
            query, k=k, evidence_types=_types(evidence_types),
            source_ids=set(sources) if sources else None,
        )
        return _render(results)

    @mcp.tool()
    def get_quran_verse(surah: int, ayah: int) -> str:
        """Return one Qur'an verse in Arabic + English + Urdu with its reference."""
        doc = stack.verse_index().get((int(surah), int(ayah)))
        if doc is None:
            return f"Qur'an {surah}:{ayah} is not in the loaded corpus."
        c = doc.citation
        lines = [f"[Qur'an {surah}:{ayah}]"]
        if c.arabic_text:
            lines.append(f"Arabic: {c.arabic_text.strip()}")
        lines.append(f"English: {doc.text.strip()}")
        if c.translation_ur:
            lines.append(f"Urdu: {c.translation_ur.strip()} — {c.translation_ur_source or 'Urdu'}")
        return "\n".join(lines)

    @mcp.tool()
    def verse_cross_references(surah: int, ayah: int, k: int = 5) -> str:
        """Tafsir sections and narrations related to a Qur'an verse (cited)."""
        result = stack.crossref(stack.engine()).related(int(surah), int(ayah), k=max(1, min(15, k)))
        if result is None:
            return f"Qur'an {surah}:{ayah} is not in the loaded corpus."
        out = [f"Cross-references for Qur'an {surah}:{ayah}:"]
        for label, items in (("Tafsir", result.tafsir), ("Related narrations", result.hadith),
                             ("Related verses", result.verses)):
            if items:
                out.append(f"\n== {label} ==")
                out.append(_render([RetrievalResult(i.document, i.similarity, i.similarity) for i in items]))
        return "\n".join(out) if len(out) > 1 else "No related passages found."

    @mcp.tool()
    def lookup_narrator(name: str, limit: int = 12) -> str:
        """Find narrations whose chain (isnad) mentions a narrator, with gradings.

        A surface reading of the chains as they appear — a research aid, not a
        rijāl verdict. The system never grades a narrator itself.
        """
        idx = stack.narrators()
        prof = idx.lookup(name)
        if not prof.narration_count:
            return f"No narration chain in the corpus mentions '{name}'."
        out = [f"'{name}' appears in {prof.narration_count} narration(s). "
               f"Grade spread: {prof.grade_distribution}."]
        seen: set[str] = set()
        for men in prof.mentions:
            if men.doc_id in seen:
                continue
            seen.add(men.doc_id)
            doc = idx.document(men.doc_id)
            if doc:
                out.append("\n" + _render([RetrievalResult(doc, 1.0, 1.0)]))
            if len(seen) >= limit:
                break
        return "\n".join(out)

    @mcp.tool()
    def list_books() -> str:
        """List the source books available in the corpus (id, title, passage count)."""
        facets = stack.facets()
        lines = [f"{len(facets['sources'])} books, {stack.n_documents:,} passages:"]
        for s in facets["sources"]:
            lines.append(f"  {s['id']:28s} {s['count']:>6,}  {s['title']}")
        return "\n".join(lines)

    return mcp


def build_http_app(
    config: Optional[web.AppConfig] = None,
    *,
    stack: Optional[web.Stack] = None,
    bearer_token: Optional[str] = None,
):
    """Return ``(mcp, asgi_app)`` for the streamable-HTTP MCP endpoint.

    The returned ASGI app serves the MCP endpoint at ``mcp.settings.streamable_http_path``
    (``/mcp`` by default). Mount it into another ASGI app (e.g. the FastAPI web
    app) so one process serves both the web UI and a remote MCP endpoint from a
    single loaded corpus. The caller MUST run ``mcp.session_manager.run()`` for
    the app's lifetime — use :func:`session_lifespan` for that.

    If ``bearer_token`` is given, requests must send
    ``Authorization: Bearer <token>``; anything else gets 401. This is a light
    guard for a private remote endpoint, not a full OAuth flow.
    """
    mcp = create_mcp(config, stack=stack)
    app = mcp.streamable_http_app()
    if bearer_token:
        _require_bearer(app, bearer_token)
    return mcp, app


def _require_bearer(app, token: str) -> None:
    """Add a tiny bearer-token gate to a Starlette app (private remote use)."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    expected = f"Bearer {token}"

    class _BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization") != expected:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(_BearerAuth)


def session_lifespan(mcp):
    """An async context manager that runs the FastMCP session manager.

    Wire it into the host app's lifespan so mounted streamable-HTTP sessions
    work::

        @asynccontextmanager
        async def lifespan(app):
            async with session_lifespan(mcp):
                yield
    """
    return mcp.session_manager.run()


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Serve the Shia-Aalim corpus over MCP.")
    p.add_argument("--transport", default=os.environ.get("MCP_TRANSPORT", "stdio"),
                   choices=["stdio", "sse", "streamable-http"],
                   help="stdio (local, Claude Desktop) | sse | streamable-http (remote)")
    p.add_argument("--knowledge-dir", default=os.environ.get("KNOWLEDGE_DIR", str(web.DEFAULT_KNOWLEDGE_DIR)))
    p.add_argument("--embedder", default=os.environ.get("EMBEDDER", "tfidf"))
    args = p.parse_args(argv)

    cache = os.environ.get("INDEX_CACHE_DIR")
    config = web.AppConfig(
        knowledge_dir=Path(args.knowledge_dir),
        embedders=[s.strip() for s in args.embedder.split(",") if s.strip()] or ["tfidf"],
        cache_dir=Path(cache) if cache else None,
    )
    print(f"Loading corpus from {config.knowledge_dir} (this can take a minute) …", file=sys.stderr)
    try:
        mcp = create_mcp(config)
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Shia-Aalim MCP server ready — transport={args.transport}", file=sys.stderr)
    mcp.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
