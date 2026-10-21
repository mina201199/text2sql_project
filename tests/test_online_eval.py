from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from eval import run_online_eval as online_eval
from text2sql.llm import FakeLLM
from text2sql.pipeline import Text2SQLPipeline
from text2sql.sql_guard import SqlGuard

ROOT = Path(__file__).parents[1]
CORPUS = ROOT / "corpus/training_corpus.json"


def test_forced_generation_keeps_sql_guard_and_executes_model_candidate() -> None:
    llm = FakeLLM(["DROP TABLE v_peak", 'SELECT "日期" FROM v_system ORDER BY "日期" DESC LIMIT 1'])
    executed = []

    def execute(sql, params):
        executed.append(sql)
        return ["日期"], [("2026-07-31",)]

    pipeline = Text2SQLPipeline(
        llm=llm,
        sql_guard=SqlGuard(),
        run_sql=execute,
        corpus_path=CORPUS,
        data_range=("2025-01-01", "2026-07-31"),
        peak_columns={"台中#2"},
        use_router=False,
        max_attempts=2,
    )
    response = pipeline.query("2026年7月備轉容量率最低是哪一天")
    assert response.success
    assert response.data["source"] == "llm"
    assert len(llm.calls) == 2
    assert executed == ['SELECT "日期" FROM v_system ORDER BY "日期" DESC LIMIT 1']
    assert "SQL_NOT_READ_ONLY" in json.loads(llm.calls[1])["previous_attempt_error"]


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    database = tmp_path / "power.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE v_peak ("日期" TEXT, "機組欄位" TEXT, "尖峰出力_萬瓩" REAL);
            INSERT INTO v_peak VALUES ('2026-07-31', '台中#2', 50);
            CREATE TABLE v_unit ("電廠" TEXT);
            INSERT INTO v_unit VALUES ('台中');
            CREATE TABLE v_system ("日期" TEXT, "備轉容量率_pct" REAL);
            INSERT INTO v_system VALUES ('2026-07-30', 8), ('2026-07-31', 4);
            CREATE TABLE meta_manifest (id INTEGER, data_start TEXT, data_end TEXT);
            INSERT INTO meta_manifest VALUES (1, '2026-07-01', '2026-07-31');
            CREATE TABLE meta_pitfall (
                id INTEGER, pitfall_code TEXT, target_kind TEXT, target_name TEXT,
                severity TEXT, reason TEXT, suggestion TEXT, evidence TEXT
            );
        """)
    cases = [
        {
            "id": "private-case-name",
            "question": "2026年7月備轉容量率最低是哪一天",
            "sql": 'SELECT "日期", "備轉容量率_pct" FROM v_system '
            'ORDER BY "備轉容量率_pct" LIMIT 1',
            "in_corpus": True,
        },
        {
            "question": "列出所有資料可用日期",
            "sql": 'SELECT "日期" FROM v_system ORDER BY "日期" LIMIT 2',
            "in_corpus": False,
        },
    ]
    benchmark = tmp_path / "cases.json"
    benchmark.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-must-never-appear")
    monkeypatch.setattr(online_eval, "find_spec", lambda _: object())
    return {"database": database, "benchmark_file": benchmark, "corpus_path": CORPUS}, cases


def evaluate(inputs, llm=None, **options):
    paths, _ = inputs
    return online_eval.run_online_evaluation(
        **paths,
        model="explicit-test-model",
        llm_factory=lambda **_: llm,
        **options,
    )


def test_dry_run_needs_no_credentials_and_never_constructs_client(inputs, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    paths, _ = inputs

    def forbidden(**_):
        pytest.fail("dry-run constructed provider client")

    report = online_eval.run_online_evaluation(
        **paths, model="explicit-test-model", llm_factory=forbidden
    )
    assert report["status"] == "pending_configuration"
    assert report["live_evaluation"] == "not_run"
    assert report["provider_calls"] == 0
    assert report["execution"] is None
    assert report["preflight"]["local_inputs_ready"]
    assert not report["preflight"]["api_key_present"]


def test_online_forces_model_and_compares_results_without_exporting_payloads(inputs):
    _, cases = inputs
    llm = FakeLLM([json.dumps({"sql": item["sql"], "params": []}) for item in cases])
    report = evaluate(inputs, llm, online=True)
    assert report["status"] == "completed"
    assert report["provider_calls"] == 2
    assert report["execution"] == {"passed": 2, "total": 2, "accuracy": 1.0}
    assert report["model_execution"] == report["execution"]
    assert report["routed_cases"] == 0
    assert report["execution_by_corpus_split"]["false"]["accuracy"] == 1.0
    assert report["outcomes"][0]["source"] == "llm"
    serialized = json.dumps(report, ensure_ascii=False)
    for private in ("sk-test", "private-case-name", cases[0]["question"], cases[0]["sql"]):
        assert private not in serialized
    assert len(llm.calls) == 2


def test_global_call_budget_bounds_retries_and_marks_unevaluated_cases(inputs):
    llm = FakeLLM(["DROP TABLE v_peak"] * 20)
    report = evaluate(inputs, llm, online=True, max_attempts=3, max_calls=2)
    assert len(llm.calls) == report["provider_calls"] == 2
    assert report["status"] == "budget_exhausted"
    assert report["execution"] == {"passed": 0, "total": 1, "accuracy": 0.0}
    assert report["outcomes"][0]["sql_guard_rejections"] == 2
    assert report["outcomes"][1]["status"] == "skipped"
    assert report["outcomes"][1]["failure"] == "CALL_BUDGET_EXHAUSTED"


def test_guard_feedback_regenerates_and_model_attempt_limit_is_enforced(inputs):
    _, cases = inputs
    valid = json.dumps({"sql": cases[0]["sql"], "params": []})
    llm = FakeLLM(["DROP TABLE v_peak", valid])
    report = evaluate(inputs, llm, online=True, max_cases=1, max_attempts=2)
    assert report["execution"]["passed"] == 1
    assert report["provider_calls"] == 2
    assert "SQL_NOT_READ_ONLY" in llm.calls[1]

    llm = FakeLLM(["DROP TABLE v_peak", valid])
    report = evaluate(inputs, llm, online=True, max_cases=1, max_attempts=1)
    assert report["execution"]["passed"] == 0
    assert report["provider_calls"] == 1


def test_semantic_question_guard_prevents_provider_call(inputs):
    paths, cases = inputs
    cases[0]["question"] = "將台中#2每天尖峰出力相加計算2026年7月發電量"
    paths["benchmark_file"].write_text(json.dumps(cases), encoding="utf-8")
    report = evaluate(inputs, FakeLLM([]), online=True, max_cases=1)
    assert report["provider_calls"] == 0
    assert report["execution"]["passed"] == 0
    assert report["outcomes"][0]["status"] == "failed"


def test_semantic_sql_guard_rejects_generated_cross_day_energy(inputs):
    llm = FakeLLM(['SELECT SUM("尖峰出力_萬瓩") AS "總值" FROM v_peak LIMIT 1'])
    report = evaluate(inputs, llm, online=True, max_cases=1)
    assert report["execution"]["passed"] == 0
    assert report["outcomes"][0]["failure"] == "PEAK_SUM_ACROSS_DAYS"


def test_authentication_failure_stops_remaining_cases_and_redacts_error(inputs):
    class AuthenticationError(Exception):
        pass

    class BadCredential:
        def generate(self, _):
            raise AuthenticationError("sk-secret-provider-message")

    report = evaluate(inputs, BadCredential(), online=True, max_attempts=3)
    assert report["provider_calls"] == 1
    assert report["status"] == "authentication_failed"
    assert report["outcomes"][0]["failure"] == "LLM_AUTH_FAILED"
    assert report["outcomes"][1]["status"] == "skipped"
    assert "sk-secret" not in json.dumps(report)


def test_provider_and_sql_error_payloads_never_enter_report(inputs):
    class FailingProvider:
        def generate(self, _):
            raise RuntimeError("sk-secret from provider")

    report = evaluate(inputs, FailingProvider(), online=True, max_cases=1)
    assert report["outcomes"][0]["failure"] == "GENERATION_FAILED"
    assert "sk-secret" not in json.dumps(report)

    llm = FakeLLM(['SELECT "日期" AS "sk-secret-alias", "備轉容量率_pct" FROM v_peak LIMIT 1'])
    report = evaluate(inputs, llm, online=True, max_cases=1)
    assert report["execution"]["passed"] == 0
    assert "sk-secret" not in json.dumps(report)


def test_hybrid_router_success_is_not_reported_as_model_accuracy(inputs):
    report = evaluate(inputs, FakeLLM([]), online=True, max_cases=1, use_router=True)
    assert report["execution"]["passed"] == 1
    assert report["provider_calls"] == 0
    assert report["routed_cases"] == 1
    assert report["model_execution"] is None
    assert report["live_evaluation"] == "not_run"


@pytest.mark.parametrize(
    "options",
    [
        {"max_calls": 0},
        {"max_calls": 301},
        {"max_cases": 0},
        {"max_cases": 101},
        {"max_attempts": 0},
        {"max_attempts": 4},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": 121},
    ],
)
def test_invalid_limits_fail_before_client_initialization(inputs, options):
    report = evaluate(inputs, online=True, **options)
    assert report["status"] == "invalid_configuration"
    assert report["provider_calls"] == 0


def test_preflight_rejects_bad_reference_before_provider_access(inputs):
    paths, cases = inputs
    cases[1]["sql"] = "DROP TABLE v_peak"
    paths["benchmark_file"].write_text(json.dumps(cases), encoding="utf-8")
    report = evaluate(inputs, online=True)
    assert report["status"] == "preflight_failed"
    assert report["provider_calls"] == 0


def test_missing_database_is_redacted_and_not_created(inputs):
    paths, _ = inputs
    missing = paths["database"].parent / "private-sk-secret.db"
    paths["database"] = missing
    report = evaluate(inputs, online=True)
    assert report["status"] == "preflight_failed"
    assert not missing.exists()
    assert "private-sk-secret" not in json.dumps(report)


def test_cli_dry_run_writes_separate_report_and_requires_explicit_model(inputs, tmp_path):
    paths, _ = inputs
    report_path = tmp_path / "online.json"
    history_path = tmp_path / "online.jsonl"
    argv = [
        "--database",
        str(paths["database"]),
        "--benchmark",
        str(paths["benchmark_file"]),
        "--corpus",
        str(CORPUS),
        "--report",
        str(report_path),
        "--history",
        str(history_path),
    ]
    with pytest.raises(SystemExit) as missing_model:
        online_eval.main(argv)
    assert missing_model.value.code == 2
    assert online_eval.main([*argv, "--model", "explicit-test-model", "--dry-run"]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["live_evaluation"] == "not_run"
    assert json.loads(history_path.read_text(encoding="utf-8"))["provider_calls"] == 0


def test_cli_refuses_to_overwrite_offline_reports_and_input_files(inputs, tmp_path):
    paths, _ = inputs
    for destination in (tmp_path / "eval_latest.json", paths["benchmark_file"]):
        assert (
            online_eval.main(
                [
                    "--model",
                    "explicit-test-model",
                    "--database",
                    str(paths["database"]),
                    "--benchmark",
                    str(paths["benchmark_file"]),
                    "--corpus",
                    str(CORPUS),
                    "--report",
                    str(destination),
                    "--history",
                    str(tmp_path / "online.jsonl"),
                ]
            )
            == 2
        )


def test_online_missing_key_or_sdk_never_initializes_provider(inputs, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    assert evaluate(inputs, online=True)["status"] == "pending_configuration"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(online_eval, "find_spec", lambda _: None)
    report = evaluate(inputs, online=True)
    assert report["status"] == "pending_configuration"
    assert report["provider_calls"] == 0
    assert report["execution"] is None


def test_reference_with_duplicate_column_names_fails_before_any_online_call(inputs):
    paths, cases = inputs
    cases[0]["sql"] = 'SELECT "日期", "日期" FROM v_system LIMIT 1'
    paths["benchmark_file"].write_text(json.dumps(cases), encoding="utf-8")
    report = evaluate(inputs, online=True)
    assert report["status"] == "preflight_failed"
    assert report["provider_calls"] == 0


def test_model_mismatch_counts_as_failure_and_respects_selected_case_limit(inputs):
    llm = FakeLLM(['SELECT "日期" FROM v_system LIMIT 1'] * 2)
    report = evaluate(inputs, llm, online=True, max_cases=1)
    assert report["selected_cases"] == report["evaluated_cases"] == 1
    assert report["provider_calls"] == 1
    assert report["outcomes"][0]["failure"] == "RESULT_MISMATCH"
    assert report["model_execution"] == {"passed": 0, "total": 1, "accuracy": 0.0}


def test_client_setup_error_is_redacted(inputs):
    paths, _ = inputs

    def bad_client(**_):
        raise RuntimeError("sk-secret with private path")

    report = online_eval.run_online_evaluation(
        **paths, model="explicit-test-model", online=True, llm_factory=bad_client
    )
    assert report["status"] == "client_initialization_failed"
    assert report["provider_calls"] == 0
    assert "sk-secret" not in json.dumps(report)


def test_literal_reference_filters_use_decoded_bound_values_in_source_order(inputs):
    paths, cases = inputs
    cases[0]["sql"] = (
        'SELECT "日期", "備轉容量率_pct" FROM v_system '
        "WHERE \"日期\" = '2026-07-31' AND 'it''s' = 'it''s' "
        "AND \"日期\" BETWEEN '2026-07-01' AND '2026-07-31' LIMIT 1"
    )
    paths["benchmark_file"].write_text(json.dumps(cases), encoding="utf-8")
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "sql": 'SELECT "日期", "備轉容量率_pct" FROM v_system WHERE "日期" = ? LIMIT 1',
                    "params": ["2026-07-31"],
                }
            )
        ]
    )
    report = evaluate(inputs, llm, online=True, max_cases=1)
    assert report["status"] == "completed"
    assert report["execution"]["passed"] == 1


def test_reference_existing_placeholders_without_params_fail_preflight(inputs):
    paths, cases = inputs
    cases[0]["sql"] = (
        'SELECT "日期" FROM v_system WHERE "日期" = ? AND "日期" > \'2026-07-01\' LIMIT 1'
    )
    paths["benchmark_file"].write_text(json.dumps(cases), encoding="utf-8")
    report = evaluate(inputs, online=True)
    assert report["status"] == "preflight_failed"
    assert report["provider_calls"] == 0


@pytest.mark.parametrize("split", [1, "false", []])
def test_corpus_split_requires_boolean_or_null_before_online_calls(inputs, split):
    paths, cases = inputs
    cases[0]["in_corpus"] = split
    paths["benchmark_file"].write_text(json.dumps(cases), encoding="utf-8")
    assert evaluate(inputs, online=True)["status"] == "preflight_failed"


def test_cli_online_uses_explicit_model_timeout_and_nonzero_for_mismatch(
    inputs, tmp_path, monkeypatch
):
    paths, _ = inputs
    options = {}

    def fake_provider(**kwargs):
        options.update(kwargs)
        return FakeLLM(['SELECT "日期" FROM v_system LIMIT 1'])

    monkeypatch.setattr(online_eval, "OpenAILLM", fake_provider)
    destination = tmp_path / "online.json"
    result = online_eval.main(
        [
            "--online",
            "--model",
            "test-explicit-model",
            "--timeout-seconds",
            "7.5",
            "--max-cases",
            "1",
            "--database",
            str(paths["database"]),
            "--benchmark",
            str(paths["benchmark_file"]),
            "--corpus",
            str(CORPUS),
            "--report",
            str(destination),
            "--history",
            str(tmp_path / "online.jsonl"),
        ]
    )
    assert result == 1
    assert options == {"model": "test-explicit-model", "timeout_seconds": 7.5}
    report = json.loads(destination.read_text(encoding="utf-8"))
    assert report["provider_calls"] == 1
    assert report["model_execution"]["accuracy"] == 0.0
