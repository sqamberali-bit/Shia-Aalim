"""Cross-referencing: link a Qurʾān verse to its tafsir and related narrations.

Tafsir and hadith documents are cited by book/volume/chapter, not by
surah:ayah, so there is no locator key that ties them to a verse. The link is
therefore built from *content*: the verse's own text is used as the query to
retrieve the tafsir sections and narrations that actually discuss it, plus other
verses on the same theme.

Everything returned is a real, cited passage retrieved from the corpus — nothing
is invented. Each link is labelled:

* ``explicit``  — the passage cites the verse reference (e.g. ``5:55``) or quotes
  enough of the verse text that it is clearly *about* this verse; and
* ``thematic``  — the passage is topically related (retrieved by similarity) but
  does not visibly quote or cite the verse.

This is a transparent heuristic, not a claim of scholarly tafsir attribution: the
reader still verifies. It never raises confidence — the related passages keep
their own source confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..grounding.lexical import content_overlap
from ..models import Document, EvidenceType
from ..retrieval.retriever import Retriever


@dataclass
class RelatedItem:
    document: Document
    similarity: float
    link_type: str  # "explicit" | "thematic"


@dataclass
class CrossRefResult:
    verse: Document
    tafsir: list[RelatedItem]
    hadith: list[RelatedItem]
    verses: list[RelatedItem]  # other Qurʾān verses on the same theme


def build_verse_index(docs: list[Document]) -> dict[tuple[int, int], Document]:
    """Map ``(surah, ayah) -> verse Document`` for quick verse lookup."""
    index: dict[tuple[int, int], Document] = {}
    for d in docs:
        c = d.citation
        if d.evidence_type is EvidenceType.QURAN and c.surah is not None and c.ayah is not None:
            index.setdefault((int(c.surah), int(c.ayah)), d)
    return index


class CrossReferencer:
    """Find the tafsir, narrations and sibling verses related to a verse."""

    def __init__(
        self, retriever: Retriever, verse_index: dict[tuple[int, int], Document]
    ) -> None:
        self.retriever = retriever
        self.verse_index = verse_index

    def verse(self, surah: int, ayah: int) -> Optional[Document]:
        return self.verse_index.get((int(surah), int(ayah)))

    def related(
        self,
        surah: int,
        ayah: int,
        *,
        k: int = 5,
        min_similarity: float = 0.15,
        explicit_overlap: float = 0.5,
    ) -> Optional[CrossRefResult]:
        """Cross-references for a verse, or ``None`` if the verse isn't in the corpus."""
        verse = self.verse(surah, ayah)
        if verse is None:
            return None

        # Seed the search with the verse's own text (translation carries the
        # meaning; the Arabic is appended so an Arabic corpus matches too).
        query = verse.text
        if verse.citation.arabic_text:
            query = f"{query} {verse.citation.arabic_text}"
        ref_token = f"{surah}:{ayah}"

        def related_of(types: list[EvidenceType]) -> list[RelatedItem]:
            out: list[RelatedItem] = []
            for res in self.retriever.retrieve(query, k=k * 3, evidence_types=types):
                doc = res.document
                if doc.id == verse.id:
                    continue  # never link a verse to itself
                if res.similarity < min_similarity:
                    continue
                out.append(RelatedItem(doc, res.similarity,
                                       _link_type(verse, doc, ref_token, explicit_overlap)))
                if len(out) >= k:
                    break
            # Surface explicit links first, then by similarity.
            out.sort(key=lambda r: (r.link_type != "explicit", -r.similarity))
            return out

        return CrossRefResult(
            verse=verse,
            tafsir=related_of([EvidenceType.TAFSIR]),
            hadith=related_of([EvidenceType.HADITH]),
            verses=related_of([EvidenceType.QURAN]),
        )


def _link_type(verse: Document, doc: Document, ref_token: str, explicit_overlap: float) -> str:
    """``explicit`` if the passage cites the verse ref or quotes its text; else ``thematic``."""
    text = doc.text or ""
    if ref_token in text:
        return "explicit"
    # Does the passage quote a large fraction of the verse's own words?
    if content_overlap(verse.text, text) >= explicit_overlap:
        return "explicit"
    if verse.citation.arabic_text and content_overlap(verse.citation.arabic_text, text) >= explicit_overlap:
        return "explicit"
    return "thematic"
