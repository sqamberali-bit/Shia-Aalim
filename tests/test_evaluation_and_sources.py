from conftest import DATA, sample_corpus

from shia_aalim.evaluation.metrics import GoldQuery, evaluate, retrieval_precision_recall
from shia_aalim.models import ConfidenceLevel, EvidenceType
from shia_aalim.research_loop import LoopConfig, build_index, run_loop
from shia_aalim.sources import load_registry_ids, load_sources


def test_registry_loads_expected_sources():
    sources = load_sources(DATA / "sources" / "registry.yaml")
    ids = {s.id for s in sources}
    for expected in ["quran", "al-kafi", "al-mizan", "nahj-al-balagha", "bihar-al-anwar"]:
        assert expected in ids
    kulayni = next(s for s in sources if s.id == "al-kafi")
    assert kulayni.kind is EvidenceType.HADITH
    assert kulayni.confidence is ConfidenceLevel.HIGH


def test_precision_recall_basic():
    p, r = retrieval_precision_recall(["a", "b", "c"], {"a", "c"}, k=3)
    assert abs(p - 2 / 3) < 1e-9
    assert abs(r - 1.0) < 1e-9


def test_evaluate_over_gold_set():
    docs = sample_corpus()
    retriever = build_index(docs)
    known = load_registry_ids(DATA / "sources" / "registry.yaml")
    gold = [
        GoldQuery("purification of the People of the House", {"quran-33-33"}),
        GoldQuery("love for the near relatives kinship", {"quran-42-23"}),
    ]
    summary = evaluate(gold, retriever, docs, known, k=5)
    assert summary.n_queries == 2
    assert summary.recall_at_k > 0.0
    assert summary.citation_accuracy > 0.0
    assert 0.0 <= summary.source_coverage <= 1.0


def test_research_loop_runs_and_recommends(tmp_path):
    log = tmp_path / "iters.jsonl"
    config = LoopConfig(
        knowledge_dir=DATA / "knowledge",
        registry_source_ids=load_registry_ids(DATA / "sources" / "registry.yaml"),
        gold=[GoldQuery("purification of the People of the House", {"quran-33-33"})],
        log_path=log,
    )
    reports = run_loop(config, iterations=2)
    assert len(reports) == 2
    assert reports[0].recommendations
    assert reports[1].deltas != {}
    assert log.exists() and log.read_text().count("\n") == 2
