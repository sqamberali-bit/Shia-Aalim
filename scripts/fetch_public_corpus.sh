#!/usr/bin/env bash
#
# Rebuild the PUBLIC knowledge corpus from upstream repositories — no private
# uploads required. Produces ~60k documents:
#   * Qur'an (fawazahmed0/quran-api)            — Uthmani Arabic + Ali Quli Qarai
#   * Hadith (narmafraz/ThaqalaynData, CC0)     — Four Books + Nahj + al-Saduq set
#   * Prose  (shiavault/shiavault-library)      — Sira / Maqtal / Irshad / Sahifa
#
# Biḥār al-Anwār (101 vols) and Tafsīr al-Mīzān (40 vols) are NOT included here:
# they were ingested from privately-uploaded source files. To add them, clone
# those source repos and pass --bihar-dir / --almizan-dir to scripts/ingest.py
# (see docs/deployment.md).
#
# Idempotent: re-running reuses already-cloned sources. Missing pieces are
# skipped gracefully — the Qur'an + hadith bulk still builds.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${CORPUS_SRC_DIR:-/tmp/shia-sources}"
mkdir -p "$SRC/quran"

echo ">> [1/4] Qur'an editions (fawazahmed0/quran-api): Arabic + English + Urdu (Jawadi)"
base="https://raw.githubusercontent.com/fawazahmed0/quran-api/1/editions"
curl -fsSL "$base/ara-quranuthmanihaf.json" -o "$SRC/quran/quran-ara-quranuthmanihaf.json"
curl -fsSL "$base/eng-aliquliqarai.json"    -o "$SRC/quran/quran-eng-aliquliqarai.json"
# Vetted Urdu translation — Syed Zeeshan Haider Jawadi (source: tanzil.net)
curl -fsSL "$base/urd-syedzeeshanhaid.json" -o "$SRC/quran/quran-urd-syedzeeshanhaid.json" \
  || echo "   (Urdu edition fetch failed — verses will show Arabic + English only)"

echo ">> [2/4] ThaqalaynData (narmafraz/ThaqalaynData, CC0)"
if [ ! -d "$SRC/ThaqalaynData/.git" ]; then
  git clone --depth 1 https://github.com/narmafraz/ThaqalaynData "$SRC/ThaqalaynData"
fi

echo ">> [3/4] Shiavault library (shiavault/shiavault-library)"
if [ ! -d "$SRC/shiavault/.git" ]; then
  git clone --depth 1 https://github.com/shiavault/shiavault-library "$SRC/shiavault" \
    || echo "   (shiavault clone failed — prose works will be skipped)"
fi

echo ">> [4/4] Ingesting into data/knowledge/ ..."
python "$ROOT/scripts/ingest.py" \
  --quran-dir "$SRC/quran" \
  --thaqalayn-dir "$SRC/ThaqalaynData" \
  --shiavault-dir "$SRC/shiavault"

count="$(find "$ROOT/data/knowledge" -name '*.jsonl' -not -path '*/sample/*' -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')"
echo ">> Done — ${count} documents under data/knowledge/"
