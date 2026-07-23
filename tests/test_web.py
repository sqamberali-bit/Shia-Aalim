import pytest

from conftest import DATA, sample_corpus

from shia_aalim.sources import load_registry_ids
from shia_aalim import web

# The web layer is an optional extra; skip cleanly where FastAPI isn't installed.
TestClient = pytest.importorskip("fastapi.testclient").TestClient

REGISTRY = DATA / "sources" / "registry.yaml"


def _sample_stack(embedders=("tfidf",)) -> web.Stack:
    """Build a Stack over the tiny in-memory sample corpus (no disk load).

    The default embedder's index is built eagerly (mirroring build_stack); any
    extra embedders build lazily on first query, exactly as in production.
    """
    docs = sample_corpus()
    known = load_registry_ids(REGISTRY)
    config = web.AppConfig(embedders=list(embedders))
    stack = web.Stack(docs, config, known)
    stack.engine(config.default_embedder)
    return stack


@pytest.fixture
def client() -> TestClient:
    app = web.create_app(stack=_sample_stack())
    return TestClient(app)


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Shia-Aalim" in r.text
    assert "No citation = not a fact" in r.text


def test_status_reports_corpus(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["documents"] == len(sample_corpus())
    assert body["default_embedder"] == "tfidf"
    specs = {e["spec"]: e for e in body["embedders"]}
    assert "tfidf" in specs and specs["tfidf"]["state"] == "ready"
    assert specs["tfidf"]["default"] is True


def test_answer_returns_cited_claims(client):
    r = client.post("/api/answer", json={"question": "purify the People of the House", "k": 3})
    assert r.status_code == 200
    body = r.json()
    a = body["answer"]
    assert a["question"] == "purify the People of the House"
    assert a["claims"], "expected at least one cited claim"
    # every claim carries a citation (no citation = not a fact)
    for c in a["claims"]:
        assert c["citations"], "a claim was returned with no citation"
    assert "markdown" in body and body["markdown"]


def test_answer_requires_question(client):
    r = client.post("/api/answer", json={"question": "   "})
    assert r.status_code == 400
    assert r.json()["error"]


def test_answer_k_is_clamped(client):
    # absurd k must not blow up; it is clamped into range
    r = client.post("/api/answer", json={"question": "intellect", "k": 9999})
    assert r.status_code == 200
    assert len(r.json()["answer"]["claims"]) <= 25


def test_unrelated_question_yields_no_evidence(client):
    r = client.post("/api/answer", json={"question": "quantum chromodynamics lattice gauge"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["claims"] == []
    assert body["answer"]["caveats"]


def test_lecture_returns_full_framework(client):
    r = client.post("/api/lecture", json={"topic": "purification of the People of the House", "depth": 2})
    assert r.status_code == 200
    body = r.json()
    titles = [s["title"] for s in body["sections"]]
    assert "Qur'anic Foundations" in titles
    assert "Reflection Points" in titles
    assert len(titles) == 12  # 11-section framework + Suggested Reading
    # evidence blocks, where present, carry a reference string
    for s in body["sections"]:
        for ev in s["evidence"]:
            assert ev["reference"]


def test_lecture_evidence_carries_full_citation_for_drawer(client):
    # the drawer needs the full citation (grade, arabic, locators), not just a ref
    r = client.post("/api/lecture", json={"topic": "intellect worship paradise", "depth": 3})
    hadith = [ev for s in r.json()["sections"] for ev in s["evidence"]
              if ev["evidence_type"] == "hadith"]
    assert hadith, "expected a hadith evidence block"
    cit = hadith[0]["citation"]
    assert cit["source_id"] and "grade" in cit           # full citation present
    assert hadith[0]["citation"]["grade"] == "sahih"     # sample al-kafi doc is graded sahih


def test_answer_claims_expose_grade_for_drawer(client):
    r = client.post("/api/answer", json={"question": "intellect worship paradise", "k": 3})
    hadith = [c for c in r.json()["answer"]["claims"] if c["evidence_type"] == "hadith"]
    assert hadith
    cit = hadith[0]["citations"][0]
    assert cit["grade"] == "sahih" and cit.get("grade_source")


def test_lecture_requires_topic(client):
    r = client.post("/api/lecture", json={"topic": ""})
    assert r.status_code == 400
    assert r.json()["error"]


def test_answer_payload_carries_markdown_and_embedder(client):
    r = client.post("/api/answer", json={"question": "intellect", "k": 2})
    body = r.json()
    assert body["markdown"].lstrip().startswith("## ")
    assert body["embedder"] == "tfidf"


def test_unknown_embedder_is_rejected_gracefully(client):
    # an embedder that isn't enabled must 503 with a helpful message, not crash
    r = client.post("/api/answer", json={"question": "intellect", "embedder": "st:BAAI/bge-m3"})
    assert r.status_code == 503
    assert "not available" in r.json()["error"]


def test_sources_facets_listed(client):
    r = client.get("/api/sources")
    assert r.status_code == 200
    body = r.json()
    src_ids = {s["id"] for s in body["sources"]}
    assert {"quran", "al-kafi"} <= src_ids
    # counts + evidence-type facets are present
    assert all(s["count"] >= 1 for s in body["sources"])
    types = {t["type"] for t in body["evidence_types"]}
    assert {"quran", "hadith"} <= types


def test_answer_filtered_by_evidence_type(client):
    # restrict to hadith only -> the sole hadith doc, no Qur'an verses
    r = client.post("/api/answer", json={
        "question": "intellect worship paradise", "k": 5, "evidence_types": ["hadith"],
    })
    assert r.status_code == 200
    claims = r.json()["answer"]["claims"]
    assert claims and all(c["evidence_type"] == "hadith" for c in claims)


def test_answer_filtered_by_source(client):
    # restrict to al-kafi -> nothing from the quran source
    r = client.post("/api/answer", json={
        "question": "intellect", "k": 5, "source_ids": ["al-kafi"],
    })
    assert r.status_code == 200
    for c in r.json()["answer"]["claims"]:
        assert all(cit["source_id"] == "al-kafi" for cit in c["citations"])


def test_min_confidence_floor_excludes_weaker_sources():
    # a corpus with one HIGH and one LOW passage on the same topic
    from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType

    def doc(sid, conf):
        return Document(
            id=f"{sid}-x", text="the mercy and compassion of the Merciful Lord",
            evidence_type=EvidenceType.HADITH,
            citation=Citation(source_id=sid, evidence_type=EvidenceType.HADITH,
                              volume="1", hadith_number="1"),
            confidence=conf, language="en",
        )
    docs = [doc("al-kafi", ConfidenceLevel.HIGH), doc("weak-book", ConfidenceLevel.LOW)]
    stack = web.Stack(docs, web.AppConfig(), known={"al-kafi", "weak-book"})
    stack.engine("tfidf")
    client = TestClient(web.create_app(stack=stack))

    lo = client.post("/api/answer", json={"question": "mercy compassion", "min_confidence": "low"})
    hi = client.post("/api/answer", json={"question": "mercy compassion", "min_confidence": "high"})
    lo_sources = {c["citations"][0]["source_id"] for c in lo.json()["answer"]["claims"]}
    hi_sources = {c["citations"][0]["source_id"] for c in hi.json()["answer"]["claims"]}
    assert "weak-book" in lo_sources          # LOW floor keeps it
    assert "weak-book" not in hi_sources      # HIGH floor drops it
    assert "al-kafi" in hi_sources            # HIGH source survives


def test_conflicting_filters_yield_filter_aware_caveat(client):
    # al-kafi has no Qur'an docs -> empty result, and the caveat names the filters
    r = client.post("/api/answer", json={
        "question": "guardian", "source_ids": ["al-kafi"], "evidence_types": ["quran"],
    })
    assert r.status_code == 200
    body = r.json()["answer"]
    assert body["claims"] == []
    assert any("filter" in c.lower() for c in body["caveats"])


def test_lecture_filtered_by_source(client):
    r = client.post("/api/lecture", json={
        "topic": "intellect", "depth": 2, "source_ids": ["al-kafi"],
    })
    assert r.status_code == 200
    for s in r.json()["sections"]:
        for ev in s["evidence"]:
            assert "al-kafi" in ev["reference"]


def test_second_embedder_listed_and_builds_lazily():
    # offer tfidf + hashing; hashing is 'lazy' until first queried, then 'ready'
    app = web.create_app(stack=_sample_stack(embedders=("tfidf", "hashing")))
    client = TestClient(app)
    specs = {e["spec"]: e for e in client.get("/api/status").json()["embedders"]}
    assert specs["hashing"]["state"] == "lazy"

    r = client.post("/api/answer", json={"question": "intellect", "embedder": "hashing"})
    assert r.status_code == 200
    assert r.json()["embedder"] == "hashing"

    specs = {e["spec"]: e for e in client.get("/api/status").json()["embedders"]}
    assert specs["hashing"]["state"] == "ready"
