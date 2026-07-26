"""Prose ingestion adapter for Shiavault-style Markdown books.

The [shiavault-library](https://github.com/shiavault/shiavault-library) mirrors
al-islam.org books as per-chapter Markdown plus a ``metadata.yml``. Unlike the
structured hadith corpora, these are **prose** works (tafsīr, biography,
history, translated supplications), so this adapter produces *coarser*
citations: source + chapter title + a within-chapter section locator. There is
no hadith number or rijāl grade, and — because most are English translations or
secondary works — confidence defaults to ``medium`` and never higher here.

Honesty rules kept intact:

* We never fabricate. A book with no readable chapters yields no documents.
* Provenance (title, author, publisher, source URL) is read from
  ``metadata.yml`` and attached, so every passage remains traceable.
* These prose passages are clearly a different evidence tier from the
  per-narration hadith corpora; callers pass the right ``evidence_type`` and a
  ``medium`` (or lower) confidence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...ingestion.loaders import chunk_text
from ...models import Citation, ConfidenceLevel, Document, EvidenceType

_TAG = re.compile(r"<[^>]+>")
_FOOTNOTE_DEF = re.compile(r"^\s*\[\^[^\]]+\]:.*$", re.MULTILINE)
_FOOTNOTE_REF = re.compile(r"\[\^[^\]]+\]")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_NUM_PREFIX = re.compile(r"^(\d+)-")
_WS_LINES = re.compile(r"\n{3,}")


def _clean_markdown(text: str) -> str:
    """Reduce Markdown/HTML to plain readable text (keeps Arabic + English)."""
    text = _IMAGE.sub("", text)
    text = _FOOTNOTE_DEF.sub("", text)
    text = _FOOTNOTE_REF.sub("", text)
    text = _MD_LINK.sub(r"\1", text)       # keep link text, drop target
    text = _TAG.sub("", text)              # strip raw HTML (blockquote/p/etc.)
    text = _BLOCKQUOTE.sub("", text)       # drop '>' quote markers
    text = re.sub(r"[*_`]{1,3}", "", text) # emphasis/code marks
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)  # ATX headings
    text = re.sub(r"\\([^\w\s]|[A-Za-z])", r"\1", text)  # unescape markdown backslashes
    text = _WS_LINES.sub("\n\n", text)
    return text.strip()


def _split_title(md: str, fallback: str) -> tuple[str, str]:
    """Return (chapter_title, body). Handles Setext (===) and ATX (#) headings."""
    lines = md.splitlines()
    # drop leading blanks
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return fallback, ""
    first = lines[i].strip()
    # Setext: title line followed by ==== or ----
    if i + 1 < len(lines) and re.match(r"^[=-]{3,}\s*$", lines[i + 1]):
        return _clean_markdown(first) or fallback, "\n".join(lines[i + 2:])
    if first.startswith("#"):
        return _clean_markdown(first) or fallback, "\n".join(lines[i + 1:])
    return fallback, md


def _read_metadata(book_dir: Path) -> dict:
    meta_path = book_dir / "metadata.yml"
    if not meta_path.exists():
        return {}
    text = meta_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - minimal fallback for a few flat keys
        out: dict = {}
        for line in text.splitlines():
            m = re.match(r"^([a-z_]+):\s*(.+?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("'\"")
        return out


def build_prose_documents(
    book_dir: str | Path,
    *,
    source_id: str,
    evidence_type: EvidenceType,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    volume: Optional[str] = None,
    max_chars: int = 1500,
) -> list[Document]:
    """Chunk a Shiavault book directory into cited prose :class:`Document`s.

    Each chunk is cited as ``source_id`` + chapter title + a ``chapter.section``
    locator (stored in ``page`` so the citation is verifiable/complete for any
    evidence type). ``volume`` is set for multi-volume works like al-Mīzān.
    """
    book_dir = Path(book_dir)
    meta = _read_metadata(book_dir)

    def _meta(*keys: str) -> Optional[str]:
        # Return the first present, non-placeholder metadata value.
        for k in keys:
            v = meta.get(k)
            if v and str(v).strip().lower() not in ("n/a", "na", "none", "-", "unknown"):
                return str(v).strip()
        return None

    publisher = _meta("publisher")
    translator = _meta("translator", "author")
    src_url = _meta("source_url")
    tsource = " / ".join(x for x in [translator, publisher, src_url] if x) or "Shiavault (al-islam.org mirror)"

    chapters = sorted(
        (p for p in book_dir.glob("*.md")),
        key=lambda p: int(_NUM_PREFIX.match(p.name).group(1)) if _NUM_PREFIX.match(p.name) else 1_000_000,
    )
    docs: list[Document] = []
    for chapter_path in chapters:
        m = _NUM_PREFIX.match(chapter_path.name)
        chapter_no = m.group(1) if m else "0"
        raw = chapter_path.read_text(encoding="utf-8")
        fallback_title = chapter_path.stem
        title, body = _split_title(raw, fallback_title)
        body = _clean_markdown(body)
        if len(body) < 40:  # skip empty / nav-only chapters, don't fabricate
            continue
        for i, chunk in enumerate(chunk_text(body, max_chars=max_chars, overlap=150)):
            citation = Citation(
                source_id=source_id,
                evidence_type=evidence_type,
                volume=volume,
                chapter=title,
                page=f"{chapter_no}.{i}",  # within-book section locator (not print page)
                translation=None,
                translation_source=tsource,
            )
            docs.append(
                Document(
                    id=f"{source_id}-{('v' + volume + '-') if volume else ''}{chapter_no}-{i}",
                    text=chunk,
                    evidence_type=evidence_type,
                    citation=citation,
                    confidence=confidence,
                    tags=[source_id, "prose"],
                    language="en",
                )
            )
    return docs
