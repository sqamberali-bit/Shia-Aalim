"""Query decomposition — split a multi-part question into atomic sub-questions.

A compound question ("What does the Qur'an say about the Ahl al-Bayt, and how do
the hadith describe their purification?") retrieves poorly as one string: the
dominant clause's words swamp the query and the second part starves. Decomposing
it and retrieving each part separately, then merging the evidence, gives every
part its due — a real recall win for multi-part asks.

Two implementations behind one small protocol:

* :class:`RuleBasedDecomposer` — dependency-free heuristics (multiple ``?``,
  enumerations, and conjunctions that join *interrogative* clauses). Conservative
  by design: it won't split a noun phrase like "the House and its purification".
* :class:`ClaudeDecomposer` — asks Claude for atomic sub-questions (one per
  line). Lazy-imported; needs ``[llm]`` + ``ANTHROPIC_API_KEY``.

Both return ``[question]`` unchanged when there is nothing to split, so callers
can always decompose without special-casing single-part questions.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Protocol

from ..grounding.lexical import content_tokens

# Words that mark a clause as an actual question/instruction (so we only split
# on "and" when both sides look interrogative, not inside a noun phrase).
_INTERROGATIVE = {
    "what", "how", "why", "when", "who", "whom", "where", "which", "whose",
    "is", "are", "was", "were", "do", "does", "did", "can", "could", "should",
    "would", "will", "explain", "describe", "compare", "contrast", "list",
    "discuss", "define", "name", "summarise", "summarize", "give", "state",
}

_ENUM = re.compile(r"\s*(?:\(\d+\)|\b\d+[.)]\s|;)\s*")
_CONJ = re.compile(r"\s+(?:and also|as well as|and then|and|also)\s+", re.IGNORECASE)
_QSPLIT = re.compile(r"(?<=\?)\s+")


class QueryDecomposer(Protocol):
    def decompose(self, question: str) -> list[str]:
        ...


def _looks_interrogative(clause: str) -> bool:
    toks = [t.lower() for t in re.findall(r"[A-Za-z']+", clause)]
    if len(content_tokens(clause)) < 3:
        return False
    return any(t in _INTERROGATIVE for t in toks)


def _tidy(parts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        p = p.strip().strip(",;").strip()
        if len(content_tokens(p)) < 1:
            continue
        if not p.endswith("?"):
            p += "?"
        key = p.lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


class RuleBasedDecomposer:
    """Heuristic, dependency-free decomposition. Returns ``[question]`` if single."""

    def decompose(self, question: str) -> list[str]:
        q = question.strip()
        if not q:
            return [q]

        # 1) Several explicit questions ("...? ...?").
        qs = [s for s in _QSPLIT.split(q) if s.strip()]
        if len(qs) > 1:
            tidy = _tidy(qs)
            if len(tidy) > 1:
                return tidy

        # 2) Explicit enumeration ("1. ... 2. ..." / "(a) ... (b) ..." / "...; ...").
        enum = [p for p in _ENUM.split(q) if p.strip()]
        if len(enum) > 1:
            tidy = _tidy(enum)
            if len(tidy) > 1:
                return tidy

        # 3) Conjunction joining interrogative clauses.
        conj = [c for c in _CONJ.split(q) if c.strip()]
        if len(conj) > 1 and sum(_looks_interrogative(c) for c in conj) >= 2:
            tidy = _tidy(conj)
            if len(tidy) > 1:
                return tidy

        return [q]


class ClaudeDecomposer:
    """LLM decomposition (Claude). Lazy-imported; needs the SDK + key."""

    _SYSTEM = (
        "Break a research question into the minimal set of atomic sub-questions "
        "needed to answer it fully. Preserve the original meaning; do not add "
        "topics. If the question is already atomic, return it unchanged. Reply "
        "with ONE sub-question per line, no numbering or extra text."
    )

    def __init__(self, model: str = "claude-sonnet-5", *, api_key: Optional[str] = None,
                 max_tokens: int = 512) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "ClaudeDecomposer needs the Anthropic SDK — `pip install shia-aalim[llm]`"
            ) from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ClaudeDecomposer needs ANTHROPIC_API_KEY.")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.max_tokens = max_tokens

    def decompose(self, question: str) -> list[str]:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._SYSTEM,
                messages=[{"role": "user", "content": question}],
            )
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        except Exception:  # noqa: BLE001 - on failure, don't decompose
            return [question]
        parts = [re.sub(r"^\s*[-*\d.)]+\s*", "", ln).strip() for ln in text.splitlines()]
        parts = [p for p in parts if p]
        return parts if len(parts) > 1 else [question]


def make_decomposer(spec: str = "none", **kwargs) -> Optional[QueryDecomposer]:
    """Build a decomposer: ``none`` | ``rule`` | ``claude:<model>``."""
    spec = (spec or "none").strip()
    if spec in ("none", ""):
        return None
    if spec in ("rule", "rules", "heuristic"):
        return RuleBasedDecomposer()
    if spec == "claude" or spec.startswith("claude:"):
        model = spec.split(":", 1)[1] if ":" in spec else "claude-sonnet-5"
        return ClaudeDecomposer(model=model, **kwargs)
    raise ValueError(f"unknown decomposer spec: {spec!r} (expected none|rule|claude:<model>)")
