"""Atomic staging, validation, promotion, and rollback for retrieval examples."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from text2sql.corpus import build_index, corpus_checksum, load_corpus, normalize_question

Validator = Callable[..., tuple[bool, str]]
RegressionGate = Callable[[dict[str, Any]], tuple[bool, dict[str, float]]]


@dataclass(frozen=True)
class CorpusCandidate:
    id: str
    question: str
    sql: str
    source: str
    created_at: str
    approved_by: str
    schema_version: str
    data_manifest_version: str
    outcome: str
    params: tuple[object, ...] = ()
    result_checksum: str = ""
    tables: tuple[str, ...] = ()
    data_provenance: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionResult:
    promoted: bool
    version: str | None
    rejected: tuple[dict[str, str], ...]
    metrics: dict[str, float]


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"\b(?:sk|sess|token)-[A-Za-z0-9_-]{8,}\b")
TAIWAN_ID_PATTERN = re.compile(r"(?<![A-Z0-9])[A-Z][12]\d{8}(?![A-Z0-9])", re.IGNORECASE)
TAIWAN_MOBILE_PATTERN = re.compile(
    r"(?<!\d)(?:\+886[-\s]?9\d{2}|09\d{2})[-\s]?\d{3}[-\s]?\d{3}(?!\d)"
)
TAIWAN_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\(0\d{1,2}\)|0\d{1,2})[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
LABELED_NAME_PATTERN = re.compile(r"((?:姓名|姓氏)\s*[:：]\s*)[一-鿿]{2,4}")
DELEGATED_NAME_PATTERN = re.compile(r"((?:請\s*)?(?:替|幫|為)\s*)[一-鿿]{2,4}(?=\s*[（(])")
ACCOUNT_PATTERN = re.compile(r"(?<![A-Z0-9])\d{10,16}(?![A-Z0-9])", re.IGNORECASE)


def deidentify(value: str) -> str:
    value = EMAIL_PATTERN.sub("[EMAIL]", value)
    value = TOKEN_PATTERN.sub("[TOKEN]", value)
    value = TAIWAN_ID_PATTERN.sub("[TW_ID]", value)
    value = TAIWAN_MOBILE_PATTERN.sub("[PHONE]", value)
    value = TAIWAN_PHONE_PATTERN.sub("[PHONE]", value)
    value = LABELED_NAME_PATTERN.sub(r"\1[NAME]", value)
    value = DELEGATED_NAME_PATTERN.sub(r"\1[NAME]", value)
    return ACCOUNT_PATTERN.sub("[ACCOUNT]", value)


def deidentify_value(value: Any) -> Any:
    """Recursively redact strings at the final corpus serialization boundary."""
    if isinstance(value, str):
        return deidentify(value)
    if isinstance(value, dict):
        return {deidentify(str(key)): deidentify_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(deidentify_value(item) for item in value)
    if isinstance(value, list):
        return [deidentify_value(item) for item in value]
    return value


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_bytes_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _candidate_example(candidate: CorpusCandidate) -> dict[str, Any]:
    return {
        "id": deidentify(candidate.id),
        "question": deidentify(candidate.question),
        "sql": deidentify(candidate.sql.strip()),
        "params": list(deidentify_value(candidate.params)),
        "intent": deidentify_value(candidate.validation.get("intent", "other")),
        "metadata": deidentify_value(
            {
                key: value
                for key, value in asdict(candidate).items()
                if key not in {"id", "question", "sql", "params", "validation"}
            }
        ),
    }


def _run_validator(
    validator: Validator,
    question: str,
    sql: str,
    params: tuple[object, ...],
) -> tuple[bool, str]:
    """Call parameter-aware validators while preserving the original two-argument API."""
    try:
        inspect.signature(validator).bind(question, sql, params)
    except (TypeError, ValueError):
        return validator(question, sql)
    return validator(question, sql, params)


def promote_batch(
    candidates: Iterable[CorpusCandidate],
    *,
    corpus_path: Path,
    index_path: Path,
    versions_dir: Path,
    benchmark_question_set: set[str],
    sql_validator: Validator,
    semantic_validator: Validator,
    result_validator: Validator,
    regression_gate: RegressionGate,
) -> PromotionResult:
    """Promote all candidates or none; a failed batch never changes published files."""
    corpus = load_corpus(corpus_path)
    existing_ids = {str(example["id"]) for example in corpus["examples"]}
    existing_questions = {normalize_question(example["question"]) for example in corpus["examples"]}
    batch_ids: set[str] = set()
    batch_questions: set[str] = set()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    materialized_candidates = list(candidates)
    if not materialized_candidates:
        return PromotionResult(
            False,
            None,
            ({"id": "batch", "reason": "empty_batch"},),
            {},
        )

    for candidate in materialized_candidates:
        reason = ""
        question = deidentify(candidate.question)
        sql = deidentify(candidate.sql.strip())
        params = tuple(deidentify_value(candidate.params))
        normalized = normalize_question(question)
        if candidate.outcome not in {"success", "corrected"}:
            reason = "ineligible_outcome"
        elif not candidate.approved_by.strip():
            reason = "missing_approval"
        elif sql != candidate.sql.strip():
            reason = "sensitive_sql"
        elif params != candidate.params:
            reason = "sensitive_params"
        elif candidate.id in existing_ids or candidate.id in batch_ids:
            reason = "duplicate_id"
        elif normalized in existing_questions or normalized in batch_questions:
            reason = "duplicate_question"
        elif normalized in benchmark_question_set:
            reason = "benchmark_leakage"
        else:
            for validator in (sql_validator, semantic_validator, result_validator):
                passed, detail = _run_validator(
                    validator,
                    question,
                    sql,
                    params,
                )
                if not passed:
                    reason = detail
                    break
        if reason:
            rejected.append({"id": candidate.id, "reason": reason})
            continue
        batch_ids.add(candidate.id)
        batch_questions.add(normalized)
        accepted.append(_candidate_example(candidate))

    if rejected:
        return PromotionResult(False, None, tuple(rejected), {})

    proposed = {**corpus, "examples": [*corpus["examples"], *accepted]}
    proposed_checksum = corpus_checksum(proposed)
    # 分隔雜湊中的數字，避免版本識別碼被當成帳號或電話遮蔽。
    proposed["version"] = f"corpus-{proposed_checksum[:6]}x{proposed_checksum[6:12]}"
    passed, metrics = regression_gate(proposed)
    if not passed:
        return PromotionResult(
            False,
            None,
            ({"id": "batch", "reason": "regression_gate_failed"},),
            metrics,
        )

    old_checksum = corpus_checksum(corpus)
    backup_path = versions_dir / f"{corpus['version']}-{old_checksum[:12]}.json"
    if not backup_path.exists():
        _atomic_json_write(backup_path, corpus)
    old_corpus = corpus_path.read_bytes()
    old_index = index_path.read_bytes() if index_path.exists() else None
    try:
        _atomic_json_write(corpus_path, proposed)
        _atomic_json_write(index_path, build_index(proposed))
    except BaseException:
        _atomic_bytes_write(corpus_path, old_corpus)
        if old_index is None:
            index_path.unlink(missing_ok=True)
        else:
            _atomic_bytes_write(index_path, old_index)
        raise
    return PromotionResult(True, proposed["version"], (), metrics)


def rollback_corpus(*, corpus_path: Path, index_path: Path, backup_path: Path) -> str:
    corpus = load_corpus(backup_path)
    old_corpus = corpus_path.read_bytes() if corpus_path.exists() else None
    old_index = index_path.read_bytes() if index_path.exists() else None
    try:
        _atomic_json_write(corpus_path, corpus)
        _atomic_json_write(index_path, build_index(corpus))
    except BaseException:
        if old_corpus is None:
            corpus_path.unlink(missing_ok=True)
        else:
            _atomic_bytes_write(corpus_path, old_corpus)
        if old_index is None:
            index_path.unlink(missing_ok=True)
        else:
            _atomic_bytes_write(index_path, old_index)
        raise
    return hashlib.sha256(corpus_path.read_bytes()).hexdigest()
