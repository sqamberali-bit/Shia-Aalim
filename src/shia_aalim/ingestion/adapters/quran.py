"""Qur'an ingestion adapter.

Source: the ``fawazahmed0/quran-api`` dataset on GitHub (per-edition JSON, each
``{"quran": [{"chapter", "verse", "text"}, ...]}`` with 6236 verses). We pair a
canonical **Arabic Uthmani** edition with an English **translation** edition so
every verse document carries the exact verse text *and* an attributed
translation — both independently verifiable against the āya reference.

The adapter is pure-stdlib and offline: it reads already-downloaded edition
files. A tiny ``fetch_edition`` helper (urllib) can pull them via the GitHub raw
host when a network build is desired, but tests and the core never require it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...models import Citation, ConfidenceLevel, Document, EvidenceType

# Raw-host URL template for fawazahmed0 editions (GitHub raw is the reachable
# channel in this environment; see docs/ingestion-guide.md).
RAW_EDITION_URL = (
    "https://raw.githubusercontent.com/fawazahmed0/quran-api/1/editions/{edition}.min.json"
)


def load_edition(path: str | Path) -> dict[tuple[int, int], str]:
    """Load a fawazahmed0 edition file into a ``{(surah, ayah): text}`` map."""
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    verses = data["quran"] if isinstance(data, dict) else data
    out: dict[tuple[int, int], str] = {}
    for v in verses:
        out[(int(v["chapter"]), int(v["verse"]))] = v["text"].strip()
    return out


def fetch_edition(edition: str, dest: str | Path) -> Path:  # pragma: no cover - network
    """Download an edition to ``dest`` via GitHub raw (urllib, honours proxy env)."""
    import urllib.request

    url = RAW_EDITION_URL.format(edition=edition)
    dest = Path(dest)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed host
        dest.write_bytes(resp.read())
    return dest


def build_quran_documents(
    arabic_path: str | Path,
    translation_path: str | Path,
    *,
    translation_name: str,
    arabic_source_id: str = "quran",
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
) -> list[Document]:
    """Build one :class:`Document` per verse (English text, Arabic in citation).

    ``text`` is the English translation (so English queries retrieve it); the
    canonical Arabic is preserved in ``citation.arabic_text`` for display and
    verification. Confidence defaults to HIGH because the canonical Arabic is
    present, making every verse independently checkable against its reference.
    """
    arabic = load_edition(arabic_path)
    translation = load_edition(translation_path)

    docs: list[Document] = []
    for (surah, ayah), ar_text in arabic.items():
        en_text = translation.get((surah, ayah))
        if not en_text:
            # Never invent a translation for a missing verse; skip and let the
            # coverage metric flag the gap.
            continue
        citation = Citation(
            source_id=arabic_source_id,
            evidence_type=EvidenceType.QURAN,
            surah=surah,
            ayah=ayah,
            arabic_text=ar_text,
            translation=en_text,
            translation_source=translation_name,
        )
        docs.append(
            Document(
                id=f"quran-{surah}-{ayah}",
                text=en_text,
                evidence_type=EvidenceType.QURAN,
                citation=citation,
                confidence=confidence,
                tags=["quran", f"surah-{surah}"],
                language="en",
            )
        )
    docs.sort(key=lambda d: (d.citation.surah or 0, d.citation.ayah or 0))
    return docs
