"""AI query refinement — fix spelling and clarify terms before retrieval.

A user may misspell a word or use a loose form of an Islamic term (e.g. "tawheed"
vs "tawhid", "namaz" vs "salat", "hazrat ali"). Lexical retrieval is sensitive to
that. A :class:`QueryRefiner` cleans the query up *before* it is searched — and
records what it changed, so the correction is transparent ("searched for: …").

It never answers the question or invents intent; it only normalises the wording.
The refined query is used for retrieval and synthesis, but the user's original
text is always kept and shown. Pluggable: the default is off; ``claude:<model>``
uses Claude; ``mock`` is a deterministic offline stub for tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class RefineResult:
    corrected: str          # the cleaned query to search with
    changed: bool           # True if it differs from the original
    note: str = ""          # short human note on what changed (optional)


class QueryRefiner(Protocol):
    def refine(self, query: str) -> RefineResult: ...


# A few high-frequency transliteration variants, for the offline/mock path and as
# a cheap fallback. Deliberately tiny and conservative — the LLM path does the
# real work.
_COMMON = {
    "tawheed": "tawhid", "tauheed": "tawhid", "namaz": "salat", "salah": "salat",
    "roza": "sawm", "zakah": "zakat", "hadees": "hadith", "ahadees": "ahadith",
    "quraan": "quran", "koran": "quran", "imamate": "imamah", "wilayah": "wilaya",
}


class MockRefiner:
    """Offline refiner: applies a tiny transliteration map (no network)."""

    def refine(self, query: str) -> RefineResult:
        words = query.split()
        out = [_COMMON.get(w.lower(), w) for w in words]
        corrected = " ".join(out)
        return RefineResult(corrected, corrected.lower() != query.lower(),
                            "normalised common term spellings" if corrected.lower() != query.lower() else "")


class ClaudeRefiner:
    """Use Claude to correct spelling and normalise Islamic terms in the query."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", *, api_key: Optional[str] = None) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError("ClaudeRefiner needs the Anthropic SDK — pip install shia-aalim[llm]") from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ClaudeRefiner needs an API key (ANTHROPIC_API_KEY).")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model

    _SYSTEM = (
        "You clean up search queries for a Twelver Shia Islamic text retrieval "
        "system. Fix spelling mistakes and normalise Islamic/Arabic terms to their "
        "common transliteration (e.g. tawheed→tawhid, namaz→salat, hazrat→). Keep "
        "the user's meaning and language EXACTLY; do NOT answer the question, add "
        "words, or change intent. Reply with ONLY the corrected query on one line, "
        "nothing else. If it is already fine, reply with it unchanged."
    )

    def refine(self, query: str) -> RefineResult:
        try:
            resp = self._client.messages.create(
                model=self.model, max_tokens=120, temperature=0,
                system=self._SYSTEM,
                messages=[{"role": "user", "content": query}],
            )
            corrected = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            ).strip().splitlines()[0].strip().strip('"')
        except Exception:  # noqa: BLE001 - never fail the query over refinement
            return RefineResult(query, False, "")
        if not corrected:
            return RefineResult(query, False, "")
        changed = corrected.lower() != query.strip().lower()
        return RefineResult(corrected, changed, "spelling / term normalisation" if changed else "")


def make_refiner(spec: str = "none", **kwargs) -> Optional[QueryRefiner]:
    """Build a refiner from a spec: ``none`` | ``mock`` | ``claude:<model>``."""
    spec = (spec or "none").strip()
    if spec in ("none", ""):
        return None
    if spec == "mock":
        return MockRefiner()
    if spec.startswith("claude:") or spec == "claude":
        model = spec.split(":", 1)[1] if ":" in spec else "claude-haiku-4-5-20251001"
        return ClaudeRefiner(model=model, **kwargs)
    raise ValueError(f"unknown refiner spec: {spec!r} (expected none|mock|claude:<model>)")
