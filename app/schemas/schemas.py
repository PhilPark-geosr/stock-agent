"""Shared Pydantic schemas for market data and analysis results."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OHLCVRecord(BaseModel):
    """One market-data candle."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketIndicators(BaseModel):
    """Computed inputs used by the analysis agent."""

    latest_close: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None
    latest_volume: Optional[int] = None
    average_volume_20: Optional[float] = None
    volume_ratio_20: Optional[float] = None
    sma_5: Optional[float] = None
    sma_20: Optional[float] = None
    high_20: Optional[float] = None
    low_20: Optional[float] = None
    volatility_20: Optional[float] = None


class MarketDataSnapshot(BaseModel):
    """Recent OHLCV records plus indicator inputs for one symbol."""

    symbol: str
    data_time: datetime
    records: List[OHLCVRecord] = Field(default_factory=list)
    indicators: MarketIndicators = Field(default_factory=MarketIndicators)


class AnalysisRequest(BaseModel):
    """Request to retrieve or create the latest analysis for a symbol."""

    symbol: str


class AnalysisResult(BaseModel):
    """Structured output returned by the Gemini analysis agent."""

    symbol: str
    analysis_time: datetime
    data_time: datetime
    verdict: str
    summary: str
    key_reasons: List[str]
    risk_factors: List[str]
    indicators: Dict[str, Union[str, float, int, bool, None]]
    alert_triggered: bool
    matched_alert_conditions: List[str]
    alert_reason: str


T = TypeVar("T", bound=BaseModel)


def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    """Return a JSON-compatible dict for Pydantic v1 and v2."""

    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")  # type: ignore[attr-defined]
    return json.loads(model.json())


def parse_model(model_type: Type[T], data: Dict[str, Any]) -> T:
    """Validate a dict with Pydantic v1 or v2."""

    if hasattr(model_type, "model_validate"):
        return model_type.model_validate(data)  # type: ignore[attr-defined]
    return model_type.parse_obj(data)


def parse_model_json(model_type: Type[T], raw_json: str) -> T:
    """Validate a JSON string with Pydantic v1 or v2."""

    if hasattr(model_type, "model_validate_json"):
        return model_type.model_validate_json(raw_json)  # type: ignore[attr-defined]
    return model_type.parse_raw(raw_json)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


class WatchlistCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=24)
    name: Optional[str] = None
    market: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = _normalize_symbol(value)
        if not normalized:
            raise ValueError("symbol is required")
        return normalized


class WatchlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    created_at: datetime


class CustomAlertConditionCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=24)
    user_rule: str = Field(..., min_length=5, max_length=1000)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = _normalize_symbol(value)
        if not normalized:
            raise ValueError("symbol is required")
        return normalized


class CustomAlertConditionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    user_rule: str
    normalized_rule: Optional[str] = None
    validation_summary: str
    required_tools: List[str] = Field(default_factory=list)
    related_symbols: List[str] = Field(default_factory=list)
    news_symbols: List[str] = Field(default_factory=list)
    enabled: bool
    created_at: datetime


class AlertConditionRejected(BaseModel):
    validation_summary: str
    rewrite_guidance: str


class AnalysisResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    analyzed_at: datetime
    data_timestamp: Optional[datetime]
    overall_judgment: str
    summary: str
    key_reasons: List[str]
    risk_factors: List[str]
    support_levels: Dict[str, Any]
    should_alert: bool
    triggered_alerts: List[str]
    alert_reason: Optional[str]
    raw_result: Optional[Dict[str, Any]]


class AnalysisResultHistoryItem(BaseModel):
    """Lightweight row for analysis history listings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    analyzed_at: datetime
    data_timestamp: Optional[datetime]
    overall_judgment: str
    summary: str
    should_alert: bool
    triggered_alerts: List[str]
