#!/usr/bin/env python3
"""Build the real knowledge base from verified upstream datasets.

Sources (GitHub-hosted, the reachable channel in this environment):
  * Qur'an — fawazahmed0/quran-api editions (Arabic Uthmani + Ali Quli Qarai)
  * Hadith — narmafraz/ThaqalaynData (CC0), al-Kafi Books of Tawheed & Intellect

This script reads already-downloaded source files (paths via flags/env) and
writes newline-delimited Documents into data/knowledge/. It never fabricates:
missing verses/translations are skipped, and hadith gradings are carried through
verbatim from the upstream rijal data.

Usage:
  python scripts/ingest.py \
      --quran-dir /path/with/quran-*.json \
      --thaqalayn-dir /path/to/ThaqalaynData

Environment fallbacks: QURAN_DIR, THAQALAYN_DATA_DIR.
"""

from __future__ import annotations

import argparse
import json
import os
import re as _re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.ingestion.adapters.bihar import build_bihar_documents, volume_from_filename  # noqa: E402
from shia_aalim.ingestion.adapters.ilal import build_ilal_documents  # noqa: E402
from shia_aalim.ingestion.adapters.ilal import volume_part_from_filename as ilal_vol_part  # noqa: E402
from shia_aalim.ingestion.adapters.mafatih import build_mafatih_documents  # noqa: E402
from shia_aalim.ingestion.adapters.plaintext import build_textbook_documents  # noqa: E402
from shia_aalim.ingestion.adapters.plaintext import volume_from_filename as txt_volume  # noqa: E402
from shia_aalim.ingestion.adapters.openiti import build_openiti_documents  # noqa: E402
from shia_aalim.ingestion.adapters.prose_pdf import build_prose_pdf_documents  # noqa: E402
from shia_aalim.ingestion.adapters.quran import build_quran_documents  # noqa: E402
from shia_aalim.ingestion.adapters.rafed_doc import build_rafed_documents  # noqa: E402
from shia_aalim.ingestion.adapters.shiavault import build_prose_documents  # noqa: E402
from shia_aalim.ingestion.adapters.thaqalayn import build_hadith_documents  # noqa: E402
from shia_aalim.ingestion.adapters.wasail import build_wasail_documents  # noqa: E402
from shia_aalim.ingestion.adapters.wasail import volume_from_filename as wasail_volume  # noqa: E402
from shia_aalim.ingestion.adapters.wasail_arabic import build_wasail_arabic_documents  # noqa: E402
from shia_aalim.models import ConfidenceLevel, Document, EvidenceType  # noqa: E402

KNOWLEDGE = ROOT / "data" / "knowledge"


def write_jsonl(docs: list[Document], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(d.to_json_line() + "\n")
    print(f"  wrote {len(docs):>5} documents -> {path.relative_to(ROOT)}")


def ingest_quran(quran_dir: Path) -> int:
    arabic = quran_dir / "quran-ara-quranuthmanihaf.json"
    qarai = quran_dir / "quran-eng-aliquliqarai.json"
    if not (arabic.exists() and qarai.exists()):
        print(f"  [skip] Qur'an editions not found in {quran_dir}")
        return 0
    # Optional vetted Urdu translation (Syed Zeeshan Haider Jawadi, via tanzil.net)
    urdu = quran_dir / "quran-urd-syedzeeshanhaid.json"
    docs = build_quran_documents(
        arabic, qarai, translation_name="Ali Quli Qarai (via fawazahmed0/quran-api)",
        urdu_path=urdu if urdu.exists() else None,
        urdu_name="Syed Zeeshan Haider Jawadi (via fawazahmed0/quran-api, tanzil.net)",
    )
    write_jsonl(docs, KNOWLEDGE / "quran" / "quran.jsonl")
    return len(docs)


# Per-book ingestion config. Each book uses its own translator and citation
# style. Candidate translation keys are tried in order (first present wins).
HADITH_TARGETS = [
    # rel path,               source_id,       book_title,                               out file,                  translation_keys,                       style,           translation_name
    ("books/al-kafi/1/3", "al-kafi", "Book of Tawheed (al-Kafi, Kitab al-Tawhid)", "al-kafi-tawhid.jsonl", ["en.hubeali"], "hierarchical", "Hubeali (via ThaqalaynData, CC0)"),
    ("books/al-kafi/1/1", "al-kafi", "Book of Intellect and Ignorance (al-Kafi)", "al-kafi-intellect.jsonl", ["en.hubeali"], "hierarchical", "Hubeali (via ThaqalaynData, CC0)"),
    ("books/al-kafi/1/4", "al-kafi", "Book of Divine Authority (al-Kafi, Kitab al-Hujjah)", "al-kafi-hujjah.jsonl", ["en.hubeali"], "hierarchical", "Hubeali (via ThaqalaynData, CC0)"),
    ("books/al-kafi/1/2", "al-kafi", "Book of Excellence of Knowledge (al-Kafi)", "al-kafi-knowledge.jsonl", ["en.hubeali"], "hierarchical", "Hubeali (via ThaqalaynData, CC0)"),
    ("books/man-la-yahduruhu-al-faqih", "man-la-yahduruhu-al-faqih", "Man la yahduruhu al-Faqih", "man-la-yahduruhu-al-faqih.jsonl", ["en.bab-ul-qaim-publications", "en.hubeali"], "hierarchical", "Bab ul Qaim Publications (via ThaqalaynData, CC0)"),
    ("books/tahdhib-al-ahkam", "tahdhib-al-ahkam", "Tahdhib al-Ahkam", "tahdhib-al-ahkam.jsonl", ["en.hubeali", "en.bab-ul-qaim-publications"], "hierarchical", "via ThaqalaynData (CC0)"),
    ("books/al-istibsar", "al-istibsar", "al-Istibsar", "al-istibsar.jsonl", ["en.hubeali", "en.bab-ul-qaim-publications"], "hierarchical", "via ThaqalaynData (CC0)"),
    ("books/nahj-al-balagha", "nahj-al-balagha", "Nahj al-Balagha", "nahj-al-balagha.jsonl", ["en.sayed-ali-raza"], "nahj", "Sayed Ali Raza (via ThaqalaynData, CC0)"),
    # al-Saduq / al-Mufid secondary hadith collections (CC0 ThaqalaynData)
    ("books/uyun-akhbar-al-rida", "uyun-akhbar-al-rida", "Uyun Akhbar al-Rida (al-Saduq)", "uyun-akhbar-al-rida.jsonl", ["en.dr-ali-peiravi"], "hierarchical", "Dr Ali Peiravi (via ThaqalaynData, CC0)"),
    ("books/al-amali-saduq", "al-amali-saduq", "al-Amali (al-Saduq)", "al-amali-saduq.jsonl", ["en.bilal-muhammad"], "hierarchical", "Bilal Muhammad (via ThaqalaynData, CC0)"),
    ("books/al-amali-mufid", "al-amali-mufid", "al-Amali (al-Mufid)", "al-amali-mufid.jsonl", ["en.mulla-asgharali-m-m-jaffer"], "hierarchical", "Mulla Asgharali M M Jaffer (via ThaqalaynData, CC0)"),
    ("books/al-khisal", "al-khisal", "al-Khisal (al-Saduq)", "al-khisal.jsonl", ["en.dr-ali-peiravi"], "hierarchical", "Dr Ali Peiravi (via ThaqalaynData, CC0)"),
    ("books/al-tawhid", "al-tawhid-saduq", "Kitab al-Tawhid (al-Saduq)", "al-tawhid-saduq.jsonl", ["en.sayed-ali-raza-rizvi"], "hierarchical", "Sayed Ali Raza Rizvi (via ThaqalaynData, CC0)"),
    # Further ThaqalaynData (CC0) Twelver collections — mostly early al-Saduq /
    # Ahwazi / Ghayba works. All ungraded in this dataset (medium confidence).
    # (kamal-al-din is an empty stub in ThaqalaynData — no matn/translation — so it is not ingested.)
    ("books/kamil-al-ziyarat", "kamil-al-ziyarat", "Kamil al-Ziyarat (Ibn Qulawayh)", "kamil-al-ziyarat.jsonl", ["en.sayyid-mohsen-al-husayni-al-milani"], "hierarchical", "Sayyid Mohsen al-Husayni al-Milani (via ThaqalaynData, CC0)"),
    ("books/maani-al-akhbar", "maani-al-akhbar", "Ma'ani al-Akhbar (al-Saduq)", "maani-al-akhbar.jsonl", ["en.basel-kadem"], "hierarchical", "Basel Kadem (via ThaqalaynData, CC0)"),
    ("books/thawab-al-amal", "thawab-al-amal", "Thawab al-A'mal wa Iqab al-A'mal (al-Saduq)", "thawab-al-amal.jsonl", ["en.sayed-athar-husain-rizvi-&-sayed-maqsood-athar"], "hierarchical", "Rizvi & Athar (via ThaqalaynData, CC0)"),
    ("books/sifat-al-shia", "sifat-al-shia", "Sifat al-Shia (al-Saduq)", "sifat-al-shia.jsonl", ["en.badr-shahin"], "hierarchical", "Badr Shahin (via ThaqalaynData, CC0)"),
    ("books/risalat-al-huquq", "risalat-al-huquq", "Risalat al-Huquq (Imam al-Sajjad)", "risalat-al-huquq.jsonl", ["en.william-c-chittick"], "hierarchical", "William C. Chittick (via ThaqalaynData, CC0)"),
    ("books/kitab-al-ghayba-numani", "kitab-al-ghayba-numani", "Kitab al-Ghayba (al-Nu'mani)", "kitab-al-ghayba-numani.jsonl", ["en.abdullah-al-shahin"], "hierarchical", "Abdullah al-Shahin (via ThaqalaynData, CC0)"),
    ("books/kitab-al-ghayba-tusi", "kitab-al-ghayba-tusi", "Kitab al-Ghayba (al-Tusi)", "kitab-al-ghayba-tusi.jsonl", ["en.sayyid-athar-husain-s-h-rizvi"], "hierarchical", "Sayyid Athar Husain S.H. Rizvi (via ThaqalaynData, CC0)"),
    ("books/kitab-al-mumin", "kitab-al-mumin", "Kitab al-Mu'min (al-Ahwazi)", "kitab-al-mumin.jsonl", ["en.muhajir-b-ali"], "hierarchical", "Muhajir b. Ali (via ThaqalaynData, CC0)"),
    ("books/kitab-al-zuhd", "kitab-al-zuhd", "Kitab al-Zuhd (al-Ahwazi)", "kitab-al-zuhd.jsonl", ["en.shaykh-tahir-ridha-jaffer"], "hierarchical", "Shaykh Tahir Ridha Jaffer (via ThaqalaynData, CC0)"),
    ("books/fadail-al-shia", "fadail-al-shia", "Fada'il al-Shia (al-Saduq)", "fadail-al-shia.jsonl", ["en.badr-shahin"], "hierarchical", "Badr Shahin (via ThaqalaynData, CC0)"),
    # Mu'jam al-Ahadith al-Mu'tabara — a modern compilation of narrations its
    # author (Muhammad Asif Muhsini) judged reliable; ~428/555 carry gradings.
    ("books/mujam-al-ahadith-al-mutabara", "mujam-al-ahadith-al-mutabara", "Mu'jam al-Ahadith al-Mu'tabara (Muhsini)", "mujam-al-ahadith-al-mutabara.jsonl", ["en.ammaar-muslim"], "hierarchical", "Ammaar Muslim (via ThaqalaynData, CC0)"),
]

# Kitab al-Du'afa (Ibn al-Ghada'iri) is a *rijal* work — verdicts on weak
# narrators, not isnad-bearing hadith — so it is typed BIOGRAPHICAL. Same
# ThaqalaynData layout; only the classification differs.
BIOGRAPHICAL_TARGETS = [
    ("books/kitab-al-duafa", "kitab-al-duafa", "Kitab al-Du'afa (Ibn al-Ghada'iri)", "kitab-al-duafa.jsonl", ["en.tashayyu"], "hierarchical", "Tashayyu (via ThaqalaynData, CC0)"),
]

# Prose works from the Shiavault Markdown mirror (al-islam.org). These are
# tafsir / biography / history / translated supplications — coarser,
# chapter-level citations, medium confidence (translations / secondary works).
# (rel path, source_id, EvidenceType, volume-or-None, out shard)
PROSE_TARGETS = [
    # al-Mizan now comes from the complete 40-volume upload (see ingest_almizan);
    # the partial Shiavault al-Mizan (vols 1,2,4,7,8 only) is intentionally dropped.
    ("books/as-sahifa-al-kamilah-al-sajjadiyya", "sahifa-sajjadiyya", "hadith", None, "sahifa-sajjadiyya.jsonl"),
    ("books/the-message", "the-message-subhani", "historical", None, "seerah-the-message.jsonl"),
    ("books/maqtal-al-husayn", "maqtal-al-husayn", "historical", None, "maqtal-al-husayn.jsonl"),
    ("books/kitab-al-irshad-1", "kitab-al-irshad", "historical", None, "kitab-al-irshad.jsonl"),
    # Classical primary hadith / creed / ethics (chapter-level citations, medium
    # confidence — English translations via the Shiavault mirror).
    ("books/tradition-of-mufaddal", "tawhid-al-mufaddal", "hadith", None, "tawhid-al-mufaddal.jsonl"),
    ("books/tuhaf-al-uqul-the-masterpieces-of-the-mind", "tuhaf-al-uqul", "hadith", None, "tuhaf-al-uqul.jsonl"),
    ("books/provisions-for-the-journey-mishkat-volume-1", "mishkat-al-anwar", "hadith", "1", "mishkat-al-anwar-v1.jsonl"),
    ("books/provisions-for-the-journey-mishkat-volume-2", "mishkat-al-anwar", "hadith", "2", "mishkat-al-anwar-v2.jsonl"),
    ("books/a-shi-ite-creed", "a-shiite-creed", "scholarly_opinion", None, "a-shiite-creed.jsonl"),
    ("books/jami-al-sa-adat-the-collector-of-felicities", "jami-al-saadat", "scholarly_opinion", None, "jami-al-saadat.jsonl"),
    ("books/lohoof-sighs-of-sorrow", "al-luhuf", "historical", None, "al-luhuf.jsonl"),
    ("books/the-event-of-taff-the-earliest-historical-account-of-the-tragedy-of-karbala", "maqtal-abu-mikhnaf", "historical", None, "maqtal-abu-mikhnaf.jsonl"),
    # --- 2026-08 expansion (all via the Shiavault mirror) ---
    ("books/kamaaluddin-wa-tamaamun-ni-ma-vol-1", "kamal-al-din", "hadith", "1", "kamal-al-din-v1.jsonl"),
    ("books/kamaaluddin-wa-tamaamun-ni-ma-vol-2", "kamal-al-din", "hadith", "2", "kamal-al-din-v2.jsonl"),
    ("books/ghurar-al-hikam-wa-durar-al-kalim-exalted-aphorisms-and-pearls-of-speech",
     "ghurar-al-hikam", "hadith", None, "ghurar-al-hikam.jsonl"),
    ("books/nafasul-mahmum-relating-to-the-heart-rending-tragedy-of-karbala",
     "nafas-al-mahmum", "historical", None, "nafas-al-mahmum.jsonl"),
    ("books/hayat-al-qulub-vol-1-stories-of-the-prophets", "hayat-al-qulub", "historical", "1", "hayat-al-qulub-v1.jsonl"),
    ("books/hayat-al-qulub-vol-2", "hayat-al-qulub", "historical", "2", "hayat-al-qulub-v2.jsonl"),
    ("books/hayat-al-qulub-vol-3", "hayat-al-qulub", "historical", "3", "hayat-al-qulub-v3.jsonl"),
    ("books/ain-al-hayat-the-essence-of-life", "ayn-al-hayat", "scholarly_opinion", None, "ayn-al-hayat.jsonl"),
    ("books/al-muraja-at", "al-murajaat", "scholarly_opinion", None, "al-murajaat.jsonl"),
    ("books/peshawar-nights", "peshawar-nights", "scholarly_opinion", None, "peshawar-nights.jsonl"),
    ("books/islamic-laws", "islamic-laws-sistani", "scholarly_opinion", None, "islamic-laws-sistani.jsonl"),
    ("books/islamic-laws-of-ayatullah-khui", "islamic-laws-khui", "scholarly_opinion", None, "islamic-laws-khui.jsonl"),
    ("books/forty-hadith-an-exposition", "forty-hadith-khomeini", "scholarly_opinion", None, "forty-hadith-khomeini.jsonl"),
    ("books/the-shiite-islam", "shiite-islam-tabatabai", "scholarly_opinion", None, "shiite-islam-tabatabai.jsonl"),
    ("books/adab-as-salat-the-disciplines-of-the-prayer-second-revised-edition",
     "adab-as-salat", "scholarly_opinion", None, "adab-as-salat.jsonl"),
    ("books/the-revealer-the-messenger-the-message",
     "the-revealer-the-messenger", "scholarly_opinion", None, "the-revealer-the-messenger.jsonl"),
]

# The 20-volume "Enlightening Commentary into the Light of the Holy Qur'an"
# (based on Tafsir Nemooneh) — one PROSE_TARGETS entry per volume.
PROSE_TARGETS += [
    (
        f"books/an-enlightening-commentary-into-the-light-of-the-holy-qur-an-vol-{v}",
        "enlightening-commentary",
        "tafsir",
        str(v),
        f"enlightening-commentary-v{v}.jsonl",
    )
    for v in range(1, 21)
]


# al-Kafi volumes to auto-enumerate as whole (each volume's books are read from
# its on-disk index, so every Book gets its real English title in the citation).
# Volume 1 (Usul) is ingested explicitly above; 2-7 are Furu', 8 is Rawda.
AL_KAFI_AUTO_VOLUMES = [2, 3, 4, 5, 6, 7, 8]


def _clean_title(title: str) -> str:
    return _re.sub(r"<[^>]+>", "", title or "").strip()


def ingest_al_kafi_volumes(thaqalayn_dir: Path) -> int:
    """Ingest whole al-Kafi volumes (Furu' + Rawda) by reading each volume index.

    Enumerates the Books inside each volume from ``books/al-kafi/<v>.json`` so
    every narration is cited under its real Book title, then writes one shard
    per volume (``al-kafi-vol<v>.jsonl``).
    """
    total = 0
    for vol in AL_KAFI_AUTO_VOLUMES:
        index_path = thaqalayn_dir / "books" / "al-kafi" / f"{vol}.json"
        if not index_path.exists():
            print(f"  [skip] al-Kafi volume {vol} index not found")
            continue
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"  [skip] al-Kafi volume {vol} index unreadable: {exc}")
            continue
        vol_docs: list[Document] = []
        for book in index.get("data", {}).get("chapters", []):
            segs = str(book.get("path", "")).split(":")[1:]  # e.g. ['2','1']
            if len(segs) < 2:
                continue
            local_book = segs[1]
            book_dir = thaqalayn_dir / "books" / "al-kafi" / str(vol) / local_book
            if not book_dir.exists():
                continue
            title = _clean_title(book.get("titles", {}).get("en", f"al-Kafi vol {vol}"))
            vol_docs += build_hadith_documents(
                book_dir,
                source_id="al-kafi",
                book_title=f"{title} (al-Kafi, vol {vol})",
                translation_keys=["en.hubeali"],
                translation_name="Hubeali (via ThaqalaynData, CC0)",
                citation_style="hierarchical",
            )
        if vol_docs:
            vol_docs.sort(key=lambda d: [int(n) for n in _re.findall(r"\d+", d.id)])
            write_jsonl(vol_docs, KNOWLEDGE / "hadith" / f"al-kafi-vol{vol}.jsonl")
            total += len(vol_docs)
    return total


def ingest_hadith(thaqalayn_dir: Path) -> int:
    total = 0
    for rel, source_id, title, out, keys, style, tname in HADITH_TARGETS:
        book_dir = thaqalayn_dir / rel
        if not book_dir.exists():
            print(f"  [skip] {rel} not found under {thaqalayn_dir}")
            continue
        docs = build_hadith_documents(
            book_dir,
            source_id=source_id,
            book_title=title,
            translation_keys=keys,
            translation_name=tname,
            citation_style=style,
        )
        if docs:
            write_jsonl(docs, KNOWLEDGE / "hadith" / out)
            total += len(docs)
    total += ingest_al_kafi_volumes(thaqalayn_dir)
    # Rijal (biographical) works from ThaqalaynData — same layout, typed as
    # BIOGRAPHICAL so narrator-criticism is not presented as hadith.
    for rel, source_id, title, out, keys, style, tname in BIOGRAPHICAL_TARGETS:
        book_dir = thaqalayn_dir / rel
        if not book_dir.exists():
            print(f"  [skip] {rel} not found under {thaqalayn_dir}")
            continue
        docs = build_hadith_documents(
            book_dir,
            source_id=source_id,
            book_title=title,
            translation_keys=keys,
            translation_name=tname,
            citation_style=style,
            evidence_type=EvidenceType.BIOGRAPHICAL,
        )
        if docs:
            write_jsonl(docs, KNOWLEDGE / "biographical" / out)
            total += len(docs)
    return total


def ingest_prose(shiavault_dir: Path) -> int:
    """Ingest Shiavault Markdown prose works (tafsir / supplications / history)."""
    total = 0
    for rel, source_id, etype, volume, out in PROSE_TARGETS:
        book_dir = shiavault_dir / rel
        if not book_dir.exists():
            print(f"  [skip] {rel} not found under {shiavault_dir}")
            continue
        docs = build_prose_documents(
            book_dir,
            source_id=source_id,
            evidence_type=EvidenceType(etype),
            confidence=ConfidenceLevel.MEDIUM,
            volume=volume,
        )
        if docs:
            write_jsonl(docs, KNOWLEDGE / "prose" / out)
            total += len(docs)
    return total


def ingest_almizan(almizan_dir: Path) -> int:
    """Ingest the complete 40-volume English al-Mizan (Tawheed Institute) from
    plain-text volume files (1.txt .. 40.txt), one shard per volume."""
    files = sorted(
        almizan_dir.glob("*.txt"),
        key=lambda p: int(txt_volume(p) or 0),
    )
    if not files:
        print(f"  [skip] no <N>.txt files under {almizan_dir}")
        return 0
    total = 0
    for txt in files:
        vol = txt_volume(txt) or "0"
        docs = build_textbook_documents(
            txt,
            source_id="al-mizan",
            evidence_type=EvidenceType.TAFSIR,
            volume=vol,
            confidence=ConfidenceLevel.MEDIUM,
            # Translators vary by volume (Rizvi, Khaleeli, …); attribute the
            # edition, not one name. Each volume's title page (in section 0)
            # records its specific translator.
            translation_source="Tawheed Institute Australia (English al-Mizan, OCR)",
        )
        if docs:
            write_jsonl(docs, KNOWLEDGE / "prose" / f"al-mizan-v{int(vol):02d}.jsonl")
            total += len(docs)
    return total


def ingest_mafatih(json_path: Path) -> int:
    """Ingest Mafātīḥ al-Jinān from the Apache-2.0 structured JSON tree."""
    if not json_path.exists():
        print(f"  [skip] Mafātīḥ JSON not found at {json_path}")
        return 0
    docs = build_mafatih_documents(json_path)
    if not docs:
        print(f"  [skip] no documents built from {json_path}")
        return 0
    write_jsonl(docs, KNOWLEDGE / "prose" / "mafatih-al-jinan.jsonl")
    return len(docs)


def ingest_wasail(wasail_dir: Path) -> int:
    """Ingest Wasāʾil al-Shīʿa volumes from English text-layer PDFs (ws<N>_eng.pdf).

    One shard per volume; each narration cited by volume + section + hadith number.
    Only the volumes actually present are ingested — missing ones are skipped, not
    approximated.
    """
    # Tolerate browser-duplicate names like "ws1_eng (2).pdf" and plain Arabic
    # volume names like "ws18.pdf". Keep one PDF per volume: an _eng (English
    # translation) file wins over an Arabic one, then the shorter name wins.
    def _pref(p: Path) -> tuple[int, int]:
        return (0 if "_eng" in p.name.lower() else 1, len(p.name))

    # WASAIL_MAX_VOL caps which volumes are ingested (0/unset = all). Used to
    # keep the deployed index within a small host's memory: the Arabic-edition
    # vols 17-28 add ~13k documents, which can push a Space over its RAM.
    max_vol = int(os.environ.get("WASAIL_MAX_VOL", "0") or 0)

    by_vol: dict[int, Path] = {}
    for p in wasail_dir.glob("**/ws*.pdf"):
        v = int(wasail_volume(p) or 0)
        if not v:
            continue
        if max_vol and v > max_vol:
            continue
        if v not in by_vol or _pref(p) < _pref(by_vol[v]):
            by_vol[v] = p
    if max_vol:
        print(f"  [cap] WASAIL_MAX_VOL={max_vol} — later volumes skipped")
    pdfs = [by_vol[v] for v in sorted(by_vol)]
    if not pdfs:
        print(f"  [skip] no ws*.pdf under {wasail_dir}")
        return 0
    def _drop_isolated(docs: list, name: str) -> list:
        # Real narration numbers run contiguously through a volume; a number
        # with neither neighbor present is a false marker (e.g. a hadith
        # number quoted in a cross-reference footnote) — drop, don't mis-cite.
        nums = {int(d.citation.hadith_number or 0) for d in docs}
        kept = [d for d in docs
                if (int(d.citation.hadith_number or 0) - 1 in nums)
                or (int(d.citation.hadith_number or 0) + 1 in nums)]
        if len(kept) < len(docs):
            print(f"  [drop] {name}: {len(docs) - len(kept)} isolated hadith "
                  f"number(s) (cross-reference artefacts) — skipped")
        return kept

    total = 0
    for pdf in pdfs:
        vol = wasail_volume(pdf) or "0"
        # English-translation volumes carry "Hadith N" markers; the later
        # Arabic-edition volumes don't — fall back to the Arabic adapter.
        docs = build_wasail_documents(pdf, volume=vol)
        if not docs:
            docs = build_wasail_arabic_documents(pdf, volume=vol)
        docs = _drop_isolated(docs, pdf.name)
        if docs:
            write_jsonl(docs, KNOWLEDGE / "hadith" / f"wasail-al-shia-v{int(vol):02d}.jsonl")
            total += len(docs)
    return total


def ingest_bihar(bihar_dir: Path) -> int:
    """Ingest the hubeali English Bihar al-Anwar PDFs (V1..V101), one shard/volume."""
    pdfs = sorted(
        bihar_dir.glob("**/BiharAlAnwaar_V*.pdf"),
        key=lambda p: int(volume_from_filename(p) or 0),
    )
    if not pdfs:
        print(f"  [skip] no BiharAlAnwaar_V*.pdf under {bihar_dir}")
        return 0
    total = 0
    for pdf in pdfs:
        vol = volume_from_filename(pdf) or "0"
        docs = build_bihar_documents(pdf, volume=vol)
        if docs:
            write_jsonl(docs, KNOWLEDGE / "hadith" / f"bihar-al-anwar-v{int(vol):03d}.jsonl")
            total += len(docs)
    return total


def ingest_ilal(ilal_dir: Path) -> int:
    """Ingest the hubeali English Ilal al-Sharayi PDFs."""
    pdfs = sorted(ilal_dir.glob("**/*ILLAL*AL*SHARAI*.pdf"), key=lambda p: p.name)
    if not pdfs:
        pdfs = sorted(ilal_dir.glob("**/*Illal*.pdf"), key=lambda p: p.name)
    seen_names: set[str] = set()
    pdfs = [p for p in pdfs if p.name not in seen_names and not seen_names.add(p.name)]  # type: ignore[func-returns-value]
    if not pdfs:
        print(f"  [skip] no Ilal al-Sharayi PDFs under {ilal_dir}")
        return 0
    total = 0
    for pdf in pdfs:
        vol, part = ilal_vol_part(pdf)
        vol = vol or "?"
        part = part or "?"
        docs = build_ilal_documents(pdf, volume=vol)
        if docs:
            write_jsonl(docs, KNOWLEDGE / "hadith" / f"ilal-al-sharayi-v{vol}-p{part}.jsonl")
            total += len(docs)
    return total


# OpenITI classical Arabic texts: filename-prefix -> (source_id, evidence_type,
# out file). Arabic-only; cited by section + printed volume/page (see the
# openiti adapter). Files are matched by prefix so version suffixes can change.
OPENITI_TARGETS = [
    ("0450Najashi.Rijal.", "rijal-al-najashi", "biographical", "rijal-al-najashi.jsonl"),
    ("0460ShaykhTusi.Rijal.", "rijal-al-tusi", "biographical", "rijal-al-tusi.jsonl"),
    ("0460ShaykhTusi.IkhtiyarMacrifatRijal.", "rijal-al-kashshi", "biographical", "rijal-al-kashshi.jsonl"),
    ("0460ShaykhTusi.Fihrist.", "fihrist-al-tusi", "biographical", "fihrist-al-tusi.jsonl"),
    ("0300IbnJacfarHimyari.QurbIsnad.", "qurb-al-isnad", "hadith", "qurb-al-isnad.jsonl"),
    ("0400IbnMuhammadKhazzaz.KifayatAthar.", "kifayat-al-athar", "hadith", "kifayat-al-athar.jsonl"),
    ("0413ShaykhMufid.AwailMaqalat.", "awail-al-maqalat", "scholarly_opinion", "awail-al-maqalat.jsonl"),
    ("0413ShaykhMufid.TashihIctiqadat.", "tashih-al-itiqadat", "scholarly_opinion", "tashih-al-itiqadat.jsonl"),
    # -- 2026-08 expansion: early hadith, kalam, history, devotional, rijal --
    ("0290IbnHasanSaffar.BasairDarajat.", "basair-al-darajat", "hadith", "basair-al-darajat.jsonl"),
    ("0274AhmadBarqi.Mahasin.", "al-mahasin", "hadith", "al-mahasin.jsonl"),
    ("0726CallamaHilli.KashfMurad.", "kashf-al-murad", "scholarly_opinion", "kashf-al-murad.jsonl"),
    ("0548IbnHasanTabarsi.IclamWara.", "ilam-al-wara", "historical", "ilam-al-wara.jsonl"),
    ("0460ShaykhTusi.MisbahMutahajjad.", "misbah-al-mutahajjid", "hadith", "misbah-al-mutahajjid.jsonl"),
    ("0436SharifMurtada.ShafiFiImama.", "al-shafi-fi-al-imamah", "scholarly_opinion", "al-shafi-fi-al-imamah.jsonl"),
    ("0588IbnShahrAshub.ManaqibAlAbiTalib.", "manaqib-al-abi-talib", "historical", "manaqib-al-abi-talib.jsonl"),
    ("1413TajDinKhui.MucjamRijal.", "mujam-rijal-al-hadith", "biographical", "mujam-rijal-al-hadith.jsonl"),
    # -- classical narration-based tafsir + Majma' al-Bayan --
    ("0329IbnIbrahimQummi.Tafsir.", "tafsir-al-qummi", "tafsir", "tafsir-al-qummi.jsonl"),
    ("0320IbnMascudCayyashi.Tafsir.", "tafsir-al-ayyashi", "tafsir", "tafsir-al-ayyashi.jsonl"),
    ("0548IbnHasanTabarsi.TafsirMajmacBayan.", "majma-al-bayan", "tafsir", "majma-al-bayan.jsonl"),
    ("1112IbnJumcaHuwayzi.TafsirNurThaqalayn.", "nur-al-thaqalayn", "tafsir", "nur-al-thaqalayn.jsonl"),
    # -- 2026-08 batch 3: debates, creed, fiqh manuals, usul, diraya --
    ("0560AbuMansurTabarsi.Ihtijaj.", "al-ihtijaj", "hadith", "al-ihtijaj.jsonl"),
    ("0400IbnJarirTabariSaghir.DalailImama.", "dalail-al-imamah", "hadith", "dalail-al-imamah.jsonl"),
    ("0436SharifMurtada.TanzihAnbiya.", "tanzih-al-anbiya", "scholarly_opinion", "tanzih-al-anbiya.jsonl"),
    ("0726CallamaHilli.BabHadiCashar.", "al-bab-al-hadi-ashar", "scholarly_opinion", "al-bab-al-hadi-ashar.jsonl"),
    ("1091MuhammadMuhsinFaydKashani.TafsirSafi.", "tafsir-al-safi", "tafsir", "tafsir-al-safi.jsonl"),
    ("0693IbnAbiFathIrbili.KashfGhumma.", "kashf-al-ghummah", "historical", "kashf-al-ghummah.jsonl"),
    ("0283AbuIshaqThaqafi.Gharat.", "al-gharat", "historical", "al-gharat.jsonl"),
    ("0664IbnTawus.IqbalAcmal.", "iqbal-al-amal", "hadith", "iqbal-al-amal.jsonl"),
    ("0676IbnHasanMuhaqqiqHilli.SharaicIslam.", "sharai-al-islam", "scholarly_opinion", "sharai-al-islam.jsonl"),
    ("1337MuhammadKazimTabatabaiYazdi.CurwaWuthqa.", "al-urwa-al-wuthqa", "scholarly_opinion", "al-urwa-al-wuthqa.jsonl"),
    ("0460ShaykhTusi.CiddatUsul.", "uddat-al-usul", "scholarly_opinion", "uddat-al-usul.jsonl"),
    ("0436SharifMurtada.Dharica.", "al-dharia", "scholarly_opinion", "al-dharia.jsonl"),
    ("1329MuhammadKazimAkhundKhurasani.KifayatUsul.", "kifayat-al-usul", "scholarly_opinion", "kifayat-al-usul.jsonl"),
    ("0965ShahidThani.RicayaFiCilmDiraya.", "al-riaya-fi-ilm-al-diraya", "scholarly_opinion", "al-riaya-fi-ilm-al-diraya.jsonl"),
    # -- 2026-08 batch 4 --
    ("0085SulaymIbnQaysHilali.KitabSulaym.", "kitab-sulaym", "hadith", "kitab-sulaym.jsonl"),
    ("0508FattalNaysaburi.RawdatWacizin.", "rawdat-al-waizin", "hadith", "rawdat-al-waizin.jsonl"),
    ("0413ShaykhMufid.FusulCashara.", "al-fusul-al-ashara", "scholarly_opinion", "al-fusul-al-ashara.jsonl"),
    ("0664IbnTawus.JamalUsbuc.", "jamal-al-usbu", "hadith", "jamal-al-usbu.jsonl"),
    ("0905IbnCaliTaqiDinKafcami.Misbah.", "misbah-al-kafami", "hadith", "misbah-al-kafami.jsonl"),
    ("0786ShahidAwwal.LumcaDimashqiyya.", "al-luma-al-dimashqiyya", "scholarly_opinion", "al-luma-al-dimashqiyya.jsonl"),
    ("0965ShahidThani.RawdaBahiyya.", "al-rawda-al-bahiyya", "scholarly_opinion", "al-rawda-al-bahiyya.jsonl"),
    ("1281MurtadaAnsari.FaraidUsul.", "faraid-al-usul", "scholarly_opinion", "faraid-al-usul.jsonl"),
    ("1011IbnShahidThani.MacalimDin.", "maalim-al-din", "scholarly_opinion", "maalim-al-din.jsonl"),
    # -- 2026-08 batch 5 --
    ("0413ShaykhMufid.Ikhtisas.", "al-ikhtisas", "hadith", "al-ikhtisas.jsonl"),
    ("0568MuwaffaqKhwarazmi.MaqtalHusayn.", "maqtal-al-khwarazmi", "historical", "maqtal-al-khwarazmi.jsonl"),
    ("1413TajDinKhui.MinhajSalihin.", "minhaj-al-salihin-khui", "scholarly_opinion", "minhaj-al-salihin-khui.jsonl"),
    ("0292Yacqubi.Tarikh.", "tarikh-al-yaqubi", "historical", "tarikh-al-yaqubi.jsonl"),
    ("0346Mascudi.MurujDhahab.", "muruj-al-dhahab", "historical", "muruj-al-dhahab.jsonl"),
    ("0573IbnHibatAllahQutbDinRawandi.Kharaij.", "al-kharaij", "hadith", "al-kharaij.jsonl"),
    ("0560IbnHamzaTusi.ThaqibFiManaqib.", "al-thaqib-fi-al-manaqib", "hadith", "al-thaqib-fi-al-manaqib.jsonl"),
    ("1107HashimBahrani.MadinatMacajiz.", "madinat-al-maajiz", "hadith", "madinat-al-maajiz.jsonl"),
    # -- 2026-08 batch 6 --
    ("0460ShaykhTusi.Amali.", "al-amali-tusi", "hadith", "al-amali-tusi.jsonl"),
    ("0436SharifMurtada.Amali.", "al-amali-murtada", "scholarly_opinion", "al-amali-murtada.jsonl"),
    ("0598IbnIdrisHilli.Sarair.", "al-sarair", "scholarly_opinion", "al-sarair.jsonl"),
    ("0726CallamaHilli.MukhtalafShica.", "mukhtalaf-al-shia", "scholarly_opinion", "mukhtalaf-al-shia.jsonl"),
    ("0726CallamaHilli.TadhkiratFuqaha.", "tadhkirat-al-fuqaha", "scholarly_opinion", "tadhkirat-al-fuqaha.jsonl"),
    ("1266MuhammadHasanNajafiJawahiri.JawahirKalam.", "jawahir-al-kalam", "scholarly_opinion", "jawahir-al-kalam.jsonl"),
    ("1281MurtadaAnsari.Makasib.", "al-makasib", "scholarly_opinion", "al-makasib.jsonl"),
    ("1450MurtadaCaskari.MacalimMadrasatayn.", "maalim-al-madrasatayn", "scholarly_opinion", "maalim-al-madrasatayn.jsonl"),
    ("0400IbnCaliHarrani.TuhafCuqul.", "tuhaf-al-uqul-ar", "hadith", "tuhaf-al-uqul-ar.jsonl"),
]


# Rafed Word-book texts: (book-dir/txt-file-prefix, source_id, evidence_type,
# volume, out file). Extracted at fetch time via antiword (see
# fetch_full_corpus.sh); Arabic-only, section + sequential locators.
RAFED_TARGETS = [
    ("1674/usul-alfiqh", "usul-al-fiqh-muzaffar", "scholarly_opinion", None, "usul-al-fiqh-muzaffar.jsonl"),
    ("4564/meqbas", "miqbas-al-hidaya", "scholarly_opinion", None, "miqbas-al-hidaya.jsonl"),
    ("1642/nihayat", "nihayat-al-hikmah", "scholarly_opinion", None, "nihayat-al-hikmah.jsonl"),
    ("1571/bedaiatolhekma", "bidayat-al-hikmah", "scholarly_opinion", None, "bidayat-al-hikmah.jsonl"),
    ("1477/alborhan-01", "tafsir-al-burhan", "tafsir", "1", "tafsir-al-burhan-v1.jsonl"),
    ("153/menhaj", "minhaj-al-salihin-sistani", "scholarly_opinion", None, "minhaj-al-salihin-sistani.jsonl"),
    ("2515/esbat-alvasya", "ithbat-al-wasiyya", "historical", None, "ithbat-al-wasiyya.jsonl"),
    ("360/t-forat", "tafsir-furat-al-kufi", "tafsir", None, "tafsir-furat-al-kufi.jsonl"),
    ("393/mostamsak", "mustamsak-al-urwa", "scholarly_opinion", None, "mustamsak-al-urwa.jsonl"),
    ("625/dros-fi-osol", "durus-fi-ilm-al-usul", "scholarly_opinion", None, "durus-fi-ilm-al-usul.jsonl"),
]


# Uploaded prose book PDFs (text-layer, page-number headers) found under the
# Bihar source repo: (glob, source_id, evidence_type, book-title marker,
# translation credit, out file). See the prose_pdf adapter.
PROSE_PDF_TARGETS = [
    ("**/Fatimah-al-Zahra*.pdf", "fatima-min-al-mahd-ila-al-lahd", "historical",
     "From the Cradle to the Grave", "Tahir Ridha Jaffer (WOFIS, 2015)",
     "fatima-min-al-mahd-ila-al-lahd.jsonl"),
]


def ingest_prose_pdfs(root_dir: Path) -> int:
    """Ingest uploaded text-layer book PDFs (see PROSE_PDF_TARGETS)."""
    total = 0
    for pattern, source_id, etype, marker, tsource, out in PROSE_PDF_TARGETS:
        matches = sorted(root_dir.glob(pattern))
        if not matches:
            print(f"  [skip] {pattern} not found under {root_dir}")
            continue
        docs = build_prose_pdf_documents(
            matches[0], source_id=source_id, evidence_type=EvidenceType(etype),
            book_title_marker=marker, translation_source=tsource,
        )
        if docs:
            write_jsonl(docs, KNOWLEDGE / "prose" / out)
            total += len(docs)
    return total


def ingest_rafed(rafed_dir: Path) -> int:
    """Ingest antiword-extracted Rafed Word books (see RAFED_TARGETS)."""
    total = 0
    for prefix, source_id, etype, volume, out in RAFED_TARGETS:
        matches = sorted(rafed_dir.glob(f"{prefix}*.txt"))
        if not matches:
            print(f"  [skip] {prefix}*.txt not found under {rafed_dir}")
            continue
        docs = build_rafed_documents(
            matches[0], source_id=source_id, evidence_type=EvidenceType(etype), volume=volume,
        )
        if docs:
            subdir = "prose"
            write_jsonl(docs, KNOWLEDGE / subdir / out)
            total += len(docs)
    return total


# Sunni canonical works ingested for COMPARATIVE research: same OpenITI
# format, tagged "sunni-comparative" and registered with explicit Sunni-source
# markers so the assistant never presents them as Twelver positions.
OPENITI_SUNNI_TARGETS = [
    ("0256Bukhari.Sahih.", "sahih-al-bukhari", "hadith", "sahih-al-bukhari.jsonl"),
    ("0261Muslim.Sahih.", "sahih-muslim", "hadith", "sahih-muslim.jsonl"),
    ("0241IbnHanbal.Musnad.", "musnad-ahmad", "hadith", "musnad-ahmad.jsonl"),
    ("0279Tirmidhi.Sunan.", "sunan-al-tirmidhi", "hadith", "sunan-al-tirmidhi.jsonl"),
    ("0303Nasai.SunanSughra.", "sunan-al-nasai", "hadith", "sunan-al-nasai.jsonl"),
    ("0275AbuDawudSijistani.Sunan.", "sunan-abi-dawud", "hadith", "sunan-abi-dawud.jsonl"),
    ("0273IbnMaja.Sunan.", "sunan-ibn-majah", "hadith", "sunan-ibn-majah.jsonl"),
    ("0405HakimNaysaburi.Mustadrak.", "al-mustadrak-hakim", "hadith", "al-mustadrak-hakim.jsonl"),
    ("0303Nasai.KhasaisAmirMumininCali.", "khasais-al-nasai", "hadith", "khasais-al-nasai.jsonl"),
    ("0480IbnAhmadHakimHaskani.ShawahidTanzil.", "shawahid-al-tanzil", "tafsir", "shawahid-al-tanzil.jsonl"),
    ("0310Tabari.Tarikh.", "tarikh-al-tabari", "historical", "tarikh-al-tabari.jsonl"),
    ("0279Baladhuri.AnsabAshraf.", "ansab-al-ashraf", "historical", "ansab-al-ashraf.jsonl"),
    ("0230IbnSacd.TabaqatKubra.", "tabaqat-ibn-sad", "biographical", "tabaqat-ibn-sad.jsonl"),
]


def ingest_openiti(openiti_dir: Path) -> int:
    """Ingest OpenITI mARkdown texts (classical Arabic, page-cited)."""
    total = 0
    for targets, extra in ((OPENITI_TARGETS, None),
                           (OPENITI_SUNNI_TARGETS, ["sunni-comparative"])):
        for prefix, source_id, etype, out in targets:
            matches = sorted(openiti_dir.glob(f"{prefix}*"))
            if not matches:
                print(f"  [skip] {prefix}* not found under {openiti_dir}")
                continue
            docs = build_openiti_documents(
                matches[0], source_id=source_id, evidence_type=EvidenceType(etype),
                extra_tags=extra,
            )
            if docs:
                subdir = "biographical" if etype == "biographical" else "hadith" \
                    if etype == "hadith" else "prose"
                write_jsonl(docs, KNOWLEDGE / subdir / out)
                total += len(docs)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quran-dir", default=os.environ.get("QURAN_DIR"))
    parser.add_argument("--thaqalayn-dir", default=os.environ.get("THAQALAYN_DATA_DIR"))
    parser.add_argument("--shiavault-dir", default=os.environ.get("SHIAVAULT_DIR"))
    parser.add_argument("--bihar-dir", default=os.environ.get("BIHAR_DIR"))
    parser.add_argument("--almizan-dir", default=os.environ.get("ALMIZAN_DIR"))
    parser.add_argument("--wasail-dir", default=os.environ.get("WASAIL_DIR"),
                        help="directory containing Wasail al-Shia ws<N>_eng.pdf volumes")
    parser.add_argument("--ilal-dir", default=os.environ.get("ILAL_DIR"),
                        help="directory containing Ilal al-Sharayi hubeali PDFs")
    parser.add_argument("--mafatih-json", default=os.environ.get("MAFATIH_JSON"),
                        help="path to the Mafatih al-Jinan chapters.json")
    parser.add_argument("--openiti-dir", default=os.environ.get("OPENITI_DIR"),
                        help="directory containing downloaded OpenITI mARkdown texts")
    parser.add_argument("--rafed-dir", default=os.environ.get("RAFED_DIR"),
                        help="directory containing antiword-extracted Rafed book texts")
    args = parser.parse_args()

    n_quran = n_hadith = n_prose = n_bihar = n_almizan = n_wasail = n_ilal = n_mafatih = 0
    n_openiti = 0
    if args.quran_dir:
        print("Ingesting Qur'an...")
        n_quran = ingest_quran(Path(args.quran_dir))
    else:
        print("  [skip] no --quran-dir / QURAN_DIR")

    if args.thaqalayn_dir:
        print("Ingesting hadith (ThaqalaynData)...")
        n_hadith = ingest_hadith(Path(args.thaqalayn_dir))
    else:
        print("  [skip] no --thaqalayn-dir / THAQALAYN_DATA_DIR")

    if args.shiavault_dir:
        print("Ingesting prose (Shiavault)...")
        n_prose = ingest_prose(Path(args.shiavault_dir))
    else:
        print("  [skip] no --shiavault-dir / SHIAVAULT_DIR")

    if args.bihar_dir:
        print("Ingesting Bihar al-Anwar (hubeali PDFs)...")
        n_bihar = ingest_bihar(Path(args.bihar_dir))
        print("Ingesting uploaded prose book PDFs...")
        n_prose += ingest_prose_pdfs(Path(args.bihar_dir))
    else:
        print("  [skip] no --bihar-dir / BIHAR_DIR")

    if args.almizan_dir:
        print("Ingesting al-Mizan (40-volume text)...")
        n_almizan = ingest_almizan(Path(args.almizan_dir))
    else:
        print("  [skip] no --almizan-dir / ALMIZAN_DIR")

    if args.wasail_dir:
        print("Ingesting Wasail al-Shia (English PDFs, per-hadith)...")
        n_wasail = ingest_wasail(Path(args.wasail_dir))
    else:
        print("  [skip] no --wasail-dir / WASAIL_DIR")

    if args.ilal_dir:
        print("Ingesting Ilal al-Sharayi (hubeali PDFs)...")
        n_ilal = ingest_ilal(Path(args.ilal_dir))
    else:
        print("  [skip] no --ilal-dir / ILAL_DIR")

    if args.mafatih_json:
        print("Ingesting Mafatih al-Jinan (structured JSON)...")
        n_mafatih = ingest_mafatih(Path(args.mafatih_json))
    else:
        print("  [skip] no --mafatih-json / MAFATIH_JSON")

    if args.openiti_dir:
        print("Ingesting OpenITI classical Arabic texts...")
        n_openiti = ingest_openiti(Path(args.openiti_dir))
    else:
        print("  [skip] no --openiti-dir / OPENITI_DIR")

    if args.rafed_dir:
        print("Ingesting Rafed Word-book texts...")
        n_openiti += ingest_rafed(Path(args.rafed_dir))
    else:
        print("  [skip] no --rafed-dir / RAFED_DIR")

    print(f"\nDone. {n_quran} Qur'an verses, {n_hadith + n_bihar + n_wasail + n_ilal} hadith "
          f"({n_bihar} Bihar, {n_wasail} Wasail, {n_ilal} Ilal), "
          f"{n_prose + n_almizan + n_mafatih} prose passages "
          f"({n_almizan} al-Mizan, {n_mafatih} Mafatih), "
          f"{n_openiti} OpenITI classical-text passages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
