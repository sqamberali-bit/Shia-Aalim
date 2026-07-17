"""Smoke tests over the small committed sample (data/knowledge/sample/).

Unlike the full corpus (which is external/out-of-git), the sample ships in the
repo so a bare checkout can still exercise the end-to-end pipeline and prove the
committed data is well-formed and citable.
"""

from conftest import DATA

from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.ingestion.loaders import load_documents_jsonl
from shia_aalim.research_loop import build_index
from shia_aalim.sources import load_registry_ids

SAMPLE = DATA / "knowledge" / "sample" / "sample.jsonl"


def test_sample_exists_and_is_wellformed():
    docs = load_documents_jsonl(SAMPLE)
    assert len(docs) >= 10
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    for d in docs:
        assert d.citation.is_complete()
        assert d.citation.source_id in known


def test_sample_supports_grounded_retrieval():
    docs = load_documents_jsonl(SAMPLE)
    retriever = build_index(docs)
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    answer = AnswerGenerator(retriever, known_source_ids=known).answer(
        "purification of the People of the House", k=3
    )
    assert answer.claims
    assert all(c.citations for c in answer.claims)
