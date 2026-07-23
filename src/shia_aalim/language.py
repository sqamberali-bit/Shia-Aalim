"""Query-language detection for Persian/Urdu/Arabic/English support.

The knowledge base is primarily English translations with the Arabic originals
attached. A user may still *ask* in Arabic, Persian or Urdu. This module detects
the query's language so the answer can be labelled and — honestly — so the
system can tell the user when cross-lingual retrieval will actually work.

Cross-lingual *retrieval* needs a multilingual semantic embedder (e.g.
``st:BAAI/bge-m3``, already integrated) that maps every language into one shared
space; the dependency-free lexical embedder cannot bridge scripts. So when a
non-English query is asked against a lexical index, the honest move is to answer
what we can and say plainly that the multilingual model is needed for good
cross-lingual results — not to pretend.

Detection is a lightweight script/character heuristic (no dependencies, no model)
and is best-effort: it distinguishes English from Arabic-script, and within
Arabic-script separates Urdu and Persian from Arabic by their distinctive
letters. It never blocks a query — an unknown result is treated as English.
"""

from __future__ import annotations

from enum import Enum


class Language(str, Enum):
    ENGLISH = "en"
    ARABIC = "ar"
    PERSIAN = "fa"
    URDU = "ur"
    UNKNOWN = "unknown"


_DISPLAY = {
    Language.ENGLISH: "English",
    Language.ARABIC: "Arabic",
    Language.PERSIAN: "Persian",
    Language.URDU: "Urdu",
    Language.UNKNOWN: "Unknown",
}

# Letters that mark Urdu specifically (retroflexes, noon-ghunna, the special
# heh/yeh forms) — strong signal it is Urdu, not Persian or Arabic.
_URDU_CHARS = set("ٹڈڑںۃہھۂۓے")
# Letters/forms that mark a Persianate script (Persian or Urdu) rather than
# Arabic: peh/cheh/jeh/gaf plus the Persian keheh and yeh.
_PERSIANATE_CHARS = set("پچژگکی")


def _is_arabic_script(ch: str) -> bool:
    o = ord(ch)
    return (
        0x0600 <= o <= 0x06FF  # Arabic
        or 0x0750 <= o <= 0x077F  # Arabic Supplement
        or 0x08A0 <= o <= 0x08FF  # Arabic Extended-A
        or 0xFB50 <= o <= 0xFDFF  # Arabic Presentation Forms-A
        or 0xFE70 <= o <= 0xFEFF  # Arabic Presentation Forms-B
    )


def detect_language(text: str) -> Language:
    """Best-effort detection of a query's language. Never raises; English by default."""
    if not text:
        return Language.UNKNOWN
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    arabic = sum(1 for c in text if _is_arabic_script(c))
    if latin == 0 and arabic == 0:
        return Language.UNKNOWN
    if latin >= arabic:
        return Language.ENGLISH

    chars = set(text)
    if chars & _URDU_CHARS:
        return Language.URDU
    if chars & _PERSIANATE_CHARS:
        return Language.PERSIAN
    return Language.ARABIC


def display_name(language: str | Language) -> str:
    try:
        return _DISPLAY[Language(language)]
    except (ValueError, KeyError):
        return "Unknown"


def is_cross_lingual(language: str | Language) -> bool:
    """True when the query language differs from the corpus's primary languages.

    English and Arabic both appear in the corpus (English translations + Arabic
    originals); Persian and Urdu do not, so those need cross-lingual retrieval.
    """
    try:
        lang = Language(language)
    except ValueError:
        return False
    return lang in (Language.PERSIAN, Language.URDU)
