"""The numpy dense-scan search must return exactly what the pure-Python
cosine scan returns — same documents, same order, same scores (to float32
precision). Guards the speed optimisation against silently changing results."""


import pytest

from conftest import DATA

from shia_aalim.ingestion.loaders import load_documents_jsonl
from shia_aalim.retrieval import vectorstore as vs
from shia_aalim.retrieval.embeddings import TfidfHashingEmbedder, cosine
from shia_aalim.retrieval.index import PersistentVectorStore

np = pytest.importorskip("numpy")


def _sample_docs(n=300):
    docs = []
    for path in sorted((DATA / "knowledge" / "sample").glob("*.jsonl")):
        docs.extend(load_documents_jsonl(path))
        if len(docs) >= n:
            return docs[:n]
    return docs


QUERIES = [
    "the guardianship of Ali and giving zakat while bowing",
    "حكم صلاة المسافر",
    "patience in hardship and trials",
]


def _pure_python_topk(store, query, k):
    qv = store.embedder.embed(query)
    scored = [(d, cosine(qv, v)) for d, v in zip(store._docs, store._vecs)]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


def test_numpy_matches_pure_python_topk(tmp_path):
    docs = _sample_docs()
    emb = TfidfHashingEmbedder(dim=512)
    store = PersistentVectorStore(emb, tmp_path / "cache.pkl")
    store.add(docs)
    for q in QUERIES:
        fast = store.search(q, k=8)
        slow = _pure_python_topk(store, q, 8)
        assert [d.id for d, _ in fast] == [d.id for d, _ in slow]
        for (_, sf), (_, ss) in zip(fast, slow):
            assert sf == pytest.approx(ss, abs=1e-4)  # float32 vs float64


def test_fallback_path_without_numpy(tmp_path, monkeypatch):
    docs = _sample_docs(60)
    emb = TfidfHashingEmbedder(dim=256)
    store = PersistentVectorStore(emb, tmp_path / "cache.pkl")
    store.add(docs)
    with_np = store.search(QUERIES[0], k=5)
    monkeypatch.setattr(vs, "_np", None)
    store._matrix = None
    without_np = store.search(QUERIES[0], k=5)
    assert [d.id for d, _ in with_np] == [d.id for d, _ in without_np]


def test_matrix_invalidated_after_add(tmp_path):
    docs = _sample_docs(80)
    emb = TfidfHashingEmbedder(dim=256)
    store = PersistentVectorStore(emb, tmp_path / "cache.pkl")
    store.add(docs[:40])
    assert store.search(QUERIES[0], k=3)
    store.add(docs[40:])
    res = store.search(QUERIES[0], k=3)
    assert len(res) == 3 and len(store) == len({d.id for d in docs})


def test_cache_roundtrip_stays_compatible(tmp_path):
    docs = _sample_docs(50)
    emb = TfidfHashingEmbedder(dim=256)
    store = PersistentVectorStore(emb, tmp_path / "cache.pkl")
    store.add(docs)
    store.save()
    # a second store over the same cache embeds nothing and searches identically
    emb2 = TfidfHashingEmbedder(dim=256)
    emb2.fit([d.text for d in docs])
    store2 = PersistentVectorStore(emb2, tmp_path / "cache.pkl")
    assert store2.embedded_count == len(docs)
    store2.add(docs)
    a = [(d.id, round(s, 5)) for d, s in store.search(QUERIES[1], k=5)]
    b = [(d.id, round(s, 5)) for d, s in store2.search(QUERIES[1], k=5)]
    assert a == b
