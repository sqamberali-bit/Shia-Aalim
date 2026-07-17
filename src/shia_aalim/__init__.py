"""Shia-Aalim — an evidence-first Twelver Shia Islamic research & lecture assistant.

Public API re-exports the most commonly used building blocks so callers can do::

    from shia_aalim import Document, Citation, EvidenceType, ConfidenceLevel

See ``AGENT.md`` for the operating charter and ``docs/architecture.md`` for how
the pieces fit together.
"""

from __future__ import annotations

from .models import (
    Answer,
    Citation,
    Claim,
    ConfidenceLevel,
    Document,
    EvidenceType,
    HadithGrade,
    Source,
    ViewStatus,
)

__version__ = "0.1.0"

__all__ = [
    "Answer",
    "Citation",
    "Claim",
    "ConfidenceLevel",
    "Document",
    "EvidenceType",
    "HadithGrade",
    "Source",
    "ViewStatus",
    "__version__",
]
