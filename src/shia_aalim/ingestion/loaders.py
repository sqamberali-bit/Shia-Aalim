"""Document loaders for the knowledge pipeline.

Supported inputs (per the charter's Knowledge Pipeline section): plain text,
JSON/JSONL knowledge files, HTML, XML, PDF, EPUB. Heavy formats depend on
optional third-party libraries; loaders degrade gracefully and raise a clear,
actionable error naming the extra to install rather than crashing on import.

Every loader returns raw text (or, for JSONL, ready-made
:class:`~shia_aalim.models.Document` objects). Turning free text into Documents
with attached citations is a separate, deliberate step — the system never
fabricates a citation just because a file lacked one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from ..models import Document


class MissingDependencyError(RuntimeError):
    """Raised when a loader needs an optional package that is not installed."""


def load_text(path: str | Path) -> str:
    """Read a UTF-8 text file."""
    return Path(path).read_text(encoding="utf-8")


def load_documents_jsonl(path: str | Path) -> list[Document]:
    """Load newline-delimited JSON where each line is a serialised Document.

    This is the canonical, loss-less format for curated knowledge with
    citations already attached (see ``data/knowledge/**/*.jsonl``).
    """
    docs: list[Document] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            docs.append(Document.from_dict(json.loads(line)))
        except Exception as exc:  # noqa: BLE001 - want the line number in the message
            raise ValueError(f"{path}:{i}: invalid Document JSON: {exc}") from exc
    return docs


def load_html(path: str | Path) -> str:
    """Extract visible text from an HTML file (requires ``beautifulsoup4``)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise MissingDependencyError(
            "HTML loading needs beautifulsoup4 — `pip install shia-aalim[ingest]`"
        ) from exc
    soup = BeautifulSoup(load_text(path), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")


def load_pdf(path: str | Path) -> str:
    """Extract text from a (text-layer) PDF (requires ``pypdf``).

    Scanned/manuscript PDFs need an OCR step first — see
    :func:`ocr_placeholder` for where that hook belongs.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise MissingDependencyError(
            "PDF loading needs pypdf — `pip install shia-aalim[ingest]`"
        ) from exc
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def load_epub(path: str | Path) -> str:
    """Extract text from an EPUB (requires ``ebooklib`` + ``beautifulsoup4``)."""
    try:
        from bs4 import BeautifulSoup  # type: ignore
        from ebooklib import ITEM_DOCUMENT, epub  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise MissingDependencyError(
            "EPUB loading needs ebooklib + beautifulsoup4 — `pip install shia-aalim[ingest]`"
        ) from exc
    book = epub.read_epub(str(path))
    parts: list[str] = []
    for item in book.get_items():
        if item.get_type() == ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            parts.append(soup.get_text("\n"))
    return "\n".join(parts)


def ocr_placeholder(path: str | Path) -> str:  # pragma: no cover - integration hook
    """Hook for scanned-manuscript OCR (e.g. Tesseract w/ Arabic models).

    Left as an explicit, honest hook rather than a stub that silently returns
    empty text — a caller must wire in a real OCR backend.
    """
    raise MissingDependencyError(
        "OCR for scanned manuscripts is not configured. Wire in an Arabic-capable "
        "OCR backend (e.g. tesseract with `ara` traineddata, or a cloud OCR API) "
        "in ingestion/loaders.py:ocr_placeholder."
    )


_TEXT_LOADERS = {
    ".txt": load_text,
    ".md": load_text,
    ".html": load_html,
    ".htm": load_html,
    ".pdf": load_pdf,
    ".epub": load_epub,
}


def load_any(path: str | Path) -> str:
    """Dispatch to the right text loader by file extension."""
    suffix = Path(path).suffix.lower()
    loader = _TEXT_LOADERS.get(suffix)
    if loader is None:
        raise ValueError(f"No text loader registered for '{suffix}' files: {path}")
    return loader(path)


def iter_knowledge_dir(root: str | Path) -> Iterator[Document]:
    """Yield every Document from all ``*.jsonl`` files under a directory tree."""
    for jsonl in sorted(Path(root).rglob("*.jsonl")):
        yield from load_documents_jsonl(jsonl)


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split long text into overlapping, paragraph-aware chunks.

    Prefers paragraph boundaries; only hard-splits paragraphs longer than
    ``max_chars``. Overlap preserves context across chunk edges for retrieval.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(para), max_chars - overlap):
                chunks.append(para[i : i + max_chars])
            continue
        if len(buf) + len(para) + 2 <= max_chars:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def dedupe_documents(docs: Iterable[Document]) -> list[Document]:
    """Drop documents with identical normalised content (keeps first seen)."""
    from .normalize import normalize_for_search

    seen: set[str] = set()
    out: list[Document] = []
    for d in docs:
        key = normalize_for_search(d.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out
