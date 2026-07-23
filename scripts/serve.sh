#!/usr/bin/env bash
# Container entrypoint.
#
# If SEMANTIC_MODEL is set, enable semantic retrieval and — on first start —
# embed the corpus into the on-disk cache HERE at runtime (where the GPU is,
# for a GPU Space; the HF Docker BUILD runs on CPU, so build-time embedding
# would be slow). Warming is one-time: the cache is reused on later starts.
# Warming is non-fatal — if it fails, the server still comes up on tfidf.
set -uo pipefail

if [ -n "${SEMANTIC_MODEL:-}" ]; then
  export EMBEDDER="tfidf,st:${SEMANTIC_MODEL}"
  cache_dir="${INDEX_CACHE_DIR:-/app/data/index_cache}"
  spec="st:${SEMANTIC_MODEL}"
  safe="$(printf '%s' "$spec" | sed 's#[/:]#_#g')"
  if [ ! -f "${cache_dir}/${safe}.pkl" ]; then
    echo "serve: warming semantic index (${spec}) — first start only, a few minutes on a GPU…" >&2
    python scripts/warm_index.py --embedder "$spec" \
      || echo "serve: semantic warm failed — continuing on tfidf only" >&2
  else
    echo "serve: semantic cache present (${safe}.pkl) — loading it" >&2
  fi
fi

exec python -m shia_aalim.web
