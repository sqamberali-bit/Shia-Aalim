"""Lecture / majlis / khutbah generation framework.

Produces the exact structure mandated by the charter's *Lecture Generation
Framework*: Executive Summary, Introduction, Quranic Foundations, Hadith
Foundations, Historical Context, Scholarly Analysis, Practical Lessons, Common
Misconceptions, Reflection Points, Conclusion and Suggested Reading.

Each evidence-bearing section is populated by *retrieval*, filtered to the right
evidence type, so the Quranic Foundations section only ever contains real,
cited Qur'anic passages, the Hadith Foundations section only cited narrations,
and so on. Narrative sections (introduction, reflection points) are left as
clearly-marked prompts for the human lecturer or an optional LLM synthesizer —
the framework never fabricates historical narrative or scholarly claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..models import EvidenceType
from ..retrieval.retriever import Retriever, RetrievalResult


@dataclass
class LectureSection:
    title: str
    body: str = ""
    evidence: list[RetrievalResult] = field(default_factory=list)
    note: str = ""  # guidance for the lecturer where evidence is not auto-filled

    def to_markdown(self) -> str:
        lines = [f"## {self.title}", ""]
        if self.body:
            lines += [self.body, ""]
        for res in self.evidence:
            cit = res.document.citation
            conf = res.document.confidence.value.upper()
            lines.append(f"> {res.document.text.strip()}")
            lines.append(f">")
            lines.append(f"> — **{cit.reference_string()}** ({conf})")
            if cit.translation:
                lines.append(f">")
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
            "delivery. Sections marked _[Lecturer note: …]_ require human "
            "composition and are intentionally not auto-written.",
            "",
        ]
        return "\n".join(header) + "\n" + "\n".join(s.to_markdown() for s in self.sections)


class LectureGenerator:
    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    def _evidence(
        self, topic: str, types: list[EvidenceType], k: int
    ) -> list[RetrievalResult]:
        return self.retriever.retrieve(topic, k=k, evidence_types=types)

    def generate(self, topic: str, *, depth: int = 4) -> Lecture:
        """Build a fully-structured lecture outline for ``topic``.

        ``depth`` controls how many evidence items to pull into each
        evidence-driven section.
        """
        quran = self._evidence(topic, [EvidenceType.QURAN], depth)
        tafsir = self._evidence(topic, [EvidenceType.TAFSIR], depth)
        hadith = self._evidence(topic, [EvidenceType.HADITH], depth)
        history = self._evidence(topic, [EvidenceType.HISTORICAL], depth)
        scholarly = self._evidence(topic, [EvidenceType.SCHOLARLY_OPINION], depth)

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
        return Lecture(topic=topic, sections=sections, generated_on=date.today().isoformat())

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
