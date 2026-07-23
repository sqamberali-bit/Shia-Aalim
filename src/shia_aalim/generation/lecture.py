"""Lecture / majlis / khutbah generation framework.

Produces the exact structure mandated by the charter's *Lecture Generation
Framework*: Executive Summary, Introduction, Quranic Foundations, Hadith
Foundations, Historical Context, Scholarly Analysis, Practical Lessons, Common
Misconceptions, Reflection Points, Conclusion and Suggested Reading.

Each evidence-bearing section is populated by *retrieval*, filtered to the right
evidence type, so the Quranic Foundations section only ever contains real, cited
Qur'anic passages, the Hadith Foundations section only cited narrations, etc.

The **narrative** sections (Executive Summary, Introduction, Practical Lessons,
Common Misconceptions, Conclusion) are, without a synthesizer, left as
clearly-marked lecturer prompts. With an optional LLM ``synthesizer`` they are
auto-written from a shared evidence pool and **re-verified** by
:func:`shia_aalim.grounding.synthesis.verify_synthesis`; prose that isn't fully
grounded (invented citation / wrong attribution / uncited claim) is discarded
and the section falls back to the lecturer prompt. Reflection Points stay a
human task — open questions are not evidence-grounded claims. The framework
never fabricates historical narrative or scholarly claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..grounding.synthesis import verify_synthesis
from ..models import EvidenceType
from ..retrieval.retriever import Retriever, RetrievalResult
from .answer import Synthesizer


@dataclass
class LectureSection:
    title: str
    body: str = ""
    evidence: list[RetrievalResult] = field(default_factory=list)
    note: str = ""  # guidance for the lecturer where evidence is not auto-filled
    synthesized: bool = False  # body was LLM-written and grounding-verified

    def to_markdown(self) -> str:
        lines = [f"## {self.title}", ""]
        if self.synthesized and self.body:
            lines += ["_[Synthesized from the evidence and verified against it.]_", ""]
        if self.body:
            lines += [self.body, ""]
        for res in self.evidence:
            cit = res.document.citation
            conf = res.document.confidence.value.upper()
            lines.append(f"> {res.document.text.strip()}")
            lines.append(">")
            lines.append(f"> — **{cit.reference_string()}** ({conf})")
            if cit.translation:
                lines.append(">")
                lines.append(f"> _{cit.translation}_")
            lines.append("")
        if self.note:
            lines += [f"_[Lecturer note: {self.note}]_", ""]
        return "\n".join(lines)


@dataclass
class Lecture:
    topic: str
    sections: list[LectureSection] = field(default_factory=list)
    generated_on: str = ""

    def to_markdown(self) -> str:
        header = [
            f"# {self.topic}",
            "",
            f"_Lecture outline generated {self.generated_on or date.today().isoformat()}._",
            "",
            "> **Integrity notice:** Evidence blocks below are retrieved, cited "
            "passages. Verify every citation against the primary source before "
            "delivery. Sections marked _[Synthesized …]_ were LLM-written and "
            "checked to be grounded in the cited evidence; sections marked "
            "_[Lecturer note: …]_ require human composition and are intentionally "
            "not auto-written.",
            "",
        ]
        return "\n".join(header) + "\n" + "\n".join(s.to_markdown() for s in self.sections)


# Narrative sections that may be auto-written from the evidence pool, with the
# instruction handed to the synthesizer. Reflection Points is deliberately NOT
# here (open questions are not grounded claims).
_NARRATIVE_PROMPTS = {
    "Executive Summary": "state the central thesis in 2–3 sentences",
    "Introduction": "explain why this topic matters to the audience today",
    "Practical Lessons": "give 2–4 practical, modern lessons",
    "Common Misconceptions": "clarify common misconceptions, only where the evidence supports the clarification",
    "Conclusion": "summarise the key takeaways",
}


class LectureGenerator:
    def __init__(self, retriever: Retriever, *, synthesizer: Optional[Synthesizer] = None) -> None:
        self.retriever = retriever
        self.synthesizer = synthesizer

    def _evidence(
        self, topic: str, types: list[EvidenceType], k: int
    ) -> list[RetrievalResult]:
        return self.retriever.retrieve(topic, k=k, evidence_types=types)

    def generate(self, topic: str, *, depth: int = 4) -> Lecture:
        """Build a fully-structured lecture outline for ``topic``.

        ``depth`` controls how many evidence items to pull into each
        evidence-driven section. If a synthesizer was supplied, the narrative
        sections are auto-written from the pooled evidence and verified.
        """
        quran = self._evidence(topic, [EvidenceType.QURAN], depth)
        tafsir = self._evidence(topic, [EvidenceType.TAFSIR], depth)
        hadith = self._evidence(topic, [EvidenceType.HADITH], depth)
        history = self._evidence(topic, [EvidenceType.HISTORICAL], depth)
        scholarly = self._evidence(topic, [EvidenceType.SCHOLARLY_OPINION], depth)

        # A pooled, de-duplicated evidence list for the narrative sections.
        pool = self._pool([quran, tafsir, hadith, history, scholarly], limit=depth * 2)

        sections = [
            LectureSection(
                "Executive Summary",
                note="State the central thesis in 2–3 sentences, grounded in the "
                "evidence gathered below.",
            ),
            LectureSection(
                "Introduction",
                note="Explain why this topic matters to the audience today; set "
                "the scene without unsupported historical claims.",
            ),
            LectureSection(
                "Qur'anic Foundations",
                evidence=quran,
                note=None if quran else "No Qur'anic evidence retrieved — ingest "
                "relevant tafsir/verse data or refine the topic.",
            ),
            LectureSection(
                "Tafsir & Commentary",
                evidence=tafsir,
                note=None if tafsir else "No tafsir retrieved for this topic.",
            ),
            LectureSection(
                "Hadith Foundations",
                evidence=hadith,
                note="Confirm the grade of each narration from an attributable "
                "rijal source before citing it as authentic."
                if hadith
                else "No hadith retrieved — do not paraphrase remembered narrations; "
                "ingest sourced hadith first.",
            ),
            LectureSection(
                "Historical Context",
                evidence=history,
                note="Present chronology from sourced reports; flag any popular "
                "narrative that lacks a citation as such.",
            ),
            LectureSection(
                "Scholarly Analysis",
                evidence=scholarly,
                note="Distinguish consensus, majority, minority and disputed views; "
                "attribute each to a named scholar/work.",
            ),
            LectureSection(
                "Practical Lessons",
                note="Derive modern, actionable lessons strictly from the evidence "
                "above.",
            ),
            LectureSection(
                "Common Misconceptions",
                note="Clarify misconceptions; where a popular story lacks evidence, "
                "say so plainly rather than repeating it.",
            ),
            LectureSection(
                "Reflection Points",
                note="Provide 3–5 open questions to engage the audience.",
            ),
            LectureSection(
                "Conclusion",
                note="Summarise the key takeaways tied back to the thesis.",
            ),
            LectureSection(
                "Suggested Reading",
                body=self._reading_list([quran, tafsir, hadith, history, scholarly]),
                note="Add further primary and scholarly references."
                if not any([quran, tafsir, hadith, history, scholarly])
                else "",
            ),
        ]

        if self.synthesizer is not None and pool:
            for section in sections:
                instruction = _NARRATIVE_PROMPTS.get(section.title)
                if instruction:
                    self._fill_narrative(section, topic, instruction, pool)

        return Lecture(topic=topic, sections=sections, generated_on=date.today().isoformat())

    def _fill_narrative(
        self, section: LectureSection, topic: str, instruction: str, pool: list[RetrievalResult]
    ) -> None:
        """Synthesize a narrative section and keep it ONLY if it verifies."""
        question = (
            f"For a lecture on '{topic}', write the '{section.title}' section: "
            f"{instruction}. Use only the evidence and cite it with [n] markers."
        )
        try:
            prose = self.synthesizer.synthesize(question, pool)
        except Exception:  # noqa: BLE001 - a failed synthesizer just leaves the note
            return
        if prose and verify_synthesis(prose, pool).grounded:
            section.body = prose
            section.synthesized = True
            section.note = ""
        else:
            section.note = (
                section.note + " (Auto-synthesis was withheld — not fully grounded.)"
            ).strip()

    @staticmethod
    def _pool(
        evidence_groups: list[list[RetrievalResult]], *, limit: int
    ) -> list[RetrievalResult]:
        """Flatten + de-duplicate evidence (by doc id), best-scored first."""
        seen: set[str] = set()
        merged: list[RetrievalResult] = []
        for res in sorted(
            (r for g in evidence_groups for r in g), key=lambda r: r.score, reverse=True
        ):
            if res.document.id in seen:
                continue
            seen.add(res.document.id)
            merged.append(res)
        return merged[:limit]

    @staticmethod
    def _reading_list(evidence_groups: list[list[RetrievalResult]]) -> str:
        seen: set[str] = set()
        items: list[str] = []
        for group in evidence_groups:
            for res in group:
                sid = res.document.citation.source_id
                if sid not in seen:
                    seen.add(sid)
                    items.append(f"- {sid}")
        return "\n".join(items) if items else ""
