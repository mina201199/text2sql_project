import pytest

from text2sql.retriever import TfidfRetriever


def test_tfidf_retrieval_is_relevant_and_deterministic() -> None:
    examples = [
        {"id": "unit", "question": "台中機組尖峰出力"},
        {"id": "reserve", "question": "備轉容量率最低日"},
        {"id": "outage", "question": "機組歲修排程"},
    ]
    retriever = TfidfRetriever(examples)
    first = retriever.retrieve("今年備轉容量率最低是哪天", top_k=2)
    second = retriever.retrieve("今年備轉容量率最低是哪天", top_k=2)
    assert first[0].example["id"] == "reserve"
    assert first == second
    assert first[0].score > first[1].score


def test_empty_retriever_returns_no_examples() -> None:
    assert TfidfRetriever([]).retrieve("任意問題") == []


@pytest.mark.parametrize(
    ("question", "relevant", "distractor", "intent"),
    [
        (
            "2031年五月二日台中二號機輸出多少",
            "德基在2020年8月3日尖峰出力",
            "2031年五月台中二號機有發電幾天",
            "unit_day",
        ),
        (
            "台中9號機期間內最低值",
            "青山歷年最高出力",
            "台中9號機期間內出力為零的天數",
            "unit_extreme",
        ),
        (
            "林口二號與三號年度平均",
            "比較青山與德基的尖峰出力",
            "林口三號機出力不是零的天數",
            "comparison",
        ),
    ],
)
def test_analysis_intent_outweighs_shared_dates_and_unit_names(
    question, relevant, distractor, intent
):
    examples = [
        {"id": "relevant", "question": relevant, "intent": intent},
        {"id": "distractor", "question": distractor, "intent": "zero_days"},
    ]
    ranked = TfidfRetriever(examples).retrieve(question)
    assert ranked[0].example["id"] == "relevant"
    assert ranked[0].score > ranked[1].score


def test_unclassified_queries_keep_lexical_order_and_exact_matches_stay_first():
    examples = [
        {"id": "lexical", "question": "alpha beta", "intent": "other"},
        {"id": "different", "question": "gamma delta", "intent": "unit_day"},
    ]
    assert TfidfRetriever(examples).retrieve("alpha beta gamma")[0].example["id"] == "lexical"
    exact = {"id": "exact", "question": "台中9號機最高出力", "intent": "other"}
    related = {"id": "related", "question": "台中8號機最高出力", "intent": "unit_extreme"}
    assert TfidfRetriever([related, exact]).retrieve(exact["question"])[0].example["id"] == "exact"
