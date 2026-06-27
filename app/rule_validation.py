"""Validate natural-language custom alert rules before persistence."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx

from app.alert_conditions import RuleValidationResult, SUPPORTED_CUSTOM_RULE_TOOLS
from app.agent import AgentConfigurationError
from app.repositories import normalize_symbol
from app.schemas import parse_model_json


class RuleValidationError(RuntimeError):
    """Raised when a custom rule cannot be validated."""


class RuleValidationAgent(Protocol):
    def validate(self, *, user_rule: str, target_symbol: str) -> RuleValidationResult:
        """Return whether a natural-language rule can be executed by this system."""


class GeminiRuleValidationAgent:
    def __init__(self, *, client: httpx.Client | None = None, model: str | None = None) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.api_key = os.getenv("GEMINI_API_KEY")
        self._client = client or httpx.Client(timeout=60.0)

    def validate(self, *, user_rule: str, target_symbol: str) -> RuleValidationResult:
        payload = {
            "target_symbol": normalize_symbol(target_symbol),
            "user_rule": user_rule.strip(),
            "allowed_tools": sorted(SUPPORTED_CUSTOM_RULE_TOOLS),
        }
        prompt = "\n\n".join(
            [
                """
You validate natural-language stock alert rules for a single-user application.
Return one JSON object only.

A rule is valid only if it has an understandable alert target and is specific
enough to be evaluated during analysis using the allowed tools. Reject subjective,
vague, or unsupported requests. When rejecting a rule, explain how the user should
rewrite it.

For valid rules, return: is_valid=true, normalized_name, normalized_rule,
target_symbol, validation_summary, rewrite_guidance=null.
For invalid rules, return: is_valid=false, validation_summary, rewrite_guidance.

Do not return a tool execution plan. Tool choice happens later at analysis time.
Symbols must use ticker notation when they are explicit. The supplied target_symbol
is the symbol the user expects to receive an alert about.
""".strip(),
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
                    "generationConfig": {"responseMimeType": "application/json"},
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuleValidationError(
                f"Gemini rule validation failed: {exc.response.status_code} {exc.response.text}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, (RuleValidationError, AgentConfigurationError)):
                raise
            raise RuleValidationError(f"Gemini rule validation failed: {exc}") from exc

        raw_json = _extract_text(response.json())
        if not raw_json:
            raise RuleValidationError("Gemini response did not include rule-validation JSON")

        result = parse_model_json(RuleValidationResult, _clean_json_text(raw_json))
        return _sanitize_result(result, target_symbol=target_symbol)

    def _require_api_key(self) -> str:
        if not self.api_key:
            raise AgentConfigurationError("GEMINI_API_KEY is required")
        return self.api_key


def _sanitize_result(result: RuleValidationResult, *, target_symbol: str) -> RuleValidationResult:
    if not result.is_valid:
        return result

    if not result.normalized_name or not result.normalized_rule:
        return RuleValidationResult(
            is_valid=False,
            validation_summary="The rule could not be normalized into an executable condition.",
            rewrite_guidance="Specify the alert target, comparison target, and measurable trigger.",
        )

    result.target_symbol = normalize_symbol(target_symbol)
    return result


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
        lines = cleaned.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned
