#!/usr/bin/env bash
#
# Rebuild the FULL corpus (~124k docs): the public set PLUS Biḥār al-Anwār
# (101 vols), Tafsīr al-Mīzān (40 vols), and ʿIlal al-Sharāʾiʿ (2 vols),
# from their public GitHub source repos. Needs pymupdf and ~2–4 GB RAM to
# index — prefer a
# host with plenty of memory (Hugging Face Spaces free tier is fine).
#
# Override the source repos via env if you forked them:
#   BIHAR_REPO=...  ALMIZAN_REPO=...  bash scripts/fetch_full_corpus.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${CORPUS_SRC_DIR:-/tmp/shia-sources}"

# 1) the public corpus first (Qur'an + Four Books + Nahj + al-Ṣadūq + prose)
bash "$ROOT/scripts/fetch_public_corpus.sh"

# 2) the two large works from their (public) source repos
BIHAR_REPO="${BIHAR_REPO:-https://github.com/sqamberali-bit/bihar-al-anwar-source}"
ALMIZAN_REPO="${ALMIZAN_REPO:-https://github.com/sqamberali-bit/al-mizan-source}"

echo ">> Biḥār al-Anwār source (101 PDFs — large clone)"
[ -d "$SRC/bihar/.git" ]   || git clone --depth 1 "$BIHAR_REPO"   "$SRC/bihar"

echo ">> Tafsīr al-Mīzān source (40 txt)"
[ -d "$SRC/almizan/.git" ] || git clone --depth 1 "$ALMIZAN_REPO" "$SRC/almizan"

echo ">> Installing PyMuPDF (Biḥār PDF text extraction)"
pip install --no-cache-dir "pymupdf>=1.24"

# Wasāʾil al-Shīʿa English volume PDFs (ws<N>_eng.pdf) ship in the same source
# repo as al-Mīzān, so the clone above already has them — ingest per-hadith.
# ʿIlal al-Sharāʾiʿ PDFs ship alongside Biḥār in the same source repo.
echo ">> Ingesting Biḥār + al-Mīzān + Wasāʾil + ʿIlal"
python "$ROOT/scripts/ingest.py" \
  --bihar-dir "$SRC/bihar" \
  --almizan-dir "$SRC/almizan" \
  --wasail-dir "$SRC/almizan" \
  --ilal-dir "$SRC/bihar"

count="$(find "$ROOT/data/knowledge" -name '*.jsonl' -not -path '*/sample/*' -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')"
echo ">> Full corpus ready — ${count} documents under data/knowledge/"
