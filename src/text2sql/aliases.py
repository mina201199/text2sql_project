"""Resolve user-facing plant and unit aliases without guessing ambiguities."""

from __future__ import annotations

import re
from dataclasses import dataclass

from align.naming import chinese_number
from text2sql.entities import normalizeQuestionText


@dataclass(frozen=True)
class AliasResolution:
    value: str | None
    candidates: tuple[str, ...]
    ambiguous: bool = False


PLANT_ALIASES = {
    "中火": "台中發電廠",
    "台中電廠": "台中發電廠",
    "興達電廠": "興達發電廠",
    "林口電廠": "林口發電廠",
    "大潭電廠": "大潭發電廠",
}

NUMBERED_PLANTS = ("台中", "林口", "大林", "興達", "大潭", "通霄")
UNIT_NUMBER = r"[0-9一二兩三四五六七八九十]+"


def normalizeUnitQuestion(question: str) -> str:
    compact = normalizeQuestionText(question)
    compact = compact.replace("臺中", "台中").replace("中火", "台中")
    compact = compact.replace("＃", "#").replace("（", "(").replace("）", ")")
    for plant in NUMBERED_PLANTS:
        compact = compact.replace(f"{plant}發電廠", plant).replace(f"{plant}電廠", plant)
    for short, plant in (("中", "台中"), ("林", "林口"), ("大", "大林")):
        compact = re.sub(rf"(?<![台大]){short}({UNIT_NUMBER})機", rf"{plant}第\1號機", compact)

    def normalizeNumber(match: re.Match) -> str:
        plant, rawNumber, suffix = match.groups()
        if rawNumber.isdigit():
            number = int(rawNumber)
        else:
            number = next(
                (
                    value
                    for value in range(1, 100)
                    if chinese_number(value) == rawNumber.replace("兩", "二")
                ),
                None,
            )
        # 保留機號與後接年份的分界，重複正規化也不能把兩者黏在一起。
        return f"{plant}#{number}{suffix or ''}" if number is not None else match.group(0)

    return re.sub(
        rf"({'|'.join(NUMBERED_PLANTS)})(?:燃煤)?(?:第)?#?({UNIT_NUMBER})"
        r"(?![0-9一二兩三四五六七八九十年])(號機組|號機|機組|號|機|部)?",
        normalizeNumber,
        compact,
    )


def numberedUnitNames(question: str) -> tuple[str, ...]:
    return tuple(
        match.group(0)
        for match in re.finditer(
            rf"({'|'.join(NUMBERED_PLANTS)})#\d+", normalizeUnitQuestion(question)
        )
    )


def resolve_plant(question: str, plants: set[str]) -> AliasResolution:
    question = question.replace("臺中", "台中")
    for alias, formal in PLANT_ALIASES.items():
        if alias in question and formal in plants:
            return AliasResolution(formal, (formal,))
    matches = tuple(sorted(plant for plant in plants if plant.removesuffix("發電廠") in question))
    return (
        AliasResolution(matches[0], matches)
        if len(matches) == 1
        else AliasResolution(None, matches, len(matches) > 1)
    )


def resolve_peak_column(question: str, columns: set[str]) -> AliasResolution:
    explicitCoal = bool(
        re.search(
            r"興達(?:發電廠|電廠)?燃煤(?:第)?#?(?:3|三)(?:號|機|部|$)",
            normalizeQuestionText(question),
        )
    ) and not any(word in question for word in ("還是", "或"))
    question = normalizeUnitQuestion(question)
    ambiguous_hsinta = re.search(r"興達#3(?:號|機|部|相關|是|的|\b)", question) and not explicitCoal
    if ambiguous_hsinta:
        candidates = tuple(column for column in ("興達#3", "興達 (#1-#5)") if column in columns)
        if len(candidates) > 1:
            return AliasResolution(None, candidates, True)

    exact = tuple(
        sorted(
            (
                column
                for column in columns
                if re.search(
                    re.escape(normalizeUnitQuestion(column))
                    + (r"(?!\d)" if re.search(r"#\d+$", column) else ""),
                    question,
                )
            ),
            key=len,
            reverse=True,
        )
    )
    if exact:
        longest = exact[0]
        ties = tuple(column for column in exact if len(column) == len(longest))
        return AliasResolution(longest if len(ties) == 1 else None, ties, len(ties) > 1)

    if not numberedUnitNames(question):
        for phrase, candidate in (
            ("大潭彙總", "大潭 (#1-#9)"),
            ("通霄彙總", "通霄 (#1-#6、GT#9)"),
            ("興達複循環彙總", "興達 (#1-#5)"),
        ):
            if phrase in question and candidate in columns:
                return AliasResolution(candidate, (candidate,))
    return AliasResolution(None, ())


def resolve_peak_columns(question: str, columns: set[str]) -> tuple[str, ...]:
    """Resolve multiple comparison targets while preserving mention order."""

    matches: list[tuple[int, str]] = []
    for column in columns:
        position = question.find(column)
        if position >= 0:
            matches.append((position, column))
            continue
        base = re.sub(r"\s*\(.*", "", column)
        if base and base in question and "(" in column and "彙總" in question:
            matches.append((question.find(base), column))

    numbered = list(re.finditer(r"(台中|林口|大林|興達)\s*#?(\d{1,2})", question))
    for match in numbered:
        candidate = f"{match.group(1)}#{int(match.group(2))}"
        if candidate in columns:
            matches.append((match.start(), candidate))
    if numbered:
        prefix = numbered[-1].group(1)
        for match in re.finditer(r"[和與及、]\s*#?(\d{1,2})", question):
            candidate = f"{prefix}#{int(match.group(1))}"
            if candidate in columns:
                matches.append((match.start(), candidate))

    unique: list[str] = []
    for _position, column in sorted(set(matches)):
        if column not in unique:
            unique.append(column)
    return tuple(unique)
