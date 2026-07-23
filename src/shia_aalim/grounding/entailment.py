"""Entailment judges — is a claim actually *supported* by its evidence?

The lexical grounding gate (content-word overlap) is fast and dependency-free
but blunt: it misses true paraphrases (a claim entailed by evidence that shares
few surface words) and can pass same-words-different-meaning. An **entailment
judge** answers the semantic question directly — *does this evidence support
this claim?* — and is used to *complement* the lexical gate, not replace it.

Three implementations behind one small protocol:

* :class:`LexicalEntailmentJudge` — wraps content-overlap; the zero-dependency
  default, so the judge interface is always usable and behaviour is unchanged
  when no LLM is configured.
* :class:`ClaudeEntailmentJudge` — asks Claude for a strict SUPPORTED/UNSUPPORTED
  verdict per claim (batched into one call). Lazy-imported; needs ``[llm]`` +
  ``ANTHROPIC_API_KEY``.
* :class:`MockEntailmentJudge` — deterministic, for tests/offline.

All judges default to **UNSUPPORTED when unsure** — the charter's burden of
proof is on the claim.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence

from .lexical import content_overlap


@dataclass
class EntailmentVerdict:
    supported: bool
    reason: str = ""


# (claim, [evidence passages]) pairs to judge.
JudgeItem = tuple[str, Sequence[str]]


class EntailmentJudge(Protocol):
    def judge_batch(self, items: Sequence[JudgeItem]) -> list[EntailmentVerdict]:
        ...


def judge_one(judge: EntailmentJudge, claim: str, passages: Sequence[str]) -> EntailmentVerdict:
    return judge.judge_batch([(claim, passages)])[0]


class LexicalEntailmentJudge:
    """Content-overlap as an entailment proxy (dependency-free default)."""

    def __init__(self, min_overlap: float = 0.2) -> None:
        self.min_overlap = min_overlap

    def judge_batch(self, items: Sequence[JudgeItem]) -> list[EntailmentVerdict]:
        out: list[EntailmentVerdict] = []
        for claim, passages in items:
            best = max((content_overlap(claim, p) for p in passages), default=0.0)
            out.append(
                EntailmentVerdict(
                    supported=best >= self.min_overlap,
                    reason=f"content-overlap {best:.2f} vs threshold {self.min_overlap}",
                )
            )
        return out


class MockEntailmentJudge:
    """Deterministic judge for tests/offline.

    ``decide`` maps ``(claim, passages) -> bool``; default is content-overlap so
    it behaves like the lexical judge unless a test overrides it.
    """

    def __init__(self, decide: Optional[Callable[[str, Sequence[str]], bool]] = None) -> None:
        self._decide = decide or (
            lambda claim, passages: max((content_overlap(claim, p) for p in passages), default=0.0)
            >= 0.2
        )

    def judge_batch(self, items: Sequence[JudgeItem]) -> list[EntailmentVerdict]:
        return [EntailmentVerdict(supported=bool(self._decide(c, p)), reason="mock") for c, p in items]


_VERDICT_LINE = re.compile(r"(?im)^\s*(\d+)\s*[:.)-]\s*(supported|unsupported)\b(.*)$")


class ClaudeEntailmentJudge:
    """LLM entailment judge (Claude). Batches all claims into one strict call."""

    _SYSTEM = (
        "You are a strict entailment checker for Twelver Shia Islamic research. "
        "For each numbered CLAIM you are given its EVIDENCE. Decide ONLY whether "
        "the evidence, on its own, SUPPORTS the claim (the claim is a faithful "
        "restatement of, or directly follows from, the evidence). Do not use "
        "outside knowledge. If the evidence is insufficient or the claim adds "
        "anything not in the evidence, answer UNSUPPORTED. Reply with one line "
        "per claim in the exact form `<n>: SUPPORTED` or `<n>: UNSUPPORTED`, "
        "optionally followed by a short reason."
    )

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        *,
        api_key: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "ClaudeEntailmentJudge needs the Anthropic SDK — `pip install shia-aalim[llm]`"
            ) from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ClaudeEntailmentJudge needs ANTHROPIC_API_KEY.")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.max_tokens = max_tokens

    def judge_batch(self, items: Sequence[JudgeItem]) -> list[EntailmentVerdict]:
        if not items:
            return []
        blocks = []
        for i, (claim, passages) in enumerate(items, 1):
            ev = "\n".join(f"  - {p.strip()}" for p in passages) or "  (no evidence)"
            blocks.append(f"CLAIM {i}: {claim.strip()}\nEVIDENCE {i}:\n{ev}")
        user = "\n\n".join(blocks) + "\n\nVerdict for each claim:"
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
        except Exception as exc:  # noqa: BLE001 - never trust on failure
            return [EntailmentVerdict(False, f"judge error: {exc}") for _ in items]
        return self._parse(text, len(items))

    @staticmethod
    def _parse(text: str, n: int) -> list[EntailmentVerdict]:
        # Default to UNSUPPORTED; fill in whatever the model returned per index.
        verdicts = [EntailmentVerdict(False, "no verdict parsed") for _ in range(n)]
        for m in _VERDICT_LINE.finditer(text):
            idx = int(m.group(1)) - 1
            if 0 <= idx < n:
                supported = m.group(2).lower() == "supported"
                verdicts[idx] = EntailmentVerdict(supported, m.group(3).strip())
        return verdicts


def make_judge(spec: str = "lexical", **kwargs) -> Optional[EntailmentJudge]:
    """Build a judge from a spec: ``lexical`` | ``mock`` | ``claude:<model>`` | ``none``."""
    spec = (spec or "lexical").strip()
    if spec in ("none", ""):
        return None
    if spec in ("lexical", "overlap"):
        return LexicalEntailmentJudge()
    if spec == "mock":
        return MockEntailmentJudge()
    for prefix in ("claude:", "claude"):
        if spec == "claude" or spec.startswith("claude:"):
            model = spec.split(":", 1)[1] if ":" in spec else "claude-sonnet-5"
            return ClaudeEntailmentJudge(model=model, **kwargs)
    raise ValueError(f"unknown judge spec: {spec!r} (expected lexical|mock|claude:<model>|none)")
