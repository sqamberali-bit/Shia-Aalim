"""OpenITI mARkdown ingestion adapter (classical Arabic texts).

The `OpenITI corpus <https://github.com/OpenITI>`_ publishes machine-readable
editions of classical Arabic works in *mARkdown*: a ``#META#`` header block,
``### |`` section headings, ``# `` paragraphs with ``~~`` continuation lines,
inline ``PageVxxPyyy`` markers tying the text to the printed edition's
volume/page, and ``ms###`` milestone tokens.

That page anchoring gives an honest, verifiable citation for Arabic-only
works: *source + section + volume/page of the printed edition* (the edition is
recorded in the header). Documents are chunked at paragraph boundaries.

Honesty rules:

* Text is preserved verbatim (only chrome — page markers, milestones — is
  stripped). Nothing is translated, reflowed, or summarised.
* The page cited is the page current where the chunk *begins*; a chunk can
  run onto the following page, and since OpenITI markers record page *ends*
  the locator is approximate to ±1 page. Chunks before the book's first
  marker borrow the first following page number (they lie on or before it).
* These texts carry no rijāl grades and are uncorrected-OCR-free editions of
  the named prints, but they are still transcriptions — confidence is capped
  at ``medium``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from ...models import Citation, ConfidenceLevel, Document, EvidenceType

_META_LINE = re.compile(r"^#META#")
_META_END = "#META#Header#End#"
_SECTION = re.compile(r"^###\s*\|+\s*(.*)$")
# mARkdown biographical-entry marker (`### $ 11 - name...`) — used by the
# rijal works for individual narrator entries; treated as a paragraph start so
# each entry becomes (the head of) its own chunk.
_BIO = re.compile(r"^###\s*\$+\s*(.*)$")
_PARA = re.compile(r"^#\s?(.*)$")
_CONT = re.compile(r"^~~(.*)$")
_PAGE = re.compile(r"PageV(\d+)P(\d+)")
_MILESTONE = re.compile(r"\bms\d+\b")
_WS = re.compile(r"[ \t]+")


def read_metadata(path: str | Path) -> dict[str, str]:
    """Parse the #META# header into a flat dict (values 'NODATA' dropped)."""
    out: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() == _META_END:
            break
        if _META_LINE.match(line):
            body = line[len("#META#"):].strip()
            key, sep, value = body.partition("::")
            if sep and value.strip() and value.strip() not in ("NODATA", "NOTGIVEN", "NOCODE"):
                out[key.strip()] = value.strip()
    return out


def _clean(text: str) -> str:
    text = _MILESTONE.sub("", text)
    text = _PAGE.sub("", text)
    return _WS.sub(" ", text).strip()


def iter_paragraphs(path: str | Path) -> Iterator[tuple[str, str, str, str]]:
    """Yield ``(section_title, volume, page, paragraph_text)`` in order.

    volume/page reflect the last ``PageVxxPyyy`` marker seen before the
    paragraph's start ("0"/"0" before the first marker).
    """
    section = ""
    vol, page = "0", "0"
    para: list[str] = []
    para_vol, para_page = vol, page
    in_body = False

    def flush():
        nonlocal para
        if para:
            text = _clean(" ".join(para))
            if text:
                yield_item = (section, para_vol, para_page, text)
                para = []
                return yield_item
            para = []
        return None

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not in_body:
            if line.strip() == _META_END:
                in_body = True
            continue
        m_sec = _SECTION.match(line)
        m_bio = _BIO.match(line)
        m_para = (m_bio or _PARA.match(line)) if (m_bio or not line.startswith("###")) else None
        m_cont = _CONT.match(line)
        if m_sec:
            item = flush()
            if item:
                yield item
            section = _clean(m_sec.group(1)).strip("[] ") or section
        elif m_para:
            item = flush()
            if item:
                yield item
            para_vol, para_page = vol, page
            para = [m_para.group(1)]
        elif m_cont and para:
            para.append(m_cont.group(1))
        # Track page markers wherever they appear (they sit inside text lines).
        for mv, mp in _PAGE.findall(line):
            vol, page = str(int(mv)), str(int(mp))
    item = flush()
    if item:
        yield item


def build_openiti_documents(
    path: str | Path,
    *,
    source_id: str,
    evidence_type: EvidenceType,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    max_chars: int = 1500,
    min_chars: int = 40,
) -> list[Document]:
    """Chunk an OpenITI text into cited Arabic :class:`Document`s.

    Paragraphs are merged into chunks of up to ``max_chars`` without breaking
    a paragraph; each chunk is cited by section + printed volume/page where it
    begins.
    """
    meta = read_metadata(path)
    ed_bits = [meta.get(k, "") for k in ("040.EdEDITOR", "043.EdPUBLISHER", "045.EdYEAR")]
    edition = ", ".join(b for b in ed_bits if b)
    tsource = f"OpenITI ({Path(path).name})" + (f" — ed. {edition}" if edition else "")

    # Pass 1: gather chunks as (section, vol, page, text).
    chunks: list[tuple[str, str, str, str]] = []
    buf: list[str] = []
    buf_key: Optional[tuple[str, str, str]] = None  # (section, vol, page) of chunk start

    def emit():
        nonlocal buf, buf_key
        if buf and buf_key is not None:
            text = "\n".join(buf)
            if len(text) >= min_chars:
                chunks.append((*buf_key, text))
        buf = []
        buf_key = None

    for section, vol, page, para in iter_paragraphs(path):
        if buf and (buf_key is None or section != buf_key[0]
                    or sum(len(b) for b in buf) + len(para) > max_chars):
            emit()
        if not buf:
            buf_key = (section, vol, page)
        buf.append(para)
    emit()

    # Pass 2: front matter before the first PageVxxPyyy marker has no locator —
    # give those chunks the first following page/volume (they lie on or before
    # it) so every citation stays verifiable.
    next_vol, next_page = "0", "0"
    for i in range(len(chunks) - 1, -1, -1):
        section, vol, page, text = chunks[i]
        if page != "0":
            next_vol, next_page = vol, page
        elif next_page != "0":
            chunks[i] = (section, next_vol, next_page, text)

    docs: list[Document] = []
    for counter, (section, vol, page, text) in enumerate(chunks):
        citation = Citation(
            source_id=source_id,
            evidence_type=evidence_type,
            volume=vol if vol != "0" else None,
            chapter=section or None,
            page=page if page != "0" else None,
            arabic_text=None,  # text itself is the Arabic
            translation=None,
            translation_source=tsource,
        )
        docs.append(
            Document(
                id=f"{source_id}-{counter}",
                text=text,
                evidence_type=evidence_type,
                citation=citation,
                confidence=confidence,
                tags=[source_id, "openiti"],
                language="ar",
            )
        )
    return docs
