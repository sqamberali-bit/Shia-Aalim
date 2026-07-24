#!/usr/bin/env python3
"""Export the JSONL corpus as clean, cited, human-readable text — for feeding
Claude (Projects / Desktop) as a knowledge base.

JSONL is poor for an LLM knowledge base; labelled plain text with the citation
on every passage is ideal (Claude can retrieve and cite it directly). This
writes one ``.txt`` per source book, each passage headed by its exact reference,
Qur'anic verses shown in Arabic + English + Urdu.

    python scripts/export_corpus.py --out export/full            # everything
    python scripts/export_corpus.py --out export/core \
        --only quran,al-kafi,man-la-yahduruhu-al-faqih,tahdhib-al-ahkam,al-istibsar,nahj-al-balagha
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from shia_aalim.ingestion.loaders import iter_knowledge_dir  # noqa: E402
from shia_aalim.models import EvidenceType  # noqa: E402
from shia_aalim.sources import load_sources  # noqa: E402

KNOWLEDGE = ROOT / "data" / "knowledge"
REGISTRY = ROOT / "data" / "sources" / "registry.yaml"


def _titles() -> dict[str, str]:
    try:
        return {s.id: s.title for s in load_sources(REGISTRY)}
    except Exception:  # noqa: BLE001
        return {}


def _passage(doc) -> str:
    c = doc.citation
    ref = c.reference_string()
    if doc.evidence_type is EvidenceType.QURAN:
        lines = [f"### Qur'an {c.surah}:{c.ayah}"]
        if c.arabic_text:
            lines.append(f"Arabic: {c.arabic_text.strip()}")
        lines.append(f"English: {doc.text.strip()}")
        if c.translation_ur:
            lines.append(f"Urdu: {c.translation_ur.strip()}")
        return "\n".join(lines)
    head = f"### {ref}"
    if c.grade and c.grade.value != "ungraded":
        head += f"  (grade: {c.grade.value}"
        if c.grade_source:
            head += f" — {c.grade_source}"
        head += ")"
    return f"{head}\n{doc.text.strip()}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--knowledge-dir", default=str(KNOWLEDGE))
    p.add_argument("--out", default=str(ROOT / "export" / "full"))
    p.add_argument("--only", default="", help="comma-separated source ids (default: all)")
    args = p.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    titles = _titles()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    by_source: dict[str, list] = defaultdict(list)
    for doc in iter_knowledge_dir(args.knowledge_dir):
        sid = doc.citation.source_id
        if only and sid not in only:
            continue
        by_source[sid].append(doc)

    total = 0
    index_lines = ["# Shia-Aalim corpus export", "",
                   "Each file is one source book; every passage is headed by its exact "
                   "citation. Qur'anic verses include Arabic + English + Urdu.", ""]
    for sid, docs in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
        docs.sort(key=lambda d: (d.citation.surah or 0, d.citation.ayah or 0, d.id))
        title = titles.get(sid, sid)
        fp = out / f"{sid}.txt"
        with fp.open("w", encoding="utf-8") as fh:
            fh.write(f"SOURCE: {title}  (id: {sid})\n")
            fh.write(f"{len(docs)} passages. Verify every citation against the primary source.\n\n")
            for d in docs:
                fh.write(_passage(d) + "\n\n")
        size_mb = fp.stat().st_size / 1e6
        index_lines.append(f"- **{title}** — {len(docs):,} passages ({size_mb:.1f} MB) → `{sid}.txt`")
        total += len(docs)
        print(f"  {len(docs):>6,}  {size_mb:5.1f} MB  {fp.name}")

    (out / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"\nExported {total:,} passages across {len(by_source)} books to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
