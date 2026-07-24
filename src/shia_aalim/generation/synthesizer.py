"""LLM synthesizers — compose fluent, *cited* prose from retrieved evidence.

A synthesizer turns ``(question, evidence)`` into prose. Per the charter it may
only use the supplied evidence and must cite it with bracketed markers ``[n]``
that refer to the numbered EVIDENCE list — nothing else. Whatever it returns is
**re-verified** by :func:`shia_aalim.grounding.synthesis.verify_synthesis`
before it reaches a user, so a model that drifts off-evidence or invents a
citation is caught, not trusted.

Three implementations:

* :class:`ClaudeSynthesizer` — Anthropic API (lazy-imported; needs the SDK +
  ``ANTHROPIC_API_KEY``). The production path.
* :class:`MockSynthesizer` — deterministic, offline: quotes the top evidence
  with correct ``[n]`` markers. Grounded by construction; used for tests and for
  running the whole pipeline with no API key.
* :func:`make_synthesizer` — build one from a spec string.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

from ..retrieval.retriever import RetrievalResult

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "answer_system.md"

_FALLBACK_SYSTEM = (
    "You are an evidence-grounded research assistant for Twelver Shia Islam. "
    "Use ONLY the supplied EVIDENCE. Cite every claim with bracketed markers "
    "[n] referring to the numbered EVIDENCE items; never cite anything not "
    "listed. Distinguish Qur'an / Tafsir / Hadith / historical / scholarly. Flag "
    "weak or ungraded material. If the evidence is insufficient, say so plainly "
    "and stop. Do not issue fatwa."
)

_CITATION_RULES = (
    "\n\nOUTPUT RULES:\n"
    "- Cite with bracketed numbers like [1], [2] that refer ONLY to the EVIDENCE "
    "items below. Do not invent citation numbers or cite anything not listed.\n"
    "- Every substantive sentence must carry at least one [n].\n"
    "- If the evidence does not answer the question, say so and stop."
)


def load_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8") + _CITATION_RULES
    except OSError:
        return _FALLBACK_SYSTEM + _CITATION_RULES


def format_evidence_block(evidence: Sequence[RetrievalResult]) -> str:
    """Render evidence as a numbered ``[n]`` list the model must cite against.

    Includes the Arabic original and grade where present so the model can render
    full Qur'anic verses (Arabic + translation) and reconcile hadith by grade —
    without inventing anything beyond what is listed here.
    """
    lines: list[str] = []
    for i, res in enumerate(evidence, 1):
        d = res.document
        c = d.citation
        ref = c.reference_string()
        etype = d.evidence_type.value
        head = f"[{i}] ({etype} · {ref} · confidence={d.confidence.value}"
        if c.grade and c.grade.value != "ungraded":
            head += f" · grade={c.grade.value}"
            if c.grade_source:
                head += f" [{c.grade_source}]"
        head += ")"
        parts = [head]
        if c.arabic_text:
            parts.append(f"ARABIC: {c.arabic_text.strip()}")
        # d.text is the English (translation for Qur'an, matn for hadith, etc.)
        parts.append(f"ENGLISH: {d.text.strip()}")
        if c.translation and c.translation.strip() != d.text.strip():
            parts.append(f"TRANSLATION: {c.translation.strip()}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


class MockSynthesizer:
    """Deterministic offline synthesizer: quotes the top evidence with markers.

    Not an LLM — it exists so the full synthesize→verify pipeline runs and is
    tested without an API key. Its output is grounded by construction.
    """

    def __init__(self, max_items: int = 3) -> None:
        self.max_items = max_items

    def synthesize(
        self, question: str, evidence: list[RetrievalResult], *, language: str = "English"
    ) -> str:
        if not evidence:
            return "The available evidence does not address this question."
        parts = []
        for i, res in enumerate(evidence[: self.max_items], 1):
            snippet = res.document.text.strip()
            snippet = (snippet[:240] + "…") if len(snippet) > 240 else snippet
            parts.append(f"{snippet} [{i}]")
        return "According to the retrieved evidence: " + " ".join(parts)


class ClaudeSynthesizer:
    """Anthropic-backed synthesizer (Claude). Lazy-imported; needs the SDK + key."""

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        *,
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "ClaudeSynthesizer needs the Anthropic SDK — `pip install shia-aalim[llm]`"
            ) from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ClaudeSynthesizer needs an API key (ANTHROPIC_API_KEY env var)."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._system = load_system_prompt()

    def synthesize(
        self, question: str, evidence: list[RetrievalResult], *, language: str = "English"
    ) -> str:
        block = format_evidence_block(evidence)
        is_english = (not language) or language.strip().lower() in ("english", "en", "")
        if is_english:
            lang_line = (
                "Write the explanatory prose in ENGLISH. After each English section, "
                "add its faithful URDU rendering on a new line prefixed with 'اردو: '."
            )
        else:
            lang_line = (
                f"Write the explanatory prose in {language}. Keep proper names recognisable."
            )
        user = (
            f"QUESTION:\n{question}\n\nEVIDENCE (numbered — cite ONLY these with [n]):\n{block}\n\n"
            "Write an ORIGINAL, SYNTHESISED answer — reason across ALL the evidence together; "
            "do NOT just quote or list passages. Structure it with these headings:\n"
            "1. **Direct answer** — 1–3 sentences.\n"
            "2. **Explanation** — synthesise the evidence into a coherent account.\n"
            "3. **Qur'anic evidence** — for EACH relevant verse, show the full Arabic text "
            "(from the evidence), then its English translation, then an Urdu translation. "
            "Never give a bare reference without the verse and translations.\n"
            "4. **Hadith evidence** — reconcile multiple narrations; note grade/authenticity "
            "and practical import. Cite each.\n"
            "5. **Tafsir synthesis** — compare the tafsir explanations present in the evidence; "
            "do not paste raw Arabic paragraphs.\n"
            "6. **Scholarly views** — where present.\n"
            "7. **Practical lessons.**\n"
            "8. **Sources** — bibliography of the exact citations used.\n\n"
            "RULES: Every factual sentence must carry a [n] citation to the evidence above. "
            "Do NOT add facts, verses, hadith or opinions that are not in the evidence. If the "
            "evidence lacks something (e.g. a tafsir), say so rather than inventing it. Prefer "
            "synthesis and reasoning over long verbatim quotes. " + lang_line
        )
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self._system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()


def make_synthesizer(spec: str = "none", **kwargs):
    """Build a synthesizer from a spec: ``none`` | ``mock`` | ``claude:<model>``."""
    spec = (spec or "none").strip()
    if spec in ("none", ""):
        return None
    if spec == "mock":
        return MockSynthesizer()
    if spec.startswith("claude:") or spec == "claude":
        model = spec.split(":", 1)[1] if ":" in spec else "claude-sonnet-5"
        return ClaudeSynthesizer(model=model, **kwargs)
    raise ValueError(f"unknown synthesizer spec: {spec!r} (expected none|mock|claude:<model>)")
