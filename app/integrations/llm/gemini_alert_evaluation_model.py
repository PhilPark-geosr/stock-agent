from __future__ import annotations

import json
import os
from typing import Any

import httpx
from pydantic import ValidationError

from app.application.user_alert_evaluator import (
    AlertEvaluationDecision,
    AlertEvaluationOutputError,
)


class AlertEvaluationModelError(RuntimeError):
    pass


class _MalformedAlertEvaluationOutput(AlertEvaluationModelError, AlertEvaluationOutputError):
    pass


class GeminiAlertEvaluationModel:
    def __init__(self, *, client: httpx.Client | None = None, model: str | None = None) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._client = client or httpx.Client(timeout=60.0)

    def evaluate(
        self,
        *,
        analysis,
        condition,
        custom_context,
        validation_errors: list[str] | None = None,
    ) -> AlertEvaluationDecision:
        payload = {
            "stock_analysis": {
                "symbol": analysis.symbol,
                "analyzed_at": analysis.analyzed_at,
                "data_timestamp": analysis.data_timestamp,
                "summary": analysis.summary,
                "key_reasons": analysis.key_reasons,
                "risk_factors": analysis.risk_factors,
                "indicators": analysis.support_levels,
            },
            "user_alert_condition": {
                "user_rule": condition.user_rule,
                "normalized_rule": condition.normalized_rule,
            },
            "custom_rule_context": {
                "gathered_facts": custom_context.gathered_facts,
                "evidence": custom_context.evidence,
                "summary": custom_context.summary,
            },
        }
        if validation_errors:
            payload["previous_validation_errors"] = validation_errors
        prompt = "\n\n".join(
            [
                SYSTEM_PROMPT,
                json.dumps(payload, ensure_ascii=False, default=str),
            ]
        )
        try:
            response = self._client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": self._require_api_key()},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AlertEvaluationModelError(
                f"Gemini alert evaluation failed: {exc.response.status_code} {exc.response.text}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, AlertEvaluationModelError):
                raise
            raise AlertEvaluationModelError(f"Gemini alert evaluation failed: {exc}") from exc

        raw = _extract_text(response.json())
        if not raw:
            raise AlertEvaluationModelError("Gemini response did not include evaluation JSON")
        try:
            return AlertEvaluationDecision.model_validate_json(_clean_json_text(raw))
        except (ValidationError, ValueError) as exc:
            raise _MalformedAlertEvaluationOutput(
                f"Gemini alert evaluation response did not match decision schema: {exc}"
            ) from exc

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise AlertEvaluationModelError("GEMINI_API_KEY is required")
        return self.api_key


SYSTEM_PROMPT = """
너는 사용자 주식 알림 조건 평가 모델이다.
- 하나의 공유 종목 분석과 하나의 사용자 알림 조건만 평가한다.
- 제공된 stock_analysis와 custom_rule_context만 근거로 사용한다.
- 새로운 사실을 추측하거나 만들지 않고 외부 도구를 호출하지 않는다.
- 명확히 충족되면 matched, 명확히 충족되지 않으면 not_matched를 반환한다.
- 자료가 부족하면 indeterminate를 반환한다.
- matched만 notification_message를 포함한다.
- 알림을 직접 발송하지 않는다.
- 반드시 AlertEvaluationDecision JSON object만 응답한다.
""".strip()


def _extract_text(payload: dict[str, Any]) -> str | None:
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    return text.strip() or None


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines.pop()
        cleaned = "\n".join(lines).strip()
    return cleaned
