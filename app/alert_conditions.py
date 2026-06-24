"""Structured system and custom alert-condition models."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


class AlertCondition(BaseModel):
    id: str
    kind: Literal["system", "custom"]
    name: str
    enabled: bool = True


class SystemAlertCondition(AlertCondition):
    kind: Literal["system"] = "system"
    code: str
    description: str


class CustomAlertCondition(AlertCondition):
    kind: Literal["custom"] = "custom"
    symbol: str
    user_rule: str
    validation_summary: str
    required_tools: list[str] = Field(default_factory=list)
    related_symbols: list[str] = Field(default_factory=list)
    news_symbols: list[str] = Field(default_factory=list)


AlertConditionUnion: TypeAlias = SystemAlertCondition | CustomAlertCondition


class RuleValidationResult(BaseModel):
    is_valid: bool
    normalized_name: str | None = None
    normalized_rule: str | None = None
    target_symbol: str | None = None
    required_tools: list[str] = Field(default_factory=list)
    related_symbols: list[str] = Field(default_factory=list)
    news_symbols: list[str] = Field(default_factory=list)
    validation_summary: str
    rewrite_guidance: str | None = None


DEFAULT_SYSTEM_ALERT_CONDITIONS = [
    SystemAlertCondition(
        id="price_move_abs_gte_3_percent",
        name="Price move",
        code="price_move_abs_gte_3_percent",
        description="Alert when the absolute daily price move is at least 3 percent.",
    ),
    SystemAlertCondition(
        id="volume_ratio_20_gte_2",
        name="Volume surge",
        code="volume_ratio_20_gte_2",
        description="Alert when volume is at least twice the 20-day average.",
    ),
    SystemAlertCondition(
        id="volatility_20_elevated",
        name="Elevated volatility",
        code="volatility_20_elevated",
        description="Alert when recent annualized 20-day volatility is elevated.",
    ),
    SystemAlertCondition(
        id="sma_5_cross_sma_20",
        name="Moving-average crossover",
        code="sma_5_cross_sma_20",
        description="Alert when the 5-day and 20-day moving averages show a crossover signal.",
    ),
]


SUPPORTED_CUSTOM_RULE_TOOLS = {
    "fetch_related_symbol_snapshot",
    "fetch_symbol_news",
}
