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

In the Space, edit the Dockerfile line to install the embeddings extra and set
the embedder, then it rebuilds:

```dockerfile
RUN pip install --no-cache-dir -e ".[web,embeddings]"
ENV EMBEDDER="tfidf,st:BAAI/bge-m3"
```

Then pick **st:BAAI/bge-m3** from the *Retrieval index* dropdown in the app.

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

## Adding Biḥār al-Anwār and Tafsīr al-Mīzān

These came from privately-uploaded source files, so they are not in the public
rebuild. To include them, make their source repos reachable to the build and
extend the corpus step:

```dockerfile
# after the public corpus step in the Dockerfile
RUN git clone --depth 1 https://github.com/<you>/bihar-source     /tmp/bihar    && \
    git clone --depth 1 https://github.com/<you>/al-mizan-source  /tmp/almizan  && \
    pip install --no-cache-dir -e ".[ingest]" && \
    python scripts/ingest.py --bihar-dir /tmp/bihar --almizan-dir /tmp/almizan
```

(`.[ingest]` pulls in PyMuPDF for the Biḥār PDFs.) Note the full 122k corpus
needs ~2–4 GB RAM to index — size the instance accordingly.

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
