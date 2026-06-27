"""Gemini-backed stock analysis agent."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

import httpx
from pydantic import ValidationError

from app.alert_conditions import AlertConditionUnion, DEFAULT_SYSTEM_ALERT_CONDITIONS

from .schemas import (
    AnalysisResult,
    MarketDataSnapshot,
    model_to_dict,
    parse_model,
)


DEFAULT_MODEL = "gemini-2.5-flash"


class AgentConfigurationError(RuntimeError):
    """Raised when the Gemini adapter is not configured."""


class AnalysisAgentError(RuntimeError):
    """Raised when analysis generation fails."""


class AnalysisAgent(Protocol):
    """Interface for structured stock analysis, intentionally easy to fake."""

    def analyze(
        self,
        market_data: MarketDataSnapshot,
        alert_conditions: Iterable[AlertConditionUnion] | None = None,
        custom_contexts: Iterable[dict[str, Any]] | None = None,
    ) -> AnalysisResult:
        ...


class GeminiAnalysisAgent:
    """Gemini REST API adapter that returns the shared structured result schema."""

    def __init__(self, *, client: httpx.Client | None = None, model: str | None = None) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._client = client or httpx.Client(timeout=60.0)

    def analyze(
        self,
        market_data: MarketDataSnapshot,
        alert_conditions: Iterable[AlertConditionUnion] | None = None,
        custom_contexts: Iterable[dict[str, Any]] | None = None,
    ) -> AnalysisResult:
        conditions = list(alert_conditions or DEFAULT_ALERT_CONDITIONS)
        payload = {
            "market_data": model_to_dict(market_data),
            "alert_conditions": [model_to_dict(condition) for condition in conditions],
            "custom_contexts": list(custom_contexts or []),
            "analysis_time_hint": datetime.now(timezone.utc).isoformat(),
        }
        prompt = "\n\n".join(
            [
                SYSTEM_PROMPT,
                (
                    "아래 시장 데이터를 분석하세요. 입력 payload를 반복하거나 감싸지 마세요. "
                    "반드시 하나의 JSON object만 반환하세요. 최상위 필드는 정확히 다음과 같아야 합니다: "
                    "symbol, analysis_time, data_time, verdict, summary, key_reasons, "
                    "risk_factors, indicators, alert_triggered, matched_alert_conditions, alert_reason. "
                    "summary, key_reasons, risk_factors, alert_reason은 반드시 자연스러운 한국어로 작성하세요. "
                    "verdict는 상승, 하락, 중립, 관망 중 하나의 한국어 값으로 작성하세요."
                ),
                json.dumps(payload, ensure_ascii=False),
            ]
        )

        try:
            response = self._client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._require_api_key(),
                },
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                    },
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise AnalysisAgentError(
                    f"Gemini analysis request failed: {exc.response.status_code} {exc.response.text}"
                ) from exc
        except Exception as exc:
            if isinstance(exc, AnalysisAgentError):
                raise
            raise AnalysisAgentError(f"Gemini analysis request failed: {exc}") from exc

        output_text = _extract_text(response.json())
        if output_text:
            return _parse_analysis_result(output_text, market_data)

        raise AnalysisAgentError("Gemini response did not include analysis JSON")

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise AgentConfigurationError("GEMINI_API_KEY is required")
        return self.api_key


DEFAULT_ALERT_CONDITIONS = DEFAULT_SYSTEM_ALERT_CONDITIONS


SYSTEM_PROMPT = """
너는 주식 분석 시스템 v1의 시장 분석 에이전트다.
반드시 요청된 JSON 구조만 반환한다.

제공된 OHLCV 데이터와 지표만 근거로 사용한다.
분석은 투자 조언이 아니라 정보 제공용이다.
하나 이상의 알림 조건이 명확히 충족될 때만 alert_triggered를 true로 설정한다.
summary, key_reasons, risk_factors, alert_reason은 개인 투자자가 이해하기 쉬운 한국어로 간결하게 작성한다.
영어 표현은 symbol, field name, alert condition id처럼 구조상 필요한 값에만 사용한다.
""".strip()


def _parse_analysis_result(raw_json: str, market_data: MarketDataSnapshot) -> AnalysisResult:
    try:
        data = json.loads(_clean_json_text(raw_json))
        if not isinstance(data, dict):
            raise ValueError("analysis JSON must be an object")
        return parse_model(AnalysisResult, _normalize_result_data(data, market_data))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise AnalysisAgentError(f"Gemini analysis response did not match AnalysisResult schema: {exc}") from exc


def _normalize_result_data(data: dict[str, Any], market_data: MarketDataSnapshot) -> dict[str, Any]:
    """Keep agent output aligned with the requested symbol and expected condition ids."""

    data = dict(data)
    data["symbol"] = market_data.symbol
    data["data_time"] = market_data.data_time
    data["matched_alert_conditions"] = _coerce_condition_ids(
        data.get("matched_alert_conditions", [])
    )
    if not data.get("analysis_time"):
        data["analysis_time"] = datetime.now(timezone.utc)
    return data


def _coerce_condition_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    condition_ids: list[str] = []
    for value in values:
        if isinstance(value, str):
            condition_ids.append(value)
        elif isinstance(value, dict) and isinstance(value.get("id"), str):
            condition_ids.append(value["id"])
    return condition_ids


def _extract_text(payload: dict[str, Any]) -> str | None:
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts") or []
    texts = [part.get("text", "") for part in parts if part.get("text")]
    return "\n".join(texts).strip() or None


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned
