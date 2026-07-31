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
from shia_aalim.ingestion.adapters.quran import build_quran_documents  # noqa: E402
from shia_aalim.ingestion.adapters.shiavault import build_prose_documents  # noqa: E402
from shia_aalim.ingestion.adapters.thaqalayn import build_hadith_documents  # noqa: E402
from shia_aalim.ingestion.adapters.wasail import build_wasail_documents  # noqa: E402
from shia_aalim.ingestion.adapters.wasail import volume_from_filename as wasail_volume  # noqa: E402
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
    pdfs = sorted(
        wasail_dir.glob("**/ws*_eng.pdf"),
        key=lambda p: int(wasail_volume(p) or 0),
    )
    if not pdfs:
        print(f"  [skip] no ws*_eng.pdf under {wasail_dir}")
        return 0
    total = 0
    for pdf in pdfs:
        vol = wasail_volume(pdf) or "0"
        docs = build_wasail_documents(pdf, volume=vol)
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
    args = parser.parse_args()

    n_quran = n_hadith = n_prose = n_bihar = n_almizan = n_wasail = n_ilal = n_mafatih = 0
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

    print(f"\nDone. {n_quran} Qur'an verses, {n_hadith + n_bihar + n_wasail + n_ilal} hadith "
          f"({n_bihar} Bihar, {n_wasail} Wasail, {n_ilal} Ilal), "
          f"{n_prose + n_almizan + n_mafatih} prose passages "
          f"({n_almizan} al-Mizan, {n_mafatih} Mafatih).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
