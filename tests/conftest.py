import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DATA = ROOT / "data"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def sample_corpus():
    """A small, topic-distinct corpus for deterministic retrieval/grounding tests.

    Unit tests must not depend on the baseline embedder pinpointing one verse
    among thousands (that is what a semantic model is for — see the real-corpus
    integrity test instead). These few documents have clearly distinct topics so
    the hashing baseline can separate them reliably.
    """
    from shia_aalim.models import (
        Citation,
        ConfidenceLevel,
        Document,
        EvidenceType,
        HadithGrade,
    )

    def q(surah, ayah, text, conf=ConfidenceLevel.HIGH, tags=()):
        return Document(
            id=f"quran-{surah}-{ayah}",
            text=text,
            evidence_type=EvidenceType.QURAN,
            citation=Citation(
                source_id="quran", evidence_type=EvidenceType.QURAN,
                surah=surah, ayah=ayah, translation_source="test",
            ),
            confidence=conf,
            tags=list(tags),
            language="en",
        )

    return [
        q(33, 33, "Allah only desires to keep away uncleanness from you O People of the "
                  "House and to purify you with a thorough purification"),
        q(42, 23, "Say I do not ask you any reward for it except love for my near relatives kinship"),
        q(5, 55, "Your guardian wali is only Allah and His Messenger and those who believe "
                 "who keep up prayer and give charity while bowing"),
        q(112, 1, "Say He is Allah the One the eternal absolute unique in oneness"),
        q(2, 255, "Allah there is no god but He the Living the Self subsisting throne kursi"),
        Document(
            id="al-kafi-1-3-1-7",
            text="The intellect is that by which the Beneficent is worshipped and paradise is earned",
            evidence_type=EvidenceType.HADITH,
            citation=Citation(
                source_id="al-kafi", evidence_type=EvidenceType.HADITH,
                volume="1", chapter="Book of Intellect, bab 1", hadith_number="7",
                grade=HadithGrade.SAHIH,
                grade_source="Majlisi: sahih",
            ),
            confidence=ConfidenceLevel.HIGH,
            tags=["hadith"],
            language="en",
        ),
    ]
