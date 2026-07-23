"""Plain-text book adapter — for OCR'd / plain ``.txt`` volumes (e.g. the
Tawheed Institute English al-Mīzān).

These are prose works with **no structural markup**, often OCR'd, so:

* front-matter tables-of-contents (dotted-leader lines), running headers/footers
  and lone page numbers are stripped as noise;
* badly-garbled lines (very low ASCII-letter ratio — typically OCR'd Arabic
  fragments) are dropped rather than presented as if they were real text;
* the surviving body is chunked into overlapping passages, cited by
  **source + volume + section** (a within-volume locator).

Like the other prose adapters, output is a *lower* evidence tier: a translated,
OCR'd tafsīr at ``medium`` confidence, no ḥadīth grade. Nothing is invented —
noise is removed, never filled in, and an empty file yields no documents.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...ingestion.loaders import chunk_text
from ...models import Citation, ConfidenceLevel, Document, EvidenceType

_DOTTED_LEADER = re.compile(r"\.{4,}|\. \. \.|(?:\.\s){4,}")
_RUNNING_HEADER = re.compile(r"(?i)^\s*al-?mizan(\s+volume\s+\d+)?\s*$")
_LONE_PAGENO = re.compile(r"^\s*\d{1,4}\s*$")
_URL = re.compile(r"(?i)tawheed\.com\.au|www\.")
_VOL_FROM_NAME = re.compile(r"(\d+)")
_BLANKS = re.compile(r"\n{3,}")


def _is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return False  # keep blanks (paragraph separators)
    if _DOTTED_LEADER.search(s):
        return True
    if s.count(".") > len(s) * 0.18:
        return True
    if _RUNNING_HEADER.match(s):
        return True
    if _LONE_PAGENO.match(s):
        return True
    if _URL.search(s):
        return True
    # Heavily-garbled line (OCR): low ratio of ASCII letters and it isn't short.
    ascii_alpha = sum(c.isalpha() and ord(c) < 128 for c in s)
    if len(s) > 15 and ascii_alpha < len(s) * 0.45:
        return True
    return False


def clean_text(raw: str) -> str:
    kept = [ln.strip() for ln in raw.splitlines() if not _is_noise(ln)]
    return _BLANKS.sub("\n\n", "\n".join(kept)).strip()


def volume_from_filename(path: str | Path) -> Optional[str]:
    m = _VOL_FROM_NAME.search(Path(path).stem)
    return m.group(1) if m else None


def build_textbook_documents(
    txt_path: str | Path,
    *,
    source_id: str,
    evidence_type: EvidenceType = EvidenceType.TAFSIR,
    volume: Optional[str] = None,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    translation_source: str = "",
    max_chars: int = 1500,
    min_chars: int = 200,
) -> list[Document]:
    """Chunk a plain-text volume into cited :class:`Document`s (one per section)."""
    txt_path = Path(txt_path)
    vol = volume if volume is not None else (volume_from_filename(txt_path) or "?")
    body = clean_text(txt_path.read_text(encoding="utf-8", errors="replace"))
    docs: list[Document] = []
    for i, chunk in enumerate(chunk_text(body, max_chars=max_chars, overlap=150)):
        if len(chunk) < min_chars:
            continue
        citation = Citation(
            source_id=source_id,
            evidence_type=evidence_type,
            volume=str(vol),
            page=str(i),  # within-volume section locator (no reliable print pages after OCR)
            translation_source=translation_source or None,
        )
        docs.append(
            Document(
                id=f"{source_id}-v{vol}-{i}",
                text=chunk,
                evidence_type=evidence_type,
                citation=citation,
                confidence=confidence,
                tags=[source_id, "prose", "tafsir"],
                language="en",
            )
        )
    return docs
