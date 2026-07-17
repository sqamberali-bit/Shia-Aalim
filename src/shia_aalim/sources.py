"""Loading and using the authoritative source registry.

Reads ``data/sources/registry.yaml`` into :class:`~shia_aalim.models.Source`
objects. Uses PyYAML when available; otherwise falls back to a minimal,
dependency-free parser that understands the flat structure this registry uses
(a ``sources:`` list of ``key: value`` blocks). Keeping a stdlib fallback means
the grounding layer's "is this a registered source?" check works even on a
bare Python install.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import ConfidenceLevel, EvidenceType, Source


def _load_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        return {"sources": _fallback_parse(text)}


_ITEM_START = re.compile(r"^\s*-\s+id:\s*(.+?)\s*$")
_KV = re.compile(r"^\s+([a-z_]+):\s*(.*?)\s*$")


def _clean(value: str) -> Optional[str]:
    value = value.strip()
    if value in ("null", "~", ""):
        return None
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1]
    return value


def _fallback_parse(text: str) -> list[dict]:
    """Parse the registry's specific shape without a YAML library.

    Handles: a top-level ``sources:`` list, each entry beginning ``- id: X``
    followed by indented ``key: value`` pairs. Comments (``#``) and blank lines
    are ignored. This is intentionally narrow — it is not a general YAML parser.
    """
    items: list[dict] = []
    current: Optional[dict] = None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip() if " #" in raw else raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = _ITEM_START.match(line)
        if m:
            if current:
                items.append(current)
            current = {"id": _clean(m.group(1))}
            continue
        if current is not None:
            kv = _KV.match(line)
            if kv:
                current[kv.group(1)] = _clean(kv.group(2))
    if current:
        items.append(current)
    return items


def load_sources(path: str | Path) -> list[Source]:
    """Load all registered sources from the registry file."""
    data = _load_yaml(Path(path).read_text(encoding="utf-8"))
    sources: list[Source] = []
    for entry in data.get("sources", []):
        if not entry or not entry.get("id"):
            continue
        sources.append(
            Source(
                id=entry["id"],
                title=entry.get("title", entry["id"]),
                kind=EvidenceType(entry.get("kind", "scholarly_opinion")),
                author=entry.get("author"),
                translator=entry.get("translator"),
                publisher=entry.get("publisher"),
                language=entry.get("language", "ar"),
                url=entry.get("url"),
                license=entry.get("license"),
                confidence=ConfidenceLevel(entry.get("confidence", "unverified")),
                notes=entry.get("notes"),
            )
        )
    return sources


def load_registry_ids(path: str | Path) -> set[str]:
    """Return just the set of registered source ids (for grounding checks)."""
    return {s.id for s in load_sources(path)}
