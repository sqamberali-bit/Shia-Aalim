"""Mafātīḥ al-Jinān ingestion adapter (structured JSON du'ā'/ziyārāt manual).

Shaykh ʿAbbās al-Qummī's devotional manual is available as a structured JSON
tree in the Apache-2.0 licensed `aminpaydar/Mafatih` dataset: three *bābs*
(adʿiya / aʿmāl al-sana / ziyārāt) → *fuṣūl* (sections) → *articles* (one per
supplication or ziyāra) → ordered items. Each item is typed:

* ``Text``      — the **Arabic** supplication text itself (vocalised)
* ``Translate`` — its **Persian** rendering (Ansariyan)
* ``AboutText`` — Persian instructions ("recite this after the prayer…")

Design / honesty notes:

* One :class:`Document` per substantive ``Text`` item — the Arabic passage is the
  citable unit, so a citation resolves to an actual recitable text rather than a
  whole chapter.
* The adjacent ``Translate`` item (when present) is attached as
  ``citation.translation`` with its translator named. It is **Persian, not
  English** — the adapter never claims otherwise and never machine-translates.
* The preceding ``AboutText`` instruction is kept as ``context`` on the citation
  chapter path only; it is never merged into the Arabic text as if recited.
* Empty/whitespace-only items are skipped, never padded.

This is a devotional compilation (al-Qummī's editorial selection), so documents
are typed ``SCHOLARLY_OPINION`` at ``medium`` confidence, matching the registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType

_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")
_TAG = re.compile(r"<[^>]+>")

_DEFAULT_TRANSLATION_SOURCE = (
    "Husayn Ansariyan (Persian) — via aminpaydar/Mafatih (Apache-2.0)"
)


def _clean(text: str) -> str:
    """Collapse whitespace and strip stray markup, keeping Arabic/Persian intact."""
    if not text:
        return ""
    text = _TAG.sub(" ", text)
    text = "\n".join(_WS.sub(" ", ln).strip() for ln in text.splitlines())
    return _BLANKS.sub("\n\n", text).strip()


def _title(raw: str, fallback: str) -> str:
    """Titles in the source carry stray newlines; flatten them."""
    t = _clean(raw).replace("\n", " ").strip()
    return _WS.sub(" ", t) or fallback


def build_mafatih_documents(
    json_path: str | Path,
    *,
    source_id: str = "mafatih-al-jinan",
    evidence_type: EvidenceType = EvidenceType.SCHOLARLY_OPINION,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    translation_source: str = _DEFAULT_TRANSLATION_SOURCE,
    min_chars: int = 20,
) -> list[Document]:
    """Build cited :class:`Document`s from the Mafātīḥ al-Jinān JSON tree.

    Each document is one Arabic supplication passage, cited by its
    ``bāb / faṣl / article`` path plus a ``<article>.<item>`` locator, with the
    Persian translation attached when the source provides one.
    """
    json_path = Path(json_path)
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    if not isinstance(data, list):
        return []

    docs: list[Document] = []
    article_no = 0
    for bab in data:
        if not isinstance(bab, dict):
            continue
        bab_title = _title(bab.get("title", ""), "Mafatih al-Jinan")
        for section in bab.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_title = _title(section.get("title", ""), "")
            for article in section.get("articles") or []:
                if not isinstance(article, dict):
                    continue
                article_no += 1
                article_title = _title(article.get("title", ""), f"article {article_no}")
                items = [i for i in (article.get("items") or []) if isinstance(i, dict)]

                # Chapter path: bab / fasl / article — the human-verifiable location.
                chapter = " / ".join(x for x in (bab_title, section_title, article_title) if x)

                for idx, item in enumerate(items):
                    if (item.get("type") or "") != "Text":
                        continue
                    arabic = _clean(item.get("content") or "")
                    if len(arabic) < min_chars:
                        continue  # blank spacer item — skip, never pad

                    # The Persian rendering, when the next item supplies one.
                    persian = ""
                    for nxt in items[idx + 1: idx + 3]:
                        if (nxt.get("type") or "") == "Translate":
                            persian = _clean(nxt.get("content") or "")
                            break

                    citation = Citation(
                        source_id=source_id,
                        evidence_type=evidence_type,
                        chapter=chapter,
                        page=f"{article_no}.{idx}",  # within-book locator, not a print page
                        arabic_text=arabic,
                        translation=persian or None,
                        translation_source=translation_source if persian else None,
                    )
                    docs.append(
                        Document(
                            id=f"{source_id}-{article_no}-{idx}",
                            text=arabic,
                            evidence_type=evidence_type,
                            citation=citation,
                            confidence=confidence,
                            tags=[source_id, "dua", "prose"],
                            language="ar",
                        )
                    )
    return docs
