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

from shia_aalim.ingestion.adapters.quran import build_quran_documents  # noqa: E402
from shia_aalim.ingestion.adapters.shiavault import build_prose_documents  # noqa: E402
from shia_aalim.ingestion.adapters.thaqalayn import build_hadith_documents  # noqa: E402
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
    docs = build_quran_documents(
        arabic, qarai, translation_name="Ali Quli Qarai (via fawazahmed0/quran-api)"
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
]

# Prose works from the Shiavault Markdown mirror (al-islam.org). These are
# tafsir / biography / history / translated supplications — coarser,
# chapter-level citations, medium confidence (translations / secondary works).
# (rel path, source_id, EvidenceType, volume-or-None, out shard)
PROSE_TARGETS = [
    ("books/al-mizan-an-exegesis-of-the-qur-an-volume-one", "al-mizan", "tafsir", "1", "al-mizan-v1.jsonl"),
    ("books/al-mizan-an-exegesis-of-the-qur-an-volume-two", "al-mizan", "tafsir", "2", "al-mizan-v2.jsonl"),
    ("books/al-mizan-an-exegesis-of-the-qur-an-volume-four", "al-mizan", "tafsir", "4", "al-mizan-v4.jsonl"),
    ("books/al-mizan-an-exegesis-of-the-quran-volume-seven", "al-mizan", "tafsir", "7", "al-mizan-v7.jsonl"),
    ("books/al-mizan-an-exegesis-of-the-qur-an-volume-eight", "al-mizan", "tafsir", "8", "al-mizan-v8.jsonl"),
    ("books/as-sahifa-al-kamilah-al-sajjadiyya", "sahifa-sajjadiyya", "hadith", None, "sahifa-sajjadiyya.jsonl"),
    ("books/the-message", "the-message-subhani", "historical", None, "seerah-the-message.jsonl"),
    ("books/maqtal-al-husayn", "maqtal-al-husayn", "historical", None, "maqtal-al-husayn.jsonl"),
    ("books/kitab-al-irshad-1", "kitab-al-irshad", "historical", None, "kitab-al-irshad.jsonl"),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quran-dir", default=os.environ.get("QURAN_DIR"))
    parser.add_argument("--thaqalayn-dir", default=os.environ.get("THAQALAYN_DATA_DIR"))
    parser.add_argument("--shiavault-dir", default=os.environ.get("SHIAVAULT_DIR"))
    args = parser.parse_args()

    n_quran = n_hadith = n_prose = 0
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

    print(f"\nDone. {n_quran} Qur'an verses, {n_hadith} hadith, {n_prose} prose passages ingested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
