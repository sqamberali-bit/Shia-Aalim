import pytest

from conftest import DATA, sample_corpus

from shia_aalim.research_loop import build_index
from shia_aalim.sources import load_registry_ids
from shia_aalim.generation.answer import AnswerGenerator
from shia_aalim.generation.lecture import LectureGenerator
from shia_aalim import web

# The web layer is an optional extra; skip cleanly where FastAPI isn't installed.
TestClient = pytest.importorskip("fastapi.testclient").TestClient

REGISTRY = DATA / "sources" / "registry.yaml"


def _sample_stack() -> web.Stack:
    """Build a Stack over the tiny in-memory sample corpus (no disk load)."""
    docs = sample_corpus()
    retriever = build_index(docs)
    known = load_registry_ids(REGISTRY)
    return web.Stack(
        answers=AnswerGenerator(retriever, known_source_ids=known),
        lectures=LectureGenerator(retriever),
        n_documents=len(docs),
        config=web.AppConfig(),
    )


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
    assert body["embedder"] == "tfidf"


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


def test_lecture_requires_topic(client):
    r = client.post("/api/lecture", json={"topic": ""})
    assert r.status_code == 400
    assert r.json()["error"]
