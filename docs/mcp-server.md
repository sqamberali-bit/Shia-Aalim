# MCP connector — let Claude query the whole corpus

This exposes the Shia-Aalim corpus to **Claude as tools** via the Model Context
Protocol (MCP). Instead of uploading files to a Project (capacity-limited),
Claude calls a `search_sources` tool that retrieves **cited passages from all
121k documents** and grounds its own answer on them — no size cap.

The server does retrieval only (Claude is the LLM), reusing the same corpus and
index as the web app. Tools: `search_sources`, `get_quran_verse` (Arabic +
English + Urdu), `verse_cross_references`, `lookup_narrator`, `list_books`.

Install the extra: `pip install -e ".[mcp]"`.

---

## Route A — Local (Claude Desktop, stdio)

Best if you can run the repo + corpus on the same machine as Claude Desktop.

1. On that machine: clone the repo, `pip install -e ".[mcp]"`, and make the
   corpus present (`python scripts/fetch_public_corpus.sh`, or copy the built
   `data/knowledge/`).
2. Open Claude Desktop → **Settings → Developer → Edit config** (this opens
   `claude_desktop_config.json`) and add:

```json
{
  "mcpServers": {
    "shia-aalim": {
      "command": "python",
      "args": ["-m", "shia_aalim.mcp_server", "--transport", "stdio"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/shia-aalim/src",
        "KNOWLEDGE_DIR": "/absolute/path/to/shia-aalim/data/knowledge",
        "INDEX_CACHE_DIR": "/absolute/path/to/shia-aalim/data/index_cache"
      }
    }
  }
}
```

3. Restart Claude Desktop. You'll see the **shia-aalim** tools (a plug/hammer
   icon). Ask a question and Claude will call `search_sources` and answer from
   the cited passages.

> First launch indexes the corpus (~1–2 min); `INDEX_CACHE_DIR` makes later
> starts instant.

---

## Route B — Remote (host it; connect by URL)

Best if you can't run it locally. Run the server on a host and connect Claude to
its URL (claude.ai **Custom Connector**, or Claude Desktop remote MCP).

Run it with an HTTP transport (bind to the platform's port):

```bash
pip install -e ".[mcp]"
HOST=0.0.0.0 PORT=8000 python -m shia_aalim.mcp_server --transport streamable-http
```

- On a host that bakes the corpus into the image (like the web-app Dockerfile),
  run the same image with this command instead of the web server, or deploy a
  second service. The endpoint is served at `/<mcp>` per the MCP HTTP spec
  (`http://<host>:<port>/mcp`).
- In **claude.ai → Settings → Connectors → Add custom connector**, give the
  server's public HTTPS URL. (Remote connectors need HTTPS; some setups also
  require the server to implement OAuth — for private use, Claude Desktop's
  developer/remote-MCP option is the lighter path.)

`sse` is also supported (`--transport sse`) for clients that prefer it.

---

## What Claude does with it

Once connected, just chat normally. For any Islamic question Claude will call
`search_sources` (per the server's built-in instructions), receive cited
passages — Qur'an in Arabic + English + Urdu, hadith with grades — and answer
grounded in them, citing the reference shown in each `[…]` header. It's the same
corpus as your app, available directly inside Claude, with no Project size
limit.

**Honesty note:** the MCP server *supplies* cited evidence; it does not run the
app's post-answer verification firewall (that lives in the app). So Claude's
MCP-grounded answers are well-sourced but not machine-verified — still verify
citations against the primary source.
