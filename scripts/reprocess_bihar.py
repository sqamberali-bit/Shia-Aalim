#!/usr/bin/env python3
"""Re-process existing Bihar al-Anwar page-level JSONL into per-hadith documents.

The adapter upgrade splits narrations using the footnote references that are
already present in the ingested text — no PDFs needed.  Run from the repo root:

    python scripts/reprocess_bihar.py [--dry-run]

This reads every ``data/knowledge/hadith/bihar-al-anwar-v*.jsonl``, re-splits
each volume's pages into per-hadith documents (where footnotes allow), and
overwrites the JSONL in place.  Use ``--dry-run`` to see counts without writing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shia_aalim.ingestion.adapters.bihar import (  # noqa: E402
    _emit_doc,
    _hadith_sort_key,
    _split_pages_into_narrations,
)
from shia_aalim.models import ConfidenceLevel, Document  # noqa: E402

KNOWLEDGE = Path("data/knowledge/hadith")
SOURCE_ID = "bihar-al-anwar"
TRANSLATION_SOURCE = "Hubeali (English), www.hubeali.com"
MIN_CHARS = 120


def _reprocess_volume(jsonl_path: Path, *, dry_run: bool) -> tuple[int, int]:
    """Re-split one volume JSONL from page-level to per-hadith.

    Returns ``(old_count, new_count)``.
    """
    with open(jsonl_path, encoding="utf-8") as f:
        pages = [json.loads(line) for line in f if line.strip()]

    old_count = len(pages)
    if not pages:
        return 0, 0

    # Build page_records in the same shape as iter_bihar_pages yields:
    #   (volume, page, cleaned_text)
    page_records: list[tuple[str, str, str]] = []
    for page_doc in pages:
        doc_id = page_doc["id"]
        text = page_doc["text"]
        id_m = re.match(r"bihar-al-anwar-v(\d+)-p(\d+)", doc_id)
        vol = id_m.group(1) if id_m else "?"
        page = id_m.group(2) if id_m else "?"
        page_records.append((vol, page, text))

    docs: list[Document] = []
    seen: set[str] = set()

    for detected_vol, page, chapter, hadith_id, body in _split_pages_into_narrations(
        page_records,
    ):
        _emit_doc(
            docs, seen, detected_vol, page, chapter, hadith_id, body,
            volume_override=None, source_id=SOURCE_ID,
            confidence=ConfidenceLevel.MEDIUM,
            translation_source=TRANSLATION_SOURCE,
            min_chars=MIN_CHARS,
        )

    docs.sort(key=lambda d: (
        d.citation.volume or "",
        _hadith_sort_key(d.citation.hadith_number or "0"),
    ))

    if not dry_run:
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for d in docs:
                f.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")

    return old_count, len(docs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count without overwriting files",
    )
    args = parser.parse_args()

    if not KNOWLEDGE.exists():
        print(f"No {KNOWLEDGE} directory — nothing to reprocess.")
        return 0

    jsonls = sorted(KNOWLEDGE.glob("bihar-al-anwar-v*.jsonl"))
    if not jsonls:
        print("No Bihar JSONL files found.")
        return 0

    total_old = 0
    total_new = 0
    for jp in jsonls:
        old, new = _reprocess_volume(jp, dry_run=args.dry_run)
        delta = new - old
        sign = "+" if delta > 0 else ""
        print(f"  {jp.name}: {old} pages → {new} hadith ({sign}{delta})")
        total_old += old
        total_new += new

    label = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{label}{len(jsonls)} volumes: {total_old} page-docs → {total_new} hadith-docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
