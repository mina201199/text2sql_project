import json
from itertools import combinations
from pathlib import Path

from eval.promotion_gate import CorpusRegressionGate, retrieval_intent_accuracy
from text2sql.retriever import TfidfRetriever


def test_retrieval_regression_gate_rejects_a_worse_corpus() -> None:
    evaluation = [{"question": "查台中機組尖峰出力", "intent": "unit_day"}]
    baseline = {"examples": [{"id": "good", "question": "台中機組尖峰出力", "intent": "unit_day"}]}
    proposed = {
        "examples": [
            *baseline["examples"],
            {"id": "bad", "question": "查台中機組尖峰出力", "intent": "other"},
        ]
    }
    gate = CorpusRegressionGate(baseline, evaluation)
    passed, metrics = gate(proposed)
    assert not passed
    assert metrics["baseline_retrieval_intent_accuracy"] == 1.0
    assert metrics["retrieval_intent_accuracy"] == 0.0


def test_empty_retrieval_evaluation_is_zero() -> None:
    assert retrieval_intent_accuracy({"examples": []}, []) == 0.0


def test_day_count_candidates_preserve_all_correct_retrievals_in_every_subset():
    root = Path(__file__).resolve().parents[1]
    corpus = json.loads((root / "corpus/training_corpus.json").read_text(encoding="utf-8"))
    evaluation = [
        item
        for path in sorted((root / "benchmarks").glob("*_questions.json"))
        for item in json.loads(path.read_text(encoding="utf-8"))
        if "question" in item and "intent" in item
    ]
    questions = [
        "2026年7月台中#2有發電幾天",
        "2026年7月台中#2沒有發電幾天",
        "2026年7月林口三號機出力不是零的天數",
        "2026年7月林口三號機出力為零的天數",
    ]
    candidates = [
        {"id": f"day-count-{index}", "question": question, "intent": "zero_days"}
        for index, question in enumerate(questions)
    ]
    assert not set(questions) & {item["question"] for item in evaluation}

    def correctIds(examples):
        retriever = TfidfRetriever(examples)
        return {
            item["id"]
            for item in evaluation
            if retriever.retrieve(item["question"], top_k=1)[0].example["intent"] == item["intent"]
        }

    baselineCorrect = correctIds(corpus["examples"])
    assert len(baselineCorrect) / len(evaluation) >= 0.90
    gate = CorpusRegressionGate(corpus, evaluation)
    for size in range(1, len(candidates) + 1):
        for additions in combinations(candidates, size):
            proposed = {**corpus, "examples": [*corpus["examples"], *additions]}
            assert gate(proposed)[0]
            assert baselineCorrect <= correctIds(proposed["examples"])
