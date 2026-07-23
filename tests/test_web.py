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


def test_index_ships_all_client_features(client):
    # cheap regression guard for the browser-only wiring (no JS engine in tests)
    html = client.get("/").text
    for needle in (
        'data-tab="compare"', 'data-tab="history"',   # tabs
        'id="drawer"', 'openDrawer(',                 # citation drawer
        'function compare(', 'renderCompare(',        # compare view
        'pushHistory(', 'restoreHistory(',            # session history
        'copyMd(', 'downloadMd(',                     # markdown export
        'loadCrossref(', 'crossrefSections(',         # cross-references
        'lookupNarrator(', 'loadRijalSummary(',       # rijāl / narrators
        'data-tab="rijal"',
    ):
        assert needle in html, f"missing UI wiring: {needle}"
    # the window.history-shadowing bug must not regress
    assert "var history" not in html


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


def test_answer_language_recorded_via_api(client):
    r = client.post("/api/answer", json={"question": "intellect", "k": 2, "answer_language": "ur"})
    assert r.status_code == 200
    assert r.json()["answer"]["answer_language"] == "ur"


def test_status_reports_ai_features(client):
    # the default test stack has no LLM providers -> all AI features off, no crash
    ai = client.get("/api/status").json()["ai"]
    assert ai == {"synthesis": False, "refine": False, "translate": False}


def test_answer_reports_query_language_and_crosslingual_caveat(client):
    en = client.post("/api/answer", json={"question": "intellect", "k": 2}).json()
    assert en["answer"]["query_language"] == "en"
    # a Persian query on the lexical index is labelled and honestly caveated
    fa = client.post("/api/answer", json={"question": "توحید چیست", "k": 2}).json()
    assert fa["answer"]["query_language"] == "fa"
    assert any("multilingual semantic embedder" in c for c in fa["answer"]["caveats"])


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


def test_compare_returns_one_column_per_book(client):
    r = client.post("/api/compare", json={
        "question": "guardian and intellect", "sources": ["quran", "al-kafi"], "k": 3,
    })
    assert r.status_code == 200
    body = r.json()
    cols = {c["source_id"]: c for c in body["columns"]}
    assert set(cols) == {"quran", "al-kafi"}
    # each column answers only on its own book's evidence
    for sid, col in cols.items():
        for claim in col["answer"]["claims"]:
            assert all(cit["source_id"] == sid for cit in claim["citations"])
    assert body["truncated"] is False


def test_compare_requires_a_source(client):
    r = client.post("/api/compare", json={"question": "justice", "sources": []})
    assert r.status_code == 400
    assert r.json()["error"]


def test_compare_requires_a_question(client):
    r = client.post("/api/compare", json={"question": "  ", "sources": ["quran"]})
    assert r.status_code == 400


def test_compare_caps_fan_out(client):
    many = ["quran", "al-kafi", "al-mizan", "nahj-al-balagha", "a", "b", "c", "d"]
    r = client.post("/api/compare", json={"question": "mercy", "sources": many, "k": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["columns"]) == 6  # MAX_COMPARE_SOURCES
    assert body["truncated"] is True


def _crossref_stack():
    from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType

    def d(id, text, et, **cit):
        return Document(id=id, text=text, evidence_type=et,
                        citation=Citation(source_id=cit.pop("source_id"), evidence_type=et, **cit),
                        confidence=ConfidenceLevel.HIGH, language="en")
    docs = [
        d("v-5-55", "Your guardian is only Allah His Apostle and the faithful who maintain "
                    "the prayer and give the zakat while bowing down", EvidenceType.QURAN,
          source_id="quran", surah=5, ayah=55),
        d("t-guardian", "The guardian is only Allah and His Apostle and the faithful who "
                        "maintain the prayer and give the zakat while bowing; the wilayah of Ali",
          EvidenceType.TAFSIR, source_id="al-mizan", volume="6", chapter="c"),
        d("h-ref", "The Imam said regarding the verse of wilayah 5:55 the faithful who gives "
                   "zakat while bowing is Ali", EvidenceType.HADITH,
          source_id="al-kafi", volume="1", hadith_number="1"),
    ]
    stack = web.Stack(docs, web.AppConfig(), known={"quran", "al-mizan", "al-kafi"})
    stack.engine("tfidf")
    return stack


def test_crossref_links_verse_to_tafsir_and_hadith():
    client = TestClient(web.create_app(stack=_crossref_stack()))
    r = client.post("/api/crossref", json={"surah": 5, "ayah": 55})
    assert r.status_code == 200
    body = r.json()
    assert body["verse"]["reference"] == "Qur'an 5:55"
    assert {i["citation"]["source_id"] for i in body["tafsir"]} == {"al-mizan"}
    assert {i["citation"]["source_id"] for i in body["hadith"]} == {"al-kafi"}
    # the narration that cites "5:55" is labelled explicit
    assert body["hadith"][0]["link_type"] == "explicit"


def test_crossref_unknown_verse_404(client):
    r = client.post("/api/crossref", json={"surah": 114, "ayah": 1})
    assert r.status_code == 404
    assert "not in the loaded corpus" in r.json()["error"]


def test_crossref_requires_surah_and_ayah(client):
    r = client.post("/api/crossref", json={"surah": 5})
    assert r.status_code == 400


def _rijal_stack():
    from shia_aalim.models import Citation, ConfidenceLevel, Document, EvidenceType, HadithGrade

    hadith = Document(
        id="k-1",
        text=("Ali Bin Ibrahim narrated to me, from his father, from Yunus Bin Abdul Rahman, "
              "from Ali Bin Mansour who said, 'Abu Abdullah said the intellect is a proof.'"),
        evidence_type=EvidenceType.HADITH,
        citation=Citation(
            source_id="al-kafi", evidence_type=EvidenceType.HADITH, volume="1", hadith_number="1",
            grade=HadithGrade.MAJHUL,
            grade_source="Allamah Baqir al-Majlisi: مجهول - Mir‘at al ‘Uqul; Shaykh Baqir al-Behbudi: ضعيف - Sahih al-Kafi",
        ),
        confidence=ConfidenceLevel.MEDIUM, language="en",
    )
    stack = web.Stack([hadith], web.AppConfig(), known={"al-kafi"})
    stack.engine("tfidf")
    return stack


def test_rijal_summary_reports_grades_and_narrators():
    client = TestClient(web.create_app(stack=_rijal_stack()))
    s = client.get("/api/rijal/summary").json()
    assert s["hadith"] == 1
    assert s["grades"].get("majhul") == 1
    assert any("Majlisi" in a["attributor"] for a in s["attributors"])
    names = {n["name"] for n in s["top_narrators"]}
    assert any("Yunus" in n for n in names)


def test_rijal_narrator_lookup_returns_chain_and_gradings():
    client = TestClient(web.create_app(stack=_rijal_stack()))
    body = client.post("/api/rijal/narrator", json={"name": "Yunus Bin Abdul Rahman"}).json()
    assert body["narration_count"] == 1
    n = body["narrations"][0]
    assert n["evidence_type"] == "hadith"
    assert "Yunus Bin Abdul Rahman" in n["chain"]
    # attributed gradings surfaced (never derived) — two attributors parsed
    assert [a["attributor"] for a in n["attributions"]] == \
        ["Allamah Baqir al-Majlisi", "Shaykh Baqir al-Behbudi"]


def test_rijal_narrator_requires_name():
    client = TestClient(web.create_app(stack=_rijal_stack()))
    r = client.post("/api/rijal/narrator", json={"name": "  "})
    assert r.status_code == 400


def test_rijal_unknown_narrator_is_empty_not_error():
    client = TestClient(web.create_app(stack=_rijal_stack()))
    r = client.post("/api/rijal/narrator", json={"name": "Zzz Nobody"})
    assert r.status_code == 200
    assert r.json()["narration_count"] == 0


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
