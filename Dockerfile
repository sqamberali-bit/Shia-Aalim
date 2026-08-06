# Shia-Aalim web app — container image for cloud hosting (Hugging Face Spaces,
# Render, Railway, Cloud Run, any Docker host).
#
# The public corpus (~60k docs: Qur'an + Four Books + Nahj + al-Saduq set +
# Shiavault prose) is rebuilt from upstream repos at BUILD time and baked into
# the image, so container cold-starts don't re-fetch. See docs/deployment.md to
# add Biḥār / al-Mīzān or to swap in a semantic embedder.
FROM python:3.11-slim

# git + curl to fetch the public corpus; ca-certificates for TLS;
# antiword + unzip to extract the Rafed digital-library Word books.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates antiword unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install the app with the web + llm + mcp extras. anthropic is a small,
# pure-Python dependency, so Claude synthesis is available whenever
# ANTHROPIC_API_KEY and SYNTHESIZE=claude:<model> are set at runtime (no rebuild
# needed to switch on). The mcp extra lets this same process also expose a remote
# MCP endpoint at /mcp (see ENABLE_MCP below) so Claude can connect by URL.
RUN pip install --no-cache-dir "mcp>=1.20,<2" \
    && pip install --no-cache-dir -e ".[web,llm,mcp]" \
    && python -c "from mcp.server.fastmcp import FastMCP; print('MCP FastMCP import OK')"

# Corpus scope: "public" (~60k docs, default, fits small hosts) or "full"
# (~122k docs incl. Biḥār 101 vols + al-Mīzān 40 vols; needs ~2–4 GB RAM).
#   • Hugging Face Spaces (no build args): change the default below to "full".
#   • Render / Cloud Run: set the CORPUS build arg to "full" in the dashboard.
ARG CORPUS=full
RUN if [ "$CORPUS" = "full" ]; then \
        bash scripts/fetch_full_corpus.sh; \
    else \
        bash scripts/fetch_public_corpus.sh; \
    fi

# --- Optional semantic search (meaning-based ranking + Persian/Urdu) ----------
# OFF by default — the TF-IDF app is unaffected. To enable, set the SEMANTIC
# build arg to a sentence-transformers model:
#   • CPU-friendly (works on the free tier, longer build):
#       SEMANTIC=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
#   • Best quality (BGE-M3) — wants a GPU Space:
#       SEMANTIC=BAAI/bge-m3
# Setting SEMANTIC only installs the model libraries here (fast, keeps the build
# safe). The corpus is embedded at container STARTUP — where a GPU Space's GPU
# is available; the HF Docker build runs on CPU. See scripts/serve.sh.
ARG SEMANTIC=""
ENV INDEX_CACHE_DIR=/app/data/index_cache \
    SEMANTIC_MODEL=${SEMANTIC}
RUN if [ -n "$SEMANTIC" ]; then \
        echo "Enabling semantic search with model: $SEMANTIC (embeddings extra)" && \
        pip install --no-cache-dir -e ".[embeddings]" ; \
    fi

# HOST/PORT/EMBEDDER are read by the app from the environment. PaaS platforms
# that inject their own $PORT (Render, Cloud Run) override this automatically.
#
# Remote MCP: ENABLE_MCP=1 mounts an MCP endpoint at /mcp in this same process,
# sharing the one loaded corpus, so Claude (claude.ai Custom Connector / Claude
# Desktop remote MCP) can connect by URL — e.g. https://<space>.hf.space/mcp.
# MCP_ALLOWED_HOSTS=* turns off the localhost-only Host check (needed behind a
# public domain). For a private endpoint, set MCP_BEARER_TOKEN=<secret> so
# callers must send `Authorization: Bearer <secret>`. Set ENABLE_MCP=0 to serve
# the web UI only.
#
# OAuth: MCP_OAUTH=1 enables the built-in OAuth authorization server so
# claude.ai Custom Connectors can authenticate reliably. Set the connector's
# OAuth Client ID to the value of MCP_OAUTH_CLIENT_ID (default: shia-aalim-mcp).
# The issuer URL is auto-detected from SPACE_HOST on HF Spaces; otherwise set
# MCP_OAUTH_ISSUER_URL to your public URL.
#
# IMPORTANT — persistent connector sessions: set MCP_OAUTH_SECRET to a long
# random string as a runtime SECRET (HF Space settings -> Variables and
# secrets; never bake it into this image). With it, tokens are stateless and
# survive restarts/rebuilds, so connectors never need to re-authenticate.
# Without it, every restart invalidates all sessions.
ENV HOST=0.0.0.0 \
    PORT=7860 \
    EMBEDDER=tfidf \
    K=15 \
    ENABLE_MCP=1 \
    MCP_ALLOWED_HOSTS=* \
    MCP_OAUTH=1 \
    MCP_OAUTH_CLIENT_ID=shia-aalim-mcp \
    PYTHONUNBUFFERED=1
EXPOSE 7860

# Serve. First request waits while the index builds/loads; after that it's fast.
CMD ["bash", "scripts/serve.sh"]
