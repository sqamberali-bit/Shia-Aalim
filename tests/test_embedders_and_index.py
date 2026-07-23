import pytest
from conftest import sample_corpus

from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType
from shia_aalim.retrieval.embeddings import (
    HashingEmbedder,
    TfidfHashingEmbedder,
    cosine,
    fit_if_needed,
    make_embedder,
)
from shia_aalim.retrieval.index import PersistentVectorStore, embedder_signature
from shia_aalim.retrieval.retriever import Retriever
from shia_aalim.retrieval.vectorstore import InMemoryVectorStore


# ---- TF-IDF embedder ----

def test_tfidf_fit_sets_state_and_normalises():
    docs = sample_corpus()
    emb = TfidfHashingEmbedder(dim=512)
    assert not emb.fitted
    emb.fit(d.text for d in docs)
    assert emb.fitted and emb._idf
    v = emb.embed(docs[0].text)
    assert abs(sum(x * x for x in v) ** 0.5 - 1.0) < 1e-9  # L2-normalised


def test_tfidf_weights_rare_terms_higher_than_common():
    # A term appearing in every doc gets low idf; a unique term gets high idf.
    emb = TfidfHashingEmbedder(dim=4096)
    emb.fit(["allah mercy", "allah guidance", "allah light", "allah kinship xyzrare"])
    assert emb._idf["w:xyzrare"] > emb._idf["w:allah"]


def test_tfidf_beats_hashing_on_a_discriminative_query():
    docs = sample_corpus()
    def rank(emb, query, gid):
        fit_if_needed(emb, [d.text for d in docs])
        s = InMemoryVectorStore(emb); s.add(docs)
        ids = [d.id for d, _ in s.search(query, k=len(docs))]
        return ids.index(gid) if gid in ids else 999
    q, gid = "love for the near relatives kinship", "quran-42-23"
    assert rank(TfidfHashingEmbedder(dim=2048), q, gid) <= rank(HashingEmbedder(dim=2048), q, gid)


# ---- factory ----

def test_make_embedder_specs():
    assert isinstance(make_embedder("hashing"), HashingEmbedder)
    assert isinstance(make_embedder("tfidf"), TfidfHashingEmbedder)
    with pytest.raises(ValueError):
        make_embedder("bogus")


def test_make_embedder_st_without_dep_raises_clear_error():
    # sentence-transformers isn't installed here; construction must fail loudly.
    with pytest.raises(Exception) as ei:
        make_embedder("st:BAAI/bge-m3")
    assert "sentence-transformers" in str(ei.value).lower()


# ---- persistent vector store ----

def _doc(i, text):
    return Document(
        id=f"d{i}", text=text, evidence_type=EvidenceType.QURAN,
        citation=Citation(source_id="quran", evidence_type=EvidenceType.QURAN, surah=1, ayah=i),
        confidence=ConfidenceLevel.HIGH,
    )


class _CountingEmbedder(HashingEmbedder):
    def __init__(self, dim=256):
        super().__init__(dim=dim)
        self.calls = 0
    def embed_batch(self, texts):
        self.calls += len(texts)
        return super().embed_batch(list(texts))


def test_persistent_store_caches_across_reload(tmp_path):
    docs = [_doc(i, f"passage number {i} about mercy") for i in range(5)]
    cache = tmp_path / "vec.pkl"

    e1 = _CountingEmbedder()
    s1 = PersistentVectorStore(e1, cache)
    s1.add(docs)
    s1.save()
    assert e1.calls == 5  # embedded all on first build

    # Fresh store + fresh embedder, same cache file: no re-embedding.
    e2 = _CountingEmbedder()
    s2 = PersistentVectorStore(e2, cache)
    s2.add(docs)
    assert e2.calls == 0
    assert len(s2) == 5
    assert s2.search("mercy passage", k=3)


def test_persistent_store_invalidates_on_embedder_change(tmp_path):
    docs = [_doc(i, f"passage {i}") for i in range(3)]
    cache = tmp_path / "vec.pkl"
    PersistentVectorStore(_CountingEmbedder(dim=256), cache).add(docs)
    PersistentVectorStore(_CountingEmbedder(dim=256), cache).save  # noqa
    s1 = PersistentVectorStore(_CountingEmbedder(dim=256), cache); s1.add(docs); s1.save()

    # Different dim => different signature => cache ignored, re-embed.
    e = _CountingEmbedder(dim=512)
    s2 = PersistentVectorStore(e, cache)
    s2.add(docs)
    assert e.calls == 3
    assert embedder_signature(e) != embedder_signature(_CountingEmbedder(dim=256))


def test_persistent_store_plugs_into_retriever(tmp_path):
    docs = sample_corpus()
    store = PersistentVectorStore(TfidfHashingEmbedder(dim=1024), tmp_path / "c.pkl")
    fit_if_needed(store.embedder, [d.text for d in docs])
    store.add(docs)
    results = Retriever(store).retrieve("purification of the People of the House", k=3)
    assert results and "quran-33-33" in [r.document.id for r in results]
