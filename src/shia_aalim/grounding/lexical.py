"""Shared lexical helpers for grounding checks (content-word overlap).

Kept in its own module so both the synthesis verifier and the lexical entailment
judge use one definition without importing each other.
"""

from __future__ import annotations

from ..ingestion.normalize import tokens

# Common function words carry no grounding signal — a shared "the"/"in" must not
# make an off-topic sentence look supported. (English + a few transliterations.)
STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "was",
    "were", "be", "been", "it", "its", "this", "that", "these", "those", "for",
    "with", "as", "by", "from", "at", "he", "him", "his", "they", "them", "their",
    "you", "your", "we", "our", "i", "not", "no", "but", "so", "if", "then",
    "which", "who", "whom", "what", "when", "will", "shall", "may", "do", "does",
    "did", "has", "have", "had", "all", "any", "one", "also", "there", "here",
}


def content_tokens(text: str) -> set[str]:
    return {t for t in tokens(text) if t not in STOPWORDS and len(t) > 1}


def content_overlap(sentence: str, passage: str) -> float:
    """Fraction of the sentence's *content* words present in the passage."""
    a = content_tokens(sentence)
    if not a:
        return 1.0  # nothing but stopwords — a connective clause, don't penalise
    return len(a & content_tokens(passage)) / len(a)
