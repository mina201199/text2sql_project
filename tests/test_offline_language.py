"""以固定快照答案驗證別名、正負條件與守門行為。"""

import json
from pathlib import Path

import pytest

from eval.run_eval import run_evaluation
from ingest.build_db import build_database
from serving.runtime import build_runtime
from text2sql.aliases import resolve_peak_column, resolve_plant
from text2sql.entities import extract_entities

ROOT = Path(__file__).parents[1]
CASES = json.loads(
    (ROOT / "tests/fixtures/offline_language_cases.json").read_text(encoding="utf-8")
)["cases"]


@pytest.fixture(scope="module")
def languageRuntime(tmp_path_factory):
    database = tmp_path_factory.mktemp("offline-language") / "power.db"
    build_database(database, root=ROOT)
    return build_runtime(database=database, root=ROOT, mode="offline")


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_offline_answers_match_independent_snapshot(languageRuntime, case):
    response = languageRuntime.pipeline.query(case["question"])
    if "error_code" in case:
        assert not response.success, response.to_dict()
        assert response.error_code == case["error_code"]
        return
    assert response.success, response.to_dict()
    assert response.data["source"] == "router"
    assert response.data["rows"] == case["rows"]
    assert response.data["columns"] == case["columns"]
    stages = {step["stage"] for step in response.data["trace"]}
    assert {"semantic_question_guard", "sql_guard", "semantic_sql_guard"} <= stages
    assert "generate" not in stages
    columns, rows = languageRuntime.pipeline.run_sql(case["reference_sql"], tuple(case["params"]))
    assert columns == case["columns"]
    assert [list(row) for row in rows] == case["rows"]


@pytest.mark.parametrize("question", ["台中#100", "中火第100號機", "臺中十一號機"])
def test_unknown_unit_does_not_match_a_number_prefix(question):
    result = resolve_peak_column(question, {"台中#1", "台中#10", "台中#2"})
    assert result.value is None


@pytest.mark.parametrize("question", ["中火設備", "臺中電廠設備", "臺中發電廠機組"])
def test_plant_alias_resolves_against_available_plants(question):
    assert resolve_plant(question, {"台中發電廠", "林口發電廠"}).value == "台中發電廠"
    assert resolve_plant(question, {"林口發電廠"}).value is None


def test_answer_pack_stays_separate_from_retrieval_and_existing_evaluations():
    existing = json.loads((ROOT / "corpus/training_corpus.json").read_text(encoding="utf-8"))[
        "examples"
    ]
    for name in ("golden_questions", "eval_questions", "trap_questions", "attack_questions"):
        existing += json.loads((ROOT / f"benchmarks/{name}.json").read_text(encoding="utf-8"))
    assert not ({case["question"] for case in CASES} & {item.get("question") for item in existing})


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("請查２０２６／０７／２１林口三號機尖峰出力", [["2026-07-21", 0.0]]),
        ("2026年6月15日中火第４號機尖峰出力", [["2026-06-15", 41.8]]),
        ("2026年五月二日林口電廠二號機的功率", [["2026-05-02", 76.2]]),
        ("2026年7月9日大林二機出力", [["2026-07-09", 75.9]]),
        ("2026年7月臺中發電廠第十號機出力不為0有幾天", [[31]]),
        ("2026年7月林口三號機有出力的日期數", [[26]]),
        ("2026年7月林口第３號機出力等於０共幾日", [[5]]),
        ("2026年7月9日興達燃煤三號機的功率", [["2026-07-09", 0.0]]),
    ],
)
def test_unseen_wordings_and_dates(languageRuntime, question, expected):
    response = languageRuntime.pipeline.query(question)
    assert response.success, response.to_dict()
    assert response.data["source"] == "router"
    assert response.data["rows"] == expected


@pytest.mark.parametrize("question", ["興達4號機2025年最高出力", "台中一號機2025年最高出力"])
def test_unit_before_year_preserves_number_boundary(languageRuntime, question):
    response = languageRuntime.pipeline.query(question)
    assert response.success, response.to_dict()
    assert response.data["params"] == [
        "興達#4" if question.startswith("興達") else "台中#1",
        "2025-01-01",
        "2025-12-31",
    ]


def test_year_after_plant_is_not_a_unit_number(languageRuntime):
    question = "大潭2025年最高出力"
    decision = languageRuntime.pipeline.semantic_guard.check_question(
        question, extract_entities(question)
    )
    assert decision.code == "OK"


@pytest.mark.parametrize("phrase", ["沒有出力", "出力等於0"])
def test_zero_ranking_never_returns_positive_power(languageRuntime, phrase):
    response = languageRuntime.pipeline.query(f"2026年7月9日{phrase}的機組由大到小")
    assert response.success, response.to_dict()
    assert response.data["rows"]
    assert all(row[1] == 0 for row in response.data["rows"])


@pytest.mark.parametrize(
    "question", ["台中#1 2025年最高出力", "台中一 2025年最高出力", "台中#1　２０２５年最高出力"]
)
def test_whitespace_separates_unit_number_from_year(languageRuntime, question):
    response = languageRuntime.pipeline.query(question)
    assert response.success, response.to_dict()
    assert response.data["rows"] == [[51.7]]
    assert response.data["params"] == ["台中#1", "2025-01-01", "2025-12-31"]


def test_existing_offline_benchmark_keeps_full_accuracy(languageRuntime):
    report = run_evaluation(
        database=languageRuntime.database,
        benchmark_dir=ROOT / "benchmarks",
        corpus_path=ROOT / "corpus/training_corpus.json",
    )
    assert report["execution"]["accuracy"] == 1.0, report["failures"]
    assert report["intent"]["golden"]["accuracy"] == 1.0
    assert report["safety"]["semantic_traps"]["accuracy"] == 1.0
    assert report["safety"]["semantic_false_positives"]["rate"] == 0
