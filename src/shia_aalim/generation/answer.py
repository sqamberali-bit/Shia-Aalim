"""Evidence-grounded answer generation.

The :class:`AnswerGenerator` follows this pipeline (charter: *answer grounding*):

1. Retrieve confidence-ranked evidence for the question.
2. Build one :class:`~shia_aalim.models.Claim` per retrieved passage, carrying
   that passage's citation, confidence and evidence type — so no claim exists
   without backing evidence.
3. Optionally hand the (question, evidence) pair to a ``Synthesizer`` (an LLM)
   to compose fluent prose. The synthesizer is told, by contract, to cite only
   the supplied evidence.
4. Run the result through the grounding layer and attach any warnings; a failed
   grounding check downgrades the answer rather than suppressing the evidence.

In the default configuration (no synthesizer) the generator is purely
*extractive*: every returned claim is verbatim evidence with a real citation. It
cannot hallucinate because it never writes original sentences.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Protocol

from ..grounding.synthesis import verify_synthesis
from ..grounding.verify import check_answer_grounding
from ..models import Answer, Claim, ConfidenceLevel, EvidenceType
from ..retrieval.retriever import Retriever, RetrievalResult


class Synthesizer(Protocol):
    """An LLM that composes an answer from retrieved evidence.

    Implementations MUST only use the supplied evidence and must return prose
    that cites it. The output is re-verified by the grounding layer regardless.
    """

    def synthesize(self, question: str, evidence: list[RetrievalResult]) -> str:
        ...


# Human-readable evidence-type labels for answer prose.
_TYPE_LABEL = {
    EvidenceType.QURAN: "Qur'an",
    EvidenceType.TAFSIR: "Tafsir",
    EvidenceType.HADITH: "Hadith",
    EvidenceType.HISTORICAL: "Historical report",
    EvidenceType.SCHOLARLY_OPINION: "Scholarly opinion",
    EvidenceType.BIOGRAPHICAL: "Biographical (rijal)",
    EvidenceType.LINGUISTIC: "Linguistic",
}


class AnswerGenerator:
    def __init__(
        self,
        retriever: Retriever,
        *,
        synthesizer: Optional[Synthesizer] = None,
        known_source_ids: Optional[set[str]] = None,
    ) -> None:
        self.retriever = retriever
        self.synthesizer = synthesizer
        self.known_source_ids = known_source_ids

    def answer(
        self,
        question: str,
        *,
        k: int = 6,
        evidence_types: Optional[list[EvidenceType]] = None,
        min_confidence: ConfidenceLevel = ConfidenceLevel.LOW,
        min_similarity: float = 0.15,
    ) -> Answer:
        evidence = self.retriever.retrieve(
            question, k=k, evidence_types=evidence_types, min_confidence=min_confidence
        )
        # Refuse to answer from barely-relevant matches: a passage that is only
        # weakly similar to the question is not evidence *for* it. This gate is a
        # core hallucination-prevention control — without it, extractive answers
        # would trivially "ground" against whatever the index returned.
        evidence = [r for r in evidence if r.similarity >= min_similarity]

        if not evidence:
            return Answer(
                question=question,
                summary=None,
                caveats=[
                    "No sufficiently-relevant evidence was found in the knowledge base "
                    f"for this question (no passage cleared the similarity floor of "
                    f"{min_similarity}). Per the charter, no answer is given beyond the "
                    "available evidence. Consider ingesting relevant sources and retrying."
                ],
                generated_on=date.today().isoformat(),
            )

        claims = [
            Claim(
                statement=res.document.text.strip(),
                evidence_type=res.document.evidence_type,
                citations=[res.document.citation],
                confidence=res.document.confidence,
                view_status=res.document.view_status,
            )
            for res in evidence
        ]

        summary = None
        caveats: list[str] = []
        if self.synthesizer is not None:
            try:
                candidate = self.synthesizer.synthesize(question, evidence)
            except Exception as exc:  # noqa: BLE001
                candidate = None
                caveats.append(f"Synthesizer failed; returning extractive evidence only ({exc}).")
            if candidate:
                # Re-verify the LLM prose before trusting it (charter: post-
                # generation fact verification). Reject rather than show
                # unsupported/invented-citation prose — the cited evidence below
                # is always available as the grounded fallback.
                report = verify_synthesis(candidate, evidence)
                if report.grounded:
                    summary = candidate
                else:
                    caveats.append(
                        "Synthesized answer REJECTED by verification and withheld "
                        "(showing cited evidence instead): " + "; ".join(report.problems[:3])
                    )

        answer = Answer(
            question=question,
            claims=claims,
            summary=summary,
            caveats=caveats,
            generated_on=date.today().isoformat(),
        )

        report = check_answer_grounding(
            answer, evidence, known_source_ids=self.known_source_ids
        )
        if not report.grounded:
            answer.caveats.append(
                "Grounding check raised warnings: " + "; ".join(report.problems[:5])
            )

        # Surface confidence/view mix honestly.
        if any(c.confidence.rank <= ConfidenceLevel.LOW.rank for c in claims):
            answer.caveats.append(
                "Some evidence is LOW/UNVERIFIED confidence — do not treat as established fact."
            )
        return answer

    def format_markdown(self, answer: Answer) -> str:
        """Render an answer as reviewer-friendly Markdown with grouped evidence."""
        lines: list[str] = [f"## {answer.question}", ""]
        if answer.summary:
            lines += ["### Synthesized answer _(LLM prose, verified against the evidence below)_",
                      "", answer.summary, ""]
        if not answer.claims:
            lines += ["_No evidence found in the knowledge base._", ""]
        else:
            lines += ["### Evidence", ""]
            for claim in answer.claims:
                label = _TYPE_LABEL.get(claim.evidence_type, claim.evidence_type.value)
                refs = "; ".join(c.reference_string() for c in claim.citations)
                conf = claim.confidence.value.upper()
                view = f" · _{claim.view_status.value}_" if claim.view_status else ""
                lines.append(f"- **[{label} · {conf}{view}]** {claim.statement}")
                lines.append(f"  — _{refs}_")
        if answer.caveats:
            lines += ["", "### Caveats", ""]
            lines += [f"- {c}" for c in answer.caveats]
        lines += ["", f"_Generated {answer.generated_on or date.today().isoformat()}._"]
        return "\n".join(lines)
