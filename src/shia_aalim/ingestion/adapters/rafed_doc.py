"""Rafed digital-library Word-book adapter (antiword text).

`books.rafed.net <https://books.rafed.net>`_ distributes classical/modern
Arabic Shia texts as Word files (``/api/download/<b_id>/doc``). Converted to
plain text with ``antiword -m UTF-8``, the layout is consistent:

* deeply indented (centred) lines are section headings;
* body paragraphs start with a small indent and wrap flat;
* each printed page's footnotes follow a ``____`` rule line. The footnotes are
  the edition's scholarly apparatus (source references) and are kept verbatim
  as part of the text; only the rule lines and ``[pic]`` artefacts are
  dropped.

The Word files carry no printed page markers after conversion, so citations
use *section heading + a sequential locator within the digital edition*
(stored in ``page``) — the same honest convention as the Shiavault prose
books. Confidence is capped at medium.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType

_HEADING = re.compile(r"^\s{18,}(\S.*)$")
_PARA_START = re.compile(r"^\s{2,8}\S")
_RULE = re.compile(r"^\s*_{6,}\s*$")
_PIC = re.compile(r"\[pic\]")
_WS = re.compile(r"[ \t]+")


def build_rafed_documents(
    txt_path: str | Path,
    *,
    source_id: str,
    evidence_type: EvidenceType,
    volume: Optional[str] = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    max_chars: int = 1500,
    min_chars: int = 40,
) -> list[Document]:
    """Chunk one antiword-extracted Rafed book into cited Arabic documents."""
    section = ""
    paras: list[tuple[str, str]] = []  # (section, paragraph)
    buf: list[str] = []

    def flush():
        if buf:
            text = _WS.sub(" ", " ".join(buf)).strip()
            if text:
                paras.append((section, text))
            buf.clear()

    for line in Path(txt_path).read_text(encoding="utf-8", errors="replace").splitlines():
        if _RULE.match(line) or _PIC.search(line):
            continue
        if not line.strip():
            flush()
            continue
        m = _HEADING.match(line)
        if m and len(m.group(1).strip()) < 90:
            flush()
            section = _WS.sub(" ", m.group(1)).strip()
            continue
        if _PARA_START.match(line):
            flush()
        buf.append(line.strip())
    flush()

    docs: list[Document] = []
    chunk: list[str] = []
    chunk_section: Optional[str] = None
    counter = 0

    def emit():
        nonlocal chunk, chunk_section, counter
        text = "\n".join(chunk)
        if len(text) >= min_chars and chunk_section is not None:
            citation = Citation(
                source_id=source_id,
                evidence_type=evidence_type,
                volume=volume,
                chapter=chunk_section or None,
                page=str(counter),  # sequential digital-edition locator
                translation_source="Rafed digital library (books.rafed.net) Word edition",
            )
            docs.append(
                Document(
                    id=f"{source_id}-{('v' + volume + '-') if volume else ''}{counter}",
                    text=text,
                    evidence_type=evidence_type,
                    citation=citation,
                    confidence=confidence,
                    tags=[source_id, "rafed"],
                    language="ar",
                )
            )
            counter += 1
        chunk = []
        chunk_section = None

    for sec, para in paras:
        if chunk and (sec != chunk_section or sum(len(c) for c in chunk) + len(para) > max_chars):
            emit()
        if not chunk:
            chunk_section = sec
        chunk.append(para)
    emit()
    return docs
