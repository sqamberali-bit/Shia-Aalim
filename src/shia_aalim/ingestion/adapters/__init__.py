"""Source-specific ingestion adapters.

Each adapter turns a real, licensed, verifiable upstream dataset into
:class:`~shia_aalim.models.Document` objects with exact citations. Adapters
never fabricate: they carry through the upstream's own references, translations
and (for hadith) rijāl gradings, and they omit rather than invent anything the
upstream does not provide.

Current adapters:

* :mod:`shia_aalim.ingestion.adapters.quran` — Qur'an (Arabic + translations)
  from the ``fawazahmed0/quran-api`` GitHub dataset.
* :mod:`shia_aalim.ingestion.adapters.thaqalayn` — Twelver hadith from the CC0
  ``narmafraz/ThaqalaynData`` dataset (the data behind thaqalayn.net).
"""

from .bihar import build_bihar_documents
from .quran import build_quran_documents, load_edition
from .shiavault import build_prose_documents
from .thaqalayn import build_hadith_documents, parse_grading

__all__ = [
    "build_quran_documents",
    "load_edition",
    "build_hadith_documents",
    "parse_grading",
    "build_prose_documents",
    "build_bihar_documents",
]
