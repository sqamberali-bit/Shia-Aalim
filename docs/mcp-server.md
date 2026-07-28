# MCP connector — let Claude query the whole corpus

This exposes the Shia-Aalim corpus to **Claude as tools** via the Model Context
Protocol (MCP). Instead of uploading files to a Project (capacity-limited),
Claude calls a `search_sources` tool that retrieves **cited passages from all
121k documents** and grounds its own answer on them — no size cap.

The server does retrieval only (Claude is the LLM), reusing the same corpus and
index as the web app. Tools: `search_sources`, `get_quran_verse` (Arabic +
English + Urdu), `verse_cross_references`, `lookup_narrator`, `list_books`.

**Corpus coverage** (see the live list any time via the `list_books` tool): the
Qur'an (Arabic + English + Urdu Jawadi); the **complete Four Books** (al-Kāfī all
8 volumes, Man Lā Yaḥḍuruhu al-Faqīh, Tahdhīb al-Aḥkām, al-Istibṣār) with rijāl
gradings; Nahj al-Balāgha and al-Ṣaḥīfa al-Sajjādiyya; the al-Ṣadūq/al-Mufīd and
Ghayba collections; **Muʿtabar** — Muʿjam al-Aḥādīth al-Muʿtabara (Muḥsinī); the
rijāl work **Kitāb al-Ḍuʿafāʾ** (Ibn al-Ghaḍāʾirī, narrator criticism, typed
*biographical*); classical works via the Shiavault mirror — **Tawḥīd al-Mufaḍḍal,
Tuḥaf al-ʿUqūl, Mishkāt al-Anwār, A Shiʿite Creed, Jāmiʿ al-Saʿādāt** — plus the
Shiavault history tier (*The Message*, Maqtal al-Ḥusayn (al-Muqarram), **Al-Luhuf**
(Ibn Tawus), **Maqtal Abu Mikhnaf** (Event of Taff), Kitāb al-Irshād);
**Mafātīḥ al-Jinān** complete (Arabic duʿāʾ/ziyārāt with the Persian rendering);
**Wasāʾil al-Shīʿa** cited per-narration (vol 1 so far, Arabic + English); and, in
the full build, **Biḥār al-Anwār** (101 vols) and **Tafsīr al-Mīzān** (40 vols) —
~128k cited passages.

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

## Route B — Remote (host it once; connect by URL)

Best if you can't run it locally. Host the server and connect Claude to its URL
(claude.ai **Custom Connector**, or Claude Desktop remote MCP).

### B1 — Mounted in the web app (recommended: one Space, one corpus load)

The web-app container can serve **both** the web UI *and* the MCP endpoint from
a single process, so the ~122k-doc corpus loads once. The Dockerfile enables
this by default:

```dockerfile
ENV ENABLE_MCP=1 \
    MCP_ALLOWED_HOSTS=*     # allow the public Space domain through the Host check
```

Deploy the image as usual (see `docs/deploy-huggingface-stepbystep.md`). The MCP
endpoint is then live at **`https://<your-space>.hf.space/mcp`** alongside the UI
at `/`.

Controls (Space → Settings → Variables/Secrets):

| Env var | Effect |
| --- | --- |
| `ENABLE_MCP=1` | Mount `/mcp` in the web process (set `0` for UI-only). |
| `MCP_ALLOWED_HOSTS=*` | Turn off the localhost-only Host check (required behind a public domain). Or list exact hosts, e.g. `my-space.hf.space`. |
| `MCP_BEARER_TOKEN=<secret>` | Require `Authorization: Bearer <secret>` on `/mcp` (leave unset for an open endpoint). The web UI is never behind this gate. |

### B2 — Standalone MCP process

If you prefer a dedicated service (no web UI), run the server directly:

```bash
pip install -e ".[mcp]"
HOST=0.0.0.0 PORT=8000 MCP_ALLOWED_HOSTS=* \
  python -m shia_aalim.mcp_server --transport streamable-http
```

The endpoint is served at `/mcp` per the MCP HTTP spec
(`http://<host>:<port>/mcp`). `sse` is also supported (`--transport sse`).

### Connecting Claude

- In **claude.ai → Settings → Connectors → Add custom connector**, give the
  server's public HTTPS URL ending in `/mcp`. If you set `MCP_BEARER_TOKEN`, add
  the `Authorization: Bearer <secret>` header where the connector dialog allows
  it. (Remote connectors need HTTPS; some claude.ai setups also require the
  server to implement OAuth — if yours does, Claude Desktop's remote-MCP option
  is the lighter path.)
- In **Claude Desktop** you can add the same URL as a remote MCP server.

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
