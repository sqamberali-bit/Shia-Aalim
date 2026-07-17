# Data management — the corpus lives outside git

The built knowledge base (`data/knowledge/**/*.jsonl`) is **derived data** and is
**not stored in version control**. Git holds the code, adapters, source registry,
the [corpus manifest](../data/manifest.yaml), tests, docs, and a small committed
**sample** — everything needed to *reconstruct* the corpus, but not the tens/
hundreds of MB of corpus itself.

## Why (not Git LFS)

The corpus is large (already ~124 MB at 57k docs) and growing — Biḥār al-Anwār
alone (101 vols) could add hundreds of MB to ~1 GB. Two reasons this stays out
of git:

* **It's derived.** Every GitHub-sourced work is regenerable from its upstream
  via `scripts/ingest.py`; committing it duplicates data that already has a home.
* **Git LFS doesn't fit the scale.** GitHub LFS free tier is 1 GB storage +
  1 GB/month bandwidth — a single Biḥār import would blow it. External bundles
  have no such cap.

## What IS in git

| In git | Not in git |
|---|---|
| adapters, `ingest.py`, `fetch_data.py` | `data/knowledge/**/*.jsonl` (built corpus) |
| `data/manifest.yaml`, `data/sources/registry.yaml` | `data/bundles/` (local archives) |
| `data/knowledge/sample/sample.jsonl` (small, for demos/tests) | |
| schemas, tests + fixtures, docs | |

## Getting the corpus onto a fresh checkout

**Option A — rebuild GitHub-sourced works** (reproducible, no hosting needed):

```bash
# clone the upstreams (blobless+sparse recommended for ThaqalaynData), then:
python scripts/ingest.py --quran-dir <dir> \
                         --thaqalayn-dir <ThaqalaynData> \
                         --shiavault-dir <shiavault-library>
```

**Option B — fetch a prebuilt bundle** (fast; needs a hosted snapshot):

```bash
python scripts/fetch_data.py --from-bundle <url-or-path> --sha256 <digest>
```

**Check what you have:**

```bash
python scripts/fetch_data.py --status      # present vs manifest, flags MISSING/DRIFT
```

## Publishing a bundle

After building the corpus locally:

```bash
python scripts/fetch_data.py --make-bundle          # -> data/bundles/shia-aalim-corpus.tar.gz + sha256
```

Host the tarball (e.g. a GitHub Release asset) and record its `url` + `sha256`
in `data/manifest.yaml` under `bundle:`. `fetch_data.py --from-bundle` verifies
the checksum before extracting and refuses path-traversal members.

## Upload-only works (e.g. Biḥār al-Anwār)

Works not reachable on GitHub can't be auto-rebuilt. Flow:

1. Add the source files to the session (JSON ≻ EPUB ≻ text-layer PDF).
2. Ingest them locally with the appropriate adapter → JSONL under
   `data/knowledge/` (git-ignored).
3. `--make-bundle` and host, so others can `--from-bundle` without the sources.

Their manifest entry carries `build.source: upload` and no auto-fetch.

## Tests & CI

Corpus-integrity tests (`tests/test_corpus_integrity.py`) **skip** automatically
when the full corpus isn't present, so unit tests and the sample smoke tests
pass on a bare checkout. CI runs those plus `fetch_data.py --status`; it does not
download the full corpus.
