"""Post-generation verification of synthesized (LLM) prose.

The charter requires that anything an LLM writes be re-verified before release.
Given the synthesized ``text`` and the ``evidence`` it was built from (a numbered
``[n]`` list), :func:`verify_synthesis` checks three failure modes:

1. **Invented citations** — a marker ``[n]`` that points outside the evidence
   list (structural; no LLM needed).
2. **Ungrounded cited sentences** — a sentence that cites ``[n]`` but whose text
   is not *entailed* by the passage it cites (wrong attribution).
3. **Uncited claims** — a substantive sentence entailed by **no** cited evidence.

Entailment (2 and 3) is decided by a pluggable :class:`EntailmentJudge`. The
default :class:`LexicalEntailmentJudge` is a conservative content-overlap proxy
(dependency-free, unchanged behaviour); pass a
:class:`ClaudeEntailmentJudge` to complement it with true semantic entailment —
catching paraphrases the lexical gate misses and same-words/wrong-meaning it
would wave through. A failed verification never silently passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..retrieval.retriever import RetrievalResult
from .entailment import EntailmentJudge, LexicalEntailmentJudge
from .lexical import content_tokens

_MARKER = re.compile(r"\[(\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SynthesisReport:
    grounded: bool
    invented_citations: list[int] = field(default_factory=list)
    ungrounded_sentences: list[str] = field(default_factory=list)
    uncited_sentences: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "grounded": self.grounded,
            "invented_citations": self.invented_citations,
            "ungrounded_sentences": self.ungrounded_sentences[:5],
            "uncited_sentences": self.uncited_sentences[:5],
            "problems": self.problems,
        }


_BOILERPLATE = re.compile(
    r"(?i)^(according to|based on|the (retrieved |available )?evidence|"
    r"in (summary|conclusion)|the evidence (does not|is insufficient))"
)


def _is_boilerplate(sentence: str) -> bool:
    """Framing/refusal sentences that legitimately carry no citation."""
    return bool(_BOILERPLATE.match(sentence.strip()))


def verify_synthesis(
    text: str,
    evidence: list[RetrievalResult],
    *,
    judge: Optional[EntailmentJudge] = None,
    min_overlap: float = 0.2,
    min_content_words: int = 4,
) -> SynthesisReport:
    judge = judge or LexicalEntailmentJudge(min_overlap)
    n = len(evidence)
    invented: list[int] = []
    problems: list[str] = []

    all_markers = [int(m) for m in _MARKER.findall(text)]
    for m in all_markers:
        if (m < 1 or m > n) and m not in invented:
            invented.append(m)
    if invented:
        problems.append(f"invented citation markers not in evidence: {sorted(invented)}")

    # Passages the answer cites anywhere (a quote may span several sentences with
    # the marker only on the last, so an unmarked sentence is fine as long as it
    # continues some cited passage).
    cited_idx = sorted({m for m in all_markers if 1 <= m <= n})
    cited_passages = [evidence[m - 1].document.text for m in cited_idx]

    # Collect entailment checks, then judge them in one batch.
    marked_checks: list[tuple[str, list[str]]] = []
    marked_sentences: list[str] = []
    unmarked_checks: list[tuple[str, list[str]]] = []
    unmarked_sentences: list[str] = []

    for raw in _SENTENCE_SPLIT.split(text.strip()):
        sentence = raw.strip()
        if not sentence:
            continue
        valid = [m for m in (int(x) for x in _MARKER.findall(sentence)) if 1 <= m <= n]
        content_words = len(content_tokens(_MARKER.sub("", sentence)))
        if valid:
            marked_checks.append((sentence, [evidence[m - 1].document.text for m in valid]))
            marked_sentences.append(sentence)
        elif content_words >= min_content_words and not _is_boilerplate(sentence):
            unmarked_checks.append((sentence, cited_passages))
            unmarked_sentences.append(sentence)

    marked_verdicts = judge.judge_batch(marked_checks) if marked_checks else []
    unmarked_verdicts = judge.judge_batch(unmarked_checks) if unmarked_checks else []

    ungrounded = [s for s, v in zip(marked_sentences, marked_verdicts) if not v.supported]
    uncited = [s for s, v in zip(unmarked_sentences, unmarked_verdicts) if not v.supported]

    if ungrounded:
        problems.append(f"{len(ungrounded)} cited sentence(s) not entailed by their citation")
    if uncited:
        problems.append(f"{len(uncited)} substantive sentence(s) not entailed by any cited evidence")

    grounded = not invented and not ungrounded and not uncited
    return SynthesisReport(
        grounded=grounded,
        invented_citations=sorted(invented),
        ungrounded_sentences=ungrounded,
        uncited_sentences=uncited,
        problems=problems,
    )
