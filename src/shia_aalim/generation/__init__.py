"""Generation: evidence-grounded answers and structured lecture material.

Both generators are *retrieval-first*: they assemble evidence before any prose,
and in the default (no-LLM) mode they never write a sentence that is not a
direct, cited passage. An optional ``synthesizer`` hook lets a real LLM compose
fluent prose — but its output is still run through the grounding layer before
release.
"""

from .answer import AnswerGenerator, Synthesizer
from .lecture import Lecture, LectureGenerator, LectureSection

__all__ = [
    "AnswerGenerator",
    "Synthesizer",
    "Lecture",
    "LectureSection",
    "LectureGenerator",
]
