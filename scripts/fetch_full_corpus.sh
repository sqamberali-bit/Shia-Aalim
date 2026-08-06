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
# 17-28 are Arabic-only. All volumes deploy by default (32 GB holds the full
# corpus with ~12 GB to spare); set WASAIL_MAX_VOL=16 (Space variable or env)
# to shrink the index if a smaller host ever needs it.
export WASAIL_MAX_VOL="${WASAIL_MAX_VOL:-0}"

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
0300AH|0290IbnHasanSaffar/0290IbnHasanSaffar.BasairDarajat/0290IbnHasanSaffar.BasairDarajat.Masaha001945-ara1
0275AH|0274AhmadBarqi/0274AhmadBarqi.Mahasin/0274AhmadBarqi.Mahasin.Shia001115Vols-ara1
0750AH|0726CallamaHilli/0726CallamaHilli.KashfMurad/0726CallamaHilli.KashfMurad.Shia004016-ara1
0550AH|0548IbnHasanTabarsi/0548IbnHasanTabarsi.IclamWara/0548IbnHasanTabarsi.IclamWara.Shia003695Vols-ara1
0475AH|0460ShaykhTusi/0460ShaykhTusi.MisbahMutahajjad/0460ShaykhTusi.MisbahMutahajjad.Shia000042-ara1
0450AH|0436SharifMurtada/0436SharifMurtada.ShafiFiImama/0436SharifMurtada.ShafiFiImama.Shia003996Vols-ara1
0600AH|0588IbnShahrAshub/0588IbnShahrAshub.ManaqibAlAbiTalib/0588IbnShahrAshub.ManaqibAlAbiTalib.Shia001349Vols-ara1
1425AH|1413TajDinKhui/1413TajDinKhui.MucjamRijal/1413TajDinKhui.MucjamRijal.Shia002992Vols-ara1
0350AH|0329IbnIbrahimQummi/0329IbnIbrahimQummi.Tafsir/0329IbnIbrahimQummi.Tafsir.Tafsir04038-ara1
0325AH|0320IbnMascudCayyashi/0320IbnMascudCayyashi.Tafsir/0320IbnMascudCayyashi.Tafsir.Masaha004648Vols-ara1
0550AH|0548IbnHasanTabarsi/0548IbnHasanTabarsi.TafsirMajmacBayan/0548IbnHasanTabarsi.TafsirMajmacBayan.Tafsir04003-ara1
1125AH|1112IbnJumcaHuwayzi/1112IbnJumcaHuwayzi.TafsirNurThaqalayn/1112IbnJumcaHuwayzi.TafsirNurThaqalayn.Shia002389Vols-ara1
0575AH|0560AbuMansurTabarsi/0560AbuMansurTabarsi.Ihtijaj/0560AbuMansurTabarsi.Ihtijaj.Rafed0001121-ara1
0400AH|0400IbnJarirTabariSaghir/0400IbnJarirTabariSaghir.DalailImama/0400IbnJarirTabariSaghir.DalailImama.Shia001286-ara1
0450AH|0436SharifMurtada/0436SharifMurtada.TanzihAnbiya/0436SharifMurtada.TanzihAnbiya.Masaha004743-ara1
0750AH|0726CallamaHilli/0726CallamaHilli.BabHadiCashar/0726CallamaHilli.BabHadiCashar.Rafed0002478-ara1
1100AH|1091MuhammadMuhsinFaydKashani/1091MuhammadMuhsinFaydKashani.TafsirSafi/1091MuhammadMuhsinFaydKashani.TafsirSafi.Shia002382Vols-ara1
0700AH|0693IbnAbiFathIrbili/0693IbnAbiFathIrbili.KashfGhumma/0693IbnAbiFathIrbili.KashfGhumma.Shia003707Vols-ara1.completed
0300AH|0283AbuIshaqThaqafi/0283AbuIshaqThaqafi.Gharat/0283AbuIshaqThaqafi.Gharat.Shia001270Vols-ara1
0675AH|0664IbnTawus/0664IbnTawus.IqbalAcmal/0664IbnTawus.IqbalAcmal.Shia001362Vols-ara1
0700AH|0676IbnHasanMuhaqqiqHilli/0676IbnHasanMuhaqqiqHilli.SharaicIslam/0676IbnHasanMuhaqqiqHilli.SharaicIslam.Shia000057Vols-ara1
1350AH|1337MuhammadKazimTabatabaiYazdi/1337MuhammadKazimTabatabaiYazdi.CurwaWuthqa/1337MuhammadKazimTabatabaiYazdi.CurwaWuthqa.Shia000405Vols-ara1
0475AH|0460ShaykhTusi/0460ShaykhTusi.CiddatUsul/0460ShaykhTusi.CiddatUsul.Shia002748Vols-ara1
0450AH|0436SharifMurtada/0436SharifMurtada.Dharica/0436SharifMurtada.Dharica.Masaha003448Vols-ara1
1350AH|1329MuhammadKazimAkhundKhurasani/1329MuhammadKazimAkhundKhurasani.KifayatUsul/1329MuhammadKazimAkhundKhurasani.KifayatUsul.Shia002773-ara1
0975AH|0965ShahidThani/0965ShahidThani.RicayaFiCilmDiraya/0965ShahidThani.RicayaFiCilmDiraya.Shia002943-ara1
0100AH|0085SulaymIbnQaysHilali/0085SulaymIbnQaysHilali.KitabSulaym/0085SulaymIbnQaysHilali.KitabSulaym.Shia001265-ara1
0525AH|0508FattalNaysaburi/0508FattalNaysaburi.RawdatWacizin/0508FattalNaysaburi.RawdatWacizin.Shia001171-ara1.completed
0425AH|0413ShaykhMufid/0413ShaykhMufid.FusulCashara/0413ShaykhMufid.FusulCashara.Shia001302-ara1
0675AH|0664IbnTawus/0664IbnTawus.JamalUsbuc/0664IbnTawus.JamalUsbuc.Shia001372-ara1
0925AH|0905IbnCaliTaqiDinKafcami/0905IbnCaliTaqiDinKafcami.Misbah/0905IbnCaliTaqiDinKafcami.Misbah.Masaha001075-ara1
0800AH|0786ShahidAwwal/0786ShahidAwwal.LumcaDimashqiyya/0786ShahidAwwal.LumcaDimashqiyya.Shia000120-ara1
0975AH|0965ShahidThani/0965ShahidThani.RawdaBahiyya/0965ShahidThani.RawdaBahiyya.Masaha001142Vols-ara1
1300AH|1281MurtadaAnsari/1281MurtadaAnsari.FaraidUsul/1281MurtadaAnsari.FaraidUsul.Shia002766Vols-ara1
1025AH|1011IbnShahidThani/1011IbnShahidThani.MacalimDin/1011IbnShahidThani.MacalimDin.Shia002755-ara1
OPENITI

# 4) Rafed digital-library Word books (Muzaffar's Usul, Miqbas al-Hidaya,
# Bidayat/Nihayat al-Hikma, al-Burhan v1) — downloaded as .doc zips from
# books.rafed.net and extracted with antiword. Needs antiword + unzip (in the
# Docker image); skipped gracefully if the download or tools are unavailable.
echo ">> Rafed Word books (usul / diraya / philosophy / al-Burhan v1)"
mkdir -p "$SRC/rafed"
RAFED_UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
if command -v antiword >/dev/null 2>&1; then
  for id in 1674 4564 1642 1571 1477; do
    d="$SRC/rafed/$id"
    if [ ! -d "$d" ] || [ -z "$(ls "$d"/*.txt 2>/dev/null)" ]; then
      mkdir -p "$d"
      curl -fsSL -m 300 -A "$RAFED_UA" "https://books.rafed.net/api/download/$id/doc" \
        -o "$d/book.zip" \
        && (cd "$d" && unzip -o -q book.zip \
            && for f in *.doc; do antiword -m UTF-8 "$f" > "${f%.doc}.txt" 2>/dev/null; done) \
        || echo "   (rafed book $id fetch failed — skipped)"
      sleep 3
    fi
  done
else
  echo "   (antiword not installed — Rafed books skipped)"
fi

echo ">> Ingesting Biḥār + al-Mīzān + Wasāʾil (vols ≤ ${WASAIL_MAX_VOL}) + ʿIlal + OpenITI + Rafed"
python "$ROOT/scripts/ingest.py" \
  --bihar-dir "$SRC/bihar" \
  --almizan-dir "$SRC/almizan" \
  --wasail-dir "$SRC/bihar" \
  --ilal-dir "$SRC/bihar" \
  --openiti-dir "$SRC/openiti" \
  --rafed-dir "$SRC/rafed"

count="$(find "$ROOT/data/knowledge" -name '*.jsonl' -not -path '*/sample/*' -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')"
echo ">> Full corpus ready — ${count} documents under data/knowledge/"
