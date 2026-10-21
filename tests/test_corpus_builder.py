from __future__ import annotations

import json
from pathlib import Path

import pytest

import text2sql.corpus_builder as corpus_builder
from text2sql.corpus import load_corpus, normalize_question
from text2sql.corpus_builder import (
    CorpusCandidate,
    deidentify,
    promote_batch,
    rollback_corpus,
)


def _write_corpus(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "version": "corpus-v1",
                "ddl": [],
                "documentation": [],
                "examples": [
                    {
                        "id": "base",
                        "question": "2026年7月最高尖峰負載日",
                        "sql": "SELECT 1 LIMIT 1",
                        "intent": "system_metric",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _candidate(**overrides: str) -> CorpusCandidate:
    values = {
        "id": "candidate-1",
        "question": "林口1號機在2026年最高出力",
        "sql": 'SELECT MAX("尖峰出力_萬瓩") FROM v_peak LIMIT 1',
        "source": "corrected",
        "created_at": "2026-09-13T00:00:00Z",
        "approved_by": "reviewer",
        "schema_version": "1",
        "data_manifest_version": "fixture",
        "outcome": "corrected",
    }
    values.update(overrides)
    return CorpusCandidate(**values)


def _pass(_question: str, _sql: str) -> tuple[bool, str]:
    return True, ""


def _regression(_corpus: dict[str, object]) -> tuple[bool, dict[str, float]]:
    return True, {"execution_accuracy": 1.0}


def test_deidentify_removes_email_token_and_long_account_number() -> None:
    value = "a@example.com sk-secret123 123456789012"
    assert deidentify(value) == "[EMAIL] [TOKEN] [ACCOUNT]"


@pytest.mark.parametrize("checksumPrefix", ["123456789012", "0912345678ab", "0212345678ab"])
def test_generated_version_survives_redaction(tmp_path, monkeypatch, checksumPrefix):
    corpusPath = tmp_path / "corpus.json"
    _write_corpus(corpusPath)
    monkeypatch.setattr(corpus_builder, "corpus_checksum", lambda _: checksumPrefix + "a" * 52)
    result = promote_batch(
        [_candidate()],
        corpus_path=corpusPath,
        index_path=tmp_path / "index.json",
        versions_dir=tmp_path / "versions",
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )
    assert result.promoted
    assert result.version == deidentify(result.version)
    assert load_corpus(corpusPath)["version"] == result.version


def test_deidentify_removes_taiwan_identity_phone_and_labeled_name() -> None:
    value = "請替王小明（0912-345-678，身分證 A123456789）查詢；姓名：陳美玲"

    assert deidentify(value) == ("請替[NAME]（[PHONE]，身分證 [TW_ID]）查詢；姓名：[NAME]")


def test_sensitive_parameter_is_rejected_before_publication(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    _write_corpus(corpus_path)

    result = promote_batch(
        [_candidate(params=("a@example.com",))],
        corpus_path=corpus_path,
        index_path=tmp_path / "index.json",
        versions_dir=tmp_path / "versions",
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.rejected == ({"id": "candidate-1", "reason": "sensitive_params"},)
    assert "a@example.com" not in corpus_path.read_text(encoding="utf-8")


def test_failed_batch_does_not_publish_partial_examples(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    index_path = tmp_path / "index.json"
    _write_corpus(corpus_path)
    before = corpus_path.read_bytes()

    result = promote_batch(
        [_candidate(), _candidate(id="bad", outcome="failed", question="另一題")],
        corpus_path=corpus_path,
        index_path=index_path,
        versions_dir=tmp_path / "versions",
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.promoted is False
    assert corpus_path.read_bytes() == before
    assert not index_path.exists()


def test_promotion_versions_and_rollback_are_atomic(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    index_path = tmp_path / "index.json"
    versions = tmp_path / "versions"
    _write_corpus(corpus_path)

    result = promote_batch(
        [_candidate()],
        corpus_path=corpus_path,
        index_path=index_path,
        versions_dir=versions,
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.promoted is True
    assert len(load_corpus(corpus_path)["examples"]) == 2
    backup = next(versions.glob("*.json"))
    rollback_corpus(corpus_path=corpus_path, index_path=index_path, backup_path=backup)
    assert len(load_corpus(corpus_path)["examples"]) == 1


def test_failed_rollback_restores_both_published_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    index_path = tmp_path / "index.json"
    versions = tmp_path / "versions"
    _write_corpus(corpus_path)
    promote_batch(
        [_candidate()],
        corpus_path=corpus_path,
        index_path=index_path,
        versions_dir=versions,
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )
    before_corpus = corpus_path.read_bytes()
    before_index = index_path.read_bytes()
    backup = next(versions.glob("*.json"))
    original_write = corpus_builder._atomic_json_write

    def fail_index_write(path: Path, payload: object) -> None:
        if path == index_path:
            raise OSError("injected index write failure")
        original_write(path, payload)

    monkeypatch.setattr(corpus_builder, "_atomic_json_write", fail_index_write)
    with pytest.raises(OSError, match="injected index write failure"):
        rollback_corpus(corpus_path=corpus_path, index_path=index_path, backup_path=backup)

    assert corpus_path.read_bytes() == before_corpus
    assert index_path.read_bytes() == before_index


def test_failed_promotion_restores_both_published_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_path = tmp_path / "corpus.json"
    index_path = tmp_path / "index.json"
    versions = tmp_path / "versions"
    _write_corpus(corpus_path)
    promote_batch(
        [_candidate()],
        corpus_path=corpus_path,
        index_path=index_path,
        versions_dir=versions,
        benchmark_question_set=set(),
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )
    before_corpus = corpus_path.read_bytes()
    before_index = index_path.read_bytes()
    original_write = corpus_builder._atomic_json_write

    def fail_index_write(path: Path, payload: object) -> None:
        if path == index_path:
            raise OSError("injected index write failure")
        original_write(path, payload)

    monkeypatch.setattr(corpus_builder, "_atomic_json_write", fail_index_write)
    with pytest.raises(OSError, match="injected index write failure"):
        promote_batch(
            [_candidate(id="candidate-2", question="第二個候選")],
            corpus_path=corpus_path,
            index_path=index_path,
            versions_dir=versions,
            benchmark_question_set=set(),
            sql_validator=_pass,
            semantic_validator=_pass,
            result_validator=_pass,
            regression_gate=_regression,
        )

    assert corpus_path.read_bytes() == before_corpus
    assert index_path.read_bytes() == before_index


def test_benchmark_question_is_rejected(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.json"
    _write_corpus(corpus_path)
    candidate = _candidate()

    result = promote_batch(
        [candidate],
        corpus_path=corpus_path,
        index_path=tmp_path / "index.json",
        versions_dir=tmp_path / "versions",
        benchmark_question_set={normalize_question(candidate.question)},
        sql_validator=_pass,
        semantic_validator=_pass,
        result_validator=_pass,
        regression_gate=_regression,
    )

    assert result.rejected == ({"id": "candidate-1", "reason": "benchmark_leakage"},)
