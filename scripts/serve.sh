#!/usr/bin/env bash
# Container entrypoint. Turns the SEMANTIC_MODEL build/env value into the
# runtime embedder list, then starts the web server. If SEMANTIC_MODEL is unset,
# the app runs on the default (tfidf) — nothing changes.
set -euo pipefail

if [ -n "${SEMANTIC_MODEL:-}" ]; then
  export EMBEDDER="tfidf,st:${SEMANTIC_MODEL}"
  echo "serve: semantic retrieval enabled (EMBEDDER=${EMBEDDER})" >&2
fi

exec python -m shia_aalim.web
