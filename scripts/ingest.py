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
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.ingestion.adapters.quran import build_quran_documents  # noqa: E402
from shia_aalim.ingestion.adapters.thaqalayn import build_hadith_documents  # noqa: E402
from shia_aalim.models import Document  # noqa: E402

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


def ingest_hadith(thaqalayn_dir: Path) -> int:
    total = 0
    targets = [
        ("books/al-kafi/1/3", "al-kafi", "Book of Tawheed (al-Kafi, Kitab al-Tawhid)", "al-kafi-tawhid.jsonl"),
        ("books/al-kafi/1/1", "al-kafi", "Book of Intellect and Ignorance (al-Kafi)", "al-kafi-intellect.jsonl"),
    ]
    for rel, source_id, title, out in targets:
        book_dir = thaqalayn_dir / rel
        if not book_dir.exists():
            print(f"  [skip] {rel} not found under {thaqalayn_dir}")
            continue
        docs = build_hadith_documents(book_dir, source_id=source_id, book_title=title)
        if docs:
            write_jsonl(docs, KNOWLEDGE / "hadith" / out)
            total += len(docs)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quran-dir", default=os.environ.get("QURAN_DIR"))
    parser.add_argument("--thaqalayn-dir", default=os.environ.get("THAQALAYN_DATA_DIR"))
    args = parser.parse_args()

    n_quran = n_hadith = 0
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

    print(f"\nDone. {n_quran} Qur'an verses, {n_hadith} hadith ingested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
