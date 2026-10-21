"""Intent-aware character n-gram TF-IDF retrieval without external services."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from text2sql.corpus import character_ngrams, normalize_question
from text2sql.router import classify_intent

RETRIEVER_VERSION = "intent-tfidf-v1"


@dataclass(frozen=True)
class RetrievedExample:
    score: float
    example: dict[str, Any]


class TfidfRetriever:
    def __init__(self, examples: list[dict[str, Any]], *, minimum: int = 2, maximum: int = 4):
        self.examples = examples
        self.minimum = minimum
        self.maximum = maximum
        self.term_counts = [
            Counter(character_ngrams(item["question"], minimum=minimum, maximum=maximum))
            for item in examples
        ]
        document_frequency = Counter(term for counts in self.term_counts for term in counts)
        total = len(examples)
        self.idf = {
            term: math.log((1 + total) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        return {term: count * self.idf.get(term, 1.0) for term, count in counts.items()}

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        numerator = sum(value * right.get(term, 0.0) for term, value in left.items())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def retrieve(self, question: str, *, top_k: int = 5) -> list[RetrievedExample]:
        if not self.examples:
            return []
        query = self._vector(
            Counter(character_ngrams(question, minimum=self.minimum, maximum=self.maximum))
        )
        intent = classify_intent(question)
        useIntent = intent != "other" and any(
            example.get("intent") == intent for example in self.examples
        )
        normalizedQuestion = normalize_question(question)
        ranked = []
        for counts, example in zip(self.term_counts, self.examples, strict=True):
            score = min(1.0, self._cosine(query, self._vector(counts)))
            if useIntent:
                # 同類分析優先，類內仍依字詞相似度；保留精確命中以免掩蓋錯標語料。
                if normalize_question(example["question"]) == normalizedQuestion:
                    score = 1.0
                else:
                    score = (score + (example.get("intent") == intent)) / 2
            ranked.append(RetrievedExample(score, example))
        return sorted(ranked, key=lambda item: (-item.score, item.example["id"]))[:top_k]
