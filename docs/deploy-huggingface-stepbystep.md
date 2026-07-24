# Deploy to Hugging Face Spaces — step by step (browser only)

Get the full 122k-document app live on a public URL. No installs, no terminal —
everything is done in the browser. ~10 minutes hands-on, then the build runs on
its own. For the shorter reference and other hosts, see
[`deployment.md`](deployment.md).

**You need:** a GitHub account (you have one) and a free Hugging Face account.

---

## Step 1 — Create the Space
1. Go to <https://huggingface.co> and sign up / log in.
2. Go to <https://huggingface.co/new-space>.
3. Fill in:
   - **Owner:** your username
   - **Space name:** `shia-aalim`
   - **License:** MIT (optional)
   - **Space SDK:** click **Docker**, then pick the **Blank** template
   - **Visibility:** Public
4. Click **Create Space** (it shows an empty Space — that's expected).

## Step 2 — Create a Hugging Face access token
1. Go to <https://huggingface.co/settings/tokens>.
2. Click **New token** (or **Create new token**).
3. **Type: Write.** Name it e.g. `github-sync`. Create it and **copy** the token.

## Step 3 — Add the token + Space name to your GitHub repo
1. Open <https://github.com/sqamberali-bit/shia-aalim>.
2. **Settings → Secrets and variables → Actions.**
3. **Secrets** tab → **New repository secret**:
   - **Name:** `HF_TOKEN` → **Value:** the token from Step 2 → **Add secret**
4. **Variables** tab → **New repository variable**:
   - **Name:** `HF_SPACE` → **Value:** `your-hf-username/shia-aalim` → **Add variable**

## Step 4 — Turn on the full corpus (this also launches the deploy)
1. In GitHub, switch to the branch **`claude/twelver-shia-research-agent-36j49z`**
   (branch dropdown above the file list).
2. Open **`Dockerfile`** → click the **pencil (Edit)** icon.
3. Change `ARG CORPUS=public` to:
   ```dockerfile
   ARG CORPUS=full
   ```
4. **Commit changes → Commit directly to the branch.**

That commit triggers the sync automatically. (To start lean instead, skip the
edit and make any small commit to the branch — you'll get the ~60k public corpus.)

## Step 5 — Watch it build
1. GitHub → **Actions** tab → **"Sync to Hugging Face Space"** should go green ✓
   (~1 min). This copies your repo into the Space.
2. Open `https://huggingface.co/spaces/your-hf-username/shia-aalim` → it shows
   **Building**. The full-corpus build clones the Biḥār PDFs + al-Mīzān and
   ingests them — expect **~15–25 minutes** (public-only is ~5 min).

## Step 6 — Use it
When the Space says **Running**, open its URL. The **first question waits ~1–3
minutes** while the 122k index builds in memory; after that it's fast. You now
have the live app — Ask, Lecture, Compare, Narrators, filters, citation drawer,
cross-references — on a public URL you can share.

---

## Troubleshooting
- **Action failed "HF_TOKEN … must be set":** names must be exactly `HF_TOKEN`
  (secret) and `HF_SPACE` (variable), and `HF_SPACE` is `username/space`.
- **Build ran out of memory:** confirm the Space hardware is the free
  **CPU basic (16 GB)** — Space → *Settings → Hardware*.
- **Re-deploy after any change:** commit to the branch again; sync re-runs.

## Optional — semantic search + Persian/Urdu (GPU recommended)
Semantic search ranks by meaning and makes Persian/Urdu work. The corpus is
embedded once at **container startup** (on the GPU) and cached. Do it in order:

1. **Add a GPU first:** Space → *Settings → Hardware* → pick a GPU (e.g.
   **T4 small** — hourly, and **pausable** so it's cheap). Wait until it's active.
2. **Turn it on:** edit `Dockerfile` on your branch, change `ARG SEMANTIC=""`
   to `ARG SEMANTIC=BAAI/bge-m3`, commit (re-syncs + rebuilds).
3. On first start it embeds the full 122k corpus on the GPU (~a few minutes),
   then serves. Pick **st:BAAI/bge-m3** from the *Retrieval index* dropdown.

> ⚠️ Add the GPU **before** setting `SEMANTIC`. On a CPU box, BGE-M3 over 122k
> docs would take hours and stall startup.

See [`deployment.md`](deployment.md) for the free-CPU alternative and details.

## Optional — AI-written answers with Claude (no GPU)
Claude composes a fluent, cited answer from the retrieved evidence (still
re-verified before display). It's an API call, so it works on the free tier.
Two settings, no rebuild:

1. Space → *Settings → Variables and secrets* → **New secret**:
   `ANTHROPIC_API_KEY` = your key from <https://console.anthropic.com>.
2. Same screen → **New variable**: `SYNTHESIZE` = `claude:claude-sonnet-5`
   (or `claude:claude-haiku-4-5-20251001` for cheaper/faster).

The Space restarts; answers now open with a **Synthesized answer** section
above the cited evidence. Billed per Anthropic API usage (one call per
question). Delete the `SYNTHESIZE` variable to turn it off.

## Connect Claude to the corpus (remote MCP) — already on
The image mounts a remote **MCP endpoint** in the same process (`ENABLE_MCP=1`,
`MCP_ALLOWED_HOSTS=*` are baked in), so once the Space is up it's live at:

```
https://<your-space>.hf.space/mcp
```

Add it in **claude.ai → Settings → Connectors → Add custom connector** (paste
that URL) — Claude can then pull cited passages from the whole corpus with no
Project size cap. To lock it down, Space → *Settings → Variables and secrets* →
**New secret** `MCP_BEARER_TOKEN` = a random string, and send it as
`Authorization: Bearer <token>`. Set the variable `ENABLE_MCP=0` to serve the
web UI only. Full details: [`mcp-server.md`](mcp-server.md).
