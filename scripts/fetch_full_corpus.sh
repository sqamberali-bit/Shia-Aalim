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

# Wasāʾil al-Shīʿa volume PDFs (ws<N>*.pdf) ship in the Biḥār source repo
# under pdfs/ — ingest per-hadith. Vols 1-16 are the English translation;
# 17-28 are Arabic-only. The deployed index is capped at vol 16 for now: the
# Arabic volumes' ~13k extra documents push the Space over its memory. Raise
# or unset WASAIL_MAX_VOL (Space variable or here) when the host has room.
export WASAIL_MAX_VOL="${WASAIL_MAX_VOL:-16}"

# 3) OpenITI classical Arabic texts (rijal + early hadith + Mufid's kalam) —
# small, page-cited, Arabic-only. See OPENITI_TARGETS in scripts/ingest.py.
echo ">> OpenITI classical texts (rijal / Qurb al-Isnad / Kifayat / Mufid)"
mkdir -p "$SRC/openiti"
openiti_base="https://raw.githubusercontent.com/OpenITI"
while IFS='|' read -r repo path; do
  f="$(basename "$path")"
  [ -f "$SRC/openiti/$f" ] || curl -fsSL "$openiti_base/$repo/master/data/$path" \
    -o "$SRC/openiti/$f" \
    || echo "   ($f fetch failed — it will be skipped)"
done <<'OPENITI'
0450AH|0450Najashi/0450Najashi.Rijal/0450Najashi.Rijal.Shia002931-ara1.mARkdown
0475AH|0460ShaykhTusi/0460ShaykhTusi.Rijal/0460ShaykhTusi.Rijal.Shia002935-ara1.mARkdown
0475AH|0460ShaykhTusi/0460ShaykhTusi.IkhtiyarMacrifatRijal/0460ShaykhTusi.IkhtiyarMacrifatRijal.Shia002932VolsBK1-ara1.mARkdown
0475AH|0460ShaykhTusi/0460ShaykhTusi.Fihrist/0460ShaykhTusi.Fihrist.Shia002934-ara1.mARkdown
0300AH|0300IbnJacfarHimyari/0300IbnJacfarHimyari.QurbIsnad/0300IbnJacfarHimyari.QurbIsnad.Shia001119-ara1
0400AH|0400IbnMuhammadKhazzaz/0400IbnMuhammadKhazzaz.KifayatAthar/0400IbnMuhammadKhazzaz.KifayatAthar.Masaha002493-ara1
0425AH|0413ShaykhMufid/0413ShaykhMufid.AwailMaqalat/0413ShaykhMufid.AwailMaqalat.Shia001292-ara1
0425AH|0413ShaykhMufid/0413ShaykhMufid.TashihIctiqadat/0413ShaykhMufid.TashihIctiqadat.Zaydiyya0000325-ara1
OPENITI

echo ">> Ingesting Biḥār + al-Mīzān + Wasāʾil (vols ≤ ${WASAIL_MAX_VOL}) + ʿIlal + OpenITI"
python "$ROOT/scripts/ingest.py" \
  --bihar-dir "$SRC/bihar" \
  --almizan-dir "$SRC/almizan" \
  --wasail-dir "$SRC/bihar" \
  --ilal-dir "$SRC/bihar" \
  --openiti-dir "$SRC/openiti"

count="$(find "$ROOT/data/knowledge" -name '*.jsonl' -not -path '*/sample/*' -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')"
echo ">> Full corpus ready — ${count} documents under data/knowledge/"
