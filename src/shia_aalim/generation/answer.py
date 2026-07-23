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

from ..grounding.entailment import EntailmentJudge
from .decompose import QueryDecomposer
from ..grounding.synthesis import verify_synthesis
from ..grounding.verify import check_answer_grounding
from ..language import Language, detect_language, display_name, is_cross_lingual
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
        judge: Optional["EntailmentJudge"] = None,
        decomposer: Optional["QueryDecomposer"] = None,
        multilingual: bool = False,
    ) -> None:
        self.retriever = retriever
        self.synthesizer = synthesizer
        self.known_source_ids = known_source_ids
        self.judge = judge  # entailment judge for verifying synthesized prose
        self.decomposer = decomposer  # splits multi-part questions before retrieval
        # True when the active embedder is a multilingual semantic model that can
        # bridge scripts; gates the honest cross-lingual caveat below.
        self.multilingual = multilingual

    def _gather_evidence(
        self,
        question: str,
        *,
        k: int,
        evidence_types: Optional[list[EvidenceType]],
        min_confidence: ConfidenceLevel,
        min_similarity: float,
        source_ids: Optional[set[str]] = None,
    ) -> tuple[list[RetrievalResult], list[str]]:
        """Retrieve evidence, decomposing multi-part questions first.

        Each sub-question is retrieved separately and the results merged
        (deduped by document id, best score kept) so every part is represented —
        a compound question no longer starves its weaker clause.
        """
        subs = self.decomposer.decompose(question) if self.decomposer else [question]
        sub_questions = subs if len(subs) > 1 else []

        merged: dict[str, RetrievalResult] = {}
        for sq in subs:
            for res in self.retriever.retrieve(
                sq, k=k, evidence_types=evidence_types,
                min_confidence=min_confidence, source_ids=source_ids,
            ):
                if res.similarity < min_similarity:
                    continue
                cur = merged.get(res.document.id)
                if cur is None or res.score > cur.score:
                    merged[res.document.id] = res

        results = sorted(merged.values(), key=lambda r: r.score, reverse=True)
        cap = k if len(subs) == 1 else min(len(results), max(k, 3 * len(subs)))
        return results[:cap], sub_questions

    def answer(
        self,
        question: str,
        *,
        k: int = 6,
        evidence_types: Optional[list[EvidenceType]] = None,
        min_confidence: ConfidenceLevel = ConfidenceLevel.LOW,
        min_similarity: float = 0.15,
        source_ids: Optional[set[str]] = None,
    ) -> Answer:
        # Detect the query language up front so it is recorded on every path and
        # the cross-lingual caveat can be raised honestly.
        language = detect_language(question)
        lang_caveats = self._language_caveats(language)

        # Retrieve evidence (decomposing multi-part questions first). The
        # similarity floor is applied per sub-question inside the helper: a
        # passage only weakly similar to the query is not evidence *for* it — a
        # core hallucination-prevention control.
        evidence, sub_questions = self._gather_evidence(
            question, k=k, evidence_types=evidence_types,
            min_confidence=min_confidence, min_similarity=min_similarity,
            source_ids=source_ids,
        )

        if not evidence:
            filters: list[str] = []
            if evidence_types:
                filters.append("type ∈ {" + ", ".join(t.value for t in evidence_types) + "}")
            if source_ids:
                filters.append("source ∈ {" + ", ".join(sorted(source_ids)) + "}")
            if min_confidence.rank > ConfidenceLevel.LOW.rank:
                filters.append(f"confidence ≥ {min_confidence.value}")
            filter_note = (
                " Active filters (" + "; ".join(filters) + ") may be excluding relevant "
                "passages — try relaxing them." if filters else
                " Consider ingesting relevant sources and retrying."
            )
            return Answer(
                question=question,
                summary=None,
                sub_questions=sub_questions,
                query_language=language.value,
                caveats=[
                    "No sufficiently-relevant evidence was found in the knowledge base "
                    f"for this question (no passage cleared the similarity floor of "
                    f"{min_similarity}). Per the charter, no answer is given beyond the "
                    "available evidence." + filter_note
                ] + lang_caveats,
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
                report = verify_synthesis(candidate, evidence, judge=self.judge)
                if report.grounded:
                    summary = candidate
                else:
                    caveats.append(
                        "Synthesized answer REJECTED by verification and withheld "
                        "(showing cited evidence instead): " + "; ".join(report.problems[:3])
                    )

        if sub_questions:
            caveats.append(
                "Multi-part question decomposed and retrieved per part: "
                + " | ".join(sub_questions)
            )

        caveats += lang_caveats
        answer = Answer(
            question=question,
            claims=claims,
            summary=summary,
            caveats=caveats,
            generated_on=date.today().isoformat(),
            sub_questions=sub_questions,
            query_language=language.value,
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

    def _language_caveats(self, language: Language) -> list[str]:
        """Honest note when a non-English query needs cross-lingual retrieval.

        Persian/Urdu do not appear in the corpus (English translations + Arabic
        originals), so they can only be matched by a multilingual *semantic*
        embedder. With a lexical index we say so plainly rather than pretend.
        """
        if not is_cross_lingual(language):
            return []
        note = (
            f"Query detected as {display_name(language)}. The knowledge base is "
            "English translations with Arabic originals, so cross-lingual matching "
        )
        if self.multilingual:
            return [note + "is handled by the active multilingual semantic embedder."]
        return [
            note + "needs the multilingual semantic embedder (st:BAAI/bge-m3); with the "
            "current lexical index, results for this query may be poor. Re-run with the "
            "semantic index, or ask in English/Arabic, for reliable results."
        ]

    def format_markdown(self, answer: Answer) -> str:
        """Render an answer as reviewer-friendly Markdown with grouped evidence."""
        lines: list[str] = [f"## {answer.question}", ""]
        if answer.query_language and answer.query_language not in ("en", "unknown"):
            lines += [f"_Query language: {display_name(answer.query_language)}._", ""]
        if answer.sub_questions:
            lines += ["_Decomposed into: "
                      + "; ".join(answer.sub_questions) + "_", ""]
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
