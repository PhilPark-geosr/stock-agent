from __future__ import annotations

from enum import StrEnum


class BriefingType(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    POST_MARKET = "POST_MARKET"


class Judgment(StrEnum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    UNKNOWN = "UNKNOWN"


JUDGMENT_SCORE = {
    Judgment.STRONG_SELL: -2,
    Judgment.SELL: -1,
    Judgment.HOLD: 0,
    Judgment.BUY: 1,
    Judgment.STRONG_BUY: 2,
}

_JUDGMENT_ALIASES = {
    "STRONG_BUY": Judgment.STRONG_BUY,
    "적극매수": Judgment.STRONG_BUY,
    "강력매수": Judgment.STRONG_BUY,
    "BUY": Judgment.BUY,
    "매수": Judgment.BUY,
    "상승": Judgment.BUY,
    "HOLD": Judgment.HOLD,
    "보유": Judgment.HOLD,
    "관망": Judgment.HOLD,
    "중립": Judgment.HOLD,
    "NEUTRAL": Judgment.HOLD,
    "SELL": Judgment.SELL,
    "매도": Judgment.SELL,
    "하락": Judgment.SELL,
    "STRONG_SELL": Judgment.STRONG_SELL,
    "적극매도": Judgment.STRONG_SELL,
    "강력매도": Judgment.STRONG_SELL,
}


def normalize_judgment(value: str | None) -> Judgment:
    if not value:
        return Judgment.UNKNOWN
    compact = value.strip().upper().replace(" ", "_").replace("-", "_")
    if compact in _JUDGMENT_ALIASES:
        return _JUDGMENT_ALIASES[compact]
    squashed = compact.replace("_", "")
    for alias, judgment in _JUDGMENT_ALIASES.items():
        if alias.replace("_", "") == squashed:
            return judgment
    return Judgment.UNKNOWN


def compare_judgments(current: str, previous: str | None) -> tuple[str, bool, int]:
    current_value = normalize_judgment(current)
    previous_value = normalize_judgment(previous)
    if current_value is Judgment.UNKNOWN or previous_value is Judgment.UNKNOWN:
        return "NOT_COMPARABLE", False, 0
    distance = abs(JUDGMENT_SCORE[current_value] - JUDGMENT_SCORE[previous_value])
    return "COMPARABLE", current_value != previous_value, distance


def infer_exchange(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized.endswith((".KS", ".KQ")):
        return "KRX"
    return "US"
