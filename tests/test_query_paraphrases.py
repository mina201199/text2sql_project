"""Independent paraphrases, with answers hand-checked against source-backed SQLite."""

from pathlib import Path

import pytest

from ingest.build_db import build_database
from serving.runtime import ServiceRuntime, build_runtime
from text2sql.aliases import resolve_peak_column
from text2sql.entities import DateRange, extract_entities

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def runtime(tmp_path_factory: pytest.TempPathFactory) -> ServiceRuntime:
    database = tmp_path_factory.mktemp("paraphrases") / "power.db"
    build_database(database, root=ROOT)
    return build_runtime(database=database, root=ROOT, mode="offline")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("2026/07台中#2非零出力幾天", [[31]]),
        ("2026-07台中#2非零出力幾天", [[31]]),
        ("20260709台中第2號機尖峰出力多少", [["2026-07-09", 28.4]]),
        ("2026年7月9號台中第２號機的尖峰出力", [["2026-07-09", 28.4]]),
        (
            "2026年7月9日出力前2名有哪些",
            [["太陽能發電", 844.2], ["大潭 (#1-#9)", 659.0]],
        ),
        (
            "２０２６年７月９日出力最高的２名有哪些",
            [["太陽能發電", 844.2], ["大潭 (#1-#9)", 659.0]],
        ),
        (
            "2026年7月9日非零出力由低到高排前兩名",
            [["水里", 0.7], ["碧海", 1.1]],
        ),
        ("2026年7月台中#2有發電幾天", [[31]]),
        ("2026年前七個月台中#2零輸出幾天", [[30]]),
    ],
)
def test_new_paraphrases_have_exact_guarded_offline_results(
    runtime: ServiceRuntime, question: str, expected: list[list[object]]
) -> None:
    assert question not in {item["question"] for item in runtime.pipeline.corpus["examples"]}
    response = runtime.pipeline.query(question)

    assert response.success, response.to_dict()
    assert response.data is not None
    assert response.data["source"] == "router"
    assert response.data["rows"] == expected
    stages = {step["stage"] for step in response.data["trace"]}
    assert {"semantic_question_guard", "sql_guard", "semantic_sql_guard"} <= stages
    assert "generate" not in stages


@pytest.mark.parametrize("separator", ["/", "-"])
def test_numeric_month_keeps_its_bounds_without_becoming_a_day(separator: str) -> None:
    entities = extract_entities(f"2026{separator}07台中#2非零出力幾天")
    assert entities.date_range == DateRange("2026-07-01", "2026-07-31")
    assert entities.explicit_date is None


@pytest.mark.parametrize("question", ["興達第3號機", "興達第３號機", "興達第三號機"])
def test_numbered_alias_does_not_resolve_ambiguous_hsinta(question: str) -> None:
    result = resolve_peak_column(question, {"興達#3", "興達 (#1-#5)"})
    assert result.ambiguous
    assert result.value is None
    assert set(result.candidates) == {"興達#3", "興達 (#1-#5)"}


@pytest.mark.parametrize(
    ("question", "code"),
    [
        ("今年台中第２號機每天尖峰出力加起來的發電量", "PEAK_SUM_ACROSS_DAYS"),
        ("今年台中#2每天尖峰出力的總和", "PEAK_SUM_ACROSS_DAYS"),
        ("2026年7月9號興達第３號機尖峰出力", "AMBIGUOUS_UNIT_NAME"),
        ("2028/07台中#2非零出力幾天", "DATA_RANGE_OUT_OF_BOUNDS"),
        ("2026年7月台中#2總發電量多少度？", "PEAK_SUM_ACROSS_DAYS"),
        ("2026/07台中第２號機發電量是多少", "PEAK_SUM_ACROSS_DAYS"),
    ],
)
def test_paraphrases_preserve_semantic_refusals(
    runtime: ServiceRuntime, question: str, code: str
) -> None:
    response = runtime.pipeline.query(question)
    assert not response.success
    assert response.error_code == code


@pytest.mark.parametrize("negative", ["沒有出力", "沒有發電", "沒發電"])
def test_positive_day_paraphrase_does_not_change_negative_day_count(
    runtime: ServiceRuntime, negative: str
) -> None:
    response = runtime.pipeline.query(f"2026年7月台中#2{negative}幾天")
    assert response.success
    assert response.data is not None
    assert response.data["rows"] == [[0]]


@pytest.mark.parametrize(
    "question",
    [
        "2026年7月備轉容量率每月平均",
        "2026年7月台中#2非零出力幾天",
        "2025年火力發電成本是多少",
        "2026年7月每天各機組的尖峰出力",
        "2026年7月各機組同一天的尖峰出力合計",
    ],
)
def test_explicit_period_guard_keeps_supported_metrics(
    runtime: ServiceRuntime, question: str
) -> None:
    decision = runtime.pipeline.semantic_guard.check_question(question, extract_entities(question))
    assert decision.severity == "pass"
