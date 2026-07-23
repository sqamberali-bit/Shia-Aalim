# Shia-Aalim web app — container image for cloud hosting (Hugging Face Spaces,
# Render, Railway, Cloud Run, any Docker host).
#
# The public corpus (~60k docs: Qur'an + Four Books + Nahj + al-Saduq set +
# Shiavault prose) is rebuilt from upstream repos at BUILD time and baked into
# the image, so container cold-starts don't re-fetch. See docs/deployment.md to
# add Biḥār / al-Mīzān or to swap in a semantic embedder.
FROM python:3.11-slim

# git + curl to fetch the public corpus; ca-certificates for TLS.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install the app with the web extra (FastAPI + uvicorn).
RUN pip install --no-cache-dir -e ".[web]"

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
ENV HOST=0.0.0.0 \
    PORT=7860 \
    EMBEDDER=tfidf \
    PYTHONUNBUFFERED=1
EXPOSE 7860

# Serve. First request waits while the index builds/loads; after that it's fast.
CMD ["bash", "scripts/serve.sh"]
