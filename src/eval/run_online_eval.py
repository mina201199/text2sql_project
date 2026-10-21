"""Opt-in, bounded online evaluation through the guarded Text2SQL pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlglot import tokenize
from sqlglot.tokens import TokenType

from eval.metrics import QueryResult, accuracy, canonical_result, grouped_accuracy, result_match
from ingest.validate import PROJECT_ROOT
from text2sql.corpus import load_corpus
from text2sql.db import ReadOnlySQLite
from text2sql.llm import LLMProtocol, OpenAILLM
from text2sql.pipeline import Text2SQLPipeline
from text2sql.semantic_guard import SemanticGuard
from text2sql.sql_guard import SqlGuard


class _BudgetedLLM:
    def __init__(self, delegate: LLMProtocol, max_calls: int):
        self.delegate = delegate
        self.max_calls = max_calls
        self.calls = 0
        self.exhausted = False

    def generate(self, prompt: str) -> str:
        if self.calls >= self.max_calls:
            self.exhausted = True
            raise RuntimeError("CALL_BUDGET_EXHAUSTED")
        self.calls += 1
        return self.delegate.generate(prompt)


def _valid_configuration(
    model: str, max_cases: int, max_calls: int, max_attempts: int, timeout_seconds: float
) -> bool:
    return (
        isinstance(model, str)
        and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,119}", model) is not None
        and not model.lower().startswith("sk-")
        and type(max_cases) is int
        and 1 <= max_cases <= 100
        and type(max_calls) is int
        and 1 <= max_calls <= 300
        and type(max_attempts) is int
        and 1 <= max_attempts <= 3
        and isinstance(timeout_seconds, (int, float))
        and math.isfinite(timeout_seconds)
        and 0 < timeout_seconds <= 120
    )


def _local_inputs(database: Path, benchmark_file: Path, corpus_path: Path, max_cases: int):
    if not database.is_file():
        raise ValueError("DATABASE_MISSING")
    load_corpus(corpus_path)
    payload = json.loads(benchmark_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("BENCHMARK_MUST_BE_NONEMPTY_ARRAY")
    cases = payload[:max_cases]
    executor = ReadOnlySQLite(database)
    _, peak_rows = executor.execute('SELECT DISTINCT "機組欄位" FROM v_peak LIMIT 200', ())
    _, plant_rows = executor.execute('SELECT DISTINCT "電廠" FROM v_unit LIMIT 200', ())
    peak_columns = {str(row[0]) for row in peak_rows}
    plants = {str(row[0]) for row in plant_rows}
    semantic_guard = SemanticGuard.from_database(database, peak_columns=peak_columns)
    guard = SqlGuard()
    references = []
    for case in cases:
        if (
            not isinstance(case, dict)
            or not isinstance(case.get("question"), str)
            or not case["question"].strip()
            or not isinstance(case.get("sql"), str)
            or (case.get("in_corpus") is not None and type(case["in_corpus"]) is not bool)
        ):
            raise ValueError("INVALID_BENCHMARK_CASE")
        reference_sql, reference_params = _bind_reference_literals(case["sql"])
        if not guard.validate(reference_sql, reference_params).allowed:
            raise ValueError("REFERENCE_SQL_REJECTED")
        columns, rows = executor.execute(reference_sql, reference_params)
        reference = QueryResult(tuple(columns), tuple(rows))
        canonical_result(reference)
        references.append(reference)
    return cases, references, executor, semantic_guard, peak_columns, plants


def _bind_reference_literals(sql: str) -> tuple[str, tuple[object, ...]]:
    """Bind benchmark strings in lexical order without changing identifiers/comments.

    SQLite tokenizer spans refer to the original source, while token.text carries
    decoded string values, including escaped quotes. Existing placeholders remain
    unbound and therefore fail the subsequent guard parameter-count check.
    """
    pieces: list[str] = []
    params: list[object] = []
    cursor = 0
    for token in tokenize(sql, read="sqlite"):
        if token.token_type == TokenType.STRING:
            pieces.extend((sql[cursor : token.start], "?"))
            params.append(token.text)
            cursor = token.end + 1
    pieces.append(sql[cursor:])
    return "".join(pieces), tuple(params)


def run_online_evaluation(
    *,
    database: Path,
    benchmark_file: Path,
    corpus_path: Path,
    model: str,
    online: bool = False,
    max_cases: int = 5,
    max_calls: int = 5,
    max_attempts: int = 1,
    timeout_seconds: float = 30.0,
    use_router: bool = False,
    llm_factory: Callable[..., LLMProtocol] | None = None,
) -> dict[str, Any]:
    """Preflight locally; construct a provider only with explicit online opt-in.

    The injectable factory is the external API boundary. Reports deliberately omit
    questions, IDs, prompts, SQL, rows, paths, exception text, and pipeline traces.
    """
    report: dict[str, Any] = {
        "schema_version": "online-eval-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "online_guarded_pipeline" if online else "online_preflight",
        "status": "invalid_configuration",
        "live_evaluation": "not_run",
        "provider_calls": 0,
        "execution": None,
        "model_execution": None,
        "outcomes": [],
    }
    if not _valid_configuration(model, max_cases, max_calls, max_attempts, timeout_seconds):
        return report
    report["configuration"] = {
        "model": model,
        "max_cases": max_cases,
        "max_calls": max_calls,
        "max_attempts": max_attempts,
        "timeout_seconds": timeout_seconds,
        "routing": "hybrid" if use_router else "force_llm",
        "sdk_retries": 0,
    }
    report["preflight"] = {
        "local_inputs_ready": False,
        "api_key_present": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "sdk_available": find_spec("openai") is not None,
    }
    try:
        cases, references, executor, semantic_guard, peak_columns, plants = _local_inputs(
            database, benchmark_file, corpus_path, max_cases
        )
        report["benchmark_sha256"] = hashlib.sha256(benchmark_file.read_bytes()).hexdigest()
        report["corpus_sha256"] = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
        report["selected_cases"] = len(cases)
        report["preflight"]["local_inputs_ready"] = True
    except Exception:
        report["status"] = "preflight_failed"
        return report
    report["status"] = (
        "preflight_ready" if all(report["preflight"].values()) else "pending_configuration"
    )
    if not online or report["status"] != "preflight_ready":
        return report

    try:
        delegate = (llm_factory or OpenAILLM)(model=model, timeout_seconds=timeout_seconds)
        llm = _BudgetedLLM(delegate, max_calls)
        pipeline = Text2SQLPipeline(
            llm=llm,
            sql_guard=SqlGuard(),
            run_sql=executor.execute,
            corpus_path=corpus_path,
            data_range=semantic_guard.data_range,
            peak_columns=peak_columns,
            plants=plants,
            semantic_guard=semantic_guard,
            max_attempts=max_attempts,
            use_router=use_router,
        )
    except Exception:
        report["status"] = "client_initialization_failed"
        return report

    report["status"] = "completed"
    stop_reason: str | None = None
    for index, (case, expected) in enumerate(zip(cases, references, strict=True), start=1):
        outcome: dict[str, Any] = {
            "case_index": index,
            "in_corpus": case.get("in_corpus"),
            "status": "skipped",
            "passed": False,
            "provider_calls": 0,
        }
        report["outcomes"].append(outcome)
        if stop_reason or llm.calls >= max_calls:
            if not stop_reason:
                stop_reason = "CALL_BUDGET_EXHAUSTED"
                report["status"] = "budget_exhausted"
            outcome["failure"] = stop_reason
            continue
        before = llm.calls
        started = perf_counter()
        try:
            response = pipeline.query(case["question"])
            data = response.data or {}
            trace = data.get("trace", [])
            outcome["sql_guard_rejections"] = sum(
                step["stage"] == "sql_guard" and step.get("code") != "OK" for step in trace
            )
            outcome["source"] = data.get("source", "llm" if llm.calls > before else "guard")
            if response.success:
                actual = QueryResult(
                    tuple(data["columns"]), tuple(tuple(row) for row in data["rows"])
                )
                outcome["passed"] = result_match(actual, expected)
                if not outcome["passed"]:
                    outcome["failure"] = "RESULT_MISMATCH"
            else:
                # Only fixed internal codes are retained; never error/evidence/trace strings.
                code = response.error_code or "PIPELINE_FAILED"
                outcome["failure"] = (
                    code if re.fullmatch(r"[A-Z][A-Z_]{0,79}", code) else "PIPELINE_FAILED"
                )
                if code == "LLM_AUTH_FAILED":
                    stop_reason = "AUTHENTICATION_FAILED"
                    report["status"] = "authentication_failed"
        except Exception:
            outcome["failure"] = "EVALUATION_ERROR"
        outcome["status"] = "passed" if outcome["passed"] else "failed"
        outcome["provider_calls"] = llm.calls - before
        outcome["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
        if llm.exhausted:
            report["status"] = "budget_exhausted"
            stop_reason = "CALL_BUDGET_EXHAUSTED"

    evaluated = [item for item in report["outcomes"] if item["status"] != "skipped"]
    model_cases = [item for item in evaluated if item["provider_calls"] > 0]
    report["provider_calls"] = llm.calls
    report["live_evaluation"] = "run" if llm.calls else "not_run"
    report["execution"] = accuracy(item["passed"] for item in evaluated)
    report["model_execution"] = (
        accuracy(item["passed"] for item in model_cases) if model_cases else None
    )
    report["execution_by_corpus_split"] = grouped_accuracy(evaluated, group_key="in_corpus")
    report["evaluated_cases"] = len(evaluated)
    report["skipped_cases"] = len(cases) - len(evaluated)
    report["routed_cases"] = sum(item.get("source") == "router" for item in evaluated)
    return report


def _valid_destinations(report: Path, history: Path, inputs: tuple[Path, ...]) -> bool:
    destinations = (report.resolve(), history.resolve())
    protected = {path.resolve() for path in inputs}
    return destinations[0] != destinations[1] and all(
        path not in protected and path.name not in {"eval_latest.json", "eval_history.jsonl"}
        for path in destinations
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--online", action="store_true", help="Allow bounded, potentially paid calls")
    mode.add_argument("--dry-run", action="store_true", help="Preflight only (the default)")
    parser.add_argument("--model", required=True, help="Explicit provider model ID; no default")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "data/processed/power.db")
    parser.add_argument(
        "--benchmark", type=Path, default=PROJECT_ROOT / "benchmarks/eval_questions.json"
    )
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "corpus/training_corpus.json")
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--max-calls", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--use-router", action="store_true", help="Measure hybrid routing + LLM")
    parser.add_argument(
        "--report", type=Path, default=PROJECT_ROOT / "reports/online/online_latest.json"
    )
    parser.add_argument(
        "--history", type=Path, default=PROJECT_ROOT / "reports/online/online_history.jsonl"
    )
    args = parser.parse_args(argv)
    if not _valid_destinations(
        args.report, args.history, (args.database, args.benchmark, args.corpus)
    ):
        print("Online evaluation refused: report destinations overlap inputs or offline reports.")
        return 2
    try:
        report = run_online_evaluation(
            database=args.database,
            benchmark_file=args.benchmark,
            corpus_path=args.corpus,
            model=args.model,
            online=args.online,
            max_cases=args.max_cases,
            max_calls=args.max_calls,
            max_attempts=args.max_attempts,
            timeout_seconds=args.timeout_seconds,
            use_router=args.use_router,
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.history.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
        with args.history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        print("Online evaluation failed: local setup or report write error (details redacted).")
        return 2
    print(f"Online evaluation {report['status']}; provider calls: {report['provider_calls']}.")
    if report["status"] in {"preflight_ready", "pending_configuration"} and not args.online:
        return 0
    if report["status"] == "completed":
        return int(any(not item["passed"] for item in report["outcomes"]))
    return 2 if report["execution"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
