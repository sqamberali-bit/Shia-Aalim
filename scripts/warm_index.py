#!/usr/bin/env python3
"""Pre-compute (warm) the on-disk vector cache for one or more embedders.

Run at *build* time so a semantic embedder embeds the whole corpus once — then
the running server loads those vectors instantly instead of re-embedding on
every start (which, for a neural model over a large corpus, is far too slow to
do at request time).

    INDEX_CACHE_DIR=data/index_cache \
    python scripts/warm_index.py \
        --knowledge-dir data/knowledge \
        --embedder "st:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

Each embedder is cached to ``<cache-dir>/<safe-spec>.pkl`` (the same key the web
app uses). Safe to re-run — already-embedded docs are reused.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.ingestion.loaders import iter_knowledge_dir  # noqa: E402
from shia_aalim.retrieval.embeddings import make_embedder  # noqa: E402
from shia_aalim.retrieval.index import build_persistent_index  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--knowledge-dir", default=os.environ.get("KNOWLEDGE_DIR", str(ROOT / "data" / "knowledge")))
    p.add_argument("--cache-dir", default=os.environ.get("INDEX_CACHE_DIR", str(ROOT / "data" / "index_cache")))
    p.add_argument("--embedder", action="append", default=[],
                   help="embedder spec to warm (repeatable); e.g. st:BAAI/bge-m3")
    args = p.parse_args()

    specs = args.embedder or [os.environ.get("EMBEDDER", "tfidf")]
    # An EMBEDDER env may be a comma list ("tfidf,st:..."); warm each.
    specs = [s.strip() for spec in specs for s in spec.split(",") if s.strip()]

    docs = list(iter_knowledge_dir(args.knowledge_dir))
    if not docs:
        print(f"No documents under {args.knowledge_dir}; nothing to warm.", file=sys.stderr)
        return 0
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Warming {len(docs):,} documents for: {', '.join(specs)}")

    for spec in specs:
        safe = spec.replace("/", "_").replace(":", "_")
        cache_path = cache_dir / f"{safe}.pkl"
        t0 = time.time()
        print(f"  → {spec}  (cache: {cache_path.name})", flush=True)
        store = build_persistent_index(docs, make_embedder(spec), cache_path)
        print(f"    embedded {store.embedded_count:,} vectors in {time.time() - t0:.0f}s", flush=True)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
