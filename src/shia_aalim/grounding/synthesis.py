"""Post-generation verification of synthesized (LLM) prose.

The charter requires that anything an LLM writes be re-verified before release.
Given the synthesized ``text`` and the ``evidence`` it was built from (a numbered
``[n]`` list), :func:`verify_synthesis` checks three failure modes:

1. **Invented citations** — a marker ``[n]`` that points outside the evidence
   list (the model cited something that was never supplied).
2. **Ungrounded cited sentences** — a sentence that cites ``[n]`` but whose text
   does not materially overlap the passage it cites (citation window mismatch /
   the model put a real reference on an unsupported claim).
3. **Uncited claims** — a substantive sentence carrying no citation at all.

This is a deliberately conservative *lexical* gate (like the answer-grounding
check): it can flag problems but should be complemented by an LLM entailment
judge for production. A failed verification never silently passes — the caller
downgrades or discards the prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ingestion.normalize import tokens
from ..retrieval.retriever import RetrievalResult

_MARKER = re.compile(r"\[(\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Common function words carry no grounding signal — a shared "the"/"in" must not
# make an off-topic sentence look supported. (English + a few transliterations.)
_STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "was",
    "were", "be", "been", "it", "its", "this", "that", "these", "those", "for",
    "with", "as", "by", "from", "at", "he", "him", "his", "they", "them", "their",
    "you", "your", "we", "our", "i", "not", "no", "but", "so", "if", "then",
    "which", "who", "whom", "what", "when", "will", "shall", "may", "do", "does",
    "did", "has", "have", "had", "all", "any", "one", "also", "there", "here",
}



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


def _content(text: str) -> set[str]:
    return {t for t in tokens(text) if t not in _STOPWORDS and len(t) > 1}


def _overlap(sentence: str, passage: str) -> float:
    """Fraction of the sentence's *content* words present in the passage."""
    a = _content(sentence)
    if not a:
        return 1.0  # nothing but stopwords — a connective clause, don't penalise
    return len(a & _content(passage)) / len(a)


def verify_synthesis(
    text: str,
    evidence: list[RetrievalResult],
    *,
    min_overlap: float = 0.2,
    min_content_words: int = 4,
) -> SynthesisReport:
    n = len(evidence)
    invented: list[int] = []
    ungrounded: list[str] = []
    uncited: list[str] = []
    problems: list[str] = []

    all_markers = [int(m) for m in _MARKER.findall(text)]
    for m in all_markers:
        if (m < 1 or m > n) and m not in invented:
            invented.append(m)
    if invented:
        problems.append(f"invented citation markers not in evidence: {sorted(invented)}")

    # All passages the answer cites anywhere (a quote may span several sentences
    # with the marker only on the last one, so an unmarked sentence is fine as
    # long as it continues some cited passage).
    cited_idx = sorted({m for m in all_markers if 1 <= m <= n})
    cited_passages = [evidence[m - 1].document.text for m in cited_idx]

    for raw in _SENTENCE_SPLIT.split(text.strip()):
        sentence = raw.strip()
        if not sentence:
            continue
        valid = [m for m in (int(x) for x in _MARKER.findall(sentence)) if 1 <= m <= n]
        content_words = len(_content(_MARKER.sub("", sentence)))

        if valid:
            # A marked sentence must overlap the passage IT cites (wrong-attribution guard).
            if max(_overlap(sentence, evidence[m - 1].document.text) for m in valid) < min_overlap:
                ungrounded.append(sentence)
        elif content_words >= min_content_words and not _is_boilerplate(sentence):
            # Unmarked substantive sentence: OK only if it continues some cited
            # passage; otherwise it's an unsupported free-floating claim.
            best_any = max((_overlap(sentence, p) for p in cited_passages), default=0.0)
            if best_any < min_overlap:
                uncited.append(sentence)

    if ungrounded:
        problems.append(f"{len(ungrounded)} cited sentence(s) not supported by their citation")
    if uncited:
        problems.append(f"{len(uncited)} substantive sentence(s) carry no citation")

    grounded = not invented and not ungrounded and not uncited
    return SynthesisReport(
        grounded=grounded,
        invented_citations=sorted(invented),
        ungrounded_sentences=ungrounded,
        uncited_sentences=uncited,
        problems=problems,
    )


_BOILERPLATE = re.compile(
    r"(?i)^(according to|based on|the (retrieved |available )?evidence|"
    r"in (summary|conclusion)|the evidence (does not|is insufficient))"
)


def _is_boilerplate(sentence: str) -> bool:
    """Framing/refusal sentences that legitimately carry no citation."""
    return bool(_BOILERPLATE.match(sentence.strip()))
