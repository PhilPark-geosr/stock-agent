"""Rule-validation agent interface."""

from __future__ import annotations

from typing import Protocol

from app.domain.alert_conditions import RuleValidationResult


class RuleValidationError(RuntimeError):
    """Raised when a custom rule cannot be validated."""


class RuleValidationAgent(Protocol):
    def validate(self, *, user_rule: str, target_symbol: str) -> RuleValidationResult:
        """Return whether a natural-language rule can be executed by this system."""
