"""Continuous briefing contracts (FR-C01 through FR-C16)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Market = Literal["KR", "US"]
Purpose = Literal["pre_market", "post_market"]


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class BriefingError(ValueError):
    pass


class BriefingConflict(BriefingError):
    pass


class LostClaim(BriefingConflict):
    pass


class ModelOutputError(BriefingError):
    pass


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetSelection(Contract):
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("symbols")
    @classmethod
    def normalize_selection(cls, value):
        if value is None:
            return None
        from app.domain.symbols import StockSymbol
        normalized = [StockSymbol.of(symbol).value for symbol in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("같은 종목을 여러 번 선택할 수 없습니다.")
        return sorted(normalized)


class BriefingRequest(TargetSelection):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    market: Market
    purpose: Purpose
    n: int | None = Field(default=None, ge=1, le=250, strict=True)
    original_id: str | None = None


class BriefingSettings(TargetSelection):
    n: int | None = Field(default=None, ge=1, le=250, strict=True)
    pre_market_enabled: bool = False
    post_market_enabled: bool = False
    kakao_enabled: bool = False


class BriefingContext(Contract):
    market: Market
    purpose: Purpose
    trade_date: date
    previous_trade_date: date
    cutoff_at: datetime
    started_at: datetime
    n: int
    sessions: list[date]
    symbols: list[str]


class Evidence(Contract):
    id: str
    symbol: str
    kind: Literal["chart", "news", "disclosure"]
    source: str
    url: str | None = None
    published_at: datetime
    collected_at: datetime
    published_precision: Literal["instant", "day"] = "instant"
    text: str
    data: dict = Field(default_factory=dict)


class SourceStatus(Contract):
    symbol: str
    source: str
    kind: str
    status: Literal["ok", "empty", "partial", "failed", "unconfigured", "delayed"]
    detail: str = ""


class EvidenceSnapshot(Contract):
    evidence: list[Evidence] = Field(default_factory=list)
    sources: list[SourceStatus] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    eligible_symbols: list[str] = Field(default_factory=list)


class BriefingItem(Contract):
    symbol: str
    verdict: Literal["매수", "매도", "보류"]
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str]
    comparison: Literal["유지", "변경", "비교 불가"] = "비교 불가"
    comparison_reason: str = Field(min_length=1, max_length=4000)
    limitations: list[str] = Field(default_factory=list)
    next_observation: str = Field(min_length=1, max_length=4000)

    @field_validator("reason", "comparison_reason", "next_observation")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("설명은 비어 있을 수 없습니다.")
        return value.strip()


class BriefingResult(Contract):
    summary: str = Field(min_length=1, max_length=6000)
    items: list[BriefingItem] = Field(min_length=1)


def market_for_symbol(symbol: str) -> Market | None:
    if symbol.endswith((".KS", ".KQ")):
        return "KR"
    # Other exchanges and indices must not silently inherit the US calendar.
    import re
    if re.fullmatch(r"[A-Z]{1,6}(?:-[A-Z])?", symbol):
        return "US"
    return None
