"""Arabic text normalisation for retrieval and de-duplication.

Arabic corpora vary wildly in their use of diacritics (tashkeel), alef and yaa
variants, tatweel (kashida) and presentation forms. Normalising these is
essential so that a query and a stored passage match even when one is fully
vocalised and the other is not.

Two complementary functions are provided:

* :func:`normalize_arabic` — light, *display-safe* normalisation (unify alef/yaa/
  taa forms, strip tatweel) that keeps the text readable.
* :func:`normalize_for_search` — aggressive, *match-only* normalisation that also
  removes all diacritics and tatweel and collapses whitespace. Never show this
  form to a user; use it only as a matching key.

Pure standard library (``unicodedata`` + ``re``); no third-party dependencies.
The diacritic ranges are written with explicit ``\\u`` escapes so the module is
transport-safe.
"""

from __future__ import annotations

import re
import unicodedata

# Arabic diacritics: harakat, tanwin, shadda, sukun, superscript alef, and the
# Quranic small-high annotation marks.
_TASHKEEL = re.compile(
    "["
    "ؐ-ؚ"  # Arabic sign marks (sallallahou, etc.)
    "ً-ٟ"  # harakat, tanwin, shadda, sukun, extended
    "ٰ"          # superscript alef
    "ۖ-ۜ"  # small high ligatures (Quranic)
    "۟-ۤ"  # small high marks (Quranic)
    "ۧ-ۨ"
    "۪-ۭ"
    "]"
)
_TATWEEL = "ـ"  # kashida / elongation
_QURANIC_ANNOTATION = re.compile("[ࣣ-ࣿ࿿۞]")  # end-of-ayah / marks

# Character folding maps applied in both modes.
_FOLD_MAP = {
    # Alef variants -> bare alef
    "آ": "ا",  # آ
    "أ": "ا",  # أ
    "إ": "ا",  # إ
    "ٱ": "ا",  # ٱ wasla
    # Alef maksura -> yaa
    "ى": "ي",  # ى -> ي
    # Taa marbuta -> haa
    "ة": "ه",  # ة -> ه
    # Persian variants -> Arabic
    "ک": "ك",  # ک -> ك
    "ی": "ي",  # ی -> ي
    # Extended Arabic-Indic (Persian) digits -> ASCII
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    # Arabic-Indic digits -> ASCII
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}

_WS = re.compile(r"\s+")


def _fold(text: str) -> str:
    return "".join(_FOLD_MAP.get(ch, ch) for ch in text)


def strip_tashkeel(text: str) -> str:
    """Remove Arabic diacritics (harakat, tanwin, shadda, sukun, superscript alef)."""
    return _TASHKEEL.sub("", text)


def strip_tatweel(text: str) -> str:
    """Remove the tatweel/kashida elongation character."""
    return text.replace(_TATWEEL, "")


def normalize_arabic(text: str, *, remove_diacritics: bool = False) -> str:
    """Display-safe normalisation.

    Applies NFC Unicode normalisation, folds alef/yaa/taa/Persian variants,
    strips tatweel and (optionally) diacritics, and collapses whitespace. The
    result is still human-readable.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = strip_tatweel(text)
    text = _QURANIC_ANNOTATION.sub("", text)
    if remove_diacritics:
        text = strip_tashkeel(text)
    text = _fold(text)
    text = _WS.sub(" ", text).strip()
    return text


def normalize_for_search(text: str) -> str:
    """Aggressive, match-only normalisation (diacritic-insensitive key).

    Use as a comparison/index key only — never render this back to a user.
    """
    return normalize_arabic(text, remove_diacritics=True).lower()


def tokens(text: str) -> list[str]:
    """Whitespace tokens of the search-normalised form (handy for BoW models)."""
    norm = normalize_for_search(text)
    return [t for t in norm.split(" ") if t]
