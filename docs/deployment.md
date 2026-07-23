# Hosting Shia-Aalim in the cloud

The app is a FastAPI web server plus a retrieval corpus. This guide gets it
running on a public URL with **no local setup** — everything is done in the
browser. It ships with a `Dockerfile` that rebuilds the **public corpus**
(~60k docs: Qur'an + the Four Books + Nahj + the al-Ṣadūq collections + Shiavault
prose) from upstream repos at build time, so there is nothing to upload.

> **Not on Claude / Artifacts.** Claude Artifacts run as sandboxed browser HTML
> with no Python backend and no outside network, so they cannot host this app's
> retrieval pipeline. Use a container host, below.

## Memory matters

The server builds an in-memory index over the corpus at startup. The public
corpus needs roughly **0.5–1.5 GB RAM**. Pick a host/plan accordingly:

| Host | Free RAM | Fits public corpus? |
|------|---------|---------------------|
| **Hugging Face Spaces** | 16 GB (free CPU) | ✅ yes — recommended |
| Render | 512 MB free/starter · 2 GB standard | ❌ free · ✅ standard |
| Railway / Fly / Cloud Run | configurable | ✅ with ≥1 GB |

---

## Option A — Hugging Face Spaces (free, recommended)

Best fit: 16 GB RAM on the free tier, and it's HuggingFace-native so the
multilingual **semantic** embedder (`st:BAAI/bge-m3`) and Persian/Urdu retrieval
work here.

1. Create a free account at <https://huggingface.co>.
2. **New → Space.** Name it (e.g. `shia-aalim`), **SDK: Docker**, blank template,
   Public. Create it.
3. Create an access token with **write** scope at
   <https://huggingface.co/settings/tokens>.
4. In your **GitHub** repo → *Settings → Secrets and variables → Actions*:
   - add a **secret** `HF_TOKEN` = the write token,
   - add a **variable** `HF_SPACE` = `your-hf-username/shia-aalim`.
5. Run the sync: GitHub repo → *Actions → “Sync to Hugging Face Space” → Run
   workflow* (it also runs automatically on every push). It mirrors the repo to
   the Space; the Space then builds the Docker image and goes live at
   `https://huggingface.co/spaces/your-hf-username/shia-aalim`.

The README's YAML front-matter already declares `sdk: docker` and
`app_port: 7860`, so the Space knows how to run it. First build takes a few
minutes (fetching the corpus); the first request then waits ~1–2 min while the
index builds, and is fast afterwards.

### Turn on semantic search + Persian/Urdu (optional)

Semantic search ranks by *meaning* (not just keywords) and makes Persian/Urdu
queries work. It uses a neural model, so the corpus is embedded once into an
on-disk cache and reused on later starts. **The embedding happens at container
startup, not at build** — because on Hugging Face the Docker *build* runs on CPU,
while a GPU Space's GPU is only available at *runtime*. So the build stays fast
and safe; the first start does the (one-time) embedding.

Enable it with the **`SEMANTIC`** build arg = a model. On HF Spaces (no build-arg
UI) change `ARG SEMANTIC=""` in the `Dockerfile`; on Render/Cloud Run set the
`SEMANTIC` build arg.

**Recommended: a small GPU with BGE-M3 (best quality, full corpus).**
Do this in order:
1. Space → *Settings → Hardware* → pick a GPU (e.g. **T4 small** — hourly, and
   **pausable** so it's cheap). Wait until it's active.
2. Set `ARG SEMANTIC=BAAI/bge-m3` and rebuild. On first start it embeds the full
   122k corpus on the GPU (~a few minutes), caches it, and serves. Pick
   **st:BAAI/bge-m3** from the *Retrieval index* dropdown.

> ⚠️ Set `SEMANTIC` **after** the GPU is active. On a CPU box, embedding 122k
> docs with BGE-M3 would take hours and stall startup.

**Free CPU alternative (lower quality, smaller corpus).** Use a fast multilingual
model — `SEMANTIC=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` —
and prefer the public/subset corpus; on CPU the first-start warm still takes many
minutes.

---

## Option B — Render (deploy straight from GitHub)

1. Sign in at <https://render.com> with GitHub.
2. **New → Blueprint**, pick this repo. Render reads [`render.yaml`](../render.yaml)
   and the `Dockerfile`.
3. It provisions a **Standard** instance (2 GB — needed; the 512 MB free/starter
   tiers will run out of memory on this corpus). Deploy.

Render injects its own `$PORT`, which the app already honours. Health check is
`/api/status`.

Railway, Fly.io and Google Cloud Run work the same way — point them at the
`Dockerfile` and give the instance ≥1 GB RAM.

---

## Full corpus (Biḥār al-Anwār + Tafsīr al-Mīzān)

Biḥār (101 vols) and al-Mīzān (40 vols) live in public source repos
(`sqamberali-bit/bihar-al-anwar-source`, `sqamberali-bit/al-mizan-source`), so
the build can pull them too — it's a **one-line toggle**, no manual editing of
ingest steps. The Dockerfile has a `CORPUS` build arg (`public` by default):

- **Hugging Face Spaces** (no build args in the UI): in the Space's `Dockerfile`,
  change `ARG CORPUS=public` → `ARG CORPUS=full`. It rebuilds with everything.
- **Render / Cloud Run / Railway**: set a **build argument** `CORPUS=full` in the
  service settings.

`CORPUS=full` runs [`scripts/fetch_full_corpus.sh`](../scripts/fetch_full_corpus.sh):
it does the public rebuild, then clones the two source repos, installs PyMuPDF,
and ingests Biḥār + al-Mīzān → ~122k documents.

Two things to size for:
- **Build**: cloning 101 Biḥār PDFs is a large download and the PDF text
  extraction adds a few minutes. Give the build ≥5 GB disk (HF Spaces: fine).
- **RAM**: indexing 122k docs in memory needs **~2–4 GB**. The HF Spaces free
  tier (16 GB) handles it comfortably; on Render use a plan with ≥4 GB.

## LLM-composed answers (optional)

Set an `ANTHROPIC_API_KEY` env var on the host and change the run to
`--synthesize claude:claude-sonnet-5` (install the `llm` extra). Synthesized
prose is still re-verified against the evidence before it is shown.

## Configuration reference

All read from the environment (so a PaaS can set them without changing the
command):

| Var | Default | Meaning |
|-----|---------|---------|
| `PORT` | `7860` | Port to bind (Render/Cloud Run inject their own) |
| `HOST` | `0.0.0.0` (in image) | Bind address |
| `KNOWLEDGE_DIR` | `data/knowledge` | Corpus directory |
| `EMBEDDER` | `tfidf` | `tfidf` · `hashing` · `st:BAAI/bge-m3` · a comma list |
