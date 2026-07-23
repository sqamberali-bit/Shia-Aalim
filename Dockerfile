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

# Rebuild the public corpus into data/knowledge/ (no private uploads needed).
RUN bash scripts/fetch_public_corpus.sh

# HOST/PORT/EMBEDDER are read by the app from the environment. PaaS platforms
# that inject their own $PORT (Render, Cloud Run) override this automatically.
ENV HOST=0.0.0.0 \
    PORT=7860 \
    EMBEDDER=tfidf \
    PYTHONUNBUFFERED=1
EXPOSE 7860

# Serve. First request waits while the in-memory index builds (~1–2 min for the
# public corpus); after that it is fast.
CMD ["python", "-m", "shia_aalim.web"]
